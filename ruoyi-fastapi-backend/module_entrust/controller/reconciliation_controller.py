"""
对账系统 — 对账单 Controller
=========================================
API 路由：
  POST /entrust/reconciliation/generate     — 生成对账单
  GET  /entrust/reconciliation/list         — 对账单列表（分页+筛选）
  GET  /entrust/reconciliation/{id}         — 对账单详情
  PUT  /entrust/reconciliation/{id}/line-items       — 编辑行项
  POST /entrust/reconciliation/{id}/line-items       — 新增行项
  DELETE /entrust/reconciliation/{id}/line-items/{item_id} — 删除行项
  POST /entrust/reconciliation/{id}/notify  — 手动发送通知
  POST /entrust/reconciliation/{id}/recalculate — 重新计算差异（手动触发）

Requirements covered: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.10, 8.3
"""
from typing import Annotated, Optional

from fastapi import Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from exceptions.exception import ServiceException
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_entrust.entity.do.reconciliation_do import (
    ReconciliationLineItem,
    ReconciliationStatement,
)
from module_entrust.entity.vo.reconciliation_vo import (
    LineItemCreateRequest,
    LineItemResponse,
    LineItemUpdateRequest,
    StatementBriefResponse,
    StatementDetailResponse,
    StatementGenerateRequest,
    StatementGenerateResponse,
)
from module_entrust.service.reconciliation_notification_service import (
    ReconciliationNotificationService,
)
from module_entrust.service.reconciliation_service import ReconciliationService
from utils.response_util import ResponseUtil

reconciliation_controller = APIRouterPro(
    prefix='/entrust/reconciliation',
    order_num=20,
    tags=['对账管理'],
    dependencies=[PreAuthDependency()],
)


# ── POST /generate — 生成对账单 ──────────────────────────────────────────────

