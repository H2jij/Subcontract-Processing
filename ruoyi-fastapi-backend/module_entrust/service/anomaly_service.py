"""
对账系统 — 异常检测 Service
=========================================
职责（Requirements 3.1 ~ 3.9 + 4.1 ~ 4.7）：
  1. 将供应商账单（SupplierClaim.claim_data）与订购单（对账单行项）逐项比对
  2. 检测五类异常并生成 Anomaly 记录：
       - amount_diff       金额差异（claim 金额 vs order_amount）
       - quantity_diff     数量差异（claim 数量 vs ordered_quantity）
       - supplier_missing  供应商漏报
       - duplicate         重复申报
       - quality_dispute   质量争议
  3. 为每条异常分类严重程度：critical / warning / info
  4. 异常创建后通知财务人员（通过 ReconciliationNotificationService）
  5. 调整审批：创建 Adjustment、判定审批层级、审批通过/驳回、3 工作日自动升级

设计要点（Property 6 / Property 7 / Property 8 / Property 9）：
  - 每个触发条件恰好生成一条 Anomaly；匹配正确的行项不生成异常。
  - amount_diff: 同一 order_no 在 claim 中只有一条且金额与 order_amount 不一致（用 0.01 容差比较）
  - quantity_diff: claim 中数量与 ordered_quantity 不一致，关联 ProductionAnomaly
  - supplier_missing: 对账单中存在该 order_no 但 claim 中不存在
  - duplicate: claim 中同一 order_no 出现两次或以上
  - quality_dispute: claim 涉及的 order_no 对应的 EntrustOutsourceOrder.quality_status == 'fail'
    （仅当 claim 中提到该 order_no 时才生成；若 claim 完全没提到 fail 单则不算"争议"）
  - severity（以 order_amount 为基准）：
       critical : anomaly_type == 'quality_dispute' 或 abs(diff)/order_amount > 10%
       warning  : 5% < abs(diff)/order_amount ≤ 10%
       info     : abs(diff)/order_amount ≤ 5%
       order_amount == 0 时退化处理：diff != 0 -> critical, 否则 info
  - approval_level (Property 8):
       manager  : abs(adjusted - original) ≤ 1000
       director : abs(adjusted - original) > 1000
  - 行项冻结 (Property 9): 对应行项存在 pending_approval 调整时拒绝新调整

claim_data 期望结构（JSON）：
  [
    { "order_no": "OS-001", "amount": 1000.00, "quantity": 100, ... },
    ...
  ]
  允许字段名为 amount / total_amount，二者任一存在即可。
  数量字段名为 quantity。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from loguru import logger
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceException
from module_entrust.entity.do.entrust_do import EntrustOutsourceOrder
from module_entrust.entity.do.reconciliation_do import (
    Adjustment,
    Anomaly,
    ProductionAnomaly,
    ReconciliationAuditLog,
    ReconciliationLineItem,
    ReconciliationStatement,
    SupplierClaim,
)
from module_entrust.service.reconciliation_notification_service import (
    ReconciliationNotificationService,
)
from module_entrust.service.reconciliation_service import ReconciliationService
from module_entrust.service.reconciliation_audit_service import (
    ACTION_APPROVE,
    ACTION_CREATE,
    ACTION_REJECT,
    ENTITY_TYPE_ANOMALY,
    ReconciliationAuditService,
)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ANOMALY_TYPE_AMOUNT_DIFF = 'amount_diff'
ANOMALY_TYPE_QUANTITY_DIFF = 'quantity_diff'
ANOMALY_TYPE_SUPPLIER_MISSING = 'supplier_missing'
ANOMALY_TYPE_DUPLICATE = 'duplicate'
ANOMALY_TYPE_QUALITY_DISPUTE = 'quality_dispute'

SEVERITY_CRITICAL = 'critical'
SEVERITY_WARNING = 'warning'
SEVERITY_INFO = 'info'

# 金额差异容差：低于该值视为相等，避免浮点/分位误差
_AMOUNT_TOLERANCE = Decimal('0.01')

# 严重程度比例阈值
_RATIO_CRITICAL = Decimal('0.10')  # > 10% -> critical
_RATIO_WARNING = Decimal('0.05')   # > 5%  -> warning, 否则 info

# ---------------------------------------------------------------------------
# 调整审批相关常量（Requirement 4.1 ~ 4.7）
# ---------------------------------------------------------------------------

# 审批层级阈值（Property 8）
_APPROVAL_LEVEL_THRESHOLD = Decimal('1000.00')

APPROVAL_LEVEL_MANAGER = 'manager'
APPROVAL_LEVEL_DIRECTOR = 'director'

# Adjustment 审批状态
ADJUSTMENT_STATUS_PENDING = 'pending_approval'
ADJUSTMENT_STATUS_APPROVED = 'approved'
ADJUSTMENT_STATUS_REJECTED = 'rejected'
ADJUSTMENT_STATUS_ESCALATED = 'escalated'

# 自动升级阈值：审批人 3 个工作日未处理则自动升级（Requirement 4.7）
_ESCALATION_WORKING_DAYS = 3

# 审计日志 entity_type 与 action
_AUDIT_ENTITY_ADJUSTMENT = 'adjustment'
_AUDIT_ACTION_ADJUSTMENT_CREATED = 'create'
_AUDIT_ACTION_ADJUSTMENT_APPROVED = 'approve'
_AUDIT_ACTION_ADJUSTMENT_REJECTED = 'reject'
_AUDIT_ACTION_ADJUSTMENT_ESCALATED = 'escalate'


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _to_decimal(value: Any) -> Optional[Decimal]:
    """将 JSON 中的金额字段转换为 Decimal；非法值返回 None。"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _claim_amount(item: dict) -> Optional[Decimal]:
    """从 claim 行项中提取金额；优先 amount，回落 total_amount。"""
    if 'amount' in item:
        return _to_decimal(item.get('amount'))
    if 'total_amount' in item:
        return _to_decimal(item.get('total_amount'))
    return None


