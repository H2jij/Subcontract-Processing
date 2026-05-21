"""
对账系统 — 通知与超时 Service
=========================================
职责（Requirements 2.1, 2.5, 2.6）：
  1. 对账单生成后向供应商发送对账通知
  2. pending 状态超过 7 个自然日时发送催办
  3. pending 状态超过 15 个自然日时标记超时并通知财务
  4. 提供批量扫描方法供调度器（如 APScheduler）每日调用

设计要点：
  - 抽象 NotificationChannel：默认 LogNotificationChannel（写日志），
    可通过 set_channel() 注入真实渠道（邮件/站内信/WS），便于后续接入。
  - 永远不通过本服务自动将 confirmation_status 置为 confirmed
    （对账确认必须由供应商主动操作，详见 Property 5）。
  - mark_timeout 仅设置 status='timeout' 与 timeout_at，
    不修改 confirmation_status。
  - 通过 ReconciliationAuditLog 留痕，扫描方法据此实现日级幂等，
    避免一日内重复发送同一类提醒。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Iterable, Optional

from loguru import logger
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceException
from module_admin.entity.do.user_do import SysUser
from module_entrust.entity.do.entrust_do import EntrustSupplier
from module_entrust.entity.do.reconciliation_do import (
    Anomaly,
    ReconciliationAuditLog,
    ReconciliationStatement,
)


# ---------------------------------------------------------------------------
# 通知渠道抽象
# ---------------------------------------------------------------------------

class NotificationChannel(ABC):
    """
    通知渠道抽象基类。

    实现类需要实现异步 send 方法。已经预留以下扩展点：
      - LogNotificationChannel: 默认实现，写入 loguru 日志
      - 邮件渠道（EmailSender 包装）
      - 站内信 / WebSocket 推送
      - 短信
    """

    @abstractmethod
    async def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        metadata: Optional[dict] = None,
    ) -> bool:
        """发送一条通知，返回是否成功。"""


class LogNotificationChannel(NotificationChannel):
    """默认通知渠道：仅写入日志，便于本地开发与默认运行。"""

    async def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        metadata: Optional[dict] = None,
    ) -> bool:
        logger.info(
            '[ReconciliationNotification] to={} subject={} body={} meta={}',
            recipient,
            subject,
            body,
            metadata or {},
        )
        return True


# ---------------------------------------------------------------------------
# 审计日志辅助：记录通知动作并支持幂等检测
# ---------------------------------------------------------------------------

# 审计日志中使用的 action 取值
_ACTION_NOTIFY_INITIAL = 'notify_initial'
_ACTION_REMINDER_SENT = 'reminder_sent'
_ACTION_TIMEOUT_MARKED = 'timeout_marked'
_ACTION_ANOMALY_NOTIFIED = 'anomaly_notified'

_AUDIT_ENTITY_TYPE = 'statement'
_AUDIT_ENTITY_TYPE_ANOMALY = 'anomaly'


async def _has_action_today(
    db: AsyncSession,
    statement_id: int,
    action: str,
    now: Optional[datetime] = None,
) -> bool:
    """检查当日是否已经为对账单写过同类型审计日志（按自然日）。"""
    now = now or datetime.now()
    today_start = datetime.combine(now.date(), datetime.min.time())
    today_end = datetime.combine(now.date(), datetime.max.time())
    stmt = select(ReconciliationAuditLog.id).where(
        and_(
            ReconciliationAuditLog.entity_type == _AUDIT_ENTITY_TYPE,
            ReconciliationAuditLog.entity_id == statement_id,
            ReconciliationAuditLog.action == action,
            ReconciliationAuditLog.created_at >= today_start,
            ReconciliationAuditLog.created_at <= today_end,
        )
    ).limit(1)
    return (await db.execute(stmt)).first() is not None


async def _has_action_ever(
    db: AsyncSession, statement_id: int, action: str
) -> bool:
    """检查对账单是否曾经写过该类型审计日志。"""
    stmt = select(ReconciliationAuditLog.id).where(
        and_(
            ReconciliationAuditLog.entity_type == _AUDIT_ENTITY_TYPE,
            ReconciliationAuditLog.entity_id == statement_id,
            ReconciliationAuditLog.action == action,
        )
    ).limit(1)
    return (await db.execute(stmt)).first() is not None


def _audit_log(
    statement_id: int,
    action: str,
    operator_id: int = 0,
    detail: Optional[dict] = None,
) -> ReconciliationAuditLog:
    """构造一条审计日志记录（不直接写库，由调用方 db.add）。"""
    return ReconciliationAuditLog(
        entity_type=_AUDIT_ENTITY_TYPE,
        entity_id=statement_id,
        action=action,
        operator_id=operator_id,
        operator_name='system',
        detail=detail,
    )


# ---------------------------------------------------------------------------
# 收件人解析
# ---------------------------------------------------------------------------

async def _resolve_supplier_recipient(
    db: AsyncSession, supplier_id: int
) -> tuple[str, Optional[EntrustSupplier]]:
    """
    解析供应商的通知地址。

    优先级：contact_email > 关联的系统账号 user_name > 供应商名称占位 > supplier:{id}
    """
    sup = await db.scalar(
        select(EntrustSupplier).where(EntrustSupplier.id == supplier_id)
    )
    if not sup:
        return f'supplier:{supplier_id}', None

    if sup.contact_email:
        return sup.contact_email, sup
    if sup.user_id:
        user_name = await db.scalar(
            select(SysUser.user_name).where(SysUser.user_id == sup.user_id)
        )
        if user_name:
            return f'user:{user_name}', sup
    if sup.name:
        return f'supplier:{sup.name}', sup
    return f'supplier:{supplier_id}', sup


_FINANCE_ROLE_KEY = 'finance'


async def _resolve_finance_recipients(db: AsyncSession) -> list[str]:
    """
    解析财务通知收件人列表。

    实现策略：占位符返回固定的 'role:finance' 收件人，
    交由通知渠道（如邮件/站内信）按角色 fan-out。
    若后续接入真实渠道，可在此扩展为按 role_key='finance' 的真实用户列表查询。
    """
    return [f'role:{_FINANCE_ROLE_KEY}']


# ---------------------------------------------------------------------------
# 主服务
# ---------------------------------------------------------------------------

class ReconciliationNotificationService:
    """对账单通知与超时管理服务。"""

    # 默认通知渠道：写日志。运行时可通过 set_channel() 替换。
    _channel: NotificationChannel = LogNotificationChannel()

    # 业务窗口（自然日）
    REMINDER_THRESHOLD_DAYS = 7
    TIMEOUT_THRESHOLD_DAYS = 15

    # ------------------------------------------------------------------
    # 渠道注入
    # ------------------------------------------------------------------

    @classmethod
    def set_channel(cls, channel: NotificationChannel) -> None:
        """注入真实通知渠道（邮件/WebSocket/短信等）。"""
        cls._channel = channel

    @classmethod
    def get_channel(cls) -> NotificationChannel:
        return cls._channel

    # ------------------------------------------------------------------
    # 内部：通知基线时间
    # ------------------------------------------------------------------

    @staticmethod
    def _baseline(stmt: ReconciliationStatement) -> datetime:
        """
        计算对账单 pending 起算时间。

        优先使用 notified_at（首次通知时间），否则回落到 created_at，
        若两者均为空则使用当前时间（极端兜底）。
        """
        return stmt.notified_at or stmt.created_at or datetime.now()

    # ------------------------------------------------------------------
    # 1. 对账单生成后通知 (Requirement 2.1)
    # ------------------------------------------------------------------

    @classmethod
    async def send_reconciliation_notification(
        cls,
        db: AsyncSession,
        statement_id: int,
        operator_id: int = 0,
    ) -> bool:
        """
        发送对账单生成通知给供应商。

        - 设置 ReconciliationStatement.notified_at = now（仅在首次通知时设置；
          后续重发也会刷新该时间，从而以最近一次通知为窗口起点）
        - 写入审计日志 action='notify_initial'

        Returns:
            True 表示渠道发送成功；False 表示渠道返回失败。
        """
        statement = await db.scalar(
            select(ReconciliationStatement).where(
                ReconciliationStatement.id == statement_id
            )
        )
        if not statement:
            raise ServiceException(message=f'对账单 {statement_id} 不存在')

        recipient, supplier = await _resolve_supplier_recipient(
            db, statement.supplier_id
        )
        subject = f'[对账通知] 对账单 {statement.statement_no} 待您确认'
        body = (
            f'您好{supplier.name if supplier else ""}：\n'
            f'对账单 {statement.statement_no} 已生成，对账周期 '
            f'{statement.period_start} 至 {statement.period_end}，'
            f'汇总金额 {statement.total_amount}。\n'
            f'请在 {cls.TIMEOUT_THRESHOLD_DAYS} 个自然日内登录系统进行确认或提出争议。'
        )
        metadata = {
            'statement_id': statement.id,
            'statement_no': statement.statement_no,
            'supplier_id': statement.supplier_id,
            'period_start': str(statement.period_start),
            'period_end': str(statement.period_end),
            'total_amount': str(statement.total_amount),
        }

        ok = await cls._channel.send(recipient, subject, body, metadata)

        now = datetime.now()
        statement.notified_at = now
        db.add(_audit_log(
            statement_id=statement.id,
            action=_ACTION_NOTIFY_INITIAL,
            operator_id=operator_id,
            detail={'recipient': recipient, 'success': ok},
        ))
        await db.flush()
        await db.commit()

        logger.info(
            '[ReconciliationNotificationService] 对账通知已发送 '
            'statement_id={} statement_no={} recipient={} success={}',
            statement.id, statement.statement_no, recipient, ok,
        )
        return ok

    # ------------------------------------------------------------------
    # 2. 催办 (Requirement 2.5)
    # ------------------------------------------------------------------

    @classmethod
    async def send_reminder(
        cls,
        db: AsyncSession,
        statement_id: int,
        operator_id: int = 0,
        force: bool = False,
    ) -> bool:
        """
        发送催办通知。

        - 仅当 confirmation_status == 'pending' 且距离 notified_at（或 created_at）
          已超过 REMINDER_THRESHOLD_DAYS（7天）时才会发送。
        - 当日已发送过 reminder 则跳过（force=True 可强制再次发送）。

        Returns:
            True 表示已发送；False 表示未满足发送条件或当日已发送。
        """
        statement = await db.scalar(
            select(ReconciliationStatement).where(
                ReconciliationStatement.id == statement_id
            )
        )
        if not statement:
            raise ServiceException(message=f'对账单 {statement_id} 不存在')

        if statement.confirmation_status != 'pending':
            logger.debug(
                '[ReconciliationNotificationService] '
                '对账单 {} 非 pending 状态，跳过催办',
                statement_id,
            )
            return False

        now = datetime.now()
        baseline = cls._baseline(statement)
        elapsed = now - baseline
        if elapsed < timedelta(days=cls.REMINDER_THRESHOLD_DAYS):
            logger.debug(
                '[ReconciliationNotificationService] '
                '对账单 {} 仅 pending {}，未达催办阈值',
                statement_id, elapsed,
            )
            return False

        if not force and await _has_action_today(
            db, statement_id, _ACTION_REMINDER_SENT, now
        ):
            logger.debug(
                '[ReconciliationNotificationService] '
                '对账单 {} 当日已发送催办，跳过',
                statement_id,
            )
            return False

        recipient, supplier = await _resolve_supplier_recipient(
            db, statement.supplier_id
        )
        subject = f'[催办] 对账单 {statement.statement_no} 仍待确认'
        body = (
            f'您好{supplier.name if supplier else ""}：\n'
            f'对账单 {statement.statement_no} 已发送 '
            f'{elapsed.days} 个自然日仍未确认，请尽快登录系统处理。\n'
            f'若 {cls.TIMEOUT_THRESHOLD_DAYS} 个自然日内仍未响应，'
            f'系统将自动标记为超时未确认。'
        )
        metadata = {
            'statement_id': statement.id,
            'statement_no': statement.statement_no,
            'pending_days': elapsed.days,
            'kind': 'reminder',
        }

        ok = await cls._channel.send(recipient, subject, body, metadata)

        db.add(_audit_log(
            statement_id=statement.id,
            action=_ACTION_REMINDER_SENT,
            operator_id=operator_id,
            detail={
                'recipient': recipient,
                'success': ok,
                'pending_days': elapsed.days,
            },
        ))
        await db.flush()
        await db.commit()

        logger.info(
            '[ReconciliationNotificationService] 已发送催办 '
            'statement_id={} pending_days={} recipient={} success={}',
            statement.id, elapsed.days, recipient, ok,
        )
        return ok

    # ------------------------------------------------------------------
    # 3. 超时标记 (Requirement 2.6)
    # ------------------------------------------------------------------

    @classmethod
    async def mark_timeout(
        cls,
        db: AsyncSession,
        statement_id: int,
        operator_id: int = 0,
    ) -> bool:
        """
        将超过 TIMEOUT_THRESHOLD_DAYS（15天）未响应的对账单标记为超时
        并通知财务。

        - 仅修改 status='timeout' 与 timeout_at；
          confirmation_status 保持 'pending'（Property 5：不得自动确认）。
        - 已标记过超时的对账单不会重复处理。

        Returns:
            True 表示完成超时标记；False 表示未满足条件或已标记过。
        """
        statement = await db.scalar(
            select(ReconciliationStatement).where(
                ReconciliationStatement.id == statement_id
            )
        )
        if not statement:
            raise ServiceException(message=f'对账单 {statement_id} 不存在')

        # 已经处于终态或已超时，跳过
        if statement.status in ('confirmed', 'paid', 'timeout'):
            logger.debug(
                '[ReconciliationNotificationService] '
                '对账单 {} 状态={} 无需超时处理',
                statement_id, statement.status,
            )
            return False

        if statement.confirmation_status != 'pending':
            logger.debug(
                '[ReconciliationNotificationService] '
                '对账单 {} 已非 pending 确认状态，跳过超时标记',
                statement_id,
            )
            return False

        now = datetime.now()
        baseline = cls._baseline(statement)
        elapsed = now - baseline
        if elapsed < timedelta(days=cls.TIMEOUT_THRESHOLD_DAYS):
            logger.debug(
                '[ReconciliationNotificationService] '
                '对账单 {} pending {} 未到超时阈值',
                statement_id, elapsed,
            )
            return False

        # 更新对账单状态
        statement.status = 'timeout'
        statement.timeout_at = now

        # 通知财务
        finance_recipients = await _resolve_finance_recipients(db)
        subject = (
            f'[超时未确认] 对账单 {statement.statement_no} '
            f'已超过 {cls.TIMEOUT_THRESHOLD_DAYS} 天未响应'
        )
        body = (
            f'对账单 {statement.statement_no}（供应商ID {statement.supplier_id}）'
            f'自 {baseline:%Y-%m-%d} 起共 {elapsed.days} 个自然日未确认，'
            f'已标记为超时。请财务人员介入处理。'
        )
        metadata = {
            'statement_id': statement.id,
            'statement_no': statement.statement_no,
            'supplier_id': statement.supplier_id,
            'pending_days': elapsed.days,
            'kind': 'timeout',
        }

        results: list[tuple[str, bool]] = []
        for recipient in finance_recipients:
            ok = await cls._channel.send(recipient, subject, body, metadata)
            results.append((recipient, ok))

        db.add(_audit_log(
            statement_id=statement.id,
            action=_ACTION_TIMEOUT_MARKED,
            operator_id=operator_id,
            detail={
                'recipients': [r for r, _ in results],
                'success_count': sum(1 for _, ok in results if ok),
                'pending_days': elapsed.days,
            },
        ))
        await db.flush()
        await db.commit()

        logger.info(
            '[ReconciliationNotificationService] 已标记超时 '
            'statement_id={} pending_days={} notified={}',
            statement.id, elapsed.days, len(results),
        )
        return True

    # ------------------------------------------------------------------
    # 4. 调度器入口：批量扫描
    # ------------------------------------------------------------------

    @classmethod
    async def _select_pending_statements(
        cls,
        db: AsyncSession,
        max_baseline: datetime,
    ) -> list[ReconciliationStatement]:
        """
        查询所有 confirmation_status='pending' 且 status 仍可推进
        （非 confirmed/paid/timeout）的对账单，
        且其基线时间（notified_at 或 created_at）早于 max_baseline。
        """
        stmt = select(ReconciliationStatement).where(
            ReconciliationStatement.confirmation_status == 'pending',
            ReconciliationStatement.status.notin_(
                ('confirmed', 'paid', 'timeout')
            ),
        )
        rows = (await db.execute(stmt)).scalars().all()

        result: list[ReconciliationStatement] = []
        for s in rows:
            baseline = cls._baseline(s)
            if baseline <= max_baseline:
                result.append(s)
        return result

    @classmethod
    async def scan_pending_for_reminders(
        cls,
        db: AsyncSession,
        operator_id: int = 0,
    ) -> dict:
        """
        定时扫描 pending 超过 7 天但不足 15 天的对账单并发送催办。

        Returns:
            {'scanned': N, 'sent': N, 'skipped': N, 'errors': N}
        """
        now = datetime.now()
        reminder_cutoff = now - timedelta(days=cls.REMINDER_THRESHOLD_DAYS)
        timeout_cutoff = now - timedelta(days=cls.TIMEOUT_THRESHOLD_DAYS)

        candidates = await cls._select_pending_statements(db, reminder_cutoff)

        sent = 0
        skipped = 0
        errors = 0
        for s in candidates:
            baseline = cls._baseline(s)
            # 已经达到超时阈值的不再发催办，由 timeout 扫描处理
            if baseline <= timeout_cutoff:
                skipped += 1
                continue
            try:
                ok = await cls.send_reminder(db, s.id, operator_id=operator_id)
                if ok:
                    sent += 1
                else:
                    skipped += 1
            except Exception as e:  # noqa: BLE001
                errors += 1
                logger.error(
                    '[ReconciliationNotificationService] 催办失败 '
                    'statement_id={} err={}', s.id, e,
                )

        summary = {
            'scanned': len(candidates),
            'sent': sent,
            'skipped': skipped,
            'errors': errors,
        }
        logger.info(
            '[ReconciliationNotificationService] 催办扫描完成 {}',
            summary,
        )
        return summary

    @classmethod
    async def scan_pending_for_timeout(
        cls,
        db: AsyncSession,
        operator_id: int = 0,
    ) -> dict:
        """
        定时扫描 pending 超过 15 天的对账单，标记超时并通知财务。

        Returns:
            {'scanned': N, 'marked': N, 'skipped': N, 'errors': N}
        """
        now = datetime.now()
        timeout_cutoff = now - timedelta(days=cls.TIMEOUT_THRESHOLD_DAYS)

        candidates = await cls._select_pending_statements(db, timeout_cutoff)

        marked = 0
        skipped = 0
        errors = 0
        for s in candidates:
            try:
                ok = await cls.mark_timeout(db, s.id, operator_id=operator_id)
                if ok:
                    marked += 1
                else:
                    skipped += 1
            except Exception as e:  # noqa: BLE001
                errors += 1
                logger.error(
                    '[ReconciliationNotificationService] 超时标记失败 '
                    'statement_id={} err={}', s.id, e,
                )

        summary = {
            'scanned': len(candidates),
            'marked': marked,
            'skipped': skipped,
            'errors': errors,
        }
        logger.info(
            '[ReconciliationNotificationService] 超时扫描完成 {}',
            summary,
        )
        return summary

    # ------------------------------------------------------------------
    # 5. 异常通知财务 (Requirement 3.8)
    # ------------------------------------------------------------------

    @classmethod
    async def notify_finance_of_anomaly(
        cls,
        db: AsyncSession,
        anomaly: Anomaly,
        operator_id: int = 0,
    ) -> bool:
        """
        异常创建后通知财务人员。

        - 通过 _resolve_finance_recipients 解析财务收件人，并向每位发送一条通知
        - 写入审计日志（entity_type='anomaly', action='anomaly_notified'）
        - 不修改异常本身的字段；调用方持有事务时本方法会 flush，但不 commit，
          以便与异常的创建保持在同一事务中

        Args:
            db: AsyncSession，由调用方控制事务边界
            anomaly: 已 flush 拿到 id 的 Anomaly ORM 实例
            operator_id: 操作人ID（系统检测时通常传 0）

        Returns:
            True 表示至少向一位财务收件人成功发送；False 表示全部失败
        """
        statement = await db.scalar(
            select(ReconciliationStatement).where(
                ReconciliationStatement.id == anomaly.statement_id
            )
        )
        statement_no = statement.statement_no if statement else f'#{anomaly.statement_id}'

        recipients = await _resolve_finance_recipients(db)
        subject = (
            f'[对账异常] 对账单 {statement_no} 检测到 '
            f'{anomaly.anomaly_type} 异常（{anomaly.severity}）'
        )
        body = (
            f'对账单 {statement_no} 在比对供应商账单时发现异常：\n'
            f'  类型: {anomaly.anomaly_type}\n'
            f'  严重程度: {anomaly.severity}\n'
            f'  差异金额: {anomaly.diff_amount}\n'
            f'  描述: {anomaly.description or ""}\n'
            f'请及时介入处理。'
        )
        metadata = {
            'anomaly_id': anomaly.id,
            'statement_id': anomaly.statement_id,
            'statement_no': statement_no,
            'anomaly_type': anomaly.anomaly_type,
            'severity': anomaly.severity,
            'diff_amount': str(anomaly.diff_amount) if anomaly.diff_amount is not None else None,
            'kind': 'anomaly',
        }

        results: list[tuple[str, bool]] = []
        for recipient in recipients:
            try:
                ok = await cls._channel.send(recipient, subject, body, metadata)
            except Exception as e:  # noqa: BLE001
                logger.error(
                    '[ReconciliationNotificationService] 异常通知发送失败 '
                    'anomaly_id={} recipient={} err={}',
                    anomaly.id, recipient, e,
                )
                ok = False
            results.append((recipient, ok))

        db.add(ReconciliationAuditLog(
            entity_type=_AUDIT_ENTITY_TYPE_ANOMALY,
            entity_id=anomaly.id,
            action=_ACTION_ANOMALY_NOTIFIED,
            operator_id=operator_id,
            operator_name='system',
            detail={
                'recipients': [r for r, _ in results],
                'success_count': sum(1 for _, ok in results if ok),
                'anomaly_type': anomaly.anomaly_type,
                'severity': anomaly.severity,
            },
        ))
        await db.flush()

        any_ok = any(ok for _, ok in results)
        logger.info(
            '[ReconciliationNotificationService] 异常已通知财务 '
            'anomaly_id={} type={} severity={} notified={} any_ok={}',
            anomaly.id, anomaly.anomaly_type, anomaly.severity,
            len(results), any_ok,
        )
        return any_ok


__all__ = [
    'NotificationChannel',
    'LogNotificationChannel',
    'ReconciliationNotificationService',
]
