"""
对账系统 — 异常管理 Controller
=========================================
API 路由：
  GET  /entrust/anomaly/list                    — 异常记录列表
  GET  /entrust/anomaly/adjustments/pending     — 待审批列表
  GET  /entrust/anomaly/{id}                    — 异常详情
  PUT  /entrust/anomaly/{id}/status             — 更新异常状态
  POST /entrust/anomaly/{id}/adjustment         — 提出金额调整
  POST /entrust/anomaly/adjustments/{id}/approve — 审批通过
  POST /entrust/anomaly/adjustments/{id}/reject  — 审批驳回

Requirements covered: 3.7, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
"""
from typing import Annotated, Optional

from fastapi import Path, Query
from fastapi.exceptions import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from exceptions.exception import ServiceException
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_entrust.entity.do.reconciliation_do import (
    Adjustment,
    Anomaly,
)
from module_entrust.entity.vo.reconciliation_vo import (
    AdjustmentApproveRequest,
    AdjustmentCreateRequest,
    AdjustmentRejectRequest,
    AdjustmentResponse,
    AnomalyResponse,
    AnomalyStatusUpdateRequest,
)
from module_entrust.service.anomaly_service import (
    ADJUSTMENT_STATUS_PENDING,
    ADJUSTMENT_STATUS_ESCALATED,
    AnomalyService,
)
from utils.response_util import ResponseUtil

anomaly_controller = APIRouterPro(
    prefix='/entrust/anomaly',
    order_num=22,
    tags=['异常管理'],
    dependencies=[PreAuthDependency()],
)


# ── GET /list — 异常记录列表 ─────────────────────────────────────────────────

