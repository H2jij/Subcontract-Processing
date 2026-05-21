// src/types/reconciliation.ts

// ==================== 通用类型 ====================

/** 分页响应 */
export interface PageResult<T> {
  rows: T[]
  total: number
  page: number
  page_size: number
}

/** 分页请求参数 */
export interface PageParams {
  page: number
  page_size: number
}

// ==================== 枚举类型 ====================

/** 对账单状态 */
export type StatementStatus = 'pending' | 'confirmed' | 'disputed' | 'timeout' | 'paid'

/** 确认状态 */
export type ConfirmationStatus = 'pending' | 'confirmed' | 'disputed'

/** 结算状态 */
export type SettlementStatus = 'draft' | 'finalized'

/** 付款状态 */
export type PaymentStatus = 'pending_payment' | 'partially_paid' | 'paid'

/** 异常状态 */
export type AnomalyStatus = 'open' | 'investigating' | 'resolved' | 'closed'

/** 异常严重程度 */
export type Severity = 'critical' | 'warning' | 'info'

/** 异常类型 */
export type AnomalyType = 'amount_diff' | 'quantity_diff' | 'supplier_missing' | 'duplicate' | 'quality_dispute'

/** 生产异常类型 */
export type ProductionAnomalyType = 'material_damage' | 'process_error' | 'unusable'

/** 虚拟入库类型 */
export type InboundType = 're_shipment_in' | 'anomaly_deduction'

/** 虚拟入库状态 */
export type VirtualInboundStatus = 'pending' | 'confirmed' | 'linked_to_settlement' | 'cancelled'

/** 责任方 */
export type ResponsibleParty = 'material_supplier' | 'processor'

/** 审批状态 */
export type ApprovalStatus = 'pending_approval' | 'approved' | 'rejected'

/** 差异原因类型 */
export type VarianceReasonType =
  | 'material_damage'
  | 'process_error'
  | 'unusable'
  | 'partial_delivery'
  | 'virtual_inbound'
  | 'anomaly_deduction'


// ==================== 业务实体 VO ====================

/** 对账单 */
export interface ReconciliationStatementVO {
  id: number
  statement_no: string
  supplier_id: number
  supplier_name: string
  period_start: string
  period_end: string
  // 汇总
  total_ordered_amount: number
  total_received_value: number
  total_logistics_cost: number
  total_variance: number
  anomaly_count: number
  total_amount: number
  // 状态
  status: StatementStatus
  confirmation_status: ConfirmationStatus
  confirmed_at: string | null
  confirmed_by: number | null
  dispute_reason: string | null
  notified_at: string | null
  created_by: number
  created_at: string
  updated_at: string
  // 关联
  line_items?: ReconciliationLineItemVO[]
}

/** 对账单行项 */
export interface ReconciliationLineItemVO {
  id: number
  statement_id: number
  order_id: number | null
  order_no: string
  process_name: string | null
  part_no: string | null
  part_name: string | null
  // 订购基准
  ordered_quantity: number | null
  ordered_unit_price: number | null
  order_amount: number | null
  // 实际交付
  actual_delivered_qty: number | null
  actual_delivered_value: number
  // 虚拟入库
  virtual_inbound_value: number
  // 异常扣除
  anomaly_deduction_amount: number
  // 物流
  logistics_cost: number
  // 差异
  variance: number
  has_mismatch: boolean
  variance_reasons: VarianceReasonVO[] | null
  // 状态
  is_frozen: boolean
  created_at: string
  updated_at: string
}

/** 差异原因 */
export interface VarianceReasonVO {
  reason_type: VarianceReasonType
  description: string | null
  impact_amount: number
  responsible_party: ResponsibleParty | null
  production_anomaly_id: number | null
  virtual_inbound_id: number | null
  deduction_id: number | null
}

/** 差异汇总 */
export interface VarianceSummaryVO {
  total_ordered_amount: number
  total_received_value: number
  total_logistics_cost: number
  total_variance: number
  anomaly_count: number
  mismatch_count: number
}

/** 异常记录 */
export interface AnomalyVO {
  id: number
  statement_id: number
  statement_no: string
  line_item_id: number
  anomaly_type: AnomalyType
  severity: Severity
  diff_amount: number
  original_amount: number
  status: AnomalyStatus
  order_no: string
  description: string | null
  created_at: string
  updated_at: string
}

/** 调整记录 */
export interface AdjustmentVO {
  id: number
  anomaly_id: number
  line_item_id: number
  original_amount: number
  adjusted_amount: number
  adjustment_reason: string
  approval_status: ApprovalStatus
  approval_level: 'manager' | 'director'
  approved_by: number | null
  approved_at: string | null
  reject_reason: string | null
  created_by: number
  created_at: string
}

/** 付款申请 */
export interface PaymentRequestVO {
  id: number
  statement_id: number
  statement_no: string
  supplier_id: number
  supplier_name: string
  payable_amount: number
  paid_amount: number
  remaining_amount: number
  payment_status: PaymentStatus
  created_at: string
  records?: PaymentRecordVO[]
  evidences?: PaymentEvidenceVO[]
}

/** 付款记录 */
export interface PaymentRecordVO {
  id: number
  payment_request_id: number
  payment_amount: number
  payment_date: string
  bank_reference: string
  created_by: number
  created_at: string
}

/** 支付凭证 */
export interface PaymentEvidenceVO {
  id: number
  payment_request_id: number | null
  settlement_id: number | null
  file_name: string
  file_path: string
  file_type: string
  file_size: number
  thumbnail_url: string | null
  uploaded_by: number
  uploaded_at: string
}

