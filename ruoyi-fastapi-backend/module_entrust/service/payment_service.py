"""
对账系统 — 付款 Service
=========================================
覆盖需求 5.1 ~ 5.7 / Property 10 / Property 11

职责：
  1. 对账单确认后生成付款申请（PaymentRequest）
       - 单个对账单仅生成一份，重复创建幂等返回已有 ID
       - payable_amount = total_received_value + total_logistics_cost
         （直接从 statement 字段计算，确保应付金额排除差异部分）
       - 向后兼容：若 total_received_value 为 None/0（旧数据），回退到 total_amount
  2. 录入付款记录（PaymentRecord），支持多笔部分付款
       - 自动累计 paid_amount
       - 自动重算 payment_status
       - 当全额付清时同步对账单 status=paid
  3. 计算付款状态：pending_payment / partially_paid / paid

并发控制（design.md "并发控制"）：
  - 录入付款时使用 SELECT FOR UPDATE 锁定 PaymentRequest 行，防止
    并发录入导致超额或状态计算错位
  - 创建付款申请时同样使用 SELECT FOR UPDATE 锁定关联对账单，避免
    并发触发的双重申请绕过 statement_id 唯一约束之前的检查
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceException
from module_entrust.entity.do.reconciliation_do import (
    PaymentRecord,
    PaymentRequest,
    ReconciliationStatement,
)
from module_entrust.service.reconciliation_audit_service import (
    ACTION_CREATE,
    ENTITY_TYPE_PAYMENT,
    ReconciliationAuditService,
)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

PAYMENT_STATUS_PENDING = 'pending_payment'
PAYMENT_STATUS_PARTIALLY_PAID = 'partially_paid'
PAYMENT_STATUS_PAID = 'paid'

# 允许触发付款申请生成的 confirmation_status
_CONFIRMABLE_STATUSES = frozenset({'confirmed'})


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _to_decimal(value) -> Decimal:
    """安全地将数值转换为 Decimal；None 视作 0。"""
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class PaymentService:
    """付款流程服务。"""

    # ------------------------------------------------------------------
    # 付款状态计算（Property 11）— 纯函数，便于属性测试
    # ------------------------------------------------------------------

    @staticmethod
    def compute_payment_status(
        paid_amount: Decimal, payable_amount: Decimal
    ) -> str:
        """
        根据已付金额与应付金额计算付款状态。

        规则（与 design.md "付款状态计算算法" 对齐 / Property 11）：
          - paid_amount >= payable_amount      -> 'paid'
          - 0 < paid_amount < payable_amount   -> 'partially_paid'
          - paid_amount <= 0                   -> 'pending_payment'
        """
        paid = _to_decimal(paid_amount)
        payable = _to_decimal(payable_amount)
        if paid >= payable:
            return PAYMENT_STATUS_PAID
        if paid > 0:
            return PAYMENT_STATUS_PARTIALLY_PAID
        return PAYMENT_STATUS_PENDING

    # ------------------------------------------------------------------
    # 付款申请生成（Requirement 5.1 / Property 10）
    # ------------------------------------------------------------------

    @staticmethod
    async def create_payment_request(
        db: AsyncSession,
        statement_id: int,
    ) -> int:
        """
        对账单确认后生成 PaymentRequest。

        - 仅 confirmation_status == 'confirmed' 的对账单允许生成
        - 单个对账单仅生成一份；若已存在则幂等返回现有 ID
        - 使用 SELECT FOR UPDATE 锁定对账单行，避免并发创建竞争

        Args:
            db: AsyncSession，事务由本方法管理（调用方提交前请勿
                重复 commit）
            statement_id: 对账单 ID

        Returns:
            生成或已存在的 PaymentRequest ID

        Raises:
            ServiceException: 对账单不存在 / 状态不为 confirmed
        """
        # 锁定对账单，避免并发触发
        statement = await db.scalar(
            select(ReconciliationStatement)
            .where(ReconciliationStatement.id == statement_id)
            .with_for_update()
        )
        if not statement:
            raise ServiceException(message=f'对账单 {statement_id} 不存在')

        if statement.confirmation_status not in _CONFIRMABLE_STATUSES:
            raise ServiceException(
                message=(
                    f'对账单 {statement.statement_no} 当前确认状态为 '
                    f'{statement.confirmation_status}，不允许生成付款申请；'
                    f'仅 confirmed 状态可生成'
                )
            )

        # 幂等：已存在则直接返回（statement_id 唯一约束）
        existing = await db.scalar(
            select(PaymentRequest).where(
                PaymentRequest.statement_id == statement_id
            )
        )
        if existing:
            logger.info(
                f'[PaymentService] 付款申请已存在，幂等返回 '
                f'statement_id={statement_id} request_id={existing.id}'
            )
            return existing.id

        # 应付金额 = 实际收到总价值 + 物流总费用（Requirement 5.1）
        # 直接使用 total_received_value + total_logistics_cost，确保应付金额
        # 排除差异部分（只为实际收到的产品付款）
        received = _to_decimal(statement.total_received_value)
        logistics = _to_decimal(statement.total_logistics_cost)
        if received:
            # 新数据：明确使用 received + logistics
            payable = received + logistics
        else:
            # 向后兼容：旧数据可能未填充 total_received_value，回退到 total_amount
            payable = _to_decimal(statement.total_amount)
        pr = PaymentRequest(
            statement_id=statement.id,
            supplier_id=statement.supplier_id,
            statement_no=statement.statement_no,
            payable_amount=payable,
            paid_amount=Decimal('0'),
            payment_status=PAYMENT_STATUS_PENDING,
        )
        db.add(pr)
        await db.flush()  # 获取 pr.id

        # 审计日志：付款申请创建（Requirement 8.1）
        await ReconciliationAuditService.log_action(
            db=db,
            entity_type=ENTITY_TYPE_PAYMENT,
            entity_id=pr.id,
            action=ACTION_CREATE,
            operator_id=0,
            operator_name='system',
            detail={
                'sub_action': 'create_payment_request',
                'statement_id': statement.id,
                'statement_no': statement.statement_no,
                'supplier_id': statement.supplier_id,
                'payable_amount': str(payable),
            },
        )

        await db.commit()

        logger.info(
            f'[PaymentService] 已生成付款申请 request_id={pr.id} '
            f'statement_no={statement.statement_no} supplier_id={pr.supplier_id} '
            f'payable={payable}'
        )
        return pr.id

    # ------------------------------------------------------------------
    # 付款记录录入（Requirements 5.3 ~ 5.7）
    # ------------------------------------------------------------------

    @staticmethod
    async def record_payment(
        db: AsyncSession,
        request_id: int,
        amount: Decimal,
        payment_date: date,
        bank_ref: Optional[str],
        created_by: int,
    ) -> int:
        """
        录入付款记录并自动重算付款状态。

        - 使用 SELECT FOR UPDATE 锁定 PaymentRequest 行，防止并发录入
        - 累计 paid_amount = 已付 + 本次金额
        - payment_status 通过 compute_payment_status 重算
        - 全额付清时同步将关联对账单 status 更新为 'paid'

        Args:
            db: AsyncSession
            request_id: 付款申请 ID
            amount: 本次付款金额（必须 > 0）
            payment_date: 付款日期
            bank_ref: 银行流水号（可选）
            created_by: 录入人 ID（必填，禁止匿名录入）

        Returns:
            新建 PaymentRecord ID

        Raises:
            ServiceException: 申请不存在 / 金额非法 / 录入人缺失
        """
        if not created_by:
            raise ServiceException(message='付款录入操作必须提供 created_by')
        if payment_date is None:
            raise ServiceException(message='付款日期不能为空')

        amt = _to_decimal(amount)
        if amt <= 0:
            raise ServiceException(message='付款金额必须大于 0')

        # 锁定付款申请行（design.md "并发控制"：SELECT FOR UPDATE 防止超额）
        pr = await db.scalar(
            select(PaymentRequest)
            .where(PaymentRequest.id == request_id)
            .with_for_update()
        )
        if not pr:
            raise ServiceException(message=f'付款申请 {request_id} 不存在')

        try:
            # 写入付款记录
            record = PaymentRecord(
                request_id=pr.id,
                statement_id=pr.statement_id,
                payment_amount=amt,
                payment_date=payment_date,
                bank_reference=(bank_ref.strip() if bank_ref else None),
                created_by=created_by,
            )
            db.add(record)

            # 累计已付与状态
            previous_paid = _to_decimal(pr.paid_amount)
            new_paid = previous_paid + amt
            payable = _to_decimal(pr.payable_amount)

            pr.paid_amount = new_paid
            pr.payment_status = PaymentService.compute_payment_status(
                new_paid, payable
            )
            pr.updated_at = datetime.now()

            # 全额付清时同步对账单状态（Requirements 5.5 / 8.3 一致性）
            if pr.payment_status == PAYMENT_STATUS_PAID:
                statement = await db.scalar(
                    select(ReconciliationStatement)
                    .where(ReconciliationStatement.id == pr.statement_id)
                    .with_for_update()
                )
                if statement and statement.status != 'paid':
                    statement.status = 'paid'
                    statement.updated_at = datetime.now()

            await db.flush()

            # 审计日志：付款记录录入（Requirement 8.1）
            await ReconciliationAuditService.log_action(
                db=db,
                entity_type=ENTITY_TYPE_PAYMENT,
                entity_id=pr.id,
                action=ACTION_CREATE,
                operator_id=int(created_by or 0),
                detail={
                    'sub_action': 'record_payment',
                    'record_id': record.id,
                    'statement_id': pr.statement_id,
                    'amount': str(amt),
                    'paid_total': str(pr.paid_amount),
                    'payment_status': pr.payment_status,
                    'payment_date': str(payment_date),
                    'bank_reference': record.bank_reference,
                },
            )

            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error(
                f'[PaymentService] 录入付款记录失败 request_id={request_id} '
                f'amount={amt} err={exc}'
            )
            raise

        logger.info(
            f'[PaymentService] 已录入付款记录 record_id={record.id} '
            f'request_id={pr.id} amount={amt} paid_total={pr.paid_amount} '
            f'status={pr.payment_status}'
        )
        return record.id

    # ------------------------------------------------------------------
    # 付款状态查询（Property 11 — 直接以 PaymentRecord 之和为准）
    # ------------------------------------------------------------------

    @staticmethod
    async def calculate_payment_status(
        db: AsyncSession, request_id: int
    ) -> str:
        """
        根据 PaymentRecord 之和计算付款状态（不修改数据）。

        等同 sum(payment_amount) 与 payable_amount 的对比。
        与存储的 paid_amount 字段相比，本方法直接依赖 PaymentRecord 行作为
        权威数据源，便于校验或对账自检。

        Args:
            db: AsyncSession
            request_id: 付款申请 ID

        Returns:
            'pending_payment' / 'partially_paid' / 'paid'

        Raises:
            ServiceException: 付款申请不存在
        """
        pr = await db.scalar(
            select(PaymentRequest).where(PaymentRequest.id == request_id)
        )
        if not pr:
            raise ServiceException(message=f'付款申请 {request_id} 不存在')

        total_raw = await db.scalar(
            select(
                func.coalesce(func.sum(PaymentRecord.payment_amount), 0)
            ).where(PaymentRecord.request_id == request_id)
        )
        paid_total = _to_decimal(total_raw)
        payable = _to_decimal(pr.payable_amount)

        return PaymentService.compute_payment_status(paid_total, payable)


__all__ = [
    'PaymentService',
    'PAYMENT_STATUS_PENDING',
    'PAYMENT_STATUS_PARTIALLY_PAID',
    'PAYMENT_STATUS_PAID',
]
