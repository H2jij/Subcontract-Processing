"""
Smoke tests for ReconciliationSecurityService (Task 11.3).

Run from the backend root:
    python test_reconciliation_security_service.py

Uses an in-memory aiosqlite DB (JSONB monkey-patched to JSON for SQLite
compatibility) so no PostgreSQL connection is needed.

Validates:
  1. assert_statement_modifiable raises ServiceException for confirmed/paid
     (Requirement 8.3 / Property 4)
  2. require_role checks user roles and raises PermissionException (403)
     (Requirement 8.2)
  3. log_unauthorized_access records security event via audit service
     (Requirement 8.6)
  4. rollback_operation enforces 24h window and admin approval
     (Requirement 8.4)
  5. admin role bypasses all role checks
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

# Ensure backend root is on path
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ---------------------------------------------------------------------------
# Patch JSONB -> JSON BEFORE importing models (SQLite has no JSONB)
# ---------------------------------------------------------------------------
from sqlalchemy import JSON
import sqlalchemy.dialects.postgresql as _pg


class _PatchedJSONB(JSON):
    pass


_pg.JSONB = _PatchedJSONB

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from module_entrust.entity.do.reconciliation_do import (  # noqa: E402
    ReconciliationAuditLog,
    ReconciliationStatement,
)
from module_entrust.service.reconciliation_security_service import (  # noqa: E402
    IMMUTABLE_STATUSES,
    ROLE_ADMIN,
    ROLE_FINANCE_DIRECTOR,
    ROLE_FINANCE_MANAGER,
    ROLE_FINANCE_STAFF,
    ROLE_SUPPLIER,
    ROLLBACK_WINDOW_HOURS,
    ReconciliationSecurityService,
    require_reconciliation_role,
)
from exceptions.exception import PermissionException, ServiceException  # noqa: E402


async def _setup_db() -> async_sessionmaker:
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', future=True)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: ReconciliationAuditLog.__table__.create(sync_conn)
        )
        await conn.run_sync(
            lambda sync_conn: ReconciliationStatement.__table__.create(sync_conn)
        )
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Test 1: assert_statement_modifiable (Requirement 8.3)
# ---------------------------------------------------------------------------

async def test_assert_statement_modifiable_pending():
    """pending 状态允许修改"""
    stmt = MagicMock()
    stmt.status = 'pending'
    stmt.statement_no = 'REC-202401-1-001'
    # Should not raise
    ReconciliationSecurityService.assert_statement_modifiable(stmt)
    print('PASS test_assert_statement_modifiable_pending')


async def test_assert_statement_modifiable_confirmed():
    """confirmed 状态禁止修改"""
    stmt = MagicMock()
    stmt.status = 'confirmed'
    stmt.statement_no = 'REC-202401-1-001'
    raised = False
    try:
        ReconciliationSecurityService.assert_statement_modifiable(stmt)
    except ServiceException as e:
        raised = True
        assert 'confirmed' in e.message or '禁止修改' in e.message
    assert raised, 'Expected ServiceException for confirmed status'
    print('PASS test_assert_statement_modifiable_confirmed')


async def test_assert_statement_modifiable_paid():
    """paid 状态禁止修改"""
    stmt = MagicMock()
    stmt.status = 'paid'
    stmt.statement_no = 'REC-202401-1-001'
    raised = False
    try:
        ReconciliationSecurityService.assert_statement_modifiable(stmt)
    except ServiceException as e:
        raised = True
        assert '禁止修改' in e.message
    assert raised, 'Expected ServiceException for paid status'
    print('PASS test_assert_statement_modifiable_paid')


# ---------------------------------------------------------------------------
# Test 2: require_role (Requirement 8.2)
# ---------------------------------------------------------------------------

async def test_require_role_allowed():
    """用户拥有允许角色时通过"""
    result = ReconciliationSecurityService.require_role(
        [ROLE_FINANCE_STAFF], ROLE_FINANCE_STAFF, ROLE_FINANCE_MANAGER
    )
    assert result is True
    print('PASS test_require_role_allowed')


async def test_require_role_denied():
    """用户无允许角色时拒绝"""
    raised = False
    try:
        ReconciliationSecurityService.require_role(
            [ROLE_SUPPLIER], ROLE_FINANCE_STAFF, ROLE_FINANCE_MANAGER
        )
    except PermissionException as e:
        raised = True
        assert '无权' in e.message
    assert raised, 'Expected PermissionException'
    print('PASS test_require_role_denied')


async def test_require_role_admin_bypass():
    """admin 角色自动拥有所有权限"""
    result = ReconciliationSecurityService.require_role(
        [ROLE_ADMIN], ROLE_FINANCE_DIRECTOR
    )
    assert result is True
    print('PASS test_require_role_admin_bypass')


async def test_require_role_empty_roles():
    """空角色列表被拒绝"""
    raised = False
    try:
        ReconciliationSecurityService.require_role(
            [], ROLE_FINANCE_STAFF
        )
    except PermissionException:
        raised = True
    assert raised, 'Expected PermissionException for empty roles'
    print('PASS test_require_role_empty_roles')


# ---------------------------------------------------------------------------
# Test 3: log_unauthorized_access (Requirement 8.6)
# ---------------------------------------------------------------------------

async def test_log_unauthorized_access():
    """未授权访问事件被记录到审计日志"""
    Session = await _setup_db()
    async with Session() as db:
        log_id = await ReconciliationSecurityService.log_unauthorized_access(
            db=db,
            user_id=999,
            resource='reconciliation_statement/42',
            ip='192.168.1.100',
            user_roles=[ROLE_SUPPLIER],
        )
        assert log_id is not None and log_id > 0

        # Verify the log was written
        from sqlalchemy import select
        stmt = select(ReconciliationAuditLog).where(
            ReconciliationAuditLog.id == log_id
        )
        log = (await db.execute(stmt)).scalar_one()
        assert log.action == 'unauthorized_access'
        assert log.operator_id == 999
        assert log.ip_address == '192.168.1.100'
        assert log.detail['resource'] == 'reconciliation_statement/42'
    print('PASS test_log_unauthorized_access')


# ---------------------------------------------------------------------------
# Test 4: check_role_access_and_log (Requirement 8.2 + 8.6)
# ---------------------------------------------------------------------------

async def test_check_role_access_and_log_denied():
    """权限检查失败时记录安全事件并抛出异常"""
    Session = await _setup_db()
    async with Session() as db:
        raised = False
        try:
            await ReconciliationSecurityService.check_role_access_and_log(
                db=db,
                user_roles=[ROLE_SUPPLIER],
                allowed_roles=[ROLE_FINANCE_STAFF, ROLE_FINANCE_MANAGER],
                operator_id=888,
                entity_type='statement',
                entity_id=10,
                resource_description='edit line item',
                ip_address='10.0.0.5',
            )
        except PermissionException:
            raised = True
        assert raised, 'Expected PermissionException'

        # Verify security event was logged
        from sqlalchemy import select, func
        count = (await db.execute(
            select(func.count()).select_from(ReconciliationAuditLog).where(
                ReconciliationAuditLog.action == 'unauthorized_access'
            )
        )).scalar_one()
        assert count == 1
    print('PASS test_check_role_access_and_log_denied')


async def test_check_role_access_and_log_allowed():
    """权限检查通过时不记录安全事件"""
    Session = await _setup_db()
    async with Session() as db:
        result = await ReconciliationSecurityService.check_role_access_and_log(
            db=db,
            user_roles=[ROLE_FINANCE_MANAGER],
            allowed_roles=[ROLE_FINANCE_STAFF, ROLE_FINANCE_MANAGER],
            operator_id=100,
            entity_type='statement',
            entity_id=10,
        )
        assert result is True

        # No security event should be logged
        from sqlalchemy import select, func
        count = (await db.execute(
            select(func.count()).select_from(ReconciliationAuditLog)
        )).scalar_one()
        assert count == 0
    print('PASS test_check_role_access_and_log_allowed')


# ---------------------------------------------------------------------------
# Test 5: rollback_operation (Requirement 8.4)
# ---------------------------------------------------------------------------

async def test_rollback_requires_admin_approval():
    """回滚操作需要管理员审批"""
    Session = await _setup_db()
    async with Session() as db:
        raised = False
        try:
            await ReconciliationSecurityService.rollback_operation(
                db=db,
                entity_type='statement',
                entity_id=1,
                operator_id=100,
                admin_approved=False,
            )
        except ServiceException as e:
            raised = True
            assert '管理员审批' in e.message
        assert raised, 'Expected ServiceException for missing admin approval'
    print('PASS test_rollback_requires_admin_approval')


async def test_rollback_within_24h():
    """24 小时内的操作允许回滚"""
    Session = await _setup_db()
    async with Session() as db:
        # Create a statement created recently
        statement = ReconciliationStatement(
            statement_no='REC-202401-1-001',
            supplier_id=1,
            period_start=datetime(2024, 1, 1).date(),
            period_end=datetime(2024, 1, 31).date(),
            total_amount=1000,
            status='confirmed',
            confirmation_status='confirmed',
            created_at=datetime.now(),
        )
        db.add(statement)
        await db.flush()
        stmt_id = statement.id

        # Also create an audit log for the create action
        from module_entrust.service.reconciliation_audit_service import (
            ReconciliationAuditService,
        )
        await ReconciliationAuditService.log_action(
            db=db,
            entity_type='statement',
            entity_id=stmt_id,
            action='create',
            operator_id=1,
            autocommit=False,
        )
        await db.commit()

        # Rollback should succeed
        result = await ReconciliationSecurityService.rollback_operation(
            db=db,
            entity_type='statement',
            entity_id=stmt_id,
            operator_id=100,
            admin_approved=True,
        )
        assert result['success'] is True

        # Verify statement was reset to pending
        from sqlalchemy import select
        stmt = select(ReconciliationStatement).where(
            ReconciliationStatement.id == stmt_id
        )
        updated = (await db.execute(stmt)).scalar_one()
        assert updated.status == 'pending'
        assert updated.confirmation_status == 'pending'
    print('PASS test_rollback_within_24h')


async def test_rollback_outside_24h():
    """超过 24 小时的操作禁止回滚"""
    Session = await _setup_db()
    async with Session() as db:
        # Create audit log with old timestamp
        old_time = datetime.now() - timedelta(hours=25)
        log = ReconciliationAuditLog(
            entity_type='statement',
            entity_id=999,
            action='create',
            operator_id=1,
            created_at=old_time,
        )
        db.add(log)
        await db.commit()

        raised = False
        try:
            await ReconciliationSecurityService.rollback_operation(
                db=db,
                entity_type='statement',
                entity_id=999,
                operator_id=100,
                admin_approved=True,
            )
        except ServiceException as e:
            raised = True
            assert '超出回滚窗口' in e.message
        assert raised, 'Expected ServiceException for expired rollback window'
    print('PASS test_rollback_outside_24h')


# ---------------------------------------------------------------------------
# Test 6: require_reconciliation_role decorator
# ---------------------------------------------------------------------------

async def test_decorator_allows_authorized():
    """装饰器允许有权限的用户"""
    @require_reconciliation_role(ROLE_FINANCE_STAFF, ROLE_FINANCE_MANAGER)
    async def protected_action(**kwargs):
        return 'success'

    result = await protected_action(user_roles=[ROLE_FINANCE_STAFF], operator_id=1)
    assert result == 'success'
    print('PASS test_decorator_allows_authorized')


async def test_decorator_denies_unauthorized():
    """装饰器拒绝无权限的用户"""
    @require_reconciliation_role(ROLE_FINANCE_STAFF, ROLE_FINANCE_MANAGER)
    async def protected_action(**kwargs):
        return 'success'

    raised = False
    try:
        await protected_action(user_roles=[ROLE_SUPPLIER], operator_id=1)
    except PermissionException:
        raised = True
    assert raised, 'Expected PermissionException from decorator'
    print('PASS test_decorator_denies_unauthorized')


async def test_decorator_admin_bypass():
    """装饰器允许 admin 角色"""
    @require_reconciliation_role(ROLE_FINANCE_STAFF)
    async def protected_action(**kwargs):
        return 'admin_pass'

    result = await protected_action(user_roles=[ROLE_ADMIN], operator_id=1)
    assert result == 'admin_pass'
    print('PASS test_decorator_admin_bypass')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    await test_assert_statement_modifiable_pending()
    await test_assert_statement_modifiable_confirmed()
    await test_assert_statement_modifiable_paid()
    await test_require_role_allowed()
    await test_require_role_denied()
    await test_require_role_admin_bypass()
    await test_require_role_empty_roles()
    await test_log_unauthorized_access()
    await test_check_role_access_and_log_denied()
    await test_check_role_access_and_log_allowed()
    await test_rollback_requires_admin_approval()
    await test_rollback_within_24h()
    await test_rollback_outside_24h()
    await test_decorator_allows_authorized()
    await test_decorator_denies_unauthorized()
    await test_decorator_admin_bypass()
    print('\nAll security service smoke tests passed!')


if __name__ == '__main__':
    asyncio.run(main())
