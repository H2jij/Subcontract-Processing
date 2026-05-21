"""
对账系统 — 审计日志 Service
=========================================
覆盖需求 8.1, 8.5, 8.7

职责：
  1. 统一写入对账相关业务的审计日志（``ReconciliationAuditLog``）
  2. 提供查询接口，支持按 entity_type / entity_id / action / operator_id /
     时间范围 / 分页过滤
  3. 强制审计日志的不可变性（Requirement 8.7 / Property 17）：
       - 本服务**禁止暴露** delete / update / 任何修改 / 删除审计日志的接口
       - 提供 ``assert_immutable()`` 与 ``ImmutableAuditLogError`` 给上层
         做主动防御；DAO 层亦不暴露 ``delete_audit_log`` / ``update_audit_log``
         之类的方法

设计约束：
  - 写入采用 ``db.add() + db.flush()``（默认）以加入调用方现有事务；
    若无外层事务可使用 ``autocommit=True`` 让本方法独立提交
  - 所有 entity_type / action 取值均在白名单中校验，避免脏数据
  - 写入失败仅在审计写入本身的异常路径上抛出；对调用方业务流程透明的
    "尽力而为"风格请使用 ``log_action_safe``（捕获异常并记日志）

整合策略（遵循 Requirements 8.1）：
  - 业务侧 Service 在 create / update / confirm / approve / reject /
    export 等"写"动作落库后调用 ``ReconciliationAuditService.log_action``
  - 详细 detail 字段按需构造（如关键字段变更前后值），并保持轻量便于审计查询
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

from loguru import logger
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceException
from module_entrust.entity.do.reconciliation_do import ReconciliationAuditLog


# ---------------------------------------------------------------------------
# 常量与白名单
# ---------------------------------------------------------------------------

# 实体类型白名单（与 design.md / DO 注释一致；payment_evidence 等扩展类型一并支持）
ENTITY_TYPE_STATEMENT = 'statement'
ENTITY_TYPE_ANOMALY = 'anomaly'
ENTITY_TYPE_ADJUSTMENT = 'adjustment'
ENTITY_TYPE_PAYMENT = 'payment'
ENTITY_TYPE_SETTLEMENT = 'settlement'
ENTITY_TYPE_PRODUCTION_ANOMALY = 'production_anomaly'
ENTITY_TYPE_PAYMENT_EVIDENCE = 'payment_evidence'

VALID_ENTITY_TYPES: frozenset[str] = frozenset({
    ENTITY_TYPE_STATEMENT,
    ENTITY_TYPE_ANOMALY,
    ENTITY_TYPE_ADJUSTMENT,
    ENTITY_TYPE_PAYMENT,
    ENTITY_TYPE_SETTLEMENT,
    ENTITY_TYPE_PRODUCTION_ANOMALY,
    ENTITY_TYPE_PAYMENT_EVIDENCE,
})

# 操作类型白名单
ACTION_CREATE = 'create'
ACTION_UPDATE = 'update'
ACTION_CONFIRM = 'confirm'
ACTION_APPROVE = 'approve'
ACTION_REJECT = 'reject'
ACTION_EXPORT = 'export'
ACTION_DELETE = 'delete'  # 仅作为业务侧"删除事件"留痕，禁止用于删除审计日志本身
ACTION_UNAUTHORIZED_ACCESS = 'unauthorized_access'  # 安全事件：未授权访问（Requirement 8.6）

VALID_ACTIONS: frozenset[str] = frozenset({
    ACTION_CREATE,
    ACTION_UPDATE,
    ACTION_CONFIRM,
    ACTION_APPROVE,
    ACTION_REJECT,
    ACTION_EXPORT,
    ACTION_DELETE,
    ACTION_UNAUTHORIZED_ACCESS,
})


# ---------------------------------------------------------------------------
# 审计日志不可变性（Requirement 8.7 / Property 17）
# ---------------------------------------------------------------------------

class ImmutableAuditLogError(ServiceException):
    """
    审计日志不可变约束被违反时抛出。

    审计日志一旦写入便不允许 update / delete；任何调用 ``update_log`` /
    ``delete_log`` / ``modify_log`` 的代码都会得到该异常。
    """

    def __init__(self, message: str = '审计日志不可变，禁止 update/delete 操作') -> None:
        super().__init__(message=message)


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _validate_entity_type(entity_type: str) -> None:
    if entity_type not in VALID_ENTITY_TYPES:
        raise ServiceException(
            message=(
                f'非法的 entity_type: {entity_type}；'
                f'允许值: {sorted(VALID_ENTITY_TYPES)}'
            )
        )


def _validate_action(action: str) -> None:
    if action not in VALID_ACTIONS:
        raise ServiceException(
            message=(
                f'非法的 action: {action}；'
                f'允许值: {sorted(VALID_ACTIONS)}'
            )
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ReconciliationAuditService:
    """对账系统审计日志服务。"""

    # ------------------------------------------------------------------
    # 写入（Requirement 8.1）
    # ------------------------------------------------------------------

    @staticmethod
    async def log_action(
        db: AsyncSession,
        entity_type: str,
        entity_id: int,
        action: str,
        operator_id: int,
        operator_name: Optional[str] = None,
        detail: Optional[Any] = None,
        ip_address: Optional[str] = None,
        autocommit: bool = False,
    ) -> int:
        """
        写入一条审计日志。

        - 默认情况下仅 ``db.add() + db.flush()``，依赖调用方提交事务，
          以保证审计与业务写入在同一事务内原子落库（Requirement 8.1）
        - 可显式指定 ``autocommit=True`` 让本方法独立提交（用于
          脱离主流程的 export/批量等异步动作）

        Args:
            db: AsyncSession
            entity_type: 业务实体类型，必须在 ``VALID_ENTITY_TYPES`` 内
            entity_id: 业务实体主键 ID
            action: 操作类型，必须在 ``VALID_ACTIONS`` 内
            operator_id: 操作人 user_id（必须 > 0；系统级操作请传 0 并显式
                标注 ``operator_name='system'`` 以保留可追溯）
            operator_name: 操作人姓名（可选）
            detail: 操作详情，建议为 dict（前后值、关键字段、上下文等）；
                数据库列为 JSONB，自动序列化
            ip_address: 客户端 IP（可选）
            autocommit: 是否在写入后立即 commit；默认 False，集成到调用方事务

        Returns:
            新建审计日志 ID

        Raises:
            ServiceException: entity_type / action 非法 / entity_id 缺失
        """
        _validate_entity_type(entity_type)
        _validate_action(action)

        if entity_id is None or entity_id <= 0:
            raise ServiceException(message=f'非法的 entity_id: {entity_id}')

        if operator_id is None:
            # 不允许 None；系统级操作显式传 0
            raise ServiceException(message='operator_id 不能为 None')

        log = ReconciliationAuditLog(
            entity_type=entity_type,
            entity_id=int(entity_id),
            action=action,
            operator_id=int(operator_id),
            operator_name=operator_name,
            detail=detail,
            ip_address=ip_address,
            created_at=datetime.now(),
        )
        db.add(log)
        await db.flush()  # 拿到 log.id

        if autocommit:
            try:
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        return log.id

    @staticmethod
    async def log_action_safe(
        db: AsyncSession,
        entity_type: str,
        entity_id: int,
        action: str,
        operator_id: int,
        operator_name: Optional[str] = None,
        detail: Optional[Any] = None,
        ip_address: Optional[str] = None,
        autocommit: bool = False,
    ) -> Optional[int]:
        """
        ``log_action`` 的"尽力而为"包装：所有异常被吞掉并记 error 日志，
        不影响调用方主流程。

        适用场景：审计写入失败时不希望连带破坏业务结果（如导出/通知后置写
        审计）。仍优先建议使用 ``log_action`` 加入主事务以保障可追溯性。
        """
        try:
            return await ReconciliationAuditService.log_action(
                db=db,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                operator_id=operator_id,
                operator_name=operator_name,
                detail=detail,
                ip_address=ip_address,
                autocommit=autocommit,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                '[ReconciliationAuditService] 审计写入失败 entity_type={} '
                'entity_id={} action={} err={}',
                entity_type, entity_id, action, exc,
            )
            return None

    # ------------------------------------------------------------------
    # 不可变保护（Requirement 8.7 / Property 17）
    # ------------------------------------------------------------------

    @staticmethod
    def assert_immutable(operation: str = 'modify') -> None:
        """
        主动拒绝任意 update / delete 调用。

        本服务/DAO 不提供修改或删除审计日志的入口；外部代码若意外调用，
        请抛出 ``ImmutableAuditLogError``。
        """
        raise ImmutableAuditLogError(
            message=f'审计日志不可变，禁止 {operation} 操作（Requirement 8.7）'
        )

    @staticmethod
    async def delete_log(*_args: Any, **_kwargs: Any) -> None:
        """显式占位方法 — 始终拒绝。"""
        ReconciliationAuditService.assert_immutable('delete')

    @staticmethod
    async def update_log(*_args: Any, **_kwargs: Any) -> None:
        """显式占位方法 — 始终拒绝。"""
        ReconciliationAuditService.assert_immutable('update')

    # ------------------------------------------------------------------
    # 查询（Requirement 8.5）
    # ------------------------------------------------------------------

    @staticmethod
    async def query_audit_logs(
        db: AsyncSession,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        filters: Optional[dict] = None,
    ) -> dict:
        """
        查询审计日志。

        支持过滤项（filters dict）：
          - action: str
          - operator_id: int
          - start_time: datetime（含）
          - end_time: datetime（含）
          - page_num: int (≥1，默认 1)
          - page_size: int (1~500，默认 20)

        返回结构（与 ``AuditLogListResponse`` 对齐）：
          ``{
              'total': int,
              'page_num': int,
              'page_size': int,
              'rows': list[ReconciliationAuditLog],
          }``

        Args:
            db: AsyncSession
            entity_type: 实体类型（可选；传入则必须合法）
            entity_id: 实体 ID（可选）
            filters: 其它过滤项与分页参数

        Returns:
            分页结果字典；``rows`` 内为 ORM 对象，便于 controller 层
            通过 ``model_validate`` 转 VO

        Raises:
            ServiceException: entity_type 非法 / 时间范围非法 / 分页参数非法
        """
        f = filters or {}

        if entity_type is not None:
            _validate_entity_type(entity_type)
        action = f.get('action')
        if action is not None:
            _validate_action(action)

        operator_id = f.get('operator_id')
        start_time: Optional[datetime] = f.get('start_time')
        end_time: Optional[datetime] = f.get('end_time')

        if start_time and end_time and start_time > end_time:
            raise ServiceException(message='start_time 不能晚于 end_time')

        page_num = int(f.get('page_num', 1) or 1)
        page_size = int(f.get('page_size', 20) or 20)
        if page_num < 1:
            raise ServiceException(message='page_num 必须 >= 1')
        if page_size < 1 or page_size > 500:
            raise ServiceException(message='page_size 必须在 [1, 500]')

        # 组装过滤条件
        conds = []
        if entity_type is not None:
            conds.append(ReconciliationAuditLog.entity_type == entity_type)
        if entity_id is not None:
            conds.append(ReconciliationAuditLog.entity_id == int(entity_id))
        if action is not None:
            conds.append(ReconciliationAuditLog.action == action)
        if operator_id is not None:
            conds.append(ReconciliationAuditLog.operator_id == int(operator_id))
        if start_time is not None:
            conds.append(ReconciliationAuditLog.created_at >= start_time)
        if end_time is not None:
            conds.append(ReconciliationAuditLog.created_at <= end_time)

        where_clause = and_(*conds) if conds else None

        # total
        count_stmt = select(func.count()).select_from(ReconciliationAuditLog)
        if where_clause is not None:
            count_stmt = count_stmt.where(where_clause)
        total = (await db.execute(count_stmt)).scalar_one()

        # rows
        stmt = select(ReconciliationAuditLog)
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        stmt = (
            stmt.order_by(
                ReconciliationAuditLog.created_at.desc(),
                ReconciliationAuditLog.id.desc(),
            )
            .offset((page_num - 1) * page_size)
            .limit(page_size)
        )
        rows = list((await db.execute(stmt)).scalars().all())

        return {
            'total': int(total or 0),
            'page_num': page_num,
            'page_size': page_size,
            'rows': rows,
        }

    @staticmethod
    async def get_logs_for_entity(
        db: AsyncSession,
        entity_type: str,
        entity_id: int,
        limit: int = 100,
    ) -> list[ReconciliationAuditLog]:
        """
        便捷查询：按实体定位最近 N 条审计日志（默认 100），按 created_at 降序。

        用于审计追溯页面的快速时间线展示，无需分页参数。
        """
        _validate_entity_type(entity_type)
        if entity_id is None or entity_id <= 0:
            raise ServiceException(message=f'非法的 entity_id: {entity_id}')
        if limit < 1 or limit > 1000:
            raise ServiceException(message='limit 必须在 [1, 1000]')

        stmt = (
            select(ReconciliationAuditLog)
            .where(
                and_(
                    ReconciliationAuditLog.entity_type == entity_type,
                    ReconciliationAuditLog.entity_id == int(entity_id),
                )
            )
            .order_by(
                ReconciliationAuditLog.created_at.desc(),
                ReconciliationAuditLog.id.desc(),
            )
            .limit(limit)
        )
        return list((await db.execute(stmt)).scalars().all())


__all__ = [
    'ReconciliationAuditService',
    'ImmutableAuditLogError',
    # entity types
    'ENTITY_TYPE_STATEMENT',
    'ENTITY_TYPE_ANOMALY',
    'ENTITY_TYPE_ADJUSTMENT',
    'ENTITY_TYPE_PAYMENT',
    'ENTITY_TYPE_SETTLEMENT',
    'ENTITY_TYPE_PRODUCTION_ANOMALY',
    'ENTITY_TYPE_PAYMENT_EVIDENCE',
    'VALID_ENTITY_TYPES',
    # actions
    'ACTION_CREATE',
    'ACTION_UPDATE',
    'ACTION_CONFIRM',
    'ACTION_APPROVE',
    'ACTION_REJECT',
    'ACTION_EXPORT',
    'ACTION_DELETE',
    'VALID_ACTIONS',
]