@anomaly_controller.get(
    '/list',
    summary='异常记录列表',
    response_model=PageResponseModel,
)
async def get_anomaly_list(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    statement_id: Optional[int] = Query(default=None, description='对账单ID'),
    anomaly_type: Optional[str] = Query(default=None, description='类型: amount_diff/supplier_missing/duplicate/quality_dispute'),
    severity: Optional[str] = Query(default=None, description='严重程度: critical/warning/info'),
    status: Optional[str] = Query(default=None, description='状态: open/investigating/resolved/closed'),
    page_num: int = Query(default=1, ge=1, description='页码'),
    page_size: int = Query(default=10, ge=1, le=100, description='每页条数'),
):
    """异常记录列表，支持按对账单、类型、严重程度、状态筛选，分页返回。"""
    stmt = select(Anomaly)
    count_stmt = select(func.count()).select_from(Anomaly)

    filters = []
    if statement_id is not None:
        filters.append(Anomaly.statement_id == statement_id)
    if anomaly_type is not None:
        filters.append(Anomaly.anomaly_type == anomaly_type)
    if severity is not None:
        filters.append(Anomaly.severity == severity)
    if status is not None:
        filters.append(Anomaly.status == status)

    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = (await query_db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(Anomaly.created_at.desc())
    stmt = stmt.offset((page_num - 1) * page_size).limit(page_size)

    rows = (await query_db.execute(stmt)).scalars().all()

    row_list = [
        AnomalyResponse.model_validate(r).model_dump()
        for r in rows
    ]

    return ResponseUtil.success(
        rows=row_list,
        dict_content={'total': total, 'page_num': page_num, 'page_size': page_size},
    )


# ── GET /adjustments/pending — 待审批列表 ────────────────────────────────────
# NOTE: 此路由必须在 /{id} 之前注册，避免 "adjustments" 被当作 {id} 匹配

@anomaly_controller.get(
    '/adjustments/pending',
    summary='待审批调整列表',
    response_model=PageResponseModel,
)
async def get_pending_adjustments(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    approval_level: Optional[str] = Query(default=None, description='审批层级: manager/director'),
    page_num: int = Query(default=1, ge=1, description='页码'),
    page_size: int = Query(default=10, ge=1, le=100, description='每页条数'),
):
    """获取待审批的调整记录列表（pending_approval 或 escalated 状态）。"""
    stmt = select(Adjustment)
    count_stmt = select(func.count()).select_from(Adjustment)

    filters = [
        Adjustment.approval_status.in_([ADJUSTMENT_STATUS_PENDING, ADJUSTMENT_STATUS_ESCALATED])
    ]
    if approval_level is not None:
        filters.append(Adjustment.approval_level == approval_level)

    stmt = stmt.where(*filters)
    count_stmt = count_stmt.where(*filters)

    total = (await query_db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(Adjustment.created_at.desc())
    stmt = stmt.offset((page_num - 1) * page_size).limit(page_size)

    rows = (await query_db.execute(stmt)).scalars().all()

    row_list = [
        AdjustmentResponse.model_validate(r).model_dump()
        for r in rows
    ]

    return ResponseUtil.success(
        rows=row_list,
        dict_content={'total': total, 'page_num': page_num, 'page_size': page_size},
    )


# ── GET /{id} — 异常详情 ─────────────────────────────────────────────────────

@anomaly_controller.get(
    '/{anomaly_id}',
    summary='异常详情',
    response_model=DataResponseModel,
)
async def get_anomaly_detail(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    anomaly_id: int = Path(..., description='异常记录ID'),
):
    """获取异常记录详情。"""
    anomaly = await query_db.scalar(
        select(Anomaly).where(Anomaly.id == anomaly_id)
    )
    if not anomaly:
        return ResponseUtil.failure(msg=f'异常记录不存在: id={anomaly_id}')

    data = AnomalyResponse.model_validate(anomaly).model_dump()
    return ResponseUtil.success(data=data)


# ── PUT /{id}/status — 更新异常状态 ──────────────────────────────────────────

@anomaly_controller.put(
    '/{anomaly_id}/status',
    summary='更新异常状态',
    response_model=ResponseBaseModel,
)
async def update_anomaly_status(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: AnomalyStatusUpdateRequest,
    anomaly_id: int = Path(..., description='异常记录ID'),
):
    """更新异常记录的处理状态（open/investigating/resolved/closed）。"""
    from datetime import datetime

    anomaly = await query_db.scalar(
        select(Anomaly).where(Anomaly.id == anomaly_id)
    )
    if not anomaly:
        return ResponseUtil.failure(msg=f'异常记录不存在: id={anomaly_id}')

    anomaly.status = data.status

    # 如果状态变为 resolved，记录解决时间和解决人
    if data.status == 'resolved':
        anomaly.resolved_at = datetime.now()
        anomaly.resolved_by = current_user.user.user_id if current_user.user else 0

    await query_db.flush()
    await query_db.commit()

    return ResponseUtil.success(msg='异常状态更新成功')


# ── POST /{id}/adjustment — 提出金额调整 ─────────────────────────────────────

@anomaly_controller.post(
    '/{anomaly_id}/adjustment',
    summary='提出金额调整',
    response_model=DataResponseModel,
)
async def create_adjustment(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: AdjustmentCreateRequest,
    anomaly_id: int = Path(..., description='异常记录ID'),
):
    """
    针对异常提出金额调整。
    - 行项已冻结（存在待审批调整）时返回 409 Conflict
    """
    try:
        adjustment_id = await AnomalyService.create_adjustment(
            db=query_db,
            anomaly_id=anomaly_id,
            new_amount=data.adjusted_amount,
            reason=data.adjustment_reason,
            created_by=current_user.user.user_id if current_user.user else 0,
        )
        return ResponseUtil.success(
            data={'adjustment_id': adjustment_id},
            msg='调整记录创建成功',
        )
    except ServiceException as e:
        msg = str(e.message) if hasattr(e, 'message') else str(e)
        # 行项冻结 → 409 Conflict
        if '冻结' in msg or '禁止重复调整' in msg:
            raise HTTPException(status_code=409, detail=msg)
        return ResponseUtil.failure(msg=msg)


# ── POST /adjustments/{id}/approve — 审批通过 ────────────────────────────────

@anomaly_controller.post(
    '/adjustments/{adjustment_id}/approve',
    summary='审批通过',
    response_model=ResponseBaseModel,
)
async def approve_adjustment(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    adjustment_id: int = Path(..., description='调整记录ID'),
    data: Optional[AdjustmentApproveRequest] = None,
):
    """
    审批通过调整记录。
    - 审批层级不匹配时返回 403 Forbidden
    """
    comment = data.comment if data and data.comment else ''

    try:
        await AnomalyService.approve_adjustment(
            db=query_db,
            adjustment_id=adjustment_id,
            approver_id=current_user.user.user_id if current_user.user else 0,
            approved=True,
            comment=comment,
        )
        return ResponseUtil.success(msg='审批通过')
    except ServiceException as e:
        msg = str(e.message) if hasattr(e, 'message') else str(e)
        # 审批层级不匹配 → 403 Forbidden
        if '权限' in msg or '层级' in msg:
            raise HTTPException(status_code=403, detail=msg)
        return ResponseUtil.failure(msg=msg)


# ── POST /adjustments/{id}/reject — 审批驳回 ─────────────────────────────────

@anomaly_controller.post(
    '/adjustments/{adjustment_id}/reject',
    summary='审批驳回',
    response_model=ResponseBaseModel,
)
async def reject_adjustment(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: AdjustmentRejectRequest,
    adjustment_id: int = Path(..., description='调整记录ID'),
):
    """
    审批驳回调整记录。
    - 审批层级不匹配时返回 403 Forbidden
    """
    try:
        await AnomalyService.approve_adjustment(
            db=query_db,
            adjustment_id=adjustment_id,
            approver_id=current_user.user.user_id if current_user.user else 0,
            approved=False,
            comment=data.reject_reason,
        )
        return ResponseUtil.success(msg='审批驳回成功')
    except ServiceException as e:
        msg = str(e.message) if hasattr(e, 'message') else str(e)
        # 审批层级不匹配 → 403 Forbidden
        if '权限' in msg or '层级' in msg:
            raise HTTPException(status_code=403, detail=msg)
        return ResponseUtil.failure(msg=msg)
