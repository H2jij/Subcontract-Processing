"""
对账系统 — 订单结算明细 Service
=====================================
职责（Requirements 10.1 ~ 10.8）：
  1. 工单交付且质检合格后生成 SettlementDetail（draft 状态）
  2. 维护结算行项（process_fee / logistics / re_shipment / deduction /
     rework / customer_payment 六类）
  3. 提供行项的新增 / 修改（仅 draft 状态可写）— Requirement 10.7
  4. 确认结算（draft → finalized），记录时间和操作人 — Requirement 10.8
  5. 计算净利润：net_profit = customer_payment - sum(成本项)
  6. finalized 后禁止修改行项、删除关联附件/虚拟入库 — Requirement 10.8

关键不变量：
  - **Property 14**：net_profit = customer_payment - Σ(line_items.amount where is_income=False)
    其中 customer_payment 由 SettlementDetail.customer_payment 字段记录，
    并由 is_income=True 的行项（典型为 item_type=customer_payment）汇总同步。
  - **Property 15**：行项仅在 status='draft' 时允许修改；finalized 后所有写操作拒绝。
  - 初始状态固定为 'draft'（DO 默认值）。
  - 一个委外工单仅生成一份 SettlementDetail（幂等）。
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceException
from module_entrust.entity.do.entrust_do import EntrustOutsourceOrder
from module_entrust.entity.do.reconciliation_do import (
    ReconciliationStatement,
    SettlementDetail,
    SettlementLineItem,
)
from module_entrust.service.reconciliation_audit_service import (
    ACTION_CONFIRM,
    ACTION_CREATE,
    ENTITY_TYPE_SETTLEMENT,
    ReconciliationAuditService,
)
from module_entrust.service.variance_calculation_service import (
    VarianceCalculationService,
)
from module_entrust.service.virtual_inbound_service import (
    VirtualInboundService,
)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 结算行项允许的 item_type
_VALID_ITEM_TYPES: frozenset[str] = frozenset({
    'process_fee',
    'logistics',
    're_shipment',
    'deduction',
    'rework',
    'customer_payment',
})

# 仅 draft 状态允许修改 / 新增 / 删除行项
_MUTABLE_STATUSES: frozenset[str] = frozenset({'draft'})

# 行项编辑允许覆盖的字段（白名单）
_LINE_ITEM_UPDATABLE_FIELDS: tuple[str, ...] = (
    'item_type',
    'description',
    'amount',
    'is_income',
)


def _to_decimal(value) -> Decimal:
    """安全转换为 Decimal（None / 空串 视为 0）。"""
    if value is None or value == '':
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SettlementService:
    """订单结算明细服务。"""

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    async def _load_settlement(
        db: AsyncSession, settlement_id: int
    ) -> SettlementDetail:
        """加载结算明细，不存在则抛出 ServiceException。"""
        stmt = select(SettlementDetail).where(SettlementDetail.id == settlement_id)
        settlement = (await db.execute(stmt)).scalar_one_or_none()
        if settlement is None:
            raise ServiceException(message=f'结算明细不存在: id={settlement_id}')
        return settlement

    @staticmethod
    def _ensure_mutable(settlement: SettlementDetail) -> None:
        """
        校验结算明细处于可修改状态（draft）。

        Requirement 10.7: draft 状态允许财务人员手动编辑行项。
        Requirement 10.8 (隐含): finalized 状态禁止任何行项修改。

        此方法在 add_line_item / update_line_item 中调用，
        确保 Property 15 不变量：行项仅在 status='draft' 时允许修改。
        """
        if settlement.status not in _MUTABLE_STATUSES:
            raise ServiceException(
                message=(
                    f'结算明细当前状态为 {settlement.status}，不允许修改行项；'
                    f'仅 draft 状态可编辑'
                )
            )

    @staticmethod
    def _validate_item_type(item_type: str) -> None:
        if item_type not in _VALID_ITEM_TYPES:
            raise ServiceException(
                message=(
                    f'非法的结算行项类型: {item_type}；'
                    f'允许值: {sorted(_VALID_ITEM_TYPES)}'
                )
            )

    @staticmethod
    async def _load_line_item(
        db: AsyncSession, settlement_id: int, item_id: int
    ) -> SettlementLineItem:
        stmt = select(SettlementLineItem).where(
            SettlementLineItem.id == item_id,
            SettlementLineItem.settlement_id == settlement_id,
        )
        line = (await db.execute(stmt)).scalar_one_or_none()
        if line is None:
            raise ServiceException(
                message=(
                    f'结算行项不存在或不属于该结算明细: '
                    f'settlement_id={settlement_id}, item_id={item_id}'
                )
            )
        return line

    @staticmethod
    async def _recalculate_totals(
        db: AsyncSession, settlement_id: int
    ) -> tuple[Decimal, Decimal, Decimal]:
        """
        基于全部行项重算 total_cost / customer_payment / net_profit
        并写回 SettlementDetail（不 commit，由调用方控制事务）。

        净利润公式（Requirement 10.6）：
        net_profit = customer_payment - (actual_delivered_amount + logistics_cost
                     + virtual_inbound_amount - anomaly_deduction_amount)

        其中 customer_payment 由 is_income=True 的行项汇总同步。
        total_cost 由 is_income=False 的行项汇总（保留兼容）。

        Returns:
            (total_cost, customer_payment, net_profit)
        """
        # 成本之和（行项维度，保留兼容）
        cost_stmt = (
            select(func.coalesce(func.sum(SettlementLineItem.amount), 0))
            .where(
                SettlementLineItem.settlement_id == settlement_id,
                SettlementLineItem.is_income.is_(False),
            )
        )
        total_cost = _to_decimal((await db.execute(cost_stmt)).scalar_one())

        # 收入之和（视为客户付款汇总；典型为 item_type='customer_payment'）
        income_stmt = (
            select(func.coalesce(func.sum(SettlementLineItem.amount), 0))
            .where(
                SettlementLineItem.settlement_id == settlement_id,
                SettlementLineItem.is_income.is_(True),
            )
        )
        customer_payment = _to_decimal((await db.execute(income_stmt)).scalar_one())

        # 写回 SettlementDetail
        settlement = await SettlementService._load_settlement(db, settlement_id)
        settlement.total_cost = total_cost
        settlement.customer_payment = customer_payment

        # 净利润使用新公式（Requirement 10.6）：
        # net_profit = customer_payment - (actual_delivered_amount + logistics_cost
        #              + virtual_inbound_amount - anomaly_deduction_amount)
        actual_delivered_amount = _to_decimal(settlement.actual_delivered_amount)
        logistics_cost = _to_decimal(settlement.logistics_cost)
        virtual_inbound_amount = _to_decimal(settlement.virtual_inbound_amount)
        anomaly_deduction_amount = _to_decimal(settlement.anomaly_deduction_amount)

        net_profit = customer_payment - (
            actual_delivered_amount
            + logistics_cost
            + virtual_inbound_amount
            - anomaly_deduction_amount
        )
        settlement.net_profit = net_profit
        await db.flush()
        return total_cost, customer_payment, net_profit

    # ------------------------------------------------------------------
    # 1. 生成结算明细
    # ------------------------------------------------------------------

    @staticmethod
    async def generate_settlement_detail(
        db: AsyncSession, order_id: int
    ) -> int:
        """
        工单交付且质检合格后生成结算明细（Requirements 10.1 ~ 10.6）。

        以订购单为基准生成结算明细，填充：
          - 订购基准：ordered_quantity, ordered_unit_price, ordered_amount
          - 实际交付：actual_delivered_qty, actual_delivered_amount
          - 虚拟入库：virtual_inbound_amount
          - 异常扣除：anomaly_deduction_amount
          - 物流费用：logistics_cost
          - 差异：variance, variance_reasons
          - 净利润：customer_payment - (actual_delivered_amount + logistics_cost
                    + virtual_inbound_amount - anomaly_deduction_amount)

        约束：
          - 工单必须存在，且 status='delivered'、quality_status='pass'
          - 同一订单仅生成一份 SettlementDetail（幂等：已存在则直接返回原 ID）
          - 初始状态为 'draft'

        Args:
            db: AsyncSession
            order_id: 委外工单 ID

        Returns:
            SettlementDetail 主键 ID（已存在则返回原 ID）

        Raises:
            ServiceException: 工单不存在或不满足生成条件
        """
        # 幂等检查
        existing_stmt = select(SettlementDetail).where(
            SettlementDetail.order_id == order_id
        )
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            logger.info(
                f'[SettlementService] 结算明细已存在 order_id={order_id} '
                f'settlement_id={existing.id}'
            )
            return existing.id

        order_stmt = select(EntrustOutsourceOrder).where(
            EntrustOutsourceOrder.id == order_id
        )
        order = (await db.execute(order_stmt)).scalar_one_or_none()
        if order is None:
            raise ServiceException(message=f'委外工单不存在: id={order_id}')

        if order.status != 'delivered':
            raise ServiceException(
                message=(
                    f'委外工单状态为 {order.status}，不满足生成结算明细条件；'
                    f'要求 status=delivered'
                )
            )
        if order.quality_status != 'pass':
            raise ServiceException(
                message=(
                    f'委外工单质检状态为 {order.quality_status}，不满足生成结算明细条件；'
                    f'要求 quality_status=pass'
                )
            )

        # --- 使用 VarianceCalculationService 和 VirtualInboundService 计算数据 ---

        # 订购基准 (Requirement 10.2)
        ordered_quantity = order.quantity or 0
        ordered_unit_price = _to_decimal(order.unit_price)
        ordered_amount = Decimal(str(ordered_quantity)) * ordered_unit_price

        # 实际交付 (Requirement 10.2)
        actual_delivered_qty, actual_delivered_amount = (
            await VarianceCalculationService.compute_actual_delivered_value(db, order)
        )

        # 虚拟入库 (Requirement 10.2)
        virtual_inbound_amount = (
            await VirtualInboundService.get_inbound_value_for_order(db, order.id)
        )

        # 异常扣除 (Requirement 10.2)
        anomaly_deduction_amount = (
            await VarianceCalculationService.get_anomaly_deduction_amount(db, order.id)
        )

        # 物流费用 (Requirement 10.2) — 当前默认为 0，后续可从物流表获取
        logistics_cost = Decimal('0')

        # 差异计算 (Requirement 10.3)
        variance = VarianceCalculationService.calculate_order_variance(
            order_amount=ordered_amount,
            actual_delivered_value=actual_delivered_amount,
            virtual_inbound_value=virtual_inbound_amount,
            anomaly_deduction_amount=anomaly_deduction_amount,
            logistics_cost=logistics_cost,
        )

        # 差异原因 (Requirement 10.4)
        variance_reasons: list | None = None
        if variance != Decimal('0'):
            variance_reasons = await VarianceCalculationService.link_variance_reasons(
                db, order.id, variance
            )

        # 净利润计算（Requirement 10.6）：
        # net_profit = customer_payment - (actual_delivered_amount + logistics_cost
        #              + virtual_inbound_amount - anomaly_deduction_amount)
        # 初始 customer_payment 为 0，净利润也为负或 0
        customer_payment = Decimal('0')
        total_cost = (
            actual_delivered_amount
            + logistics_cost
            + virtual_inbound_amount
            - anomaly_deduction_amount
        )
        net_profit = customer_payment - total_cost

        settlement = SettlementDetail(
            order_id=order.id,
            order_no=order.order_no,
            supplier_id=order.supplier_id,
            statement_id=None,
            status='draft',
            # 订购基准
            ordered_quantity=ordered_quantity,
            ordered_unit_price=ordered_unit_price,
            ordered_amount=ordered_amount,
            # 实际交付
            actual_delivered_qty=actual_delivered_qty,
            actual_delivered_amount=actual_delivered_amount,
            # 虚拟入库
            virtual_inbound_amount=virtual_inbound_amount,
            # 异常扣除
            anomaly_deduction_amount=anomaly_deduction_amount,
            # 物流费用
            logistics_cost=logistics_cost,
            # 差异
            variance=variance,
            variance_reasons=variance_reasons,
            # 财务汇总
            total_cost=total_cost,
            customer_payment=customer_payment,
            net_profit=net_profit,
        )
        db.add(settlement)
        await db.flush()

        # 审计日志：结算明细生成（Requirement 8.1）
        await ReconciliationAuditService.log_action(
            db=db,
            entity_type=ENTITY_TYPE_SETTLEMENT,
            entity_id=settlement.id,
            action=ACTION_CREATE,
            operator_id=0,
            operator_name='system',
            detail={
                'sub_action': 'generate_settlement_detail',
                'order_id': order.id,
                'order_no': order.order_no,
                'supplier_id': order.supplier_id,
                'ordered_amount': str(ordered_amount),
                'actual_delivered_amount': str(actual_delivered_amount),
                'virtual_inbound_amount': str(virtual_inbound_amount),
                'anomaly_deduction_amount': str(anomaly_deduction_amount),
                'logistics_cost': str(logistics_cost),
                'variance': str(variance),
                'net_profit': str(net_profit),
            },
        )

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        logger.info(
            f'[SettlementService] 已生成结算明细 settlement_id={settlement.id} '
            f'order_no={order.order_no} supplier_id={order.supplier_id} '
            f'ordered_amount={ordered_amount} actual_delivered={actual_delivered_amount} '
            f'variance={variance} net_profit={net_profit}'
        )
        return settlement.id

    # ------------------------------------------------------------------
    # 2. 行项管理
    # ------------------------------------------------------------------

    @staticmethod
    async def add_line_item(
        db: AsyncSession,
        settlement_id: int,
        item_type: str,
        description: Optional[str],
        amount,
        is_income: bool = False,
    ) -> int:
        """
        新增结算行项（仅 draft 状态允许 — Requirement 10.7）。

        Args:
            settlement_id: 结算明细 ID
            item_type: 行项类型（process_fee / logistics / re_shipment /
                       deduction / rework / customer_payment）
            description: 描述（可选）
            amount: 金额（数字或可被 Decimal 解析的字符串）
            is_income: 是否为收入项；item_type=customer_payment 通常 True

        Returns:
            新建行项 ID

        Raises:
            ServiceException: 结算不存在 / 状态非 draft / item_type 非法
        """
        settlement = await SettlementService._load_settlement(db, settlement_id)
        SettlementService._ensure_mutable(settlement)
        SettlementService._validate_item_type(item_type)

        amount_dec = _to_decimal(amount)

        line = SettlementLineItem(
            settlement_id=settlement_id,
            item_type=item_type,
            description=description,
            amount=amount_dec,
            is_income=bool(is_income),
        )
        db.add(line)
        await db.flush()

        # 重算汇总（Property 14）
        await SettlementService._recalculate_totals(db, settlement_id)

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        logger.info(
            f'[SettlementService] 新增结算行项 settlement_id={settlement_id} '
            f'item_id={line.id} type={item_type} amount={amount_dec} '
            f'is_income={bool(is_income)}'
        )
        return line.id

    @staticmethod
    async def update_line_item(
        db: AsyncSession,
        settlement_id: int,
        item_id: int,
        data: dict,
    ) -> bool:
        """
        修改结算行项（仅 draft 状态允许 — Requirement 10.7）。

        - 仅白名单字段（item_type / description / amount / is_income）生效
        - item_type 修改时校验合法性
        - amount / is_income 变化后会触发汇总重算

        Args:
            settlement_id: 结算明细 ID
            item_id: 行项 ID
            data: 待更新字段字典

        Returns:
            True 表示更新成功

        Raises:
            ServiceException: 结算不存在 / 状态非 draft / 行项不存在 / 类型非法
        """
        settlement = await SettlementService._load_settlement(db, settlement_id)
        SettlementService._ensure_mutable(settlement)
        line = await SettlementService._load_line_item(db, settlement_id, item_id)

        if 'item_type' in data and data['item_type'] is not None:
            SettlementService._validate_item_type(data['item_type'])

        applied = 0
        for field in _LINE_ITEM_UPDATABLE_FIELDS:
            if field in data and data[field] is not None:
                value = data[field]
                if field == 'amount':
                    value = _to_decimal(value)
                elif field == 'is_income':
                    value = bool(value)
                setattr(line, field, value)
                applied += 1

        await db.flush()

        # 行项任意变化都重算（保持 Property 14 不变量稳定）
        await SettlementService._recalculate_totals(db, settlement_id)

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        logger.info(
            f'[SettlementService] 更新结算行项 settlement_id={settlement_id} '
            f'item_id={item_id} fields_updated={applied}'
        )
        return True

    # ------------------------------------------------------------------
    # 3. 净利润计算
    # ------------------------------------------------------------------

    @staticmethod
    async def calculate_net_profit(
        db: AsyncSession, settlement_id: int
    ) -> Decimal:
        """
        重算并落库净利润（Property 14 / Requirement 10.4）。

        net_profit = customer_payment - Σ(line_items.amount where is_income=False)

        其中 customer_payment 由 is_income=True 的行项汇总同步至
        SettlementDetail.customer_payment。

        Args:
            settlement_id: 结算明细 ID

        Returns:
            最新净利润值

        Raises:
            ServiceException: 结算不存在
        """
        await SettlementService._load_settlement(db, settlement_id)
        _, _, net_profit = await SettlementService._recalculate_totals(
            db, settlement_id
        )

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        logger.info(
            f'[SettlementService] 重算净利润 settlement_id={settlement_id} '
            f'net_profit={net_profit}'
        )
        return net_profit

    # ------------------------------------------------------------------
    # 4. 确认结算
    # ------------------------------------------------------------------

    @staticmethod
    async def finalize_settlement(
        db: AsyncSession,
        settlement_id: int,
        operator_id: int,
        statement_id: Optional[int] = None,
    ) -> dict:
        """
        确认结算明细（Requirement 10.8）。

        原子完成：
          1. 重算 total_cost / customer_payment / net_profit
          2. 状态 draft → finalized
          3. 记录 finalized_at（精确到秒）/ finalized_by
          4. 可选：关联 statement_id（须存在；提供 None 则保持原值）

        约束（Requirement 10.7 / 10.8）：
          - 仅 draft 状态可确认；finalized 重复确认拒绝
          - operator_id 必填，禁止匿名/自动确认
          - 若提供 statement_id，必须存在，否则抛 ServiceException

        副作用（Requirement 10.8 — finalized 后不可变性）：
          - finalized 后，_ensure_mutable() 将拒绝所有行项写操作
          - finalized 后，PaymentEvidenceService 将拒绝删除关联凭证
          - finalized 后，VirtualInboundService 将拒绝修改/删除关联虚拟入库记录

        Args:
            db: AsyncSession
            settlement_id: 结算明细 ID
            operator_id: 操作人 user_id
            statement_id: 关联的对账单 ID（可选）

        Returns:
            ``{success, settlement_id, status, statement_id, net_profit,
                finalized_at}``

        Raises:
            ValueError: operator_id 缺失
            ServiceException: 结算不存在 / 状态非 draft / statement_id 不存在
        """
        if not operator_id:
            raise ValueError('finalize_settlement 必须由有效用户操作，operator_id 不能为空')

        settlement = await SettlementService._load_settlement(db, settlement_id)
        if settlement.status != 'draft':
            raise ServiceException(
                message=(
                    f'结算明细当前状态为 {settlement.status}，仅 draft 状态可确认'
                )
            )

        # 校验关联对账单存在
        if statement_id is not None:
            stmt_exists = await db.scalar(
                select(ReconciliationStatement.id).where(
                    ReconciliationStatement.id == statement_id
                )
            )
            if stmt_exists is None:
                raise ServiceException(
                    message=f'关联对账单不存在: statement_id={statement_id}'
                )

        # 确认前重算，确保汇总字段为最新值
        _, _, net_profit = await SettlementService._recalculate_totals(
            db, settlement_id
        )

        now = datetime.now()
        try:
            settlement.status = 'finalized'
            settlement.finalized_at = now
            settlement.finalized_by = operator_id
            if statement_id is not None:
                settlement.statement_id = statement_id
            settlement.updated_at = now

            await db.flush()

            # 审计日志：结算确认（Requirement 8.1）
            await ReconciliationAuditService.log_action(
                db=db,
                entity_type=ENTITY_TYPE_SETTLEMENT,
                entity_id=settlement.id,
                action=ACTION_CONFIRM,
                operator_id=operator_id,
                detail={
                    'sub_action': 'finalize_settlement',
                    'order_id': settlement.order_id,
                    'order_no': settlement.order_no,
                    'statement_id': settlement.statement_id,
                    'net_profit': str(net_profit),
                    'finalized_at': now.isoformat(),
                },
            )

            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error(
                f'[SettlementService] 确认结算失败 settlement_id={settlement_id}: {exc}'
            )
            raise

        logger.info(
            f'[SettlementService] 结算明细已确认 settlement_id={settlement_id} '
            f'operator_id={operator_id} statement_id={settlement.statement_id} '
            f'net_profit={net_profit}'
        )
        return {
            'success': True,
            'settlement_id': settlement.id,
            'status': settlement.status,
            'statement_id': settlement.statement_id,
            'net_profit': net_profit,
            'finalized_at': now,
        }
