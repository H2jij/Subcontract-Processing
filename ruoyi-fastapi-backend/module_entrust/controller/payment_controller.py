"""
对账系统 — 付款管理 Controller
=========================================
API 路由：
  GET  /entrust/payment/requests              — 付款申请列表
  GET  /entrust/payment/requests/{id}         — 付款申请详情
  POST /entrust/payment/requests/{id}/records — 录入付款记录
  GET  /entrust/payment/requests/{id}/records — 查看付款记录
  POST /entrust/payment/evidences/upload      — 上传支付凭证
  GET  /entrust/payment/evidences/{id}        — 查看凭证
  DELETE /entrust/payment/evidences/{id}      — 删除凭证

Requirements covered: 5.2, 5.3, 5.4, 5.7, 12.1, 12.2, 12.3
"""
from typing import Annotated, Optional

from fastapi import Path, Query, UploadFile, File, Form
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
    PaymentRecord,
    PaymentRequest,
)
from module_entrust.entity.vo.reconciliation_vo import (
    EvidenceUploadResponse,
    PaymentRecordCreateRequest,
    PaymentRecordResponse,
    PaymentRequestResponse,
)
from module_entrust.service.payment_evidence_service import PaymentEvidenceService
from module_entrust.service.payment_service import PaymentService
from utils.response_util import ResponseUtil

payment_controller = APIRouterPro(
    prefix='/entrust/payment',
    order_num=23,
    tags=['付款管理'],
    dependencies=[PreAuthDependency()],
)


# ── GET /requests — 付款申请列表 ─────────────────────────────────────────────

@payment_controller.get(
    '/requests',
    summary='付款申请列表',
    response_model=PageResponseModel,
)
async def get_payment_request_list(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    supplier_id: Optional[int] = Query(default=None, description='供应商ID'),
    payment_status: Optional[str] = Query(default=None, description='付款状态: pending_payment/partially_paid/paid'),
    page_num: int = Query(default=1, ge=1, description='页码'),
    page_size: int = Query(default=10, ge=1, le=100, description='每页条数'),
):
    """付款申请列表，支持按供应商、付款状态筛选，分页返回。"""
    stmt = select(PaymentRequest)
    count_stmt = select(func.count()).select_from(PaymentRequest)

    # 筛选条件
    filters = []
    if supplier_id is not None:
        filters.append(PaymentRequest.supplier_id == supplier_id)
    if payment_status is not None:
        filters.append(PaymentRequest.payment_status == payment_status)

    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    # 总数
    total = (await query_db.execute(count_stmt)).scalar() or 0

    # 分页 + 排序
    stmt = stmt.order_by(PaymentRequest.created_at.desc())
    stmt = stmt.offset((page_num - 1) * page_size).limit(page_size)

    rows = (await query_db.execute(stmt)).scalars().all()

    # 转换为响应模型
    row_list = [
        PaymentRequestResponse.model_validate(r).model_dump()
        for r in rows
    ]

    return ResponseUtil.success(
        rows=row_list,
        dict_content={'total': total, 'page_num': page_num, 'page_size': page_size},
    )


# ── GET /requests/{id} — 付款申请详情 ────────────────────────────────────────

@payment_controller.get(
    '/requests/{request_id}',
    summary='付款申请详情',
    response_model=DataResponseModel,
)
async def get_payment_request_detail(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    request_id: int = Path(..., description='付款申请ID'),
):
    """获取付款申请详情。"""
    pr = await query_db.scalar(
        select(PaymentRequest).where(PaymentRequest.id == request_id)
    )
    if not pr:
        return ResponseUtil.failure(msg=f'付款申请不存在: id={request_id}')

    detail = PaymentRequestResponse.model_validate(pr)
    return ResponseUtil.success(data=detail.model_dump())


# ── POST /requests/{id}/records — 录入付款记录 ───────────────────────────────

