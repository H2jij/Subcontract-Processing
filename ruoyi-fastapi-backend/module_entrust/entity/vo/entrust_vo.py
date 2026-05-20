"""
委外加工模块 — Pydantic VO（View Object）请求/响应模型
"""
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================================================
# 通用分页查询
# ============================================================================

class PageQuery(BaseModel):
    """通用分页查询参数"""
    page_num: int = Field(default=1, ge=1, description='页码')
    page_size: int = Field(default=10, ge=1, le=100, description='每页条数')


# ============================================================================
# 加工方/供应商
# ============================================================================

class SupplierCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description='供应商名称')
    supplier_type: Optional[str] = Field(default='processor', description='类型：processor/material/other')
    category: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    legal_rep: Optional[str] = Field(default=None, description='法定代表人')
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    credit_code: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    bank_account_name: Optional[str] = None
    rating: Optional[float] = None
    base_price: Optional[float] = None
    contract_amount: Optional[float] = None
    contract_start: Optional[date] = None
    contract_end: Optional[date] = None
    signed_at: Optional[date] = None
    remark: Optional[str] = None
    link_username: Optional[str] = None
    link_password: Optional[str] = None


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    supplier_type: Optional[str] = None
    category: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    legal_rep: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    credit_code: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    bank_account_name: Optional[str] = None
    rating: Optional[float] = None
    base_price: Optional[float] = None
    contract_amount: Optional[float] = None
    contract_start: Optional[date] = None
    contract_end: Optional[date] = None
    signed_at: Optional[date] = None
    status: Optional[str] = None
    remark: Optional[str] = None
    link_username: Optional[str] = None
    link_password: Optional[str] = None


class SupplierQuery(PageQuery):
    name: Optional[str] = None
    supplier_type: Optional[str] = Field(default=None, description='processor/material/other')
    category: Optional[str] = None
    status: Optional[str] = None


class SupplierResponse(BaseModel):
    id: int
    name: str
    supplier_type: Optional[str] = None
    category: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    legal_rep: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    credit_code: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    bank_account_name: Optional[str] = None
    rating: Optional[float] = None
    base_price: Optional[float] = None
    contract_amount: Optional[float] = None
    contract_start: Optional[date] = None
    contract_end: Optional[date] = None
    signed_at: Optional[date] = None
    status: Optional[str] = None
    remark: Optional[str] = None
    user_id: Optional[int] = None
    link_username: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


class SupplierQuery(PageQuery):
    name: Optional[str] = None
    supplier_type: Optional[str] = Field(default=None, description='processor/material/other')
    category: Optional[str] = None
    status: Optional[str] = None


