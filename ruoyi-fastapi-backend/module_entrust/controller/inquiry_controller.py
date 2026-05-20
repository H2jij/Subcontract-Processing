"""
委外加工 — 询价/报价 Controller
"""
from typing import Annotated, Optional

from fastapi import Path, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import io

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from module_admin.entity.vo.user_vo import CurrentUserModel
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from module_entrust.entity.vo.entrust_vo import (
    InquiryCreate, InquirySend, InquiryQuery, QuoteSubmit,
    QuoteDraftSave, QuoteDecline,
    SendContractRequest, BatchSendContractRequest,
)
from module_entrust.entity.do.entrust_do import EntrustInvitation, EntrustOutsourceRequest, EntrustSupplier
from module_entrust.service.inquiry_service import InquiryService
from module_entrust.service.contract_service import ContractService
from utils.response_util import ResponseUtil
from sqlalchemy import select

inquiry_controller = APIRouterPro(
    prefix='/entrust/inquiry',
    order_num=12,
    tags=['委外管理-询价管理'],
    dependencies=[PreAuthDependency()],
)


@inquiry_controller.get(
    '/my-invitations',
    summary='加工方查看收到的询价邀请',
    response_model=DataResponseModel,
)
async def get_my_invitations(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    status: str = Query(default=None, description='邀请状态'),
):
    """加工方角色：查看自己收到的询价邀请列表（含完整询价单信息）"""
    sup_stmt = select(EntrustSupplier).where(EntrustSupplier.user_id == current_user.user.user_id)
    supplier = (await query_db.execute(sup_stmt)).scalar_one_or_none()
    if not supplier:
        return ResponseUtil.success(data=[])
    supplier_id = supplier.id

    inv_stmt = select(EntrustInvitation).where(EntrustInvitation.supplier_id == supplier_id)
    if status:
        inv_stmt = inv_stmt.where(EntrustInvitation.status == status)
    inv_stmt = inv_stmt.order_by(EntrustInvitation.sent_at.desc())
    invitations = (await query_db.execute(inv_stmt)).scalars().all()

    result = []
    for inv in invitations:
        req_stmt = select(EntrustOutsourceRequest).where(EntrustOutsourceRequest.id == inv.request_id)
        req = (await query_db.execute(req_stmt)).scalar_one_or_none()
        if req:
            result.append({
                'invitation_id': inv.id,
                'inquiry_id': req.id,
                'title': req.title,
                'scope_json': req.scope_json,
                'deadline': req.deadline.isoformat() if req.deadline else None,
                'inquiry_status': req.status,
                'invitation_status': inv.status,
                'sent_at': inv.sent_at.isoformat() if inv.sent_at else None,
                'quoted_at': inv.quoted_at.isoformat() if inv.quoted_at else None,
                'decline_remark': inv.decline_remark,
                'draft_quote_json': inv.draft_quote_json,
                # 完整询价单信息
                'customer_name': req.customer_name,
                'customer_contact': req.customer_contact,
                'customer_phone': req.customer_phone,
                'order_no': req.order_no,
                'inquiry_date': req.inquiry_date.isoformat() if req.inquiry_date else None,
                'delivery_date': req.delivery_date.isoformat() if req.delivery_date else None,
                'created_by': req.created_by,
                # 加工方自身信息
                'supplier_name': supplier.name,
                'supplier_contact': supplier.contact_name,
                'supplier_phone': supplier.contact_phone,
            })
    return ResponseUtil.success(data=result)


@inquiry_controller.get(
    '/list',
    summary='获取询价单列表',
    response_model=PageResponseModel,
)
async def get_inquiry_list(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    project_id: int = Query(default=None, description='项目ID'),
    status: str = Query(default=None, description='状态'),
    page_num: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
):
    query = InquiryQuery(project_id=project_id, status=status, page_num=page_num, page_size=page_size)
    rows, total = await InquiryService.get_inquiry_list(query_db, query)
    return ResponseUtil.success(rows=[r.model_dump() for r in rows], dict_content={'total': total})