def _normalize_order_no(value: Any) -> Optional[str]:
    """提取并规范化 order_no（去除首尾空白，空字符串视为 None）。"""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _claim_quantity(item: dict) -> Optional[int]:
    """从 claim 行项中提取数量；返回整数或 None。"""
    raw = item.get('quantity')
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _add_working_days(start: datetime, working_days: int) -> datetime:
    """
    在 start 基础上推进 ``working_days`` 个工作日（仅排除周末，不考虑法定节假日）。

    Args:
        start: 起始时间
        working_days: 需要推进的工作日数（≥ 0）

    Returns:
        推进后的时间点（保留原始 start 的时分秒）
    """
    if working_days <= 0:
        return start
    cur = start
    remaining = working_days
    while remaining > 0:
        cur = cur + timedelta(days=1)
        # weekday(): Monday=0 ... Sunday=6；5 / 6 为周末
        if cur.weekday() < 5:
            remaining -= 1
    return cur


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class AnomalyService:
    """对账异常检测服务。"""

    # ------------------------------------------------------------------
    # 严重程度分类（Property 7）
    # ------------------------------------------------------------------

    @staticmethod
    def classify_severity(
        anomaly_type: str,
        diff_amount: Optional[Decimal],
        line_amount: Optional[Decimal],
    ) -> str:
        """
        分类异常严重程度。

        规则（与 design.md "异常严重程度分类算法" 对齐）：
          - quality_dispute: 始终 critical
          - line_amount（即 order_amount）为 0 或缺失：
              * diff 非零 -> critical
              * diff 为零或缺失 -> info
          - 否则按比率 r = abs(diff) / order_amount：
              * r > 10%        -> critical
              * 5% < r ≤ 10%   -> warning
              * r ≤ 5%         -> info

        Note:
            line_amount 参数在新逻辑中应传入 order_amount（订购金额）作为基准。
        """
        if anomaly_type == ANOMALY_TYPE_QUALITY_DISPUTE:
            return SEVERITY_CRITICAL

        diff = abs(diff_amount) if diff_amount is not None else Decimal('0')
        base = line_amount if line_amount is not None else Decimal('0')

        if base == 0:
            return SEVERITY_CRITICAL if diff > 0 else SEVERITY_INFO

        ratio = diff / base
        if ratio > _RATIO_CRITICAL:
            return SEVERITY_CRITICAL
        if ratio > _RATIO_WARNING:
            return SEVERITY_WARNING
        return SEVERITY_INFO

    # ------------------------------------------------------------------
    # 主流程：检测异常
    # ------------------------------------------------------------------

    @staticmethod
    async def detect_anomalies(
        db: AsyncSession,
        statement_id: int,
        claim_data: Iterable[dict],
        claim_id: Optional[int] = None,
        operator_id: int = 0,
    ) -> list[int]:
        """
        逐项比对供应商账单与订购单（对账单行项），生成异常记录。

        比对基准为行项的 order_amount（= ordered_quantity × ordered_unit_price），
        而非旧的 total_amount。

        Args:
            db: AsyncSession，事务由本方法管理（最终 commit）
            statement_id: 对账单 ID
            claim_data: 供应商提交的账单明细列表，每条至少包含
                        ``order_no`` 与金额字段（amount 或 total_amount），
                        可选 ``quantity`` 字段用于数量比对
            claim_id: 关联的 SupplierClaim 记录 ID；若未传入会尝试以
                      statement_id 查询最近一条 SupplierClaim
            operator_id: 检测发起人；系统自动检测时为 0

        Returns:
            生成的 Anomaly ID 列表（按生成顺序）

        Raises:
            ServiceException: 当对账单不存在时
        """
        statement = await db.scalar(
            select(ReconciliationStatement).where(
                ReconciliationStatement.id == statement_id
            )
        )
        if not statement:
            raise ServiceException(message=f'对账单 {statement_id} 不存在')

        # 解析 claim_id（可选）
        if claim_id is None:
            claim_id = await db.scalar(
                select(SupplierClaim.id)
                .where(SupplierClaim.statement_id == statement_id)
                .order_by(SupplierClaim.submitted_at.desc())
                .limit(1)
            )

        # 加载对账单行项
        line_items: list[ReconciliationLineItem] = list(
            (await db.execute(
                select(ReconciliationLineItem).where(
                    ReconciliationLineItem.statement_id == statement_id
                )
            )).scalars().all()
        )
        # 按 order_no 索引行项；对账单中同一 order_no 一般唯一，
        # 若存在多条则取首条（行项端的重复不属于本服务关心范畴）
        line_by_order: dict[str, ReconciliationLineItem] = {}
        for li in line_items:
            key = _normalize_order_no(li.order_no)
            if key and key not in line_by_order:
                line_by_order[key] = li

        # 整理 claim 行项：按 order_no 分桶，便于检测重复 / 漏报 / 金额差异
        claim_items: list[dict] = list(claim_data or [])
        claim_buckets: dict[str, list[dict]] = {}
        for raw in claim_items:
            if not isinstance(raw, dict):
                continue
            order_no = _normalize_order_no(raw.get('order_no'))
            if not order_no:
                continue
            claim_buckets.setdefault(order_no, []).append(raw)

        created_ids: list[int] = []
        anomalies_to_notify: list[Anomaly] = []

        # 辅助函数：获取行项的 order_amount 作为比对基准
        def _get_order_amount(line: Optional[ReconciliationLineItem]) -> Decimal:
            """获取行项的 order_amount；优先使用 order_amount 字段，回落到 total_amount。"""
            if line is None:
                return Decimal('0')
            if line.order_amount is not None:
                return Decimal(str(line.order_amount))
            # 兼容旧数据：回落到 total_amount
            if line.total_amount is not None:
                return Decimal(str(line.total_amount))
            return Decimal('0')

        # ------------------------------------------------------------
        # 1. duplicate：claim 中同一 order_no 出现 ≥2 次
        # ------------------------------------------------------------
        duplicate_orders: set[str] = set()
        for order_no, bucket in claim_buckets.items():
            if len(bucket) >= 2:
                duplicate_orders.add(order_no)
                line = line_by_order.get(order_no)
                order_amount = _get_order_amount(line)
                # 重复申报的差异金额：累计申报额 - 订购金额
                claim_total = sum(
                    (_claim_amount(b) or Decimal('0')) for b in bucket
                )
                diff = claim_total - order_amount
                anomaly = Anomaly(
                    statement_id=statement_id,
                    claim_id=claim_id,
                    line_item_id=line.id if line else None,
                    anomaly_type=ANOMALY_TYPE_DUPLICATE,
                    severity=AnomalyService.classify_severity(
                        ANOMALY_TYPE_DUPLICATE, diff, order_amount
                    ),
                    diff_amount=diff,
                    description=(
                        f'供应商账单中订单 {order_no} 重复申报 {len(bucket)} 次，'
                        f'累计金额 {claim_total}，订购金额 {order_amount}'
                    ),
                    status='open',
                )
                db.add(anomaly)
                anomalies_to_notify.append(anomaly)

        # ------------------------------------------------------------
        # 2. quality_dispute：claim 涉及的 order_no 对应 quality_status='fail'
        # ------------------------------------------------------------
        quality_failed_orders: set[str] = set()
        if claim_buckets:
            order_nos = list(claim_buckets.keys())
            fail_rows = (await db.execute(
                select(EntrustOutsourceOrder.order_no).where(
                    EntrustOutsourceOrder.order_no.in_(order_nos),
                    EntrustOutsourceOrder.quality_status == 'fail',
                )
            )).scalars().all()
            quality_failed_orders = {
                _normalize_order_no(x) for x in fail_rows if x
            }
            quality_failed_orders.discard(None)

        for order_no in quality_failed_orders:
            line = line_by_order.get(order_no)
            order_amount = _get_order_amount(line)
            # 质量争议本身的差异金额：取 claim 首条的金额减订购金额（仅作参考）
            bucket = claim_buckets.get(order_no, [])
            claim_amt = _claim_amount(bucket[0]) if bucket else None
            diff = (
                (claim_amt - order_amount)
                if claim_amt is not None
                else None
            )
            anomaly = Anomaly(
                statement_id=statement_id,
                claim_id=claim_id,
                line_item_id=line.id if line else None,
                anomaly_type=ANOMALY_TYPE_QUALITY_DISPUTE,
                severity=AnomalyService.classify_severity(
                    ANOMALY_TYPE_QUALITY_DISPUTE, diff, order_amount
                ),
                diff_amount=diff,
                description=(
                    f'供应商账单涉及质检不合格订单 {order_no}，'
                    f'对应工单 quality_status=fail'
                ),
                status='open',
            )
            db.add(anomaly)
            anomalies_to_notify.append(anomaly)

        # ------------------------------------------------------------
        # 3. amount_diff：claim 中存在该 order_no（非重复且非质量争议）
        #    且金额与订购金额（order_amount）不一致（容差 0.01）
        # ------------------------------------------------------------
        for order_no, bucket in claim_buckets.items():
            if order_no in duplicate_orders:
                continue
            if order_no in quality_failed_orders:
                continue
            line = line_by_order.get(order_no)
            if line is None:
                # claim 提到了但对账单没有该 order_no：不属于"漏报"也不属于"金额差异"
                # 当前需求未明确这种"超额申报"的处理方式，跳过避免噪声
                continue
            claim_amt = _claim_amount(bucket[0])
            if claim_amt is None:
                # claim 行项缺金额字段，无法比对 — 跳过
                continue
            order_amount = _get_order_amount(line)
            diff = claim_amt - order_amount
            if abs(diff) <= _AMOUNT_TOLERANCE:
                continue  # Property 6: 匹配项不生成异常
            anomaly = Anomaly(
                statement_id=statement_id,
                claim_id=claim_id,
                line_item_id=line.id,
                anomaly_type=ANOMALY_TYPE_AMOUNT_DIFF,
                severity=AnomalyService.classify_severity(
                    ANOMALY_TYPE_AMOUNT_DIFF, diff, order_amount
                ),
                diff_amount=diff,
                description=(
                    f'订单 {order_no} 金额差异：供应商申报 {claim_amt}，'
                    f'订购金额 {order_amount}，差额 {diff}'
                ),
                status='open',
            )
            db.add(anomaly)
            anomalies_to_notify.append(anomaly)

        # ------------------------------------------------------------
        # 3b. quantity_diff：claim 中数量与 ordered_quantity 不一致
        #     （非重复、非质量争议、非漏报的行项）
        #     关联 ProductionAnomaly（如有）
        # ------------------------------------------------------------
        for order_no, bucket in claim_buckets.items():
            if order_no in duplicate_orders:
                continue
            if order_no in quality_failed_orders:
                continue
            line = line_by_order.get(order_no)
            if line is None:
                continue
            if line.ordered_quantity is None:
                # 行项无订购数量信息，无法比对
                continue
            claim_qty = _claim_quantity(bucket[0])
            if claim_qty is None:
                # claim 行项缺数量字段，无法比对
                continue
            qty_diff = claim_qty - int(line.ordered_quantity)
            if qty_diff == 0:
                continue  # 数量一致，不生成异常

            # 计算差异金额：数量差 × 订购单价
            unit_price = (
                Decimal(str(line.ordered_unit_price))
                if line.ordered_unit_price is not None
                else Decimal('0')
            )
            diff_amount = Decimal(str(qty_diff)) * unit_price
            order_amount = _get_order_amount(line)

            # 尝试关联 ProductionAnomaly（查找该工单的生产异常）
            related_anomaly_desc = ''
            if line.order_id:
                pa_rows = (await db.execute(
                    select(ProductionAnomaly).where(
                        ProductionAnomaly.order_id == line.order_id,
                        ProductionAnomaly.status != 'closed',
                    )
                )).scalars().all()
                if pa_rows:
                    pa_descs = [
                        f'{pa.anomaly_type}(损失{pa.total_loss})'
                        for pa in pa_rows
                    ]
                    related_anomaly_desc = f'，关联生产异常: {"; ".join(pa_descs)}'

            anomaly = Anomaly(
                statement_id=statement_id,
                claim_id=claim_id,
                line_item_id=line.id,
                anomaly_type=ANOMALY_TYPE_QUANTITY_DIFF,
                severity=AnomalyService.classify_severity(
                    ANOMALY_TYPE_QUANTITY_DIFF, diff_amount, order_amount
                ),
                diff_amount=diff_amount,
                description=(
                    f'订单 {order_no} 数量差异：供应商申报 {claim_qty}，'
                    f'订购数量 {line.ordered_quantity}，差 {qty_diff} 件'
                    f'{related_anomaly_desc}'
                ),
                status='open',
            )
            db.add(anomaly)
            anomalies_to_notify.append(anomaly)

        # ------------------------------------------------------------
        # 4. supplier_missing：对账单中有但 claim 中没有
        # ------------------------------------------------------------
        for order_no, line in line_by_order.items():
            if order_no in claim_buckets:
                continue
            order_amount = _get_order_amount(line)
            # 漏报差异 = -order_amount（供应商少报这一金额）
            diff = -order_amount
            anomaly = Anomaly(
                statement_id=statement_id,
                claim_id=claim_id,
                line_item_id=line.id,
                anomaly_type=ANOMALY_TYPE_SUPPLIER_MISSING,
                severity=AnomalyService.classify_severity(
                    ANOMALY_TYPE_SUPPLIER_MISSING, diff, order_amount
                ),
                diff_amount=diff,
                description=(
                    f'对账单行项订单 {order_no} 在供应商账单中缺失，'
                    f'订购金额 {order_amount}'
                ),
                status='open',
            )
            db.add(anomaly)
            anomalies_to_notify.append(anomaly)

        # 一次性 flush 拿到所有 anomaly.id
        await db.flush()
        created_ids = [a.id for a in anomalies_to_notify]

        # ------------------------------------------------------------
        # 审计日志：每条 Anomaly 创建（Requirement 8.1）
        # ------------------------------------------------------------
        for a in anomalies_to_notify:
            await ReconciliationAuditService.log_action(
                db=db,
                entity_type=ENTITY_TYPE_ANOMALY,
                entity_id=a.id,
                action=ACTION_CREATE,
                operator_id=int(operator_id or 0),
                operator_name='system' if not operator_id else None,
                detail={
                    'statement_id': statement_id,
                    'claim_id': claim_id,
                    'line_item_id': a.line_item_id,
                    'anomaly_type': a.anomaly_type,
                    'severity': a.severity,
                    'diff_amount': str(a.diff_amount) if a.diff_amount is not None else None,
                },
            )

        # ------------------------------------------------------------
        # 5. 通知财务（Requirement 3.9）
        # ------------------------------------------------------------
        for a in anomalies_to_notify:
            try:
                await ReconciliationNotificationService.notify_finance_of_anomaly(
                    db, a, operator_id=operator_id
                )
            except Exception as exc:  # noqa: BLE001
                # 通知失败不阻断异常落库
                logger.error(
                    '[AnomalyService] 通知财务失败 anomaly_id={} type={} err={}',
                    a.id, a.anomaly_type, exc,
                )

        await db.commit()
        logger.info(
            '[AnomalyService] 异常检测完成 statement_id={} claim_id={} '
            'created={} duplicate={} quality_dispute={} amount_diff={} '
            'quantity_diff={} missing={}',
            statement_id, claim_id, len(created_ids),
            len([a for a in anomalies_to_notify if a.anomaly_type == ANOMALY_TYPE_DUPLICATE]),
            len([a for a in anomalies_to_notify if a.anomaly_type == ANOMALY_TYPE_QUALITY_DISPUTE]),
            len([a for a in anomalies_to_notify if a.anomaly_type == ANOMALY_TYPE_AMOUNT_DIFF]),
            len([a for a in anomalies_to_notify if a.anomaly_type == ANOMALY_TYPE_QUANTITY_DIFF]),
            len([a for a in anomalies_to_notify if a.anomaly_type == ANOMALY_TYPE_SUPPLIER_MISSING]),
        )
        return created_ids

    # ==================================================================
    # 调整审批（Requirements 4.1 ~ 4.7）
    # ==================================================================

    # ------------------------------------------------------------------
    # 审批层级判定（Property 8 / Requirement 4.2）
    # ------------------------------------------------------------------

    @staticmethod
    def determine_approval_level(adjustment_amount: Any) -> str:
        """
        根据调整金额判定审批层级。

        规则（Property 8）：
          - abs(adjustment_amount) ≤ 1000 → 'manager'
          - abs(adjustment_amount) > 1000 → 'director'

        Args:
            adjustment_amount: 调整差额（``adjusted_amount - original_amount``）。
                可为 Decimal / int / float / str；非法值视为 0。

        Returns:
            'manager' 或 'director'
        """
        amt = _to_decimal(adjustment_amount) or Decimal('0')
        return (
            APPROVAL_LEVEL_MANAGER
            if abs(amt) <= _APPROVAL_LEVEL_THRESHOLD
            else APPROVAL_LEVEL_DIRECTOR
        )

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    async def _load_anomaly(
        db: AsyncSession, anomaly_id: int
    ) -> Anomaly:
        anomaly = await db.scalar(
            select(Anomaly).where(Anomaly.id == anomaly_id)
        )
        if not anomaly:
            raise ServiceException(message=f'异常记录不存在: id={anomaly_id}')
        return anomaly

    @staticmethod
    async def _load_line_item_for_adjustment(
        db: AsyncSession, line_item_id: int
    ) -> ReconciliationLineItem:
        line = await db.scalar(
            select(ReconciliationLineItem).where(
                ReconciliationLineItem.id == line_item_id
            )
        )
        if not line:
            raise ServiceException(
                message=f'对账单行项不存在: id={line_item_id}'
            )
        return line

    @staticmethod
    async def _load_adjustment(
        db: AsyncSession, adjustment_id: int
    ) -> Adjustment:
        adj = await db.scalar(
            select(Adjustment).where(Adjustment.id == adjustment_id)
        )
        if not adj:
            raise ServiceException(message=f'调整记录不存在: id={adjustment_id}')
        return adj

    @staticmethod
    def _audit_adjustment(
        adjustment_id: int,
        action: str,
        operator_id: int,
        detail: Optional[dict] = None,
    ) -> ReconciliationAuditLog:
        """构造调整审批审计日志（不直接写库，由调用方 db.add）"""
        return ReconciliationAuditLog(
            entity_type=_AUDIT_ENTITY_ADJUSTMENT,
            entity_id=adjustment_id,
            action=action,
            operator_id=operator_id,
            detail=detail,
        )

    # ------------------------------------------------------------------
    # 创建调整（Requirements 4.1, 4.2, 4.3）
    # ------------------------------------------------------------------

    @staticmethod
    async def create_adjustment(
        db: AsyncSession,
        anomaly_id: int,
        new_amount: Any,
        reason: str,
        created_by: int,
    ) -> int:
        """
        基于异常创建调整记录。

        - 校验异常存在且关联对账单行项
        - Property 9：若行项已被冻结（存在 pending_approval 调整），拒绝重复调整
        - 创建 Adjustment 记录，approval_status='pending_approval'，
          approval_level 由 determine_approval_level(new_amount - original_amount) 决定
        - 冻结对应行项（is_frozen=True）以阻止后续重复调整与编辑
        - 写入审计日志

        Args:
            anomaly_id: 关联的异常 ID
            new_amount: 调整后的行项金额
            reason: 调整原因（必填）
            created_by: 发起人 ID

        Returns:
            新建 Adjustment 的 ID

        Raises:
            ServiceException: 异常或行项不存在 / 无 line_item_id / 行项已冻结 /
                              金额或原因非法
        """
        if not reason or not str(reason).strip():
            raise ServiceException(message='调整原因不能为空')

        new_amt = _to_decimal(new_amount)
        if new_amt is None:
            raise ServiceException(message=f'调整后金额非法: {new_amount}')

        anomaly = await AnomalyService._load_anomaly(db, anomaly_id)

        if anomaly.line_item_id is None:
            raise ServiceException(
                message=f'异常 {anomaly_id} 未关联行项，无法创建调整'
            )

        line = await AnomalyService._load_line_item_for_adjustment(
            db, anomaly.line_item_id
        )

        # Property 9：行项冻结即拒绝
        if bool(line.is_frozen):
            raise ServiceException(
                message=(
                    f'行项 {line.id} 已存在待审批调整，'
                    f'禁止重复调整（Property 9）'
                )
            )

        # 双重保险：即便 is_frozen 标志意外被清，也通过查询再校验一次
        existing_pending = await db.scalar(
            select(Adjustment.id).where(
                and_(
                    Adjustment.line_item_id == line.id,
                    Adjustment.approval_status.in_(
                        (ADJUSTMENT_STATUS_PENDING, ADJUSTMENT_STATUS_ESCALATED)
                    ),
                )
            ).limit(1)
        )
        if existing_pending is not None:
            raise ServiceException(
                message=(
                    f'行项 {line.id} 已存在待审批调整 '
                    f'(adjustment_id={existing_pending})，禁止重复调整'
                )
            )

        original_amt = (
            Decimal(str(line.total_amount))
            if line.total_amount is not None
            else Decimal('0')
        )
        diff = new_amt - original_amt
        approval_level = AnomalyService.determine_approval_level(diff)

        adjustment = Adjustment(
            anomaly_id=anomaly.id,
            statement_id=anomaly.statement_id,
            line_item_id=line.id,
            original_amount=original_amt,
            adjusted_amount=new_amt,
            adjustment_reason=str(reason).strip(),
            approval_status=ADJUSTMENT_STATUS_PENDING,
            approval_level=approval_level,
            created_by=created_by,
        )
        db.add(adjustment)

        # 冻结行项（Requirement 4.3）
        line.is_frozen = True

        await db.flush()  # 拿到 adjustment.id

        db.add(AnomalyService._audit_adjustment(
            adjustment_id=adjustment.id,
            action=_AUDIT_ACTION_ADJUSTMENT_CREATED,
            operator_id=created_by,
            detail={
                'anomaly_id': anomaly.id,
                'line_item_id': line.id,
                'original_amount': str(original_amt),
                'adjusted_amount': str(new_amt),
                'diff': str(diff),
                'approval_level': approval_level,
                'reason': str(reason).strip(),
            },
        ))

        await db.flush()
        await db.commit()

        logger.info(
            '[AnomalyService] 创建调整 adjustment_id={} anomaly_id={} '
            'line_item_id={} diff={} approval_level={}',
            adjustment.id, anomaly.id, line.id, diff, approval_level,
        )
        return adjustment.id

    # ------------------------------------------------------------------
    # 审批调整（Requirements 4.4, 4.5, 4.6）
    # ------------------------------------------------------------------

    @staticmethod
    async def approve_adjustment(
        db: AsyncSession,
        adjustment_id: int,
        approver_id: int,
        approved: bool,
        comment: str = '',
    ) -> bool:
        """
        审批调整记录。

        - approved=True：
            * 更新行项 total_amount = adjusted_amount
            * 解除行项冻结（is_frozen=False）
            * 调用 ReconciliationService.calculate_summary 重算对账单汇总
              （Property 2 一致性）
            * approval_status='approved'，记录审批人/时间
        - approved=False（驳回）：
            * approval_status='rejected'，记录驳回原因（comment）
            * 解除行项冻结（is_frozen=False），允许后续重新提交调整
            * 通过 NotificationService 通知发起人

        无论通过/驳回，都会写入审计日志。
        已经处于 approved/rejected 状态的调整不可重复审批。

        Args:
            adjustment_id: 调整 ID
            approver_id: 审批人 ID
            approved: True 通过 / False 驳回
            comment: 驳回原因（驳回时建议必填）或审批备注

        Returns:
            True 表示审批已落库

        Raises:
            ServiceException: 调整不存在 / 状态非待审批
        """
        adj = await AnomalyService._load_adjustment(db, adjustment_id)

        if adj.approval_status not in (
            ADJUSTMENT_STATUS_PENDING, ADJUSTMENT_STATUS_ESCALATED
        ):
            raise ServiceException(
                message=(
                    f'调整 {adjustment_id} 当前状态={adj.approval_status}，'
                    f'不可再次审批'
                )
            )

        if not approved and (not comment or not str(comment).strip()):
            # 驳回必须填写原因（Requirement 4.5）
            raise ServiceException(message='驳回调整必须填写原因')

        line = await AnomalyService._load_line_item_for_adjustment(
            db, adj.line_item_id
        )

        now = datetime.now()

        if approved:
            # 落地金额变更
            line.total_amount = Decimal(str(adj.adjusted_amount))
            line.is_frozen = False
            adj.approval_status = ADJUSTMENT_STATUS_APPROVED
            adj.approved_by = approver_id
            adj.approved_at = now
            adj.reject_reason = None

            await db.flush()

            # 重算对账单汇总（Property 2 / Requirement 4.4）
            summary = await ReconciliationService.calculate_summary(
                db, adj.statement_id
            )

            db.add(AnomalyService._audit_adjustment(
                adjustment_id=adj.id,
                action=_AUDIT_ACTION_ADJUSTMENT_APPROVED,
                operator_id=approver_id,
                detail={
                    'anomaly_id': adj.anomaly_id,
                    'line_item_id': adj.line_item_id,
                    'original_amount': str(adj.original_amount),
                    'adjusted_amount': str(adj.adjusted_amount),
                    'statement_total': str(summary.get('total_amount', 0)),
                    'comment': str(comment).strip() if comment else None,
                },
            ))
            await db.flush()
            await db.commit()

            logger.info(
                '[AnomalyService] 审批通过 adjustment_id={} approver={} '
                'line_item_id={} new_amount={} statement_total={}',
                adj.id, approver_id, adj.line_item_id,
                adj.adjusted_amount, summary.get('total_amount', 0),
            )
            return True

        # 驳回路径
        line.is_frozen = False
        adj.approval_status = ADJUSTMENT_STATUS_REJECTED
        adj.approved_by = approver_id
        adj.approved_at = now
        adj.reject_reason = str(comment).strip()

        db.add(AnomalyService._audit_adjustment(
            adjustment_id=adj.id,
            action=_AUDIT_ACTION_ADJUSTMENT_REJECTED,
            operator_id=approver_id,
            detail={
                'anomaly_id': adj.anomaly_id,
                'line_item_id': adj.line_item_id,
                'original_amount': str(adj.original_amount),
                'adjusted_amount': str(adj.adjusted_amount),
                'reject_reason': adj.reject_reason,
            },
        ))
        await db.flush()
        await db.commit()

        # 通知发起人（Requirement 4.5）
        try:
            await AnomalyService._notify_originator_rejected(db, adj)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                '[AnomalyService] 通知发起人驳回失败 adjustment_id={} err={}',
                adj.id, exc,
            )

        logger.info(
            '[AnomalyService] 审批驳回 adjustment_id={} approver={} '
            'reason={}',
            adj.id, approver_id, adj.reject_reason,
        )
        return True

    # ------------------------------------------------------------------
    # 驳回通知发起人
    # ------------------------------------------------------------------

    @staticmethod
    async def _notify_originator_rejected(
        db: AsyncSession, adjustment: Adjustment
    ) -> bool:
        """
        通过 ReconciliationNotificationService 的渠道向调整发起人发送驳回通知。

        采用 NotificationChannel 直接发送，不写额外的对账单维度审计日志，
        保留通用通知接口。
        """
        channel = ReconciliationNotificationService.get_channel()
        recipient = f'user:{adjustment.created_by}'
        subject = (
            f'[调整驳回] 您发起的调整 #{adjustment.id} 已被驳回'
        )
        body = (
            f'您发起的对账单 #{adjustment.statement_id} '
            f'行项 #{adjustment.line_item_id} 的金额调整已被驳回。\n'
            f'原金额：{adjustment.original_amount}\n'
            f'调整后金额：{adjustment.adjusted_amount}\n'
            f'驳回原因：{adjustment.reject_reason or ""}\n'
            f'请根据驳回原因修正后重新发起调整。'
        )
        metadata = {
            'adjustment_id': adjustment.id,
            'statement_id': adjustment.statement_id,
            'line_item_id': adjustment.line_item_id,
            'kind': 'adjustment_rejected',
        }
        return await channel.send(recipient, subject, body, metadata)

    # ------------------------------------------------------------------
    # 自动升级（Requirement 4.7）
    # ------------------------------------------------------------------

    @staticmethod
    async def escalate_pending_adjustments(
        db: AsyncSession, operator_id: int = 0
    ) -> dict:
        """
        扫描超过 3 个工作日仍处于 pending_approval 的调整并升级。

        升级规则：
          - manager → director（升至总监）
          - director → director（已是最高层级，仅状态切换为 escalated 并发催办）
        升级后将 approval_status 置为 'escalated'，调用方/审批人后续仍可走
        approve_adjustment 处理。

        Returns:
            {'scanned': N, 'escalated': N, 'errors': N}

        Note:
            实际的调度器钩子（如 APScheduler）应在系统启动时注册，
            周期性调用本方法即可；本方法本身不绑定调度器。
        """
        now = datetime.now()
        # cutoff 表示：created_at 早于该时间的调整即视为已超过 3 工作日
        # 简化策略：先粗筛 created_at < now - 3 自然日的候选，再精确按工作日核验
        rough_cutoff = now - timedelta(days=_ESCALATION_WORKING_DAYS)

        candidates = (await db.execute(
            select(Adjustment).where(
                Adjustment.approval_status == ADJUSTMENT_STATUS_PENDING,
                Adjustment.created_at <= rough_cutoff,
            )
        )).scalars().all()

        escalated = 0
        errors = 0
        for adj in candidates:
            try:
                # 精确判定：created_at + 3 工作日 ≤ now 才升级
                deadline = _add_working_days(
                    adj.created_at or now, _ESCALATION_WORKING_DAYS
                )
                if deadline > now:
                    continue

                old_level = adj.approval_level
                new_level = (
                    APPROVAL_LEVEL_DIRECTOR
                    if old_level == APPROVAL_LEVEL_MANAGER
                    else APPROVAL_LEVEL_DIRECTOR
                )

                adj.approval_status = ADJUSTMENT_STATUS_ESCALATED
                adj.approval_level = new_level

                db.add(AnomalyService._audit_adjustment(
                    adjustment_id=adj.id,
                    action=_AUDIT_ACTION_ADJUSTMENT_ESCALATED,
                    operator_id=operator_id,
                    detail={
                        'anomaly_id': adj.anomaly_id,
                        'line_item_id': adj.line_item_id,
                        'old_level': old_level,
                        'new_level': new_level,
                        'created_at': str(adj.created_at),
                        'escalated_at': str(now),
                    },
                ))
                escalated += 1
            except Exception as exc:  # noqa: BLE001
                errors += 1
                logger.error(
                    '[AnomalyService] 调整升级失败 adjustment_id={} err={}',
                    adj.id, exc,
                )

        if escalated:
            await db.flush()
            await db.commit()

        summary = {
            'scanned': len(candidates),
            'escalated': escalated,
            'errors': errors,
        }
        logger.info('[AnomalyService] 调整升级扫描完成 {}', summary)
        return summary


__all__ = [
    'AnomalyService',
    'ANOMALY_TYPE_AMOUNT_DIFF',
    'ANOMALY_TYPE_QUANTITY_DIFF',
    'ANOMALY_TYPE_SUPPLIER_MISSING',
    'ANOMALY_TYPE_DUPLICATE',
    'ANOMALY_TYPE_QUALITY_DISPUTE',
    'SEVERITY_CRITICAL',
    'SEVERITY_WARNING',
    'SEVERITY_INFO',
    'APPROVAL_LEVEL_MANAGER',
    'APPROVAL_LEVEL_DIRECTOR',
    'ADJUSTMENT_STATUS_PENDING',
    'ADJUSTMENT_STATUS_APPROVED',
    'ADJUSTMENT_STATUS_REJECTED',
    'ADJUSTMENT_STATUS_ESCALATED',
]