class SupplierResponse(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    credit_code: Optional[str] = None
    rating: Optional[float] = None
    base_price: Optional[float] = None
    status: Optional[str] = None
    remark: Optional[str] = None
    user_id: Optional[int] = None
    link_username: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


# ============================================================================
# 项目
# ============================================================================

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    customer: str = Field(..., min_length=1, max_length=255)
    deadline: Optional[date] = None
    unit_price: Optional[float] = None
    quantity: Optional[int] = None
    description: str = ''


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    customer: Optional[str] = None
    deadline: Optional[date] = None
    unit_price: Optional[float] = None
    quantity: Optional[int] = None
    description: Optional[str] = None
    status: Optional[str] = None


class ProjectQuery(PageQuery):
    name: Optional[str] = None
    customer: Optional[str] = None
    status: Optional[str] = None


class ProjectResponse(BaseModel):
    id: int
    project_no: str
    name: str
    customer: str
    deadline: Optional[date] = None
    unit_price: Optional[float] = None
    quantity: Optional[int] = None
    description: Optional[str] = None
    status: Optional[str] = None
    created_by: Optional[int] = None
    confirmed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


# ============================================================================
# 模具套
# ============================================================================

class MoldCreate(BaseModel):
    name: Optional[str] = None
    sort_no: Optional[int] = None
    remark: Optional[str] = None


class MoldResponse(BaseModel):
    id: int
    project_id: int
    name: Optional[str] = None
    sort_no: Optional[int] = None
    remark: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


# ============================================================================
# 零件
# ============================================================================

class PartCreate(BaseModel):
    part_no: Optional[str] = None
    part_name: Optional[str] = None
    material: Optional[str] = None
    material_id: Optional[int] = None
    qty: int = Field(default=1, ge=1)
    spec: Optional[str] = None
    mold_id: Optional[int] = None
    part_type: Optional[str] = None
    processes: list[str] = Field(default_factory=list)
    process_method_ids: Optional[list[int]] = None


class PartUpdate(BaseModel):
    part_no: Optional[str] = None
    part_name: Optional[str] = None
    material: Optional[str] = None
    material_id: Optional[int] = None
    qty: Optional[int] = None
    spec: Optional[str] = None
    mold_id: Optional[int] = None
    part_type: Optional[str] = None
    processes: Optional[list[str]] = None
    process_method_ids: Optional[list[int]] = None


class PartResponse(BaseModel):
    id: int
    project_id: int
    mold_id: Optional[int] = None
    part_no: Optional[str] = None
    part_name: Optional[str] = None
    material: Optional[str] = None
    qty: Optional[int] = None
    spec: Optional[str] = None
    part_type: Optional[str] = None
    processes_json: Optional[Any] = None
    process_method_ids: Optional[Any] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


# ============================================================================
# 询价
# ============================================================================

class InquiryCreate(BaseModel):
    project_id: int
    title: str = Field(..., min_length=1, max_length=255)
    scope_json: Optional[list[dict]] = None
    deadline: Optional[date] = None
    customer_name: Optional[str] = None
    customer_contact: Optional[str] = None
    customer_phone: Optional[str] = None
    order_no: Optional[str] = None
    inquiry_date: Optional[date] = None
    delivery_date: Optional[date] = None


class InquirySend(BaseModel):
    supplier_ids: list[int] = Field(..., min_length=1)


class InquiryQuery(PageQuery):
    project_id: Optional[int] = None
    status: Optional[str] = None


class InquiryResponse(BaseModel):
    id: int
    project_id: int
    title: str
    scope_json: Optional[Any] = None
    deadline: Optional[date] = None
    status: Optional[str] = None
    closed_at: Optional[datetime] = None
    winning_quote_id: Optional[int] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    customer_name: Optional[str] = None
    customer_contact: Optional[str] = None
    customer_phone: Optional[str] = None
    order_no: Optional[str] = None
    inquiry_date: Optional[date] = None
    delivery_date: Optional[date] = None

    model_config = {'from_attributes': True}


# ============================================================================
# 报价
# ============================================================================

class QuoteSubmit(BaseModel):
    unit_price: Optional[float] = None
    lead_time_days: Optional[int] = None
    note: Optional[str] = None
    lines: Optional[list[dict]] = None


class QuoteDraftSave(BaseModel):
    draft_quote_json: Optional[list[dict]] = None


class QuoteDecline(BaseModel):
    decline_remark: str = Field(..., min_length=1, description='拒绝备注')


class QuoteResponse(BaseModel):
    id: int
    invitation_id: int
    unit_price: Optional[float] = None
    lead_time_days: Optional[int] = None
    note: Optional[str] = None
    lines_json: Optional[Any] = None
    submitted_by: Optional[int] = None
    submitted_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


# ============================================================================
# 委外工单
# ============================================================================

class OutsourceOrderResponse(BaseModel):
    id: int
    request_id: Optional[int] = None
    quotation_id: Optional[int] = None
    supplier_id: int
    project_id: Optional[int] = None
    part_id: Optional[int] = None
    order_no: str
    process_name: Optional[str] = None
    unit_price: Optional[float] = None
    quantity: Optional[int] = None
    total_amount: Optional[float] = None
    lead_time_days: Optional[int] = None
    plan_delivery_date: Optional[datetime] = None
    actual_delivery_date: Optional[datetime] = None
    status: Optional[str] = None
    quality_status: Optional[str] = None
    remark: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


class OrderStatusTransition(BaseModel):
    to_status: str = Field(..., pattern=r'^(accepted|producing|delivered|cancelled)$')
    note: Optional[str] = None


# ============================================================================
# 附件
# ============================================================================

class AttachmentResponse(BaseModel):
    id: int
    related_type: str
    related_id: int
    file_name: str
    file_path: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    category: Optional[str] = None
    uploaded_by: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


# ============================================================================
# 批量询价
# ============================================================================

class BatchInquiryRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    deadline: Optional[date] = None
    supplier_ids: list[int] = Field(..., min_length=1)


# ============================================================================
# 聊天
# ============================================================================

class ChatMessageVO(BaseModel):
    id: int
    session_id: int
    sender_type: str
    sender_name: Optional[str] = None
    content: str
    message_type: str = 'text'
    extra_data: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {'from_attributes': True, 'populate_by_name': True, 'alias_generator': lambda x: ''.join(
        word.capitalize() if i else word for i, word in enumerate(x.split('_'))
    )}


class ChatSessionVO(BaseModel):
    id: int
    our_user_id: int
    our_user_name: Optional[str] = None
    supplier_id: int
    supplier_user_id: Optional[int] = None
    supplier_name: Optional[str] = None
    project_id: Optional[int] = None
    request_id: Optional[int] = None
    status: str = 'inquiring'
    last_message: Optional[str] = None
    last_message_type: Optional[str] = None
    last_message_at: Optional[datetime] = None
    is_pinned: bool = False
    unread: int = 0
    created_at: Optional[datetime] = None

    model_config = {'from_attributes': True, 'populate_by_name': True, 'alias_generator': lambda x: ''.join(
        word.capitalize() if i else word for i, word in enumerate(x.split('_'))
    )}


# ============================================================================
# 合同发送
# ============================================================================

class SendContractRequest(BaseModel):
    supplier_id: int = Field(..., description='加工方ID')
    recipient_email: Optional[str] = Field(default=None, description='收件邮箱（留空则从供应商档案自动获取）')
    extra_values: Optional[dict[str, str]] = Field(default=None, description='额外占位符覆盖值')


class BatchSendContractRequest(BaseModel):
    email_map: Optional[dict[str, str]] = Field(
        default=None, description='邮箱覆盖映射 {"supplier_id": "email"}，留空则全部从供应商档案获取'
    )
    extra_values: Optional[dict[str, str]] = Field(default=None, description='额外占位符覆盖值')


class ContractRecordResponse(BaseModel):
    id: int
    inquiry_id: int
    supplier_id: int
    supplier_name: Optional[str] = None
    recipient_email: str
    status: str
    smtp_message_id: Optional[str] = None
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {'from_attributes': True}