/** 结算明细 */
export interface SettlementDetailVO {
  id: number
  order_id: number
  order_no: string
  supplier_id: number
  supplier_name: string
  statement_id: number | null
  status: SettlementStatus
  // 订购基准
  ordered_quantity: number | null
  ordered_unit_price: number | null
  ordered_amount: number
  // 实际交付
  actual_delivered_qty: number | null
  actual_delivered_amount: number
  // 虚拟入库
  virtual_inbound_amount: number
  // 异常扣除
  anomaly_deduction_amount: number
  // 物流
  logistics_cost: number
  // 差异
  variance: number
  variance_reasons: VarianceReasonVO[] | null
  // 利润
  total_cost: number
  customer_payment: number
  net_profit: number
  // 状态
  finalized_at: string | null
  finalized_by: number | null
  created_at: string
  updated_at: string
  // 关联
  line_items?: any[]
  evidences?: PaymentEvidenceVO[]
}

/** 虚拟入库 */
export interface VirtualInboundVO {
  id: number
  order_id: number
  order_no: string | null
  part_id: number | null
  part_no: string | null
  part_name: string | null
  inbound_type: InboundType
  quantity: number
  unit_price: number
  amount: number
  production_anomaly_id: number | null
  re_shipment_id: number | null
  anomaly_reason: string
  responsible_party: ResponsibleParty
  status: VirtualInboundStatus
  created_by: number | null
  created_at: string
  updated_at: string
}

/** 生产异常 */
export interface ProductionAnomalyVO {
  id: number
  order_id: number
  order_no: string
  part_id: number | null
  part_no: string | null
  part_name: string | null
  anomaly_type: ProductionAnomalyType
  description: string
  occurred_at: string
  liability_type: ResponsibleParty | null
  liability_description: string | null
  material_cost: number
  rework_cost: number
  delay_penalty: number
  total_loss: number
  status: string
  re_shipments?: ReShipmentVO[]
  deductions?: DeductionVO[]
  negotiations?: NegotiationRecordVO[]
  created_at: string
  updated_at: string
}

/** 补发记录 */
export interface ReShipmentVO {
  id: number
  production_anomaly_id: number
  part_id: number
  part_name: string
  quantity: number
  expected_ship_date: string
  actual_ship_date: string | null
  status: string
}

/** 扣款记录 */
export interface DeductionVO {
  id: number
  production_anomaly_id: number
  order_id: number
  amount: number
  reason: string
  status: string
  created_at: string
}

/** 协商记录 */
export interface NegotiationRecordVO {
  id: number
  production_anomaly_id: number
  content: string
  created_by: number
  created_at: string
}


// ==================== 报表 VO ====================

/** 仪表盘 */
export interface DashboardVO {
  total_statements: number
  confirmed_count: number
  disputed_count: number
  pending_count: number
  mismatch_order_count: number
  total_variance_amount: number
}

/** 供应商汇总 */
export interface SupplierSummaryVO {
  supplier_id: number
  supplier_name: string
  total_ordered_amount: number
  total_received_value: number
  total_variance: number
  anomaly_count: number
}

/** 月度趋势 */
export interface MonthlyTrendVO {
  month: string
  statement_count: number
  mismatch_ratio: number
  variance_amount: number
}

/** 账龄分析 */
export interface AgingAnalysisVO {
  buckets: AgingBucketVO[]
  total_unpaid: number
}

export interface AgingBucketVO {
  range: '0-30' | '31-60' | '61-90' | '90+'
  count: number
  amount: number
}

// ==================== 请求参数类型 ====================

/** 对账单筛选参数 */
export interface StatementFilterParams extends PageParams {
  supplier_id?: number
  status?: StatementStatus
  period_start?: string
  period_end?: string
}

/** 生成对账单参数 */
export interface GenerateStatementParams {
  period_start: string
  period_end: string
  supplier_id?: number
}

/** 争议参数 */
export interface DisputeParams {
  dispute_reason: string
  disputed_line_item_ids?: number[]
}

/** 异常筛选参数 */
export interface AnomalyFilterParams extends PageParams {
  anomaly_type?: AnomalyType
  severity?: Severity
  status?: AnomalyStatus
}

/** 创建调整参数 */
export interface CreateAdjustmentParams {
  adjusted_amount: number
  adjustment_reason: string
}

/** 创建付款记录参数 */
export interface CreatePaymentRecordParams {
  payment_amount: number
  payment_date: string
  bank_reference: string
}

/** 虚拟入库筛选参数 */
export interface VirtualInboundFilterParams extends PageParams {
  order_no?: string
  part_id?: number
  inbound_type?: InboundType
  responsible_party?: ResponsibleParty
}

/** 创建虚拟入库参数 */
export interface CreateVirtualInboundParams {
  order_id: number
  part_id: number
  inbound_type: InboundType
  quantity: number
  unit_price: number
  anomaly_reason: string
  responsible_party: ResponsibleParty
  production_anomaly_id?: number
  re_shipment_id?: number
}

/** 修改虚拟入库参数 */
export interface UpdateVirtualInboundParams {
  quantity?: number
  unit_price?: number
  anomaly_reason?: string
  responsible_party?: ResponsibleParty
}

/** 创建生产异常参数 */
export interface CreateProductionAnomalyParams {
  order_id: number
  part_id: number
  anomaly_type: ProductionAnomalyType
  description: string
  occurred_at: string
}

/** 责任判定参数 */
export interface LiabilityParams {
  liability_type: ResponsibleParty
  liability_description: string
}

/** 补发参数 */
export interface ReShipmentParams {
  part_id: number
  quantity: number
  expected_ship_date: string
}

/** 扣款参数 */
export interface DeductionParams {
  amount: number
  reason: string
}

/** 协商参数 */
export interface NegotiationParams {
  content: string
}
