"""
对账系统 — 结算明细 Controller
=========================================
API 路由：
  GET  /entrust/settlement/list              — 结算明细列表（分页+筛选）
  GET  /entrust/settlement/{id}              — 结算明细详情
  PUT  /entrust/settlement/{id}/line-items   — 编辑行项（draft 状态）
  POST /entrust/settlement/{id}/finalize     — 确认结算明细
  GET  /entrust/settlement/{id}/pdf          — 生成/下载 PDF 结算单

Requirements covered: 10.1, 10.2, 10.5, 10.6, 11.1, 11.4
"""
import io
import os
from typing import Annotated, Optional
from urllib.parse import quote

from fastapi import Path, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from exceptions.exception import ServiceException
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_entrust.entity.do.reconciliation_do import (
    PaymentEvidence,
    SettlementDetail,
    SettlementLineItem,
)
from module_entrust.entity.vo.reconciliation_vo import (
    SettlementBriefResponse,
    SettlementDetailResponse,
    SettlementLineItemResponse,
    SettlementLineItemUpdateRequest,
)
from module_entrust.service.reconciliation_pdf_service import (
    ReconciliationPdfService,
)
from module_entrust.service.settlement_service import SettlementService
from utils.response_util import ResponseUtil

settlement_controller = APIRouterPro(
    prefix='/entrust/settlement',
    order_num=24,
    tags=['结算明细'],
    dependencies=[PreAuthDependency()],
)


# ── GET /list — 结算明细列表（分页+筛选） ────────────────────────────────────

@settlement_controller.get(
    '/list',
    summary='结算明细列表',
    response_model=PageResponseModel,
)
async def get_settlement_list(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    supplier_id: Optional[int] = Query(default=None, description='供应商ID'),
    order_no: Optional[str] = Query(default=None, description='委外单号'),
    status: Optional[str] = Query(default=None, description='状态: draft/finalized'),
    page_num: int = Query(default=1, ge=1, description='页码'),
    page_size: int = Query(default=10, ge=1, le=100, description='每页条数'),
):
    """结算明细列表，支持按供应商、委外单号、状态筛选，分页返回。"""
    stmt = select(SettlementDetail)
    count_stmt = select(func.count()).select_from(SettlementDetail)

    # 筛选条件
    filters = []
    if supplier_id is not None:
        filters.append(SettlementDetail.supplier_id == supplier_id)
    if order_no is not None:
        filters.append(SettlementDetail.order_no.ilike(f'%{order_no}%'))
    if status is not None:
        filters.append(SettlementDetail.status == status)

    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    # 总数
    total = (await query_db.execute(count_stmt)).scalar() or 0

    # 分页 + 排序
    stmt = stmt.order_by(SettlementDetail.created_at.desc())
    stmt = stmt.offset((page_num - 1) * page_size).limit(page_size)

    rows = (await query_db.execute(stmt)).scalars().all()

    # 转换为响应模型
    row_list = [
        SettlementBriefResponse.model_validate(r).model_dump()
        for r in rows
    ]

    return ResponseUtil.success(
        rows=row_list,
        dict_content={'total': total, 'page_num': page_num, 'page_size': page_size},
    )


# ── GET /{id} — 结算明细详情 ─────────────────────────────────────────────────

