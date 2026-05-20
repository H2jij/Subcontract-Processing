"""
委外加工 — 加工方管理 Controller
"""
from typing import Annotated

from fastapi import Path, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from module_admin.entity.vo.user_vo import CurrentUserModel
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from module_entrust.entity.vo.entrust_vo import SupplierCreate, SupplierUpdate, SupplierQuery
from module_entrust.entity.do.entrust_do import EntrustSupplier
from module_entrust.service.supplier_service import SupplierService
from utils.response_util import ResponseUtil

supplier_controller = APIRouterPro(
    prefix='/entrust/supplier',
    order_num=11,
    tags=['委外管理-加工方管理'],
    dependencies=[PreAuthDependency()],
)


# --- 加工方视角：当前用户关联的加工方信息（必须在 /{supplier_id} 之前注册） ---

@supplier_controller.get(
    '/current/profile',
    summary='获取当前登录加工方的信息',
    response_model=DataResponseModel,
)
async def get_current_supplier(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
):
    """根据当前登录用户的 user_id 查询关联的加工方信息"""
    stmt = select(EntrustSupplier).where(EntrustSupplier.user_id == current_user.user.user_id)
    supplier = (await query_db.execute(stmt)).scalar_one_or_none()
    if not supplier:
        return ResponseUtil.failure(msg='当前用户未关联加工方')
    return ResponseUtil.success(data={
        'id': supplier.id,
        'name': supplier.name,
        'contact_name': supplier.contact_name,
        'contact_phone': supplier.contact_phone,
        'province': supplier.province,
        'city': supplier.city,
        'address': supplier.address,
        'status': supplier.status,
    })


@supplier_controller.get(
    '/list',
    summary='获取加工方列表',
    response_model=PageResponseModel,
)
async def get_supplier_list(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    name: str = Query(default=None, description='名称'),
    supplier_type: str = Query(default=None, description='类型：processor/material/other'),
    category: str = Query(default=None, description='分类'),
    status: str = Query(default=None, description='状态'),
    page_num: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
):
    query = SupplierQuery(name=name, supplier_type=supplier_type, category=category, status=status, page_num=page_num, page_size=page_size)
    rows, total = await SupplierService.get_supplier_list(query_db, query)
    return ResponseUtil.success(rows=[r.model_dump() for r in rows], dict_content={'total': total})


@supplier_controller.get(
    '/{supplier_id}',
    summary='获取加工方详情',
    response_model=DataResponseModel,
)
async def get_supplier_detail(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    supplier_id: int = Path(..., description='加工方ID'),
):
    result = await SupplierService.get_supplier_detail(query_db, supplier_id)
    if not result:
        return ResponseUtil.failure(msg='加工方不存在')
    return ResponseUtil.success(data=result.model_dump())


@supplier_controller.post(
    '',
    summary='创建加工方',
    response_model=DataResponseModel,
)
async def create_supplier(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: SupplierCreate,
):
    # 只有超级管理员能创建关联账号
    if 'admin' not in (current_user.roles or []):
        data.link_username = None
        data.link_password = None
    result = await SupplierService.create_supplier(query_db, data, current_user.user.user_id if current_user.user else 0)
    return ResponseUtil.success(data=result.model_dump(), msg='创建成功')


@supplier_controller.put(
    '/{supplier_id}',
    summary='更新加工方',
    response_model=DataResponseModel,
)
async def update_supplier(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    supplier_id: int = Path(..., description='加工方ID'),
    data: SupplierUpdate = None,
):
    # 只有超级管理员能创建关联账号
    if 'admin' not in (current_user.roles or []):
        data.link_username = None
        data.link_password = None
    result = await SupplierService.update_supplier(query_db, supplier_id, data)
    if not result:
        return ResponseUtil.failure(msg='加工方不存在')
    return ResponseUtil.success(data=result.model_dump(), msg='更新成功')


@supplier_controller.delete(
    '/{supplier_id}',
    summary='删除加工方',
    response_model=ResponseBaseModel,
)
async def delete_supplier(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    supplier_id: int = Path(..., description='加工方ID'),
):
    success = await SupplierService.delete_supplier(query_db, supplier_id)
    if not success:
        return ResponseUtil.failure(msg='加工方不存在')
    return ResponseUtil.success(msg='删除成功')


# --- 能力标签 ---

@supplier_controller.get(
    '/{supplier_id}/capabilities',
    summary='获取加工方能力标签',
    response_model=DataResponseModel,
)
async def get_capabilities(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    supplier_id: int = Path(..., description='加工方ID'),
):
    result = await SupplierService.get_capabilities(query_db, supplier_id)
    return ResponseUtil.success(data=result)


@supplier_controller.put(
    '/{supplier_id}/capabilities',
    summary='设置加工方能力标签',
    response_model=ResponseBaseModel,
)
async def set_capabilities(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    supplier_id: int = Path(..., description='加工方ID'),
    process_names: list[str] = None,
):
    await SupplierService.set_capabilities(query_db, supplier_id, process_names or [])
    return ResponseUtil.success(msg='更新成功')


# --- 关联用户 ---

class LinkUserRequest(BaseModel):
    user_id: int

@supplier_controller.post(
    '/{supplier_id}/link-user',
    summary='关联加工方登录账号',
    response_model=ResponseBaseModel,
)
async def link_user(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    supplier_id: int = Path(..., description='加工方ID'),
    data: LinkUserRequest = None,
):
    stmt = select(EntrustSupplier).where(EntrustSupplier.id == supplier_id)
    supplier = (await query_db.execute(stmt)).scalar_one_or_none()
    if not supplier:
        return ResponseUtil.failure(msg='加工方不存在')
    supplier.user_id = data.user_id
    await query_db.flush()
    await query_db.commit()
    return ResponseUtil.success(msg='关联成功')
