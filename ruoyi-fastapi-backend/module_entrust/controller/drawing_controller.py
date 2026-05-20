"""
委外加工 — 图纸管理 Controller
"""
import os
from typing import Annotated, Optional

from fastapi import Path, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel
from module_entrust.entity.vo.entrust_vo import (
    DrawingLookupRequest, DrawingSplitRequest, DrawingPreviewResponse,
)
from module_entrust.service import drawing_service
from utils.response_util import ResponseUtil

drawing_controller = APIRouterPro(
    prefix='/entrust/drawing',
    order_num=13,
    tags=['委外管理-图纸管理'],
    dependencies=[PreAuthDependency()],
)


@drawing_controller.get(
    '/list',
    summary='图纸列表',
    response_model=PageResponseModel,
)
async def list_drawings(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    mold_code: Optional[str] = Query(default=None, description='模具编号'),
    part_code: Optional[str] = Query(default=None, description='零件编号'),
    page_num: int = Query(default=1, description='页码'),
    page_size: int = Query(default=20, description='每页条数'),
):
    rows, total = await drawing_service.list_drawings(
        query_db, mold_code=mold_code, part_code=part_code,
        page=page_num, page_size=page_size,
    )
    data = []
    for r in rows:
        item = {
            'id': r.id,
            'moldCode': r.mold_code,
            'partCode': r.part_code,
            'fileName': r.file_name,
            'filePath': r.file_path,
            'fileSizeKb': r.file_size_kb,
            'version': r.version,
            'isLatest': r.is_latest,
            'sourceType': r.source_type,
            'splitAt': r.split_at.isoformat() if r.split_at else None,
            'status': r.status,
            'remark': r.remark,
            'createdAt': r.created_at.isoformat() if r.created_at else None,
        }
        data.append(item)
    return ResponseUtil.success(data=data, dict_content={'total': total, 'page_num': page_num, 'page_size': page_size})


@drawing_controller.post(
    '/lookup',
    summary='批量查找图纸（询价时调用）',
    response_model=DataResponseModel,
)
async def lookup_drawings(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    req: DrawingLookupRequest,
):
    results = await drawing_service.lookup_drawings(
        query_db, req.mold_code, req.part_codes,
    )
    return ResponseUtil.success(data=results)


@drawing_controller.post(
    '/split',
    summary='手动触发拆图',
    response_model=DataResponseModel,
)
async def manual_split(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    req: DrawingSplitRequest,
):
    try:
        results = await drawing_service.manual_split(
            query_db, req.mold_code, req.part_codes,
        )
        return ResponseUtil.success(data=results)
    except (ValueError, FileNotFoundError) as e:
        return ResponseUtil.failure(msg=str(e))


@drawing_controller.get(
    '/preview/{mold_code}',
    summary='预览原图中有哪些可拆的零件编号',
    response_model=DataResponseModel,
)
async def preview_assembly(
    mold_code: str = Path(..., description='模具编号'),
):
    result = await drawing_service.preview_assembly(mold_code)
    return ResponseUtil.success(data=result)


@drawing_controller.get(
    '/download/{drawing_id}',
    summary='下载图纸文件',
)
async def download_drawing(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    drawing_id: int = Path(..., description='图纸ID'),
):
    drawing = await drawing_service.get_drawing_by_id(query_db, drawing_id)
    if not drawing or drawing.status != 'available':
        return ResponseUtil.failure(msg='图纸不存在或不可用')

    # 用绝对路径解析文件位置
    from module_entrust.service.drawing_service import PART_DRAWINGS_DIR, PART_DRAWINGS_REL
    rel_path = drawing.file_path
    if rel_path.startswith(PART_DRAWINGS_REL):
        rel_path = rel_path[len(PART_DRAWINGS_REL) + 1:]
    abs_path = os.path.join(PART_DRAWINGS_DIR, rel_path)

    if not os.path.exists(abs_path):
        return ResponseUtil.failure(msg='图纸文件不存在')

    return FileResponse(
        path=abs_path,
        filename=drawing.file_name,
        media_type='application/octet-stream',
    )


@drawing_controller.delete(
    '/{drawing_id}',
    summary='删除图纸',
    response_model=DataResponseModel,
)
async def delete_drawing(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    drawing_id: int = Path(..., description='图纸ID'),
):
    ok = await drawing_service.delete_drawing(query_db, drawing_id)
    if ok:
        return ResponseUtil.success(msg='删除成功')
    return ResponseUtil.failure(msg='图纸不存在')
