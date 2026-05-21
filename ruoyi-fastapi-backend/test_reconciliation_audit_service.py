"""
Smoke tests for ReconciliationAuditService (Task 11.1).

Run from the backend root:
    python test_reconciliation_audit_service.py

Uses an in-memory aiosqlite DB (JSONB monkey-patched to JSON for SQLite
compatibility) so no PostgreSQL connection is needed.

Validates:
  1. log_action persists rows with the right entity_type/action/operator
  2. Input validation rejects unknown entity_type / action / entity_id<=0
  3. Immutability guard rejects update/delete attempts
     (Requirement 8.7 / Property 17)
  4. query_audit_logs supports filtering & pagination (Requirement 8.5)
  5. log_action_safe swallows errors instead of raising
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta

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
)
from module_entrust.service.reconciliation_audit_service import (  # noqa: E402
    ACTION_CREATE,
    ACTION_UPDATE,
    ENTITY_TYPE_PAYMENT,
    ENTITY_TYPE_STATEMENT,
    ImmutableAuditLogError,
    ReconciliationAuditService,
)


async def _setup_db() -> async_sessionmaker:
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', future=True)
    async with engine.begin() as conn:
        # Only create the audit log table; we don't need others for these tests
        await conn.run_sync(
            lambda sync_conn: ReconciliationAuditLog.__table__.create(sync_conn)
        )
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def test_log_action_basic():
    Session = await _setup_db()
    async with Session() as db:
        log_id = await ReconciliationAuditService.log_action(
            db=db,
            entity_type=ENTITY_TYPE_STATEMENT,
            entity_id=42,
            action=ACTION_CREATE,
            operator_id=1001,
            operator_name='alice',
            detail={'foo': 'bar'},
            ip_address='10.0.0.1',
            autocommit=True,
        )
        assert log_id > 0

        rows = await ReconciliationAuditService.get_logs_for_entity(
            db, ENTITY_TYPE_STATEMENT, 42
        )
        assert len(rows) == 1
        log = rows[0]
        assert log.action == ACTION_CREATE
        assert log.operator_id == 1001
        assert log.operator_name == 'alice'
        assert log.detail == {'foo': 'bar'}
        assert log.ip_address == '10.0.0.1'
    print('PASS test_log_action_basic')


async def test_log_action_validates_inputs():
    Session = await _setup_db()
    async with Session() as db:
        for bad in [
            dict(entity_type='unknown_entity', action=ACTION_CREATE, entity_id=1),
            dict(entity_type=ENTITY_TYPE_STATEMENT, action='hack', entity_id=1),
            dict(entity_type=ENTITY_TYPE_STATEMENT, action=ACTION_CREATE, entity_id=0),
        ]:
            raised = False
            try:
                await ReconciliationAuditService.log_action(
                    db=db, operator_id=1, **bad
                )
            except Exception:
                raised = True
            assert raised, f'expected exception for {bad}'
    print('PASS test_log_action_validates_inputs')


async def test_immutability_guard():
    raised = 0
    try:
        await ReconciliationAuditService.delete_log(123)
    except ImmutableAuditLogError:
        raised += 1
    try:
        await ReconciliationAuditService.update_log(123, detail={'x': 1})
    except ImmutableAuditLogError:
        raised += 1
    try:
        ReconciliationAuditService.assert_immutable('delete')
    except ImmutableAuditLogError:
        raised += 1
    assert raised == 3
    print('PASS test_immutability_guard')


async def test_query_audit_logs_filters_and_pagination():
    Session = await _setup_db()
    async with Session() as db:
        for i in range(5):
            await ReconciliationAuditService.log_action(
                db=db,
                entity_type=ENTITY_TYPE_STATEMENT if i < 3 else ENTITY_TYPE_PAYMENT,
                entity_id=100 + i,
                action=ACTION_CREATE if i % 2 == 0 else ACTION_UPDATE,
                operator_id=10 if i < 2 else 20,
                detail={'i': i},
                autocommit=True,
            )

        result = await ReconciliationAuditService.query_audit_logs(
            db=db, entity_type=ENTITY_TYPE_STATEMENT
        )
        assert result['total'] == 3

        result = await ReconciliationAuditService.query_audit_logs(
            db=db, filters={'action': ACTION_CREATE}
        )
        assert result['total'] == 3

        result = await ReconciliationAuditService.query_audit_logs(
            db=db, filters={'operator_id': 10}
        )
        assert result['total'] == 2

        result = await ReconciliationAuditService.query_audit_logs(
            db=db, filters={'page_num': 1, 'page_size': 2}
        )
        assert result['total'] == 5 and len(result['rows']) == 2

        result = await ReconciliationAuditService.query_audit_logs(
            db=db, filters={'page_num': 3, 'page_size': 2}
        )
        assert len(result['rows']) == 1

        future = datetime.now() + timedelta(days=1)
        result = await ReconciliationAuditService.query_audit_logs(
            db=db, filters={'start_time': future}
        )
        assert result['total'] == 0
    print('PASS test_query_audit_logs_filters_and_pagination')


async def test_log_action_safe_swallows_errors():
    Session = await _setup_db()
    async with Session() as db:
        log_id = await ReconciliationAuditService.log_action_safe(
            db=db,
            entity_type=ENTITY_TYPE_STATEMENT,
            entity_id=99,
            action='garbage',
            operator_id=1,
        )
        assert log_id is None
    print('PASS test_log_action_safe_swallows_errors')


async def main():
    await test_log_action_basic()
    await test_log_action_validates_inputs()
    await test_immutability_guard()
    await test_query_audit_logs_filters_and_pagination()
    await test_log_action_safe_swallows_errors()
    print('\nAll audit service smoke tests passed!')


if __name__ == '__main__':
    asyncio.run(main())