@payment_controller.post(
    '/requests/{request_id}/records',
    summary='录入付款记录',
    response_model=DataResponseModel,
)
async def create_payment_record(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: PaymentRecordCreateRequest,
    request_id: int = Path(..., description='付款申请ID'),
):
    """录入付款记录，自动更新付款状态。"""
    try:
        record_id = await PaymentService.record_payment(
            db=query_db,
            request_id=request_id,
            amount=data.payment_amount,
            payment_date=data.payment_date,
            bank_ref=data.bank_reference,
            created_by=current_user.user.user_id if current_user.user else 0,
        )
        return ResponseUtil.success(
            data={'record_id': record_id},
            msg='付款记录录入成功',
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── GET /requests/{id}/records — 查看付款记录 ────────────────────────────────

@payment_controller.get(
    '/requests/{request_id}/records',
    summary='查看付款记录',
    response_model=DataResponseModel,
)
async def get_payment_records(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    request_id: int = Path(..., description='付款申请ID'),
):
    """查看某付款申请下的所有付款记录。"""
    # 验证付款申请存在
    pr = await query_db.scalar(
        select(PaymentRequest).where(PaymentRequest.id == request_id)
    )
    if not pr:
        return ResponseUtil.failure(msg=f'付款申请不存在: id={request_id}')

    # 查询付款记录
    records_result = await query_db.execute(
        select(PaymentRecord)
        .where(PaymentRecord.request_id == request_id)
        .order_by(PaymentRecord.created_at.desc())
    )
    records = records_result.scalars().all()

    # 计算汇总
    from decimal import Decimal
    total_paid = sum(
        (Decimal(str(r.payment_amount)) if r.payment_amount else Decimal('0'))
        for r in records
    )
    payable_amount = Decimal(str(pr.payable_amount)) if pr.payable_amount else Decimal('0')
    remaining = payable_amount - total_paid

    record_list = [
        PaymentRecordResponse.model_validate(r).model_dump()
        for r in records
    ]

    result = {
        'records': record_list,
        'total_paid': str(total_paid),
        'payable_amount': str(payable_amount),
        'remaining_amount': str(remaining),
        'payment_status': pr.payment_status,
    }

    return ResponseUtil.success(data=result)


# ── POST /evidences/upload — 上传支付凭证 ────────────────────────────────────

@payment_controller.post(
    '/evidences/upload',
    summary='上传支付凭证',
    response_model=DataResponseModel,
)
async def upload_evidence(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    file: UploadFile = File(..., description='凭证文件（jpg/png/pdf/jpeg）'),
    related_type: str = Form(..., description='关联类型: payment_record/settlement_detail'),
    related_id: int = Form(..., description='关联ID'),
):
    """上传支付凭证，关联到付款记录或结算明细。"""
    try:
        evidence = await PaymentEvidenceService.upload_evidence(
            db=query_db,
            file=file,
            related_type=related_type,
            related_id=related_id,
            uploaded_by=current_user.user.user_id if current_user.user else 0,
        )
        result = EvidenceUploadResponse.model_validate(evidence)
        return ResponseUtil.success(
            data=result.model_dump(),
            msg='凭证上传成功',
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── GET /evidences/{id} — 查看凭证 ───────────────────────────────────────────

@payment_controller.get(
    '/evidences/{evidence_id}',
    summary='查看凭证',
    response_model=DataResponseModel,
)
async def get_evidence_detail(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    evidence_id: int = Path(..., description='凭证ID'),
):
    """查看支付凭证详情。"""
    evidence = await query_db.scalar(
        select(PaymentEvidence).where(PaymentEvidence.id == evidence_id)
    )
    if not evidence:
        return ResponseUtil.failure(msg=f'支付凭证不存在: id={evidence_id}')

    result = EvidenceUploadResponse.model_validate(evidence)
    return ResponseUtil.success(data=result.model_dump())


# ── DELETE /evidences/{id} — 删除凭证 ────────────────────────────────────────

@payment_controller.delete(
    '/evidences/{evidence_id}',
    summary='删除凭证',
    response_model=ResponseBaseModel,
)
async def delete_evidence(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    evidence_id: int = Path(..., description='凭证ID'),
):
    """删除支付凭证（非 finalized 状态允许）。"""
    try:
        await PaymentEvidenceService.delete_evidence(
            db=query_db,
            evidence_id=evidence_id,
        )
        return ResponseUtil.success(msg='凭证删除成功')
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))