@inquiry_controller.get(
    '/{inquiry_id}',
    summary='获取询价单详情',
    response_model=DataResponseModel,
)
async def get_inquiry_detail(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    inquiry_id: int = Path(..., description='询价单ID'),
):
    result = await InquiryService.get_inquiry_detail(query_db, inquiry_id)
    if not result:
        return ResponseUtil.failure(msg='询价单不存在')
    return ResponseUtil.success(data=result.model_dump())


@inquiry_controller.delete(
    '/{inquiry_id}',
    summary='删除询价单',
    response_model=ResponseBaseModel,
)
async def delete_inquiry(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    inquiry_id: int = Path(..., description='询价单ID'),
):
    result = await InquiryService.delete_inquiry(query_db, inquiry_id)
    if not result:
        return ResponseUtil.failure(msg='询价单不存在')
    return ResponseUtil.success(msg='删除成功')


@inquiry_controller.post(
    '',
    summary='创建询价单',
    response_model=DataResponseModel,
)
async def create_inquiry(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: InquiryCreate,
):
    result = await InquiryService.create_inquiry(query_db, data, current_user.user.user_id if current_user.user else 0)
    return ResponseUtil.success(data=result.model_dump(), msg='创建成功')


@inquiry_controller.post(
    '/{inquiry_id}/send',
    summary='发送询价邀请',
    response_model=ResponseBaseModel,
)
async def send_inquiry(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    inquiry_id: int = Path(..., description='询价单ID'),
    data: InquirySend = None,
):
    result = await InquiryService.send_inquiry(query_db, inquiry_id, data)
    if not result:
        return ResponseUtil.failure(msg='询价单不存在')
    return ResponseUtil.success(msg='发送成功')


@inquiry_controller.get(
    '/{inquiry_id}/invitations',
    summary='获取询价邀请列表(含报价)',
    response_model=DataResponseModel,
)
async def get_invitations(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    inquiry_id: int = Path(..., description='询价单ID'),
):
    result = await InquiryService.get_invitations(query_db, inquiry_id)
    return ResponseUtil.success(data=result)


@inquiry_controller.post(
    '/invitation/{invitation_id}/save-draft',
    summary='加工方保存报价草稿',
    response_model=ResponseBaseModel,
)
async def save_draft_quote(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    invitation_id: int = Path(..., description='邀请ID'),
    data: QuoteDraftSave = None,
):
    result = await InquiryService.save_draft_quote(query_db, invitation_id, data)
    if not result:
        return ResponseUtil.failure(msg='邀请不存在')
    return ResponseUtil.success(msg='保存成功')


@inquiry_controller.post(
    '/invitation/{invitation_id}/quote',
    summary='加工方提交报价',
    response_model=DataResponseModel,
)
async def submit_quote(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    invitation_id: int = Path(..., description='邀请ID'),
    data: QuoteSubmit = None,
):
    result = await InquiryService.submit_quote(query_db, invitation_id, data, current_user.user.user_id if current_user.user else 0)
    if not result:
        return ResponseUtil.failure(msg='邀请不存在')
    return ResponseUtil.success(data=result.model_dump(), msg='报价成功')


@inquiry_controller.post(
    '/invitation/{invitation_id}/decline',
    summary='加工方拒绝询价',
    response_model=ResponseBaseModel,
)
async def decline_invitation(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    invitation_id: int = Path(..., description='邀请ID'),
    data: QuoteDecline = None,
):
    result = await InquiryService.decline_invitation(query_db, invitation_id, data)
    if not result:
        return ResponseUtil.failure(msg='邀请不存在')
    return ResponseUtil.success(msg='已拒绝')


@inquiry_controller.post(
    '/{inquiry_id}/award/{quotation_id}',
    summary='选标：将询价单授予指定报价',
    response_model=DataResponseModel,
)
async def award_inquiry(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    inquiry_id: int = Path(..., description='询价单ID'),
    quotation_id: int = Path(..., description='报价单ID'),
):
    result = await InquiryService.award_inquiry(
        query_db, inquiry_id, quotation_id, current_user.user.user_id if current_user.user else 0
    )
    if not result:
        return ResponseUtil.failure(msg='选标失败')
    return ResponseUtil.success(data=result.model_dump(), msg='选标成功，已生成委外工单')


# ─────────────────────────────────────────────────────────────────────────────
# 合同生成 & 邮件分发
# ─────────────────────────────────────────────────────────────────────────────

