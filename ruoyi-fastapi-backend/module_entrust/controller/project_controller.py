"""
委外加工 — 项目管理 Controller
"""
import os
import uuid
from datetime import datetime
from pathlib import Path as FilePath
from typing import Annotated

from fastapi import Path, Query, Request, Response, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from module_admin.entity.vo.user_vo import CurrentUserModel
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from module_entrust.entity.do.entrust_do import EntrustProcessMethod, EntrustMold, EntrustPart, EntrustProject, EntrustOutsourceRequest, EntrustInvitation
from module_entrust.entity.vo.entrust_vo import (
    ProjectCreate, ProjectUpdate, ProjectQuery, ProjectResponse,
    MoldCreate, MoldResponse, PartCreate, PartUpdate, PartResponse,
    AttachmentResponse, BatchInquiryRequest,
)
from module_entrust.service.project_service import ProjectService
from module_entrust.service.match_service import MatchService
from utils.response_util import ResponseUtil

# 上传目录
UPLOADS_DIR = FilePath(__file__).resolve().parent.parent.parent.parent / 'uploads' / 'drawings'
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

project_controller = APIRouterPro(
    prefix='/entrust/project',
    order_num=10,
    tags=['委外管理-项目管理'],
    dependencies=[PreAuthDependency()],
)


@project_controller.get(
    '/list',
    summary='获取项目列表',
    response_model=PageResponseModel,
)
async def get_project_list(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    name: str = Query(default=None, description='项目名称'),
    customer: str = Query(default=None, description='客户名称'),
    status: str = Query(default=None, description='状态'),
    page_num: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
):
    query = ProjectQuery(name=name, customer=customer, status=status, page_num=page_num, page_size=page_size)
    rows, total = await ProjectService.get_project_list(query_db, query, current_user.user.user_id if current_user.user else 0)
    return ResponseUtil.success(rows=[r.model_dump() for r in rows], dict_content={'total': total})


# --- 工艺方法（必须在 /{project_id} 之前注册，否则会被当成 project_id 匹配）---

@project_controller.get(
    '/process-methods',
    summary='获取所有工艺方法',
    response_model=DataResponseModel,
)
async def get_process_methods(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
):
    stmt = select(EntrustProcessMethod).order_by(EntrustProcessMethod.id)
    result = (await query_db.execute(stmt)).scalars().all()
    return ResponseUtil.success(data=[{'id': r.id, 'name': r.name, 'category': r.category} for r in result])


# --- 项目提交 & 匹配 ---

@project_controller.post(
    '/{project_id}/submit',
    summary='提交项目（待审批）',
    response_model=DataResponseModel,
)
async def submit_project(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    project_id: int = Path(..., description='项目ID'),
):
    # 检查项目存在
    proj_stmt = select(EntrustProject).where(EntrustProject.id == project_id)
    project = (await query_db.execute(proj_stmt)).scalar_one_or_none()
    if not project:
        return ResponseUtil.failure(msg='项目不存在')
    if project.status not in ('drafted',):
        return ResponseUtil.failure(msg='当前状态不允许提交')

    # 更新状态为待审批
    project.status = 'pending_approval'
    await query_db.flush()
    await query_db.commit()
    await query_db.refresh(project)
    return ResponseUtil.success(data={
        'project_id': project_id,
        'status': project.status,
    }, msg='提交成功，等待审批')


@project_controller.post(
    '/{project_id}/approve',
    summary='审批通过项目（触发匹配）',
    response_model=DataResponseModel,
)
async def approve_project(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    project_id: int = Path(..., description='项目ID'),
):
    # 只有 admin/manager 可以审批
    if not set(current_user.roles or []) & {'admin', 'manager'}:
        return ResponseUtil.failure(msg='无审批权限')

    proj_stmt = select(EntrustProject).where(EntrustProject.id == project_id)
    project = (await query_db.execute(proj_stmt)).scalar_one_or_none()
    if not project:
        return ResponseUtil.failure(msg='项目不存在')
    if project.status not in ('pending_approval',):
        return ResponseUtil.failure(msg='当前状态不允许审批')

    # 更新状态为 confirmed
    project.status = 'confirmed'
    await query_db.flush()
    await query_db.commit()
    await query_db.refresh(project)

    # 执行匹配
    result = await MatchService.match_suppliers(query_db, project_id)
    return ResponseUtil.success(data={
        'project_id': project_id,
        'status': project.status,
        'match_result': result,
    }, msg='审批通过')


