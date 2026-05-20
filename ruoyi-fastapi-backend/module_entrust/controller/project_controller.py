"""
委外加工 — 项目管理 Controller
"""
import asyncio
import threading
from datetime import datetime
from typing import Annotated

from fastapi import Path, Query, Request, Response
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

import logging as _logging
_bg_logger = _logging.getLogger(__name__)


async def _background_match_and_split(project_id: int):
    """后台任务：先匹配供应商，再拆图（使用独立的 engine，不阻塞主事件循环）"""
    from config.database import create_async_db_engine, create_async_session_local
    engine = create_async_db_engine(echo=False)
    session_local = create_async_session_local(engine)
    try:
        async with session_local() as db:
            # 1. 匹配供应商
            try:
                _bg_logger.info(f'[后台] 项目 {project_id} 开始匹配供应商')
                result = await MatchService.match_suppliers(db, project_id)
                _bg_logger.info(f'[后台] 项目 {project_id} 匹配完成')
            except Exception as e:
                _bg_logger.error(f'[后台] 项目 {project_id} 匹配异常: {e}', exc_info=True)

            # 2. 拆图
            try:
                _bg_logger.info(f'[后台] 项目 {project_id} 开始拆图')

                proj = (await db.execute(
                    select(EntrustProject).where(EntrustProject.id == project_id)
                )).scalar_one_or_none()
                if proj:
                    proj.drawing_status = 'splitting'
                    await db.commit()

                from module_entrust.service.drawing_service import ensure_project_drawings
                split_result = await ensure_project_drawings(db, project_id)
                await db.commit()

                proj = (await db.execute(
                    select(EntrustProject).where(EntrustProject.id == project_id)
                )).scalar_one_or_none()
                if proj:
                    proj.drawing_status = 'done'
                    proj.drawing_message = str(split_result.get('details', ''))
                    await db.commit()

                _bg_logger.info(f'[后台] 项目 {project_id} 拆图完成: {split_result}')

            except Exception as e:
                _bg_logger.error(f'[后台] 项目 {project_id} 拆图异常: {e}', exc_info=True)
                try:
                    proj = (await db.execute(
                        select(EntrustProject).where(EntrustProject.id == project_id)
                    )).scalar_one_or_none()
                    if proj:
                        proj.drawing_status = 'error'
                        proj.drawing_message = str(e)[:500]
                        await db.commit()
                except Exception:
                    pass
    finally:
        await engine.dispose()


def _run_background_in_thread(project_id: int):
    """在独立线程中运行后台任务，使用自己的事件循环，不阻塞主事件循环"""
    _bg_logger.info(f'[后台线程] 启动独立线程处理项目 {project_id}')
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_background_match_and_split(project_id))
        finally:
            loop.close()
        _bg_logger.info(f'[后台线程] 项目 {project_id} 处理完成')
    except Exception as e:
        _bg_logger.error(f'[后台线程] 项目 {project_id} 线程异常: {e}', exc_info=True)

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
    summary='决策：确认项目并触发匹配',
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
        return ResponseUtil.failure(msg='当前状态不允许操作')

    # 直接确认项目（无需审批）
    project.status = 'confirmed'
    project.confirmed_at = datetime.now()
    await query_db.flush()
    await query_db.commit()

    # 匹配 + 拆图在独立线程中执行，不阻塞主事件循环
    t = threading.Thread(target=_run_background_in_thread, args=(project_id,), daemon=True)
    t.start()
    _bg_logger.info(f'[决策] 项目 {project_id} 已确认，后台线程已启动 (thread={t.name})')

    return ResponseUtil.success(data={
        'project_id': project_id,
        'status': 'confirmed',
    }, msg='项目已确认，匹配和拆图后台进行中')


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

    # 获取项目模具映射 (mold_id → mold_name)
    molds_stmt = select(EntrustMold).where(EntrustMold.project_id == project_id)
    molds = (await query_db.execute(molds_stmt)).scalars().all()
    mold_map = {m.id: m for m in molds}
    from module_entrust.service.drawing_service import normalize_mold_code

    # 构建 scope_json
    scope_items = []
    for p in parts:
        # 查零件关联的模具号
        mold_code = ''
        if p.mold_id and p.mold_id in mold_map:
            mold_code = normalize_mold_code(mold_map[p.mold_id].name or '')
        elif molds:
            mold_code = normalize_mold_code(molds[0].name or '')

        item = {
            'part_id': p.id,
            'part_no': p.part_no,
            'part_name': p.part_name,
            'qty': p.qty,
            'material': p.material,
            'mold_code': mold_code,
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
