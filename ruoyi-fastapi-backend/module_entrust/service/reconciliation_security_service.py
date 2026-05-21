"""
对账系统 — 权限与数据安全 Service
=========================================
覆盖需求 8.2, 8.3, 8.4, 8.6

职责：
  1. 基于角色的访问控制（RBAC）— 权限检查装饰器/工具函数
     (Requirement 8.2)
  2. 对账单状态守卫 — confirmed/paid 状态禁止修改
     (Requirement 8.3 / Property 4)
  3. 未授权访问拒绝并记录安全事件
     (Requirement 8.6)
  4. 数据回滚功能 — 仅 24 小时内，需管理员审批
     (Requirement 8.4)

设计约束：
  - 遵循现有 RuoYi-style RBAC 模式（CheckRoleInterfaceAuth / role_key）
  - 服务层守卫，供 controller 层调用
  - 安全事件通过 ReconciliationAuditService.log_action 记录
  - 轻量实现，不引入额外中间件
"""
from __future__ import annotations

from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Optional, Sequence

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import PermissionException, ServiceException
from module_entrust.entity.do.reconciliation_do import (
    ReconciliationAuditLog,
    ReconciliationStatement,
)
from module_entrust.service.reconciliation_audit_service import (
    ACTION_DELETE,
    ENTITY_TYPE_STATEMENT,
    ReconciliationAuditService,
    VALID_ENTITY_TYPES,
)


# ---------------------------------------------------------------------------
# 角色常量
# ---------------------------------------------------------------------------

ROLE_FINANCE_STAFF = 'finance_staff'
ROLE_FINANCE_MANAGER = 'finance_manager'
ROLE_FINANCE_DIRECTOR = 'finance_director'
ROLE_SUPPLIER = 'supplier'
ROLE_ADMIN = 'admin'

# 所有对账系统相关角色
RECONCILIATION_ROLES: frozenset[str] = frozenset({
    ROLE_FINANCE_STAFF,
    ROLE_FINANCE_MANAGER,
    ROLE_FINANCE_DIRECTOR,
    ROLE_SUPPLIER,
    ROLE_ADMIN,
})

# 不可修改的对账单状态（Requirement 8.3 / Property 4）
IMMUTABLE_STATUSES: frozenset[str] = frozenset({'confirmed', 'paid'})

# 数据回滚时间窗口（Requirement 8.4）
ROLLBACK_WINDOW_HOURS: int = 24


# ---------------------------------------------------------------------------
# 角色权限检查（Requirement 8.2）
# ---------------------------------------------------------------------------

