"""
对账系统 — Pydantic VO（View Object）请求/响应模型

覆盖 7 个 Controller 的全部 API 请求/响应 schema：
- ReconciliationController: 对账单 CRUD + 生成
- SupplierClaimController: 供应商账单提交/确认
- AnomalyController: 异常管理 + 调整审批
- PaymentController: 付款申请/记录/凭证
- SettlementController: 结算明细 + PDF
- ProductionAnomalyController: 生产异常/责任判定
- ReportController: 报表/仪表盘
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# 通用分页查询
# ============================================================================

class PageQuery(BaseModel):
    """通用分页查询参数"""
    page_num: int = Field(default=1, ge=1, description='页码')
    page_size: int = Field(default=10, ge=1, le=100, description='每页条数')


class PageResponse(BaseModel):
    """通用分页响应"""
    total: int = Field(default=0, description='总记录数')
    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页条数')


# ============================================================================
# ReconciliationController — 对账单
# ============================================================================

class StatementGenerateRequest(BaseModel):
    """生成对账单请求"""
    period_start: date = Field(..., description='对账周期起始日期')
    period_end: date = Field(..., description='对账周期结束日期')
    supplier_id: Optional[int] = Field(default=None, description='指定供应商ID（为空则全部供应商）')


class StatementListQuery(PageQuery):
    """对账单列表查询"""
    supplier_id: Optional[int] = Field(default=None, description='供应商ID')
    status: Optional[str] = Field(default=None, description='状态: pending/confirmed/disputed/timeout/paid')
    confirmation_status: Optional[str] = Field(default=None, description='确认状态: pending/confirmed/disputed')
    period_start: Optional[date] = Field(default=None, description='周期起始日期(筛选)')
    period_end: Optional[date] = Field(default=None, description='周期结束日期(筛选)')


class LineItemResponse(BaseModel):
    """对账单行项响应"""
    id: int
    statement_id: int
    order_id: Optional[int] = None
    order_no: str
    process_name: Optional[str] = None
    part_no: Optional[str] = None
    part_name: Optional[str] = None

    # 订购基准
    ordered_quantity: Optional[int] = None
    ordered_unit_price: Optional[Decimal] = None
    order_amount: Optional[Decimal] = None

    # 实际交付
    actual_delivered_qty: Optional[int] = None
    actual_delivered_value: Optional[Decimal] = Field(default=Decimal('0'))

    # 虚拟入库
    virtual_inbound_value: Optional[Decimal] = Field(default=Decimal('0'))

    # 异常扣除
    anomaly_deduction_amount: Optional[Decimal] = Field(default=Decimal('0'))

    # 物流费用
    logistics_cost: Optional[Decimal] = Field(default=Decimal('0'))

    # 差异计算结果
    variance: Optional[Decimal] = Field(default=Decimal('0'))
    has_mismatch: bool = False
    variance_reasons: Optional[Any] = None

    # 保留字段
    unit_price: Optional[Decimal] = None
    quantity: Optional[int] = None
    total_amount: Optional[Decimal] = None
    is_frozen: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)



class StatementListResponse(PageResponse):
    """对账单列表响应"""
    rows: list['StatementBriefResponse'] = Field(default_factory=list)


class StatementBriefResponse(BaseModel):
    """对账单摘要（列表用）"""
    id: int
    statement_no: str
    supplier_id: int
    supplier_name: Optional[str] = None
    period_start: date
    period_end: date
    total_amount: Decimal = Decimal('0')
    status: Optional[str] = None
    confirmation_status: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    notified_at: Optional[datetime] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


class StatementDetailResponse(BaseModel):
    """对账单详情响应（含行项）"""
    id: int
    statement_no: str
    supplier_id: int
    supplier_name: Optional[str] = None
    period_start: date
    period_end: date
    total_amount: Decimal = Decimal('0')

    # 汇总字段
    total_ordered_amount: Decimal = Decimal('0')
    total_received_value: Decimal = Decimal('0')
    total_logistics_cost: Decimal = Decimal('0')
    total_variance: Decimal = Decimal('0')
    anomaly_count: int = 0

    status: Optional[str] = None
    confirmation_status: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[int] = None
    dispute_reason: Optional[str] = None
    notified_at: Optional[datetime] = None
    timeout_at: Optional[datetime] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    line_items: list[LineItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class LineItemCreateRequest(BaseModel):
    """新增行项请求"""
    order_id: Optional[int] = Field(default=None, description='委外工单ID')
    order_no: str = Field(..., min_length=1, max_length=64, description='委外单号')
    process_name: Optional[str] = Field(default=None, max_length=200, description='工序名称')
    part_no: Optional[str] = Field(default=None, max_length=64, description='零件编号')
    part_name: Optional[str] = Field(default=None, max_length=255, description='零件名称')
    unit_price: Optional[Decimal] = Field(default=None, ge=0, description='单价')
    quantity: Optional[int] = Field(default=None, ge=0, description='数量')
    total_amount: Optional[Decimal] = Field(default=None, ge=0, description='行项金额')


class LineItemUpdateRequest(BaseModel):
    """编辑行项请求"""
    order_no: Optional[str] = Field(default=None, max_length=64, description='委外单号')
    process_name: Optional[str] = Field(default=None, max_length=200, description='工序名称')
    part_no: Optional[str] = Field(default=None, max_length=64, description='零件编号')
    part_name: Optional[str] = Field(default=None, max_length=255, description='零件名称')
    unit_price: Optional[Decimal] = Field(default=None, ge=0, description='单价')
    quantity: Optional[int] = Field(default=None, ge=0, description='数量')
    total_amount: Optional[Decimal] = Field(default=None, ge=0, description='行项金额')


class StatementGenerateResponse(BaseModel):
    """对账单生成响应"""
    statement_ids: list[int] = Field(default_factory=list, description='生成的对账单ID列表')
    count: int = Field(default=0, description='生成数量')


# ============================================================================
# SupplierClaimController — 供应商账单/确认
# ============================================================================

class SupplierClaimLineItem(BaseModel):
    """供应商账单行项"""
    order_no: str = Field(..., min_length=1, description='委外单号')
    process_name: Optional[str] = None
    part_no: Optional[str] = None
    part_name: Optional[str] = None
    unit_price: Optional[Decimal] = None
    quantity: Optional[int] = None
    total_amount: Decimal = Field(..., description='行项金额')


class SupplierClaimSubmitRequest(BaseModel):
    """供应商提交账单请求"""
    statement_id: int = Field(..., description='对账单ID')
    claim_items: list[SupplierClaimLineItem] = Field(..., min_length=1, description='账单明细行项')


class SupplierClaimResponse(BaseModel):
    """供应商账单响应"""
    id: int
    statement_id: int
    supplier_id: int
    claim_data: Optional[Any] = None
    submitted_at: Optional[datetime] = None
    submitted_by: Optional[int] = None

    model_config = {'from_attributes': True}


class SupplierConfirmRequest(BaseModel):
    """供应商确认对账单请求"""
    pass  # 确认操作无需额外参数，operator 从 token 获取


class SupplierDisputeRequest(BaseModel):
    """供应商提出争议请求"""
    dispute_reason: str = Field(..., min_length=1, max_length=2000, description='争议说明')


class ConfirmationHistoryResponse(BaseModel):
    """确认历史记录响应"""
    id: int
    statement_id: int
    action: str
    operator_id: int
    operator_name: Optional[str] = None
    remark: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


# ============================================================================
# AnomalyController — 异常管理 + 调整审批
# ============================================================================

class AnomalyListQuery(PageQuery):
    """异常记录列表查询"""
    statement_id: Optional[int] = Field(default=None, description='对账单ID')
    anomaly_type: Optional[str] = Field(default=None, description='类型: amount_diff/supplier_missing/duplicate/quality_dispute')
    severity: Optional[str] = Field(default=None, description='严重程度: critical/warning/info')
    status: Optional[str] = Field(default=None, description='状态: open/investigating/resolved/closed')


class AnomalyResponse(BaseModel):
    """异常记录响应"""
    id: int
    statement_id: int
    claim_id: Optional[int] = None
    line_item_id: Optional[int] = None
    anomaly_type: str
    severity: str
    diff_amount: Optional[Decimal] = None
    description: Optional[str] = None
    status: str
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


class AnomalyListResponse(PageResponse):
    """异常记录列表响应"""
    rows: list[AnomalyResponse] = Field(default_factory=list)


class AnomalyStatusUpdateRequest(BaseModel):
    """更新异常状态请求"""
    status: str = Field(..., pattern=r'^(open|investigating|resolved|closed)$', description='目标状态')
    remark: Optional[str] = Field(default=None, max_length=1000, description='备注')


class AdjustmentCreateRequest(BaseModel):
    """创建调整请求"""
    adjusted_amount: Decimal = Field(..., description='调整后金额')
    adjustment_reason: str = Field(..., min_length=1, max_length=2000, description='调整原因')


class AdjustmentResponse(BaseModel):
    """调整记录响应"""
    id: int
    anomaly_id: int
    statement_id: int
    line_item_id: int
    original_amount: Decimal
    adjusted_amount: Decimal
    adjustment_reason: str
    approval_status: str
    approval_level: Optional[str] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    reject_reason: Optional[str] = None
    created_by: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


class AdjustmentApproveRequest(BaseModel):
    """审批通过请求"""
    comment: Optional[str] = Field(default=None, max_length=1000, description='审批备注')


class AdjustmentRejectRequest(BaseModel):
    """审批驳回请求"""
    reject_reason: str = Field(..., min_length=1, max_length=2000, description='驳回原因')


class AdjustmentListQuery(PageQuery):
    """待审批调整列表查询"""
    approval_status: Optional[str] = Field(default=None, description='审批状态: pending_approval/approved/rejected/escalated')
    approval_level: Optional[str] = Field(default=None, description='审批层级: manager/director')


class AdjustmentListResponse(PageResponse):
    """调整列表响应"""
    rows: list[AdjustmentResponse] = Field(default_factory=list)



# ============================================================================
# PaymentController — 付款申请/记录/凭证
# ============================================================================

class PaymentRequestListQuery(PageQuery):
    """付款申请列表查询"""
    supplier_id: Optional[int] = Field(default=None, description='供应商ID')
    payment_status: Optional[str] = Field(default=None, description='付款状态: pending_payment/partially_paid/paid')


class PaymentRequestResponse(BaseModel):
    """付款申请响应"""
    id: int
    statement_id: int
    supplier_id: int
    supplier_name: Optional[str] = None
    statement_no: Optional[str] = None
    payable_amount: Decimal
    paid_amount: Decimal = Decimal('0')
    remaining_amount: Optional[Decimal] = None
    payment_status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


class PaymentRequestListResponse(PageResponse):
    """付款申请列表响应"""
    rows: list[PaymentRequestResponse] = Field(default_factory=list)


class PaymentRecordCreateRequest(BaseModel):
    """录入付款记录请求"""
    payment_amount: Decimal = Field(..., gt=0, description='付款金额')
    payment_date: date = Field(..., description='付款日期')
    bank_reference: Optional[str] = Field(default=None, max_length=128, description='银行流水号')
    remark: Optional[str] = Field(default=None, max_length=1000, description='备注')


class PaymentRecordResponse(BaseModel):
    """付款记录响应"""
    id: int
    request_id: int
    statement_id: int
    payment_amount: Decimal
    payment_date: date
    bank_reference: Optional[str] = None
    remark: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


class PaymentRecordListResponse(BaseModel):
    """付款记录列表响应"""
    records: list[PaymentRecordResponse] = Field(default_factory=list)
    total_paid: Decimal = Decimal('0')
    payable_amount: Decimal = Decimal('0')
    remaining_amount: Decimal = Decimal('0')
    payment_status: str = 'pending_payment'


class EvidenceUploadResponse(BaseModel):
    """支付凭证上传响应"""
    id: int
    related_type: str
    related_id: int
    file_name: str
    file_path: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    uploaded_by: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


class EvidenceListResponse(BaseModel):
    """支付凭证列表响应"""
    evidences: list[EvidenceUploadResponse] = Field(default_factory=list)


# ============================================================================
# SettlementController — 结算明细 + PDF
# ============================================================================

class SettlementListQuery(PageQuery):
    """结算明细列表查询"""
    supplier_id: Optional[int] = Field(default=None, description='供应商ID')
    order_no: Optional[str] = Field(default=None, description='委外单号')
    status: Optional[str] = Field(default=None, description='状态: draft/finalized')


class SettlementLineItemResponse(BaseModel):
    """结算行项响应"""
    id: int
    settlement_id: int
    item_type: str
    description: Optional[str] = None
    amount: Decimal
    is_income: bool = False
    created_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


class SettlementDetailResponse(BaseModel):
    """结算明细详情响应"""
    id: int
    order_id: int
    order_no: str
    supplier_id: int
    supplier_name: Optional[str] = None
    statement_id: Optional[int] = None
    status: str

    # 订购基准
    ordered_quantity: Optional[int] = None
    ordered_unit_price: Optional[Decimal] = None
    ordered_amount: Decimal = Decimal('0')

    # 实际交付
    actual_delivered_qty: Optional[int] = None
    actual_delivered_amount: Decimal = Decimal('0')

    # 虚拟入库
    virtual_inbound_amount: Decimal = Decimal('0')

    # 异常扣除
    anomaly_deduction_amount: Decimal = Decimal('0')

    # 物流费用
    logistics_cost: Decimal = Decimal('0')

    # 差异
    variance: Decimal = Decimal('0')
    variance_reasons: Optional[Any] = None

    # 保留字段
    total_cost: Decimal = Decimal('0')
    customer_payment: Decimal = Decimal('0')
    net_profit: Decimal = Decimal('0')
    finalized_at: Optional[datetime] = None
    finalized_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    line_items: list[SettlementLineItemResponse] = Field(default_factory=list)
    evidences: list[EvidenceUploadResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class SettlementBriefResponse(BaseModel):
    """结算明细摘要（列表用）"""
    id: int
    order_id: int
    order_no: str
    supplier_id: int
    supplier_name: Optional[str] = None
    status: str
    total_cost: Decimal = Decimal('0')
    customer_payment: Decimal = Decimal('0')
    net_profit: Decimal = Decimal('0')
    finalized_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


class SettlementListResponse(PageResponse):
    """结算明细列表响应"""
    rows: list[SettlementBriefResponse] = Field(default_factory=list)


class SettlementLineItemCreateRequest(BaseModel):
    """新增结算行项请求"""
    item_type: str = Field(..., pattern=r'^(process_fee|logistics|re_shipment|deduction|rework|customer_payment)$',
                           description='类型: process_fee/logistics/re_shipment/deduction/rework/customer_payment')
    description: Optional[str] = Field(default=None, max_length=255, description='描述')
    amount: Decimal = Field(..., description='金额')
    is_income: bool = Field(default=False, description='是否收入项')


class SettlementLineItemUpdateRequest(BaseModel):
    """编辑结算行项请求"""
    item_type: Optional[str] = Field(default=None, pattern=r'^(process_fee|logistics|re_shipment|deduction|rework|customer_payment)$')
    description: Optional[str] = Field(default=None, max_length=255)
    amount: Optional[Decimal] = None
    is_income: Optional[bool] = None


# ============================================================================
# VirtualInboundController — 虚拟入库
# ============================================================================

class VirtualInboundCreate(BaseModel):
    """创建虚拟入库记录请求"""
    order_id: int = Field(..., description='关联委外工单ID')
    order_no: Optional[str] = Field(default=None, max_length=64, description='委外单号(冗余)')
    part_id: Optional[int] = Field(default=None, description='零件ID')
    part_no: Optional[str] = Field(default=None, max_length=64, description='零件编号')
    part_name: Optional[str] = Field(default=None, max_length=255, description='零件名称')
    inbound_type: str = Field(..., pattern=r'^(re_shipment_in|anomaly_deduction)$',
                              description='入库类型: re_shipment_in(补发入库) / anomaly_deduction(异常扣除)')
    quantity: int = Field(..., gt=0, description='入库数量')
    unit_price: Decimal = Field(..., ge=0, description='单价')
    amount: Decimal = Field(..., ge=0, description='金额 = quantity × unit_price')
    production_anomaly_id: Optional[int] = Field(default=None, description='关联生产异常ID')
    re_shipment_id: Optional[int] = Field(default=None, description='关联补发记录ID')
    anomaly_reason: str = Field(..., min_length=1, max_length=2000, description='异常原因说明(必填)')
    responsible_party: str = Field(..., pattern=r'^(material_supplier|processor)$',
                                   description='责任方: material_supplier/processor')


class VirtualInboundUpdate(BaseModel):
    """修改虚拟入库记录请求"""
    order_no: Optional[str] = Field(default=None, max_length=64, description='委外单号')
    part_id: Optional[int] = Field(default=None, description='零件ID')
    part_no: Optional[str] = Field(default=None, max_length=64, description='零件编号')
    part_name: Optional[str] = Field(default=None, max_length=255, description='零件名称')
    inbound_type: Optional[str] = Field(default=None, pattern=r'^(re_shipment_in|anomaly_deduction)$',
                                        description='入库类型')
    quantity: Optional[int] = Field(default=None, gt=0, description='入库数量')
    unit_price: Optional[Decimal] = Field(default=None, ge=0, description='单价')
    amount: Optional[Decimal] = Field(default=None, ge=0, description='金额')
    production_anomaly_id: Optional[int] = Field(default=None, description='关联生产异常ID')
    re_shipment_id: Optional[int] = Field(default=None, description='关联补发记录ID')
    anomaly_reason: Optional[str] = Field(default=None, min_length=1, max_length=2000, description='异常原因说明')
    responsible_party: Optional[str] = Field(default=None, pattern=r'^(material_supplier|processor)$',
                                             description='责任方')
    status: Optional[str] = Field(default=None, pattern=r'^(pending|confirmed|linked_to_settlement|cancelled)$',
                                  description='状态')


class VirtualInboundResponse(BaseModel):
    """虚拟入库记录响应"""
    id: int
    order_id: int
    order_no: Optional[str] = None
    part_id: Optional[int] = None
    part_no: Optional[str] = None
    part_name: Optional[str] = None
    inbound_type: str
    quantity: int
    unit_price: Decimal
    amount: Decimal
    production_anomaly_id: Optional[int] = None
    re_shipment_id: Optional[int] = None
    anomaly_reason: str
    responsible_party: str
    status: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class VirtualInboundListQuery(PageQuery):
    """虚拟入库记录列表查询"""
    order_id: Optional[int] = Field(default=None, description='委外工单ID')
    order_no: Optional[str] = Field(default=None, description='委外单号')
    part_no: Optional[str] = Field(default=None, description='零件编号')
    inbound_type: Optional[str] = Field(default=None, description='入库类型: re_shipment_in/anomaly_deduction')
    responsible_party: Optional[str] = Field(default=None, description='责任方: material_supplier/processor')
    status: Optional[str] = Field(default=None, description='状态')


class VirtualInboundListResponse(PageResponse):
    """虚拟入库记录列表响应"""
    rows: list[VirtualInboundResponse] = Field(default_factory=list)


# ============================================================================
# LineItemVarianceReason — 行项差异原因
# ============================================================================

class LineItemVarianceReasonResponse(BaseModel):
    """行项差异原因响应"""
    id: int
    line_item_id: int
    reason_type: str
    production_anomaly_id: Optional[int] = None
    virtual_inbound_id: Optional[int] = None
    deduction_id: Optional[int] = None
    description: Optional[str] = None
    impact_amount: Optional[Decimal] = None
    responsible_party: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# VarianceSummary — 差异汇总
# ============================================================================

class VarianceSummaryResponse(BaseModel):
    """对账单差异汇总响应"""
    total_ordered_amount: Decimal = Decimal('0')
    total_received_value: Decimal = Decimal('0')
    total_logistics_cost: Decimal = Decimal('0')
    total_variance: Decimal = Decimal('0')
    anomaly_count: int = 0
    mismatch_count: int = 0



# ============================================================================
# ProductionAnomalyController — 生产异常/责任判定
# ============================================================================

class ProductionAnomalyCreateRequest(BaseModel):
    """创建生产异常请求"""
    order_id: int = Field(..., description='委外工单ID')
    order_no: Optional[str] = Field(default=None, max_length=64, description='委外单号')
    part_id: Optional[int] = Field(default=None, description='零件ID')
    anomaly_type: str = Field(..., pattern=r'^(material_damage|process_error|unusable)$',
                              description='异常类型: material_damage/process_error/unusable')
    description: Optional[str] = Field(default=None, max_length=2000, description='损失描述')
    occurred_at: datetime = Field(..., description='发生时间')
    material_cost: Decimal = Field(default=Decimal('0'), ge=0, description='材料成本')
    rework_cost: Decimal = Field(default=Decimal('0'), ge=0, description='返工成本')
    delay_penalty: Decimal = Field(default=Decimal('0'), ge=0, description='误工费')


class ProductionAnomalyResponse(BaseModel):
    """生产异常响应"""
    id: int
    order_id: int
    order_no: Optional[str] = None
    part_id: Optional[int] = None
    anomaly_type: str
    description: Optional[str] = None
    occurred_at: datetime
    liability_type: Optional[str] = None
    material_cost: Decimal = Decimal('0')
    rework_cost: Decimal = Decimal('0')
    delay_penalty: Decimal = Decimal('0')
    total_loss: Decimal = Decimal('0')
    status: str
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    re_shipments: list['ReShipmentResponse'] = Field(default_factory=list)
    deductions: list['DeductionResponse'] = Field(default_factory=list)
    negotiations: list['NegotiationRecordResponse'] = Field(default_factory=list)

    model_config = {'from_attributes': True}


class ProductionAnomalyListQuery(PageQuery):
    """生产异常列表查询"""
    order_id: Optional[int] = Field(default=None, description='委外工单ID')
    anomaly_type: Optional[str] = Field(default=None, description='异常类型')
    liability_type: Optional[str] = Field(default=None, description='责任类型')
    status: Optional[str] = Field(default=None, description='状态: open/liability_confirmed/resolved/closed')


class ProductionAnomalyBriefResponse(BaseModel):
    """生产异常摘要（列表用）"""
    id: int
    order_id: int
    order_no: Optional[str] = None
    part_id: Optional[int] = None
    anomaly_type: str
    description: Optional[str] = None
    occurred_at: datetime
    liability_type: Optional[str] = None
    total_loss: Decimal = Decimal('0')
    status: str
    created_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


class ProductionAnomalyListResponse(PageResponse):
    """生产异常列表响应"""
    rows: list[ProductionAnomalyBriefResponse] = Field(default_factory=list)


class LiabilitySetRequest(BaseModel):
    """判定责任方请求"""
    liability_type: str = Field(..., pattern=r'^(material_supplier_fault|processor_fault)$',
                                description='责任类型: material_supplier_fault/processor_fault')


class ReShipmentCreateRequest(BaseModel):
    """创建补发请求"""
    shipment_type: str = Field(..., pattern=r'^(material|part)$',
                               description='补发类型: material/part')
    responsible_party: str = Field(..., pattern=r'^(material_supplier|processor)$',
                                   description='责任方: material_supplier/processor')
    description: Optional[str] = Field(default=None, max_length=1000, description='补发说明')


class ReShipmentConfirmRequest(BaseModel):
    """确认补发发货请求（Requirement 13.1）"""
    order_id: int = Field(..., description='关联委外工单ID')
    part_id: int = Field(..., description='零件ID')
    quantity: int = Field(..., gt=0, description='补发数量')
    unit_price: Decimal = Field(..., ge=0, description='单价')
    anomaly_reason: str = Field(..., min_length=1, max_length=1000, description='异常原因说明')


class ReShipmentResponse(BaseModel):
    """补发记录响应"""
    id: int
    production_anomaly_id: int
    shipment_type: str
    responsible_party: str
    description: Optional[str] = None
    status: str
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


class DeductionCreateRequest(BaseModel):
    """创建扣款记录请求"""
    amount: Decimal = Field(..., gt=0, description='扣款金额')
    reason: Optional[str] = Field(default=None, max_length=1000, description='扣款原因')


class DeductionResponse(BaseModel):
    """扣款记录响应"""
    id: int
    production_anomaly_id: int
    order_id: Optional[int] = None
    amount: Decimal
    reason: Optional[str] = None
    status: str
    applied_to_settlement_id: Optional[int] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


class NegotiationCreateRequest(BaseModel):
    """记录协商过程请求"""
    negotiation_time: datetime = Field(..., description='协商时间')
    participants: Optional[str] = Field(default=None, max_length=500, description='参与方')
    result: Optional[str] = Field(default=None, max_length=2000, description='协商结果')


class NegotiationRecordResponse(BaseModel):
    """协商记录响应"""
    id: int
    production_anomaly_id: int
    negotiation_time: datetime
    participants: Optional[str] = None
    result: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {'from_attributes': True}



# ============================================================================
# ReportController — 报表/仪表盘
# ============================================================================

class DashboardResponse(BaseModel):
    """对账概览仪表盘响应"""
    total_statements: int = Field(default=0, description='对账单总数')
    confirmed_count: int = Field(default=0, description='已确认数量')
    disputed_count: int = Field(default=0, description='有争议数量')
    pending_count: int = Field(default=0, description='待确认数量')
    timeout_count: int = Field(default=0, description='超时未确认数量')
    total_payable: Decimal = Field(default=Decimal('0'), description='应付总金额')
    total_paid: Decimal = Field(default=Decimal('0'), description='已付总金额')
    total_unpaid: Decimal = Field(default=Decimal('0'), description='未付总金额')
    anomaly_count: int = Field(default=0, description='异常记录总数')
    open_anomaly_count: int = Field(default=0, description='待处理异常数')


class SupplierSummaryQuery(PageQuery):
    """供应商汇总报表查询"""
    supplier_id: Optional[int] = Field(default=None, description='供应商ID')
    period_start: Optional[date] = Field(default=None, description='起始日期')
    period_end: Optional[date] = Field(default=None, description='结束日期')


class SupplierSummaryItem(BaseModel):
    """供应商汇总项"""
    supplier_id: int
    supplier_name: Optional[str] = None
    total_amount: Decimal = Decimal('0')
    paid_amount: Decimal = Decimal('0')
    unpaid_amount: Decimal = Decimal('0')
    statement_count: int = 0
    confirmed_count: int = 0
    disputed_count: int = 0


class SupplierSummaryResponse(PageResponse):
    """供应商汇总报表响应"""
    rows: list[SupplierSummaryItem] = Field(default_factory=list)


class MonthlyTrendQuery(BaseModel):
    """月度趋势查询"""
    months: int = Field(default=12, ge=1, le=24, description='查询月数')


class MonthlyTrendItem(BaseModel):
    """月度趋势项"""
    month: str = Field(..., description='月份 YYYY-MM')
    statement_count: int = 0
    anomaly_count: int = 0
    anomaly_rate: float = Field(default=0.0, description='异常率(%)')
    avg_confirm_days: float = Field(default=0.0, description='平均确认耗时(天)')


class MonthlyTrendResponse(BaseModel):
    """月度趋势响应"""
    items: list[MonthlyTrendItem] = Field(default_factory=list)


class AgingBucket(BaseModel):
    """账龄分桶"""
    bucket: str = Field(..., description='分桶: 0-30/31-60/61-90/90+')
    count: int = Field(default=0, description='数量')
    total_amount: Decimal = Field(default=Decimal('0'), description='金额合计')


class AgingAnalysisResponse(BaseModel):
    """账龄分析响应"""
    buckets: list[AgingBucket] = Field(default_factory=list)
    total_unpaid_amount: Decimal = Field(default=Decimal('0'), description='未付总金额')
    total_unpaid_count: int = Field(default=0, description='未付总数')


class ReportFilterQuery(BaseModel):
    """报表通用筛选"""
    period_start: Optional[date] = Field(default=None, description='起始日期')
    period_end: Optional[date] = Field(default=None, description='结束日期')
    supplier_id: Optional[int] = Field(default=None, description='供应商ID')
    status: Optional[str] = Field(default=None, description='状态筛选')


# ============================================================================
# 导出相关
# ============================================================================

class ExportRequest(BaseModel):
    """导出请求"""
    statement_ids: list[int] = Field(default_factory=list, description='对账单ID列表')
    supplier_id: Optional[int] = Field(default=None, description='供应商ID')
    period_start: Optional[date] = Field(default=None, description='起始日期')
    period_end: Optional[date] = Field(default=None, description='结束日期')


class ExportResponse(BaseModel):
    """导出响应"""
    file_path: str = Field(..., description='文件路径')
    file_name: str = Field(..., description='文件名')
    file_size: Optional[int] = Field(default=None, description='文件大小(字节)')


# ============================================================================
# 审计日志
# ============================================================================

class AuditLogQuery(PageQuery):
    """审计日志查询"""
    entity_type: Optional[str] = Field(default=None, description='实体类型: statement/anomaly/adjustment/payment/settlement')
    entity_id: Optional[int] = Field(default=None, description='实体ID')
    action: Optional[str] = Field(default=None, description='操作: create/update/confirm/approve/reject/export/delete')
    operator_id: Optional[int] = Field(default=None, description='操作人ID')
    start_time: Optional[datetime] = Field(default=None, description='起始时间')
    end_time: Optional[datetime] = Field(default=None, description='结束时间')


class AuditLogResponse(BaseModel):
    """审计日志响应"""
    id: int
    entity_type: str
    entity_id: int
    action: str
    operator_id: int
    operator_name: Optional[str] = None
    detail: Optional[Any] = None
    ip_address: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {'from_attributes': True}


class AuditLogListResponse(PageResponse):
    """审计日志列表响应"""
    rows: list[AuditLogResponse] = Field(default_factory=list)