@inquiry_controller.post(
    '/{inquiry_id}/send-contract',
    summary='向指定加工方发送填充后的合同 DOCX',
    response_model=DataResponseModel,
)
async def send_contract(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    inquiry_id: int = Path(..., description='询价单ID'),
    data: SendContractRequest = None,
):
    """
    从数据库读取询价单和加工方信息，自动填充 DOCX 合同模板，
    发送至收件邮箱（留空则从供应商档案自动获取），并记录发送历史。
    """
    from module_entrust.entity.vo.entrust_vo import SendContractRequest as Req
    req = data or Req(supplier_id=0)
    result = await ContractService.send_contract(
        db=query_db,
        inquiry_id=inquiry_id,
        supplier_id=req.supplier_id,
        recipient_email=req.recipient_email,
        extra_values=req.extra_values,
        created_by=current_user.user.user_id if current_user.user else 0,
    )
    if not result['success']:
        return ResponseUtil.failure(msg=result['message'])
    return ResponseUtil.success(
        data={
            'smtp_message_id': result.get('smtp_message_id'),
            'record_id': result.get('record_id'),
            'missing_fields': result.get('missing_fields', []),
        },
        msg=result['message'],
    )


@inquiry_controller.post(
    '/{inquiry_id}/send-contract/batch',
    summary='批量向询价单所有受邀加工方发送合同 DOCX',
    response_model=DataResponseModel,
)
async def batch_send_contract(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    inquiry_id: int = Path(..., description='询价单ID'),
    data: BatchSendContractRequest = None,
):
    """
    自动从供应商档案获取邮箱，批量发送合同。
    可通过 email_map 覆盖部分供应商的收件地址。
    """
    from module_entrust.entity.vo.entrust_vo import BatchSendContractRequest as Req
    req = data or Req()
    int_email_map = {int(k): v for k, v in (req.email_map or {}).items()}
    result = await ContractService.batch_send_contract(
        db=query_db,
        inquiry_id=inquiry_id,
        email_map=int_email_map or None,
        extra_values=req.extra_values,
        created_by=current_user.user.user_id if current_user.user else 0,
    )
    return ResponseUtil.success(
        data=result,
        msg=f"批量发送完成：{result['success_count']}/{result['total']} 封成功",
    )


@inquiry_controller.get(
    '/{inquiry_id}/contract/preview',
    summary='预览合同 DOCX（下载文件，不发邮件）',
)
async def preview_contract(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    inquiry_id: int = Path(..., description='询价单ID'),
    supplier_id: int = Query(..., description='加工方ID'),
):
    """生成填充后的合同 DOCX 文件流，用于前端预览/下载，不发送邮件。"""
    inquiry = await query_db.scalar(
        select(EntrustOutsourceRequest).where(EntrustOutsourceRequest.id == inquiry_id)
    )
    if not inquiry:
        return ResponseUtil.failure(msg='询价单不存在')

    supplier = await query_db.scalar(
        select(EntrustSupplier).where(EntrustSupplier.id == supplier_id)
    )
    if not supplier:
        return ResponseUtil.failure(msg='加工方不存在')

    from module_entrust.service.contract_service import _get_party_a_config
    party_a = await _get_party_a_config(query_db)
    docx_bytes, filename = ContractService.generate_docx_only(inquiry, supplier, party_a)

    from urllib.parse import quote
    encoded_name = quote(filename, safe='')
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@inquiry_controller.get(
    '/{inquiry_id}/contract/records',
    summary='获取询价单的合同发送历史',
    response_model=DataResponseModel,
)
async def get_contract_records(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    inquiry_id: int = Path(..., description='询价单ID'),
):
    records = await ContractService.get_contract_records(query_db, inquiry_id)
    return ResponseUtil.success(data=records)


@inquiry_controller.get(
    '/contract/records/{record_id}',
    summary='获取单条合同发送记录详情',
    response_model=DataResponseModel,
)
async def get_contract_record(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    record_id: int = Path(..., description='记录ID'),
):
    record = await ContractService.get_contract_record(query_db, record_id)
    if not record:
        return ResponseUtil.failure(msg='记录不存在')
    return ResponseUtil.success(data=record)