@project_controller.post(
    '/{project_id}/reject',
    summary='审批驳回项目',
    response_model=DataResponseModel,
)
async def reject_project(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    project_id: int = Path(..., description='项目ID'),
):
    # 只有 admin/manager 可以审批
    if not set(current_user.roles or []) & {'admin', 'manager'}:
        return ResponseUtil.failure(msg='无审批权限')

    proj_stmt = select(EntrustProject).where(EntrustProject.id == project_id)
    project = (await query_db.execute(proj_stmt)).scalar_one_or_none()
    if not project:
        return ResponseUtil.failure(msg='项目不存在')
    if project.status not in ('pending_approval',):
        return ResponseUtil.failure(msg='当前状态不允许驳回')

    # 驳回回草稿
    project.status = 'drafted'
    await query_db.flush()
    await query_db.commit()
    return ResponseUtil.success(data={
        'project_id': project_id,
        'status': project.status,
    }, msg='已驳回')


@project_controller.get(
    '/{project_id}/match-result',
    summary='获取项目匹配结果',
    response_model=DataResponseModel,
)
async def get_match_result(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    project_id: int = Path(..., description='项目ID'),
):
    result = await MatchService.match_suppliers(query_db, project_id)
    return ResponseUtil.success(data=result)


@project_controller.post(
    '/{project_id}/batch-inquiry',
    summary='从匹配结果批量创建询价单并发送',
    response_model=DataResponseModel,
)
async def batch_create_inquiry(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    project_id: int = Path(..., description='项目ID'),
    data: BatchInquiryRequest = None,
):
    """自动构建 scope_json 并创建询价单 + 发送邀请"""
    # 获取项目零件信息构建 scope_json
    parts_stmt = select(EntrustPart).where(EntrustPart.project_id == project_id)
    parts = (await query_db.execute(parts_stmt)).scalars().all()

    # 获取工艺方法名称映射
    pm_stmt = select(EntrustProcessMethod)
    pm_rows = (await query_db.execute(pm_stmt)).scalars().all()
    pm_map = {r.id: r.name for r in pm_rows}

    # 构建 scope_json
    scope_items = []
    for p in parts:
        item = {
            'part_id': p.id,
            'part_no': p.part_no,
            'part_name': p.part_name,
            'qty': p.qty,
            'material': p.material,
        }
        if p.process_method_ids:
            item['processes'] = [pm_map.get(pid, str(pid)) for pid in p.process_method_ids]
        scope_items.append(item)

    # 创建询价单
    inquiry = EntrustOutsourceRequest(
        project_id=project_id,
        title=data.title,
        scope_json=scope_items,
        deadline=data.deadline,
        status='sent',
        created_by=current_user.user.user_id if current_user.user else 0,
    )
    query_db.add(inquiry)
    await query_db.flush()

    # 创建邀请
    now = datetime.now()
    for sid in data.supplier_ids:
        inv = EntrustInvitation(
            request_id=inquiry.id,
            supplier_id=sid,
            status='sent',
            sent_at=now,
        )
        query_db.add(inv)

    await query_db.flush()
    await query_db.commit()
    await query_db.refresh(inquiry)

    return ResponseUtil.success(data={
        'inquiry_id': inquiry.id,
        'title': inquiry.title,
        'status': inquiry.status,
        'supplier_count': len(data.supplier_ids),
    }, msg='询价单已创建并发送')


@project_controller.get(
    '/{project_id}',
    summary='获取项目详情',
    response_model=DataResponseModel,
)
async def get_project_detail(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    project_id: int = Path(..., description='项目ID'),
):
    result = await ProjectService.get_project_detail(query_db, project_id)
    if not result:
        return ResponseUtil.failure(msg='项目不存在')
    return ResponseUtil.success(data=result.model_dump())


@project_controller.post(
    '',
    summary='创建项目',
    response_model=DataResponseModel,
)
async def create_project(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: ProjectCreate,
):
    result = await ProjectService.create_project(query_db, data, current_user.user.user_id if current_user.user else 0)
    return ResponseUtil.success(data=result.model_dump(), msg='创建成功')


@project_controller.put(
    '/{project_id}',
    summary='更新项目',
    response_model=DataResponseModel,
)
async def update_project(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    project_id: int = Path(..., description='项目ID'),
    data: ProjectUpdate = None,
):
    result = await ProjectService.update_project(query_db, project_id, data)
    if not result:
        return ResponseUtil.failure(msg='项目不存在')
    return ResponseUtil.success(data=result.model_dump(), msg='更新成功')


@project_controller.delete(
    '/{project_id}',
    summary='删除项目',
    response_model=ResponseBaseModel,
)
async def delete_project(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    project_id: int = Path(..., description='项目ID'),
):
    success = await ProjectService.delete_project(query_db, project_id)
    if not success:
        return ResponseUtil.failure(msg='项目不存在')
    return ResponseUtil.success(msg='删除成功')


