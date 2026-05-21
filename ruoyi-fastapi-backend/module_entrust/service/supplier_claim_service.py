"""
对账系统 — 供应商对账确认 Service
=====================================

负责供应商对对账单的主动确认/争议操作，以及确认历史的查询。

核心约束（来自需求 2.3 / Property 5）：
- 确认操作必须由供应商主动点击触发，**禁止任何自动/超时/规则化确认**
- 所有写入操作在同一事务内原子完成：更新 ReconciliationStatement
  状态字段、记录 ConfirmationHistory，并在确认时触发 PaymentRequest 生成
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.user_do import SysUser
from module_entrust.entity.do.reconciliation_do import (
    ConfirmationHistory,
    PaymentRequest,
    ReconciliationStatement,
)
from module_entrust.service.reconciliation_audit_service import (
    ACTION_CONFIRM,
    ACTION_REJECT,
    ENTITY_TYPE_STATEMENT,
    ReconciliationAuditService,
)


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

# 允许发起确认/争议的源状态集合
_CONFIRMABLE_SOURCE_STATUSES = {'pending', 'disputed'}
# 终态：已确认 / 已付款，禁止再修改
_TERMINAL_CONFIRMATION_STATUSES = {'confirmed'}


async def _resolve_operator_name(db: AsyncSession, operator_id: int) -> Optional[str]:
    """根据 operator_id 解析操作人昵称（可选，失败不阻断主流程）。"""
    if not operator_id:
        return None
    try:
        user = await db.scalar(
            select(SysUser).where(SysUser.user_id == operator_id)
        )
        if not user:
            return None
        return user.nick_name or user.user_name
    except Exception as exc:
        logger.warning(f'[SupplierClaimService] 解析操作人姓名失败 operator_id={operator_id}: {exc}')
        return None


async def _create_payment_request(
    db: AsyncSession,
    statement: ReconciliationStatement,
) -> Optional[int]:
    """
    在同一事务内为已确认的对账单生成 PaymentRequest。

    Notes:
        - payable_amount = total_received_value + total_logistics_cost（Requirement 5.1）
          statement.total_amount 在 generate_statements 中已按此公式赋值
        - 单个对账单仅生成一份付款申请（DO 层 statement_id 唯一约束）
        - 若已存在则直接返回已有 ID，保证幂等
        - 内联实现以保持与 confirm_statement 的事务原子性；
          独立调用场景请使用 PaymentService.create_payment_request
    """
    existing = await db.scalar(
        select(PaymentRequest).where(PaymentRequest.statement_id == statement.id)
    )
    if existing:
        return existing.id

    # 应付金额 = 实际收到总价值 + 物流总费用（Requirement 5.1）
    # statement.total_amount 在 generate_statements 中已按此公式计算：
    #   total_amount = total_received_value + total_logistics_cost
    payable = statement.total_amount if statement.total_amount is not None else Decimal('0')
    pr = PaymentRequest(
        statement_id=statement.id,
        supplier_id=statement.supplier_id,
        statement_no=statement.statement_no,
        payable_amount=payable,
        paid_amount=Decimal('0'),
        payment_status='pending_payment',
    )
    db.add(pr)
    await db.flush()
    return pr.id


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SupplierClaimService:
    """供应商对账确认服务。"""

    @staticmethod
    async def confirm_statement(
        db: AsyncSession,
        statement_id: int,
        operator_id: int,
    ) -> dict:
        """
        供应商主动确认对账单。

        原子完成：
            1. confirmation_status → 'confirmed'
            2. status → 'confirmed'（与确认状态保持一致）
            3. 记录 confirmed_at（精确到秒）/ confirmed_by
            4. 创建 ConfirmationHistory（action=confirm）
            5. 触发 PaymentRequest 生成（无则新建，已存在则复用）

        Args:
            db: AsyncSession，事务由本方法管理
            statement_id: 对账单 ID
            operator_id: 操作人（供应商账号对应的 user_id）；由 token 解析得到，
                调用方必须传入真实用户 ID，禁止传 0/None 以避免自动确认绕过审计

        Returns:
            ``{success, message, statement_id, payment_request_id, history_id}``

        Raises:
            ValueError: 当 operator_id 缺失（违反"必须供应商主动操作"）或
                状态不允许确认时
        """
        if not operator_id:
            raise ValueError('confirm_statement 必须由供应商主动操作，operator_id 不能为空')

        stmt = await db.scalar(
            select(ReconciliationStatement).where(ReconciliationStatement.id == statement_id)
        )
        if not stmt:
            return {
                'success': False,
                'message': f'对账单 {statement_id} 不存在',
                'statement_id': statement_id,
                'payment_request_id': None,
                'history_id': None,
            }

        if stmt.confirmation_status in _TERMINAL_CONFIRMATION_STATUSES:
            return {
                'success': False,
                'message': f'对账单 {stmt.statement_no} 已确认，禁止重复确认',
                'statement_id': stmt.id,
                'payment_request_id': None,
                'history_id': None,
            }
        if stmt.confirmation_status not in _CONFIRMABLE_SOURCE_STATUSES:
            return {
                'success': False,
                'message': f'对账单当前确认状态为 {stmt.confirmation_status}，不允许执行确认操作',
                'statement_id': stmt.id,
                'payment_request_id': None,
                'history_id': None,
            }

        operator_name = await _resolve_operator_name(db, operator_id)
        now = datetime.now()

        # —— 原子事务：状态更新 + 历史记录 + 付款申请 ——————————————————————
        try:
            stmt.confirmation_status = 'confirmed'
            stmt.status = 'confirmed'
            stmt.confirmed_at = now
            stmt.confirmed_by = operator_id
            stmt.updated_at = now

            history = ConfirmationHistory(
                statement_id=stmt.id,
                action='confirm',
                operator_id=operator_id,
                operator_name=operator_name,
                remark=None,
                created_at=now,
            )
            db.add(history)
            await db.flush()

            payment_request_id = await _create_payment_request(db, stmt)

            # 审计日志：供应商确认对账单（Requirement 8.1 / Property 5）
            await ReconciliationAuditService.log_action(
                db=db,
                entity_type=ENTITY_TYPE_STATEMENT,
                entity_id=stmt.id,
                action=ACTION_CONFIRM,
                operator_id=operator_id,
                operator_name=operator_name,
                detail={
                    'statement_no': stmt.statement_no,
                    'supplier_id': stmt.supplier_id,
                    'history_id': history.id,
                    'payment_request_id': payment_request_id,
                    'confirmed_at': now.isoformat(),
                },
            )

            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error(
                f'[SupplierClaimService] 确认对账单失败 statement_id={statement_id} '
                f'operator_id={operator_id}: {exc}'
            )
            raise

        logger.info(
            f'[SupplierClaimService] 供应商确认对账单成功 statement_no={stmt.statement_no} '
            f'operator_id={operator_id} payment_request_id={payment_request_id}'
        )
        return {
            'success': True,
            'message': '对账单已确认',
            'statement_id': stmt.id,
            'payment_request_id': payment_request_id,
            'history_id': history.id,
        }

    @staticmethod
    async def dispute_statement(
        db: AsyncSession,
        statement_id: int,
        operator_id: int,
        reason: str,
    ) -> dict:
        """
        供应商对对账单提出争议。

        原子完成：
            1. confirmation_status → 'disputed'
            2. status → 'disputed'
            3. dispute_reason 写入争议说明
            4. 创建 ConfirmationHistory（action=dispute, remark=reason）

        Args:
            db: AsyncSession
            statement_id: 对账单 ID
            operator_id: 操作人 user_id（必须，禁止匿名/自动）
            reason: 争议说明（必填）

        Returns:
            ``{success, message, statement_id, history_id}``
        """
        if not operator_id:
            raise ValueError('dispute_statement 必须由供应商主动操作，operator_id 不能为空')
        if not reason or not reason.strip():
            raise ValueError('争议说明不能为空')

        stmt = await db.scalar(
            select(ReconciliationStatement).where(ReconciliationStatement.id == statement_id)
        )
        if not stmt:
            return {
                'success': False,
                'message': f'对账单 {statement_id} 不存在',
                'statement_id': statement_id,
                'history_id': None,
            }

        if stmt.confirmation_status in _TERMINAL_CONFIRMATION_STATUSES:
            return {
                'success': False,
                'message': f'对账单 {stmt.statement_no} 已确认，禁止再提出争议',
                'statement_id': stmt.id,
                'history_id': None,
            }

        operator_name = await _resolve_operator_name(db, operator_id)
        now = datetime.now()
        reason = reason.strip()

        # —— 原子事务：状态更新 + 历史记录 ——————————————————————————————
        try:
            stmt.confirmation_status = 'disputed'
            stmt.status = 'disputed'
            stmt.dispute_reason = reason
            stmt.updated_at = now

            history = ConfirmationHistory(
                statement_id=stmt.id,
                action='dispute',
                operator_id=operator_id,
                operator_name=operator_name,
                remark=reason,
                created_at=now,
            )
            db.add(history)
            await db.flush()

            # 审计日志：供应商提出争议（Requirement 8.1）
            await ReconciliationAuditService.log_action(
                db=db,
                entity_type=ENTITY_TYPE_STATEMENT,
                entity_id=stmt.id,
                action=ACTION_REJECT,
                operator_id=operator_id,
                operator_name=operator_name,
                detail={
                    'statement_no': stmt.statement_no,
                    'supplier_id': stmt.supplier_id,
                    'history_id': history.id,
                    'reason': reason,
                    'sub_action': 'dispute',
                },
            )

            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error(
                f'[SupplierClaimService] 提出争议失败 statement_id={statement_id} '
                f'operator_id={operator_id}: {exc}'
            )
            raise

        logger.info(
            f'[SupplierClaimService] 供应商提出争议 statement_no={stmt.statement_no} '
            f'operator_id={operator_id} reason_len={len(reason)}'
        )
        return {
            'success': True,
            'message': '争议已提交',
            'statement_id': stmt.id,
            'history_id': history.id,
        }

    @staticmethod
    async def get_confirmation_history(
        db: AsyncSession,
        statement_id: int,
    ) -> list[ConfirmationHistory]:
        """
        查询对账单的完整确认历史，按时间升序返回。

        覆盖需求 2.7：记录每份对账单的完整确认历史（操作时间、操作人、操作类型）。
        """
        stmt = (
            select(ConfirmationHistory)
            .where(ConfirmationHistory.statement_id == statement_id)
            .order_by(ConfirmationHistory.created_at.asc(), ConfirmationHistory.id.asc())
        )
        rows = (await db.execute(stmt)).scalars().all()
        return list(rows)