@settlement_controller.get(
    '/{settlement_id}',
    summary='结算明细详情',
    response_model=DataResponseModel,
)
async def get_settlement_detail(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    settlement_id: int = Path(..., description='结算明细ID'),
):
    """获取结算明细详情，包含所有行项及关联支付凭证。"""
    settlement = await query_db.scalar(
        select(SettlementDetail).where(
            SettlementDetail.id == settlement_id
        )
    )
    if not settlement:
        return ResponseUtil.failure(msg=f'结算明细不存在: id={settlement_id}')

    # 查询行项
    line_items_result = await query_db.execute(
        select(SettlementLineItem)
        .where(SettlementLineItem.settlement_id == settlement_id)
        .order_by(SettlementLineItem.id.asc())
    )
    line_items = line_items_result.scalars().all()

    # 查询关联支付凭证
    evidences_result = await query_db.execute(
        select(PaymentEvidence)
        .where(
            PaymentEvidence.related_type == 'settlement_detail',
            PaymentEvidence.related_id == settlement_id,
        )
        .order_by(PaymentEvidence.id.asc())
    )
    evidences = evidences_result.scalars().all()

    # 构建响应
    detail = SettlementDetailResponse.model_validate(settlement)
    detail.line_items = [
        SettlementLineItemResponse.model_validate(item)
        for item in line_items
    ]
    from module_entrust.entity.vo.reconciliation_vo import EvidenceUploadResponse
    detail.evidences = [
        EvidenceUploadResponse.model_validate(ev)
        for ev in evidences
    ]

    return ResponseUtil.success(data=detail.model_dump())


# ── PUT /{id}/line-items — 编辑行项（draft 状态） ────────────────────────────

@settlement_controller.put(
    '/{settlement_id}/line-items',
    summary='编辑结算行项',
    response_model=ResponseBaseModel,
)
async def update_settlement_line_item(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: SettlementLineItemUpdateRequest,
    settlement_id: int = Path(..., description='结算明细ID'),
    item_id: int = Query(..., description='行项ID'),
):
    """
    编辑结算行项（仅 draft 状态允许）。
    通过 query param item_id 指定要编辑的行项。
    """
    try:
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return ResponseUtil.failure(msg='未提供任何更新字段')

        await SettlementService.update_line_item(
            db=query_db,
            settlement_id=settlement_id,
            item_id=item_id,
            data=update_data,
        )
        return ResponseUtil.success(msg='结算行项更新成功')
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── POST /{id}/finalize — 确认结算明细 ───────────────────────────────────────

@settlement_controller.post(
    '/{settlement_id}/finalize',
    summary='确认结算明细',
    response_model=DataResponseModel,
)
async def finalize_settlement(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    settlement_id: int = Path(..., description='结算明细ID'),
    statement_id: Optional[int] = Query(default=None, description='关联对账单ID（可选）'),
):
    """确认结算明细，状态从 draft 变为 finalized。"""
    try:
        operator_id = current_user.user.user_id if current_user.user else 0
        result = await SettlementService.finalize_settlement(
            db=query_db,
            settlement_id=settlement_id,
            operator_id=operator_id,
            statement_id=statement_id,
        )
        return ResponseUtil.success(data=result, msg='结算明细确认成功')
    except (ServiceException, ValueError) as e:
        msg = str(e.message) if hasattr(e, 'message') else str(e)
        return ResponseUtil.failure(msg=msg)


# ── GET /{id}/pdf — 生成/下载 PDF 结算单 ─────────────────────────────────────

@settlement_controller.get(
    '/{settlement_id}/pdf',
    summary='生成/下载 PDF 结算单',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回 PDF 文件',
            'content': {
                'application/pdf': {},
            },
        }
    },
)
async def download_settlement_pdf(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    settlement_id: int = Path(..., description='结算明细ID'),
) -> Response:
    """生成结算明细 PDF 并以流式响应返回下载。"""
    try:
        operator_id = current_user.user.user_id if current_user.user else 0
        operator_name = ''
        if current_user.user and current_user.user.nick_name:
            operator_name = current_user.user.nick_name

        pdf_path = await ReconciliationPdfService.generate_settlement_pdf(
            db=query_db,
            settlement_id=settlement_id,
            operator_id=operator_id,
            operator_name=operator_name or None,
        )

        # 读取 PDF 文件并返回 StreamingResponse
        file_name = os.path.basename(pdf_path)
        encoded_name = quote(file_name, safe='')

        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type='application/pdf',
            headers={
                'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_name}",
            },
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))