# --- 模具套 ---

@project_controller.get(
    '/{project_id}/molds',
    summary='获取模具套列表',
    response_model=DataResponseModel,
)
async def get_molds(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    project_id: int = Path(..., description='项目ID'),
):
    result = await ProjectService.get_molds(query_db, project_id)
    return ResponseUtil.success(data=[r.model_dump() for r in result])


@project_controller.post(
    '/{project_id}/molds',
    summary='创建模具套',
    response_model=DataResponseModel,
)
async def create_mold(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    project_id: int = Path(..., description='项目ID'),
    data: MoldCreate = None,
):
    result = await ProjectService.create_mold(query_db, project_id, data)
    return ResponseUtil.success(data=result.model_dump(), msg='创建成功')


# --- 零件 ---

@project_controller.get(
    '/{project_id}/parts',
    summary='获取零件列表',
    response_model=DataResponseModel,
)
async def get_parts(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    project_id: int = Path(..., description='项目ID'),
):
    result = await ProjectService.get_parts(query_db, project_id)
    return ResponseUtil.success(data=[r.model_dump() for r in result])


@project_controller.post(
    '/{project_id}/parts',
    summary='创建零件',
    response_model=DataResponseModel,
)
async def create_part(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    project_id: int = Path(..., description='项目ID'),
    data: PartCreate = None,
):
    result = await ProjectService.create_part(query_db, project_id, data)
    return ResponseUtil.success(data=result.model_dump(), msg='创建成功')


@project_controller.put(
    '/parts/{part_id}',
    summary='更新零件',
    response_model=DataResponseModel,
)
async def update_part(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    part_id: int = Path(..., description='零件ID'),
    data: PartUpdate = None,
):
    result = await ProjectService.update_part(query_db, part_id, data)
    if not result:
        return ResponseUtil.failure(msg='零件不存在')
    return ResponseUtil.success(data=result.model_dump(), msg='更新成功')


@project_controller.delete(
    '/parts/{part_id}',
    summary='删除零件',
    response_model=ResponseBaseModel,
)
async def delete_part(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    part_id: int = Path(..., description='零件ID'),
):
    stmt = select(EntrustPart).where(EntrustPart.id == part_id)
    part = (await query_db.execute(stmt)).scalar_one_or_none()
    if not part:
        return ResponseUtil.failure(msg='零件不存在')
    await query_db.delete(part)
    await query_db.flush()
    await query_db.commit()
    return ResponseUtil.success(msg='删除成功')


# --- 删除模具 ---

@project_controller.delete(
    '/molds/{mold_id}',
    summary='删除模具套',
    response_model=ResponseBaseModel,
)
async def delete_mold(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    mold_id: int = Path(..., description='模具套ID'),
):
    stmt = select(EntrustMold).where(EntrustMold.id == mold_id)
    mold = (await query_db.execute(stmt)).scalar_one_or_none()
    if not mold:
        return ResponseUtil.failure(msg='模具套不存在')
    await query_db.delete(mold)
    await query_db.flush()
    await query_db.commit()
    return ResponseUtil.success(msg='删除成功')


# --- 附件/图纸上传 ---

@project_controller.post(
    '/{project_id}/attachments',
    summary='上传附件/图纸',
    response_model=DataResponseModel,
)
async def upload_attachment(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    project_id: int = Path(..., description='项目ID'),
    file: UploadFile = File(...),
    category: str = Form(default='drawing'),
    related_type: str = Form(default='project'),
    related_id: int = Form(default=None),
):
    # 保存文件
    ext = os.path.splitext(file.filename)[1] if file.filename else ''
    filename = f'{uuid.uuid4().hex}{ext}'
    file_path = UPLOADS_DIR / filename
    content = await file.read()
    with open(file_path, 'wb') as f:
        f.write(content)

    rid = related_id or project_id
    result = await ProjectService.add_attachment(
        query_db, related_type=related_type, related_id=rid,
        file_name=file.filename, file_path=str(file_path),
        file_size=len(content), mime_type=file.content_type,
        category=category, uploaded_by=current_user.user.user_id if current_user.user else 0,
    )
    return ResponseUtil.success(data=result.model_dump(), msg='上传成功')


@project_controller.get(
    '/{project_id}/attachments',
    summary='获取项目附件列表',
    response_model=DataResponseModel,
)
async def get_attachments(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    project_id: int = Path(..., description='项目ID'),
    related_type: str = Query(default='project'),
    related_id: int = Query(default=None),
):
    rid = related_id or project_id
    result = await ProjectService.get_attachments(query_db, related_type, rid)
    return ResponseUtil.success(data=[r.model_dump() for r in result])