@reconciliation_controller.post(
    '/generate',
    summary='生成对账单',
    response_model=DataResponseModel,
)
async def generate_statements(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: StatementGenerateRequest,
):
    """
    按对账周期 + 供应商生成对账单。
    支持自定义周期起止日期，可选指定单个供应商。
    """
    try:
        statement_ids = await ReconciliationService.generate_statements(
            db=query_db,
            period_start=data.period_start,
            period_end=data.period_end,
            supplier_id=data.supplier_id,
            created_by=current_user.user.user_id if current_user.user else 0,
        )
        result = StatementGenerateResponse(
            statement_ids=statement_ids,
            count=len(statement_ids),
        )
        return ResponseUtil.success(
            data=result.model_dump(),
            msg=f'成功生成 {len(statement_ids)} 份对账单',
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── GET /list — 对账单列表（分页+筛选） ──────────────────────────────────────

@reconciliation_controller.get(
    '/list',
    summary='对账单列表',
    response_model=PageResponseModel,
)
async def get_statement_list(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    supplier_id: Optional[int] = Query(default=None, description='供应商ID'),
    status: Optional[str] = Query(default=None, description='状态: pending/confirmed/disputed/timeout/paid'),
    confirmation_status: Optional[str] = Query(default=None, description='确认状态'),
    period_start: Optional[str] = Query(default=None, description='周期起始日期 YYYY-MM-DD'),
    period_end: Optional[str] = Query(default=None, description='周期结束日期 YYYY-MM-DD'),
    page_num: int = Query(default=1, ge=1, description='页码'),
    page_size: int = Query(default=10, ge=1, le=100, description='每页条数'),
):
    """对账单列表，支持按供应商、状态、周期筛选，分页返回。"""
    from datetime import date as date_type

    stmt = select(ReconciliationStatement)
    count_stmt = select(func.count()).select_from(ReconciliationStatement)

    # 筛选条件
    filters = []
    if supplier_id is not None:
        filters.append(ReconciliationStatement.supplier_id == supplier_id)
    if status is not None:
        filters.append(ReconciliationStatement.status == status)
    if confirmation_status is not None:
        filters.append(ReconciliationStatement.confirmation_status == confirmation_status)
    if period_start is not None:
        try:
            ps = date_type.fromisoformat(period_start)
            filters.append(ReconciliationStatement.period_start >= ps)
        except ValueError:
            return ResponseUtil.failure(msg='period_start 格式错误，应为 YYYY-MM-DD')
    if period_end is not None:
        try:
            pe = date_type.fromisoformat(period_end)
            filters.append(ReconciliationStatement.period_end <= pe)
        except ValueError:
            return ResponseUtil.failure(msg='period_end 格式错误，应为 YYYY-MM-DD')

    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    # 总数
    total = (await query_db.execute(count_stmt)).scalar() or 0

    # 分页 + 排序
    stmt = stmt.order_by(ReconciliationStatement.created_at.desc())
    stmt = stmt.offset((page_num - 1) * page_size).limit(page_size)

    rows = (await query_db.execute(stmt)).scalars().all()

    # 转换为响应模型
    row_list = [
        StatementBriefResponse.model_validate(r).model_dump()
        for r in rows
    ]

    return ResponseUtil.success(
        rows=row_list,
        dict_content={'total': total, 'page_num': page_num, 'page_size': page_size},
    )


# ── GET /{id} — 对账单详情 ───────────────────────────────────────────────────

@reconciliation_controller.get(
    '/{statement_id}',
    summary='对账单详情',
    response_model=DataResponseModel,
)
async def get_statement_detail(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    statement_id: int = Path(..., description='对账单ID'),
):
    """获取对账单详情，包含所有行项。"""
    statement = await query_db.scalar(
        select(ReconciliationStatement).where(
            ReconciliationStatement.id == statement_id
        )
    )
    if not statement:
        return ResponseUtil.failure(msg=f'对账单不存在: id={statement_id}')

    # 查询行项
    line_items_result = await query_db.execute(
        select(ReconciliationLineItem)
        .where(ReconciliationLineItem.statement_id == statement_id)
        .order_by(ReconciliationLineItem.id.asc())
    )
    line_items = line_items_result.scalars().all()

    # 构建响应
    detail = StatementDetailResponse.model_validate(statement)
    detail.line_items = [
        LineItemResponse.model_validate(item)
        for item in line_items
    ]

    return ResponseUtil.success(data=detail.model_dump())


# ── PUT /{id}/line-items — 编辑行项 ──────────────────────────────────────────

@reconciliation_controller.put(
    '/{statement_id}/line-items',
    summary='编辑行项',
    response_model=ResponseBaseModel,
)
async def update_line_item(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: LineItemUpdateRequest,
    statement_id: int = Path(..., description='对账单ID'),
    item_id: int = Query(..., description='行项ID'),
):
    """
    编辑对账单行项（仅 pending 状态允许）。
    通过 query param item_id 指定要编辑的行项。
    """
    try:
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return ResponseUtil.failure(msg='未提供任何更新字段')

        await ReconciliationService.update_line_item(
            db=query_db,
            statement_id=statement_id,
            item_id=item_id,
            data=update_data,
            operator_id=current_user.user.user_id if current_user.user else 0,
        )
        return ResponseUtil.success(msg='行项更新成功')
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── POST /{id}/line-items — 新增行项 ─────────────────────────────────────────

@reconciliation_controller.post(
    '/{statement_id}/line-items',
    summary='新增行项',
    response_model=DataResponseModel,
)
async def add_line_item(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: LineItemCreateRequest,
    statement_id: int = Path(..., description='对账单ID'),
):
    """新增对账单行项（仅 pending 状态允许）。"""
    try:
        item_data = data.model_dump(exclude_unset=True)
        item_id = await ReconciliationService.add_line_item(
            db=query_db,
            statement_id=statement_id,
            data=item_data,
            operator_id=current_user.user.user_id if current_user.user else 0,
        )
        return ResponseUtil.success(
            data={'item_id': item_id},
            msg='行项新增成功',
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── DELETE /{id}/line-items/{item_id} — 删除行项 ─────────────────────────────

@reconciliation_controller.delete(
    '/{statement_id}/line-items/{item_id}',
    summary='删除行项',
    response_model=ResponseBaseModel,
)
async def delete_line_item(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    statement_id: int = Path(..., description='对账单ID'),
    item_id: int = Path(..., description='行项ID'),
):
    """删除对账单行项（仅 pending 状态允许且行项未冻结）。"""
    try:
        await ReconciliationService.delete_line_item(
            db=query_db,
            statement_id=statement_id,
            item_id=item_id,
            operator_id=current_user.user.user_id if current_user.user else 0,
        )
        return ResponseUtil.success(msg='行项删除成功')
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── POST /{id}/notify — 手动发送通知 ─────────────────────────────────────────

@reconciliation_controller.post(
    '/{statement_id}/notify',
    summary='手动发送对账通知',
    response_model=ResponseBaseModel,
)
async def send_notification(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    statement_id: int = Path(..., description='对账单ID'),
):
    """手动触发对账单通知发送给供应商。"""
    try:
        ok = await ReconciliationNotificationService.send_reconciliation_notification(
            db=query_db,
            statement_id=statement_id,
            operator_id=current_user.user.user_id if current_user.user else 0,
        )
        if ok:
            return ResponseUtil.success(msg='通知发送成功')
        else:
            return ResponseUtil.failure(msg='通知发送失败，请稍后重试')
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── POST /{id}/recalculate — 重新计算差异（手动触发） ─────────────────────────

@reconciliation_controller.post(
    '/{statement_id}/recalculate',
    summary='重新计算差异',
    response_model=DataResponseModel,
)
async def recalculate_variance(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    statement_id: int = Path(..., description='对账单ID'),
):
    """
    手动触发对账单差异重算。

    当底层数据（虚拟入库、扣款记录等）发生变化后，可手动触发此接口
    重新计算每个行项的差异字段，并更新对账单汇总。
    仅 pending 状态的对账单允许重算。
    """
    try:
        summary = await ReconciliationService.recalculate_variance(
            db=query_db,
            statement_id=statement_id,
            operator_id=current_user.user.user_id if current_user.user else 0,
        )
        return ResponseUtil.success(
            data={k: str(v) for k, v in summary.items()},
            msg='差异重算完成',
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))
