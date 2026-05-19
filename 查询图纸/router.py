# -*- coding: utf-8 -*-
"""
图纸查询 API 路由

所有接口只读，不修改任何数据。
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

import crud
from models import DwgSingleResponse, DwgListResponse, DwgRecord

router = APIRouter(prefix="/dwg", tags=["图纸查询"])


# ==================== 接口1：根据 group_uid 查询 ====================

@router.get(
    "/by_group_uid",
    response_model=DwgSingleResponse,
    summary="根据子订单ID查图纸",
    description="""
    根据 group_uid 查询对应的图纸文件路径。

    group_uid 是子订单的唯一标识（UUID 格式），
    一个 group_uid 对应一份拆图文件。
    """,
)
def get_by_group_uid(
    group_uid: str = Query(..., description="子订单ID（UUID）", example="550e8400-e29b-41d4-a716-446655440000"),
):
    row = crud.query_by_group_uid(group_uid)
    if not row:
        return DwgSingleResponse(
            success=False,
            data=None,
            message=f"未找到 group_uid={group_uid} 的图纸记录",
        )
    return DwgSingleResponse(success=True, data=DwgRecord(**row))


# ==================== 接口2：根据请购单号查询 ====================

@router.get(
    "/by_no",
    response_model=DwgListResponse,
    summary="根据请购单号查所有图纸",
    description="""
    根据请购单编号（no）查询该订单下的所有图纸。

    一个请购单下可能有多个供应商分组，每组对应一份图纸。
    """,
)
def get_by_no(
    no: str = Query(..., description="请购单编号", example="WJJQG202512080005"),
):
    rows = crud.query_by_no(no)
    return DwgListResponse(
        success=True,
        total=len(rows),
        page=1,
        page_size=len(rows),
        data=[DwgRecord(**r) for r in rows],
    )


# ==================== 接口3：根据模具编号查询 ====================

@router.get(
    "/by_order_code",
    response_model=DwgListResponse,
    summary="根据模具编号查图纸",
    description="""
    根据模具订单编号查询相关图纸。

    支持两种格式：M250247-P6 或 M250247.P6，自动兼容。
    也可以只传项目号 M250247，会返回该项目下所有模具的图纸。
    """,
)
def get_by_order_code(
    order_code: str = Query(..., description="模具编号", example="M250247-P6"),
):
    rows = crud.query_by_order_code(order_code)
    return DwgListResponse(
        success=True,
        total=len(rows),
        page=1,
        page_size=len(rows),
        data=[DwgRecord(**r) for r in rows],
    )


# ==================== 接口4：分页列表 ====================

@router.get(
    "/list",
    response_model=DwgListResponse,
    summary="分页查询图纸列表",
    description="""
    分页获取所有图纸记录，支持按状态过滤、只看有图纸文件的记录。
    """,
)
def get_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    only_with_dwg: bool = Query(False, description="只返回已有图纸文件的记录"),
    status: Optional[str] = Query(None, description="状态过滤，如：待拆单 / 待接单 / 跟单 / 加工完成"),
):
    rows, total = crud.query_list(
        page=page,
        page_size=page_size,
        only_with_dwg=only_with_dwg,
        status=status,
    )
    return DwgListResponse(
        success=True,
        total=total,
        page=page,
        page_size=page_size,
        data=[DwgRecord(**r) for r in rows],
    )


# ==================== 接口5：多条件搜索 ====================

@router.get(
    "/search",
    response_model=DwgListResponse,
    summary="多条件搜索图纸",
    description="""
    支持以下条件组合查询（所有参数可选，多个条件同时满足）：

    - **no**：请购单编号（模糊匹配）
    - **order_code**：模具编号，如 M250247 或 M250247-P6（模糊匹配）
    - **supplier_code**：供应商编码（精确匹配）
    - **status**：状态（精确匹配）
    - **created_after**：创建时间起始，格式 YYYY-MM-DD
    - **created_before**：创建时间截止，格式 YYYY-MM-DD
    - **only_with_dwg**：只看有图纸文件的记录
    """,
)
def search(
    no: Optional[str] = Query(None, description="请购单编号（模糊）", example="WJJQG2025"),
    order_code: Optional[str] = Query(None, description="模具编号（模糊）", example="M250247"),
    supplier_code: Optional[str] = Query(None, description="供应商编码（精确）", example="SUP001"),
    status: Optional[str] = Query(None, description="状态", example="跟单"),
    created_after: Optional[str] = Query(None, description="创建时间起始 YYYY-MM-DD", example="2025-01-01"),
    created_before: Optional[str] = Query(None, description="创建时间截止 YYYY-MM-DD", example="2025-12-31"),
    only_with_dwg: bool = Query(False, description="只返回有图纸文件的记录"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    rows, total = crud.query_search(
        no=no,
        order_code=order_code,
        supplier_code=supplier_code,
        status=status,
        created_after=created_after,
        created_before=created_before,
        only_with_dwg=only_with_dwg,
        page=page,
        page_size=page_size,
    )
    return DwgListResponse(
        success=True,
        total=total,
        page=page,
        page_size=page_size,
        data=[DwgRecord(**r) for r in rows],
    )
