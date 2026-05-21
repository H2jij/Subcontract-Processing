"""
对账系统 — 虚拟入库 Controller
=========================================
API 路由：
  GET  /entrust/virtual-inbound/list              — 虚拟入库记录列表（支持筛选）
  GET  /entrust/virtual-inbound/{id}              — 虚拟入库详情
  POST /entrust/virtual-inbound/                  — 手动创建虚拟入库记录
  PUT  /entrust/virtual-inbound/{id}              — 修改虚拟入库记录
  DELETE /entrust/virtual-inbound/{id}            — 删除虚拟入库记录
  GET  /entrust/virtual-inbound/by-order/{order_id} — 按工单查询

Requirements covered: 13.1, 13.2, 13.6
"""
from typing import Annotated, Optional

from fastapi import Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from exceptions.exception import ServiceException
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_entrust.entity.vo.reconciliation_vo import (
    VirtualInboundCreate,
    VirtualInboundResponse,
    VirtualInboundUpdate,
)
from module_entrust.service.virtual_inbound_service import VirtualInboundService
from utils.response_util import ResponseUtil

virtual_inbound_controller = APIRouterPro(
    prefix='/entrust/virtual-inbound',
    order_num=25,
    tags=['虚拟入库'],
    dependencies=[PreAuthDependency()],
)


# ── GET /list — 虚拟入库记录列表（支持筛选） ─────────────────────────────────

@virtual_inbound_controller.get(
    '/list',
    summary='虚拟入库记录列表',
    response_model=PageResponseModel,
)
async def get_virtual_inbound_list(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    order_id: Optional[int] = Query(default=None, description='委外工单ID'),
    order_no: Optional[str] = Query(default=None, description='委外单号'),
    part_no: Optional[str] = Query(default=None, description='零件编号'),
    inbound_type: Optional[str] = Query(default=None, description='入库类型: re_shipment_in/anomaly_deduction'),
    responsible_party: Optional[str] = Query(default=None, description='责任方: material_supplier/processor'),
    status: Optional[str] = Query(default=None, description='状态: pending/confirmed/linked_to_settlement/cancelled'),
    page_num: int = Query(default=1, ge=1, description='页码'),
    page_size: int = Query(default=10, ge=1, le=100, description='每页条数'),
):
    """虚拟入库记录列表，支持按工单、零件、入库类型、责任方、状态筛选，分页返回。"""
    result = await VirtualInboundService.list_virtual_inbounds(
        db=query_db,
        order_id=order_id,
        order_no=order_no,
        part_no=part_no,
        inbound_type=inbound_type,
        responsible_party=responsible_party,
        status=status,
        page_num=page_num,
        page_size=page_size,
    )

    row_list = [
        VirtualInboundResponse.model_validate(r).model_dump()
        for r in result['rows']
    ]

    return ResponseUtil.success(
        rows=row_list,
        dict_content={
            'total': result['total'],
            'page_num': result['page_num'],
            'page_size': result['page_size'],
        },
    )


# ── GET /by-order/{order_id} — 按工单查询虚拟入库记录 ────────────────────────

@virtual_inbound_controller.get(
    '/by-order/{order_id}',
    summary='按工单查询虚拟入库记录',
    response_model=DataResponseModel,
)
async def get_virtual_inbound_by_order(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    order_id: int = Path(..., description='委外工单ID'),
):
    """查询指定工单的所有虚拟入库记录。"""
    rows = await VirtualInboundService.list_by_order(db=query_db, order_id=order_id)

    row_list = [
        VirtualInboundResponse.model_validate(r).model_dump()
        for r in rows
    ]

    return ResponseUtil.success(data=row_list)


# ── GET /{id} — 虚拟入库详情 ─────────────────────────────────────────────────

@virtual_inbound_controller.get(
    '/{record_id}',
    summary='虚拟入库详情',
    response_model=DataResponseModel,
)
async def get_virtual_inbound_detail(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    record_id: int = Path(..., description='虚拟入库记录ID'),
):
    """获取虚拟入库记录详情。"""
    from sqlalchemy import select
    from module_entrust.entity.do.reconciliation_do import VirtualInbound

    record = await query_db.scalar(
        select(VirtualInbound).where(VirtualInbound.id == record_id)
    )
    if not record:
        return ResponseUtil.failure(msg=f'虚拟入库记录不存在: id={record_id}')

    detail = VirtualInboundResponse.model_validate(record)
    return ResponseUtil.success(data=detail.model_dump())


# ── POST / — 手动创建虚拟入库记录 ────────────────────────────────────────────

@virtual_inbound_controller.post(
    '/',
    summary='手动创建虚拟入库记录',
    response_model=DataResponseModel,
)
async def create_virtual_inbound(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: VirtualInboundCreate,
):
    """手动创建虚拟入库记录。"""
    try:
        record_id = await VirtualInboundService.create_virtual_inbound(
            db=query_db,
            order_id=data.order_id,
            part_id=data.part_id or 0,
            inbound_type=data.inbound_type,
            quantity=data.quantity,
            unit_price=data.unit_price,
            anomaly_reason=data.anomaly_reason,
            responsible_party=data.responsible_party,
            re_shipment_id=data.re_shipment_id,
            production_anomaly_id=data.production_anomaly_id,
            created_by=current_user.user.user_id if current_user.user else 0,
        )
        return ResponseUtil.success(
            data={'id': record_id},
            msg='虚拟入库记录创建成功',
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── PUT /{id} — 修改虚拟入库记录 ─────────────────────────────────────────────

@virtual_inbound_controller.put(
    '/{record_id}',
    summary='修改虚拟入库记录',
    response_model=ResponseBaseModel,
)
async def update_virtual_inbound(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: VirtualInboundUpdate,
    record_id: int = Path(..., description='虚拟入库记录ID'),
):
    """修改虚拟入库记录（关联结算已确认时禁止修改）。"""
    try:
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return ResponseUtil.failure(msg='未提供任何更新字段')

        await VirtualInboundService.update_virtual_inbound(
            db=query_db,
            record_id=record_id,
            update_data=update_data,
            operator_id=current_user.user.user_id if current_user.user else 0,
        )
        return ResponseUtil.success(msg='虚拟入库记录更新成功')
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── DELETE /{id} — 删除虚拟入库记录 ──────────────────────────────────────────

@virtual_inbound_controller.delete(
    '/{record_id}',
    summary='删除虚拟入库记录',
    response_model=ResponseBaseModel,
)
async def delete_virtual_inbound(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    record_id: int = Path(..., description='虚拟入库记录ID'),
):
    """删除虚拟入库记录（关联结算已确认时禁止删除）。"""
    try:
        await VirtualInboundService.delete_virtual_inbound(
            db=query_db,
            record_id=record_id,
            operator_id=current_user.user.user_id if current_user.user else 0,
        )
        return ResponseUtil.success(msg='虚拟入库记录删除成功')
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))