class ReconciliationSecurityService:
    """对账系统权限与数据安全服务。"""

    # ------------------------------------------------------------------
    # 角色权限检查（Requirement 8.2）
    # ------------------------------------------------------------------

    @staticmethod
    def check_role_access(
        user_roles: list[str],
        allowed_roles: Sequence[str],
        operator_id: int = 0,
        operator_name: Optional[str] = None,
        resource_description: str = '',
    ) -> bool:
        """
        检查用户角色是否在允许的角色列表中。

        admin 角色拥有所有权限（超级管理员）。

        Args:
            user_roles: 当前用户拥有的角色 key 列表
            allowed_roles: 允许访问的角色列表
            operator_id: 操作人 ID（用于安全事件记录）
            operator_name: 操作人姓名
            resource_description: 资源描述（用于日志）

        Returns:
            True 表示有权限

        Raises:
            PermissionException: 无权限时抛出
        """
        # admin 角色拥有所有权限
        if ROLE_ADMIN in user_roles:
            return True

        # 检查是否有任一允许角色
        if any(role in allowed_roles for role in user_roles):
            return True

        # 无权限 — 记录日志并拒绝
        logger.warning(
            '[ReconciliationSecurity] 权限拒绝: operator_id={} roles={} '
            'required={} resource={}',
            operator_id, user_roles, list(allowed_roles), resource_description,
        )
        raise PermissionException(
            message=(
                f'无权访问对账数据：需要角色 {list(allowed_roles)} 之一，'
                f'当前角色 {user_roles}'
            )
        )

    @staticmethod
    async def check_role_access_and_log(
        db: AsyncSession,
        user_roles: list[str],
        allowed_roles: Sequence[str],
        operator_id: int,
        operator_name: Optional[str] = None,
        entity_type: str = ENTITY_TYPE_STATEMENT,
        entity_id: int = 0,
        resource_description: str = '',
        ip_address: Optional[str] = None,
    ) -> bool:
        """
        检查角色权限，未授权时记录安全事件（Requirement 8.6）。

        与 check_role_access 相同逻辑，但在拒绝时额外写入审计日志
        记录未授权访问事件。

        Args:
            db: AsyncSession（用于写审计日志）
            user_roles: 当前用户角色列表
            allowed_roles: 允许的角色列表
            operator_id: 操作人 ID
            operator_name: 操作人姓名
            entity_type: 被访问的实体类型
            entity_id: 被访问的实体 ID（0 表示列表级访问）
            resource_description: 资源描述
            ip_address: 客户端 IP

        Returns:
            True 表示有权限

        Raises:
            PermissionException: 无权限时抛出（安全事件已记录）
        """
        # admin 角色拥有所有权限
        if ROLE_ADMIN in user_roles:
            return True

        # 检查是否有任一允许角色
        if any(role in allowed_roles for role in user_roles):
            return True

        # 无权限 — 记录安全事件（Requirement 8.6）
        await ReconciliationSecurityService._log_unauthorized_access(
            db=db,
            operator_id=operator_id,
            operator_name=operator_name,
            entity_type=entity_type,
            entity_id=entity_id,
            user_roles=user_roles,
            required_roles=list(allowed_roles),
            resource_description=resource_description,
            ip_address=ip_address,
        )

        raise PermissionException(
            message=(
                f'无权访问对账数据：需要角色 {list(allowed_roles)} 之一，'
                f'当前角色 {user_roles}'
            )
        )

    # ------------------------------------------------------------------
    # 对账单状态守卫（Requirement 8.3 / Property 4）
    # ------------------------------------------------------------------

    @staticmethod
    def assert_statement_modifiable(statement: ReconciliationStatement) -> None:
        """
        校验对账单是否允许修改。

        confirmed/paid 状态的对账单禁止任何修改操作（数据不可变）。
        仅 pending 状态允许修改。

        Args:
            statement: 对账单 ORM 对象

        Raises:
            ServiceException: 状态为 confirmed/paid 时抛出 (HTTP 409 Conflict)
        """
        if statement.status in IMMUTABLE_STATUSES:
            raise ServiceException(
                message=(
                    f'对账单 {statement.statement_no} 当前状态为 '
                    f'"{statement.status}"，已确认/已付款的对账单禁止修改'
                )
            )

    @staticmethod
    async def assert_statement_modifiable_by_id(
        db: AsyncSession, statement_id: int
    ) -> ReconciliationStatement:
        """
        按 ID 加载对账单并校验是否允许修改。

        Args:
            db: AsyncSession
            statement_id: 对账单 ID

        Returns:
            对账单 ORM 对象（已通过校验）

        Raises:
            ServiceException: 对账单不存在或状态不允许修改
        """
        stmt = select(ReconciliationStatement).where(
            ReconciliationStatement.id == statement_id
        )
        statement = (await db.execute(stmt)).scalar_one_or_none()
        if statement is None:
            raise ServiceException(message=f'对账单不存在: id={statement_id}')

        ReconciliationSecurityService.assert_statement_modifiable(statement)
        return statement

    # ------------------------------------------------------------------
    # 便捷角色检查（Requirement 8.2）— 简化签名
    # ------------------------------------------------------------------

    @staticmethod
    def require_role(user_roles: list[str], *roles: str) -> bool:
        """
        简化的角色权限检查。

        检查用户角色是否在允许的角色列表中。admin 角色自动拥有所有权限。

        Args:
            user_roles: 当前用户拥有的角色 key 列表
            *roles: 允许访问的角色（可变参数）

        Returns:
            True 表示有权限

        Raises:
            PermissionException: 无权限时抛出 (HTTP 403)
        """
        if ROLE_ADMIN in user_roles:
            return True
        if any(role in roles for role in user_roles):
            return True
        raise PermissionException(
            message=(
                f'无权访问对账数据：需要角色 {list(roles)} 之一，'
                f'当前角色 {user_roles}'
            )
        )

    # ------------------------------------------------------------------
    # 安全事件记录（Requirement 8.6）
    # ------------------------------------------------------------------

    @staticmethod
    async def log_unauthorized_access(
        db: AsyncSession,
        user_id: int,
        resource: str,
        ip: Optional[str] = None,
        user_roles: Optional[list[str]] = None,
        operator_name: Optional[str] = None,
    ) -> Optional[int]:
        """
        记录未授权访问安全事件（公开接口）。

        供 controller 层在捕获到未授权访问时调用，将安全事件
        写入审计日志。

        Args:
            db: AsyncSession
            user_id: 尝试访问的用户 ID
            resource: 被访问的资源描述
            ip: 客户端 IP 地址
            user_roles: 用户角色列表（可选，用于详情记录）
            operator_name: 操作人姓名

        Returns:
            审计日志 ID 或 None（写入失败时）
        """
        return await ReconciliationAuditService.log_action_safe(
            db=db,
            entity_type=ENTITY_TYPE_STATEMENT,
            entity_id=1,  # 占位，列表级访问
            action='unauthorized_access',
            operator_id=user_id or 0,
            operator_name=operator_name,
            detail={
                'event': 'unauthorized_access',
                'resource': resource,
                'user_roles': user_roles or [],
                'denied_at': datetime.now().isoformat(),
            },
            ip_address=ip,
            autocommit=True,
        )

    @staticmethod
    async def _log_unauthorized_access(
        db: AsyncSession,
        operator_id: int,
        operator_name: Optional[str],
        entity_type: str,
        entity_id: int,
        user_roles: list[str],
        required_roles: list[str],
        resource_description: str = '',
        ip_address: Optional[str] = None,
    ) -> None:
        """
        记录未授权访问安全事件到审计日志。

        使用 log_action_safe 以避免审计写入失败影响主流程
        （拒绝访问仍然会正常抛出 PermissionException）。
        """
        # 确保 entity_type 合法；若不合法则降级为 'statement'
        safe_entity_type = (
            entity_type if entity_type in VALID_ENTITY_TYPES
            else ENTITY_TYPE_STATEMENT
        )
        # entity_id 为 0 时表示列表级访问，审计日志要求 > 0，使用 1 作为占位
        safe_entity_id = entity_id if entity_id > 0 else 1

        await ReconciliationAuditService.log_action_safe(
            db=db,
            entity_type=safe_entity_type,
            entity_id=safe_entity_id,
            action='unauthorized_access',
            operator_id=operator_id or 0,
            operator_name=operator_name,
            detail={
                'event': 'unauthorized_access',
                'user_roles': user_roles,
                'required_roles': required_roles,
                'resource': resource_description,
                'denied_at': datetime.now().isoformat(),
            },
            ip_address=ip_address,
            autocommit=True,
        )

        logger.warning(
            '[ReconciliationSecurity] 安全事件: 未授权访问 '
            'operator_id={} entity_type={} entity_id={} '
            'user_roles={} required_roles={} resource={}',
            operator_id, entity_type, entity_id,
            user_roles, required_roles, resource_description,
        )

    @staticmethod
    async def log_security_event(
        db: AsyncSession,
        event_type: str,
        operator_id: int,
        entity_type: str = ENTITY_TYPE_STATEMENT,
        entity_id: int = 1,
        operator_name: Optional[str] = None,
        detail: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ) -> Optional[int]:
        """
        通用安全事件记录接口。

        供外部调用记录各类安全事件（如暴力尝试、异常操作模式等）。

        Args:
            db: AsyncSession
            event_type: 事件类型描述（写入 detail.event）
            operator_id: 操作人 ID
            entity_type: 实体类型
            entity_id: 实体 ID
            operator_name: 操作人姓名
            detail: 额外详情
            ip_address: 客户端 IP

        Returns:
            审计日志 ID 或 None（写入失败时）
        """
        safe_entity_type = (
            entity_type if entity_type in VALID_ENTITY_TYPES
            else ENTITY_TYPE_STATEMENT
        )
        safe_entity_id = entity_id if entity_id > 0 else 1

        event_detail = {
            'event': event_type,
            'timestamp': datetime.now().isoformat(),
            **(detail or {}),
        }

        return await ReconciliationAuditService.log_action_safe(
            db=db,
            entity_type=safe_entity_type,
            entity_id=safe_entity_id,
            action='unauthorized_access',
            operator_id=operator_id or 0,
            operator_name=operator_name,
            detail=event_detail,
            ip_address=ip_address,
            autocommit=True,
        )

    # ------------------------------------------------------------------
    # 数据回滚（Requirement 8.4）
    # ------------------------------------------------------------------

    @staticmethod
    async def rollback_operation(
        db: AsyncSession,
        entity_type: str,
        entity_id: int,
        operator_id: int,
        admin_approved: bool = False,
        operator_name: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        数据回滚操作 — 仅允许对 24 小时内的误操作进行回滚。

        约束（Requirement 8.4）：
          1. 仅 24 小时内创建的数据允许回滚
          2. 必须经管理员审批确认（admin_approved=True）
          3. 回滚操作本身记录审计日志

        Args:
            db: AsyncSession
            entity_type: 实体类型（statement/anomaly/adjustment/payment/settlement）
            entity_id: 实体 ID
            operator_id: 操作人 ID
            admin_approved: 管理员是否已审批确认
            operator_name: 操作人姓名
            ip_address: 客户端 IP

        Returns:
            dict 包含回滚结果信息:
              - success: bool
              - message: str
              - entity_type: str
              - entity_id: int
              - rolled_back_at: str (ISO format)

        Raises:
            ServiceException: 未通过管理员审批 / 超出 24 小时窗口 / 实体不存在
            PermissionException: 权限不足
        """
        # 1. 校验管理员审批
        if not admin_approved:
            raise ServiceException(
                message='数据回滚操作需要管理员审批确认（admin_approved=True）'
            )

        # 2. 校验实体类型
        if entity_type not in VALID_ENTITY_TYPES:
            raise ServiceException(
                message=f'非法的实体类型: {entity_type}'
            )

        # 3. 校验时间窗口 — 查找该实体的创建审计日志
        cutoff_time = datetime.now() - timedelta(hours=ROLLBACK_WINDOW_HOURS)

        # 查找实体的最早创建记录来判断是否在 24 小时内
        created_at = await ReconciliationSecurityService._get_entity_created_at(
            db, entity_type, entity_id
        )

        if created_at is None:
            raise ServiceException(
                message=f'未找到实体的创建记录: {entity_type} id={entity_id}'
            )

        if created_at < cutoff_time:
            hours_ago = (datetime.now() - created_at).total_seconds() / 3600
            raise ServiceException(
                message=(
                    f'数据回滚仅允许对 {ROLLBACK_WINDOW_HOURS} 小时内的操作进行；'
                    f'该实体创建于 {hours_ago:.1f} 小时前，已超出回滚窗口'
                )
            )

        # 4. 执行回滚（标记为已删除/回滚状态）
        rollback_result = await ReconciliationSecurityService._perform_rollback(
            db, entity_type, entity_id
        )

        # 5. 记录回滚审计日志
        await ReconciliationAuditService.log_action(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            action=ACTION_DELETE,
            operator_id=operator_id,
            operator_name=operator_name,
            detail={
                'sub_action': 'rollback',
                'admin_approved': True,
                'rollback_reason': 'admin_initiated_rollback',
                'rolled_back_at': datetime.now().isoformat(),
                'original_created_at': created_at.isoformat(),
            },
            ip_address=ip_address,
        )

        await db.commit()

        logger.info(
            '[ReconciliationSecurity] 数据回滚完成: entity_type={} entity_id={} '
            'operator_id={}',
            entity_type, entity_id, operator_id,
        )

        return {
            'success': True,
            'message': f'{entity_type} id={entity_id} 已成功回滚',
            'entity_type': entity_type,
            'entity_id': entity_id,
            'rolled_back_at': datetime.now().isoformat(),
        }

    @staticmethod
    async def _get_entity_created_at(
        db: AsyncSession, entity_type: str, entity_id: int
    ) -> Optional[datetime]:
        """
        获取实体的创建时间。

        优先从审计日志中查找 create 操作记录；
        若无审计记录，则尝试直接查询实体表的 created_at 字段。
        """
        # 先查审计日志中的 create 记录
        stmt = (
            select(ReconciliationAuditLog.created_at)
            .where(
                ReconciliationAuditLog.entity_type == entity_type,
                ReconciliationAuditLog.entity_id == entity_id,
                ReconciliationAuditLog.action == 'create',
            )
            .order_by(ReconciliationAuditLog.created_at.asc())
            .limit(1)
        )
        result = (await db.execute(stmt)).scalar_one_or_none()
        if result is not None:
            return result

        # 降级：直接查实体表的 created_at（仅支持 statement）
        if entity_type == ENTITY_TYPE_STATEMENT:
            stmt2 = select(ReconciliationStatement.created_at).where(
                ReconciliationStatement.id == entity_id
            )
            return (await db.execute(stmt2)).scalar_one_or_none()

        return None

    @staticmethod
    async def _perform_rollback(
        db: AsyncSession, entity_type: str, entity_id: int
    ) -> bool:
        """
        执行实际的回滚操作。

        对于对账单（statement）：将状态重置为 'pending' 并清除确认信息。
        其他实体类型：标记为逻辑删除（通过审计日志记录回滚事件）。

        Returns:
            True 表示回滚成功
        """
        if entity_type == ENTITY_TYPE_STATEMENT:
            stmt = select(ReconciliationStatement).where(
                ReconciliationStatement.id == entity_id
            )
            statement = (await db.execute(stmt)).scalar_one_or_none()
            if statement is None:
                raise ServiceException(
                    message=f'对账单不存在: id={entity_id}'
                )
            # 重置状态
            statement.status = 'pending'
            statement.confirmation_status = 'pending'
            statement.confirmed_at = None
            statement.confirmed_by = None
            statement.dispute_reason = None
            await db.flush()
            return True

        # 其他实体类型 — 回滚通过审计日志标记（实际删除需按业务需求扩展）
        # 此处仅记录回滚意图，不做物理删除
        return True


# ---------------------------------------------------------------------------
# 装饰器 — 角色权限检查（Requirement 8.2）
# ---------------------------------------------------------------------------

def require_reconciliation_role(*allowed_roles: str) -> Callable:
    """
    对账系统角色权限检查装饰器。

    用于 service 层方法，要求调用方传入 user_roles 参数。
    如果用户不具备任一允许角色，则抛出 PermissionException。

    用法示例::

        @require_reconciliation_role('finance_staff', 'finance_manager')
        async def some_service_method(db, ..., user_roles=None, **kwargs):
            ...

    注意：
      - 被装饰函数必须接受 user_roles 关键字参数（list[str]）
      - admin 角色自动拥有所有权限
      - 装饰器在函数执行前进行权限检查
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            user_roles = kwargs.get('user_roles') or []
            operator_id = kwargs.get('operator_id', 0)

            # admin 角色拥有所有权限
            if ROLE_ADMIN in user_roles:
                return await func(*args, **kwargs)

            # 检查是否有任一允许角色
            if not any(role in allowed_roles for role in user_roles):
                logger.warning(
                    '[ReconciliationSecurity] 装饰器拒绝: func={} '
                    'operator_id={} user_roles={} required={}',
                    func.__name__, operator_id, user_roles, allowed_roles,
                )
                raise PermissionException(
                    message=(
                        f'无权执行此操作：需要角色 {list(allowed_roles)} 之一，'
                        f'当前角色 {user_roles}'
                    )
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

__all__ = [
    'ReconciliationSecurityService',
    'require_reconciliation_role',
    # 角色常量
    'ROLE_FINANCE_STAFF',
    'ROLE_FINANCE_MANAGER',
    'ROLE_FINANCE_DIRECTOR',
    'ROLE_SUPPLIER',
    'ROLE_ADMIN',
    'RECONCILIATION_ROLES',
    # 状态常量
    'IMMUTABLE_STATUSES',
    'ROLLBACK_WINDOW_HOURS',
]
