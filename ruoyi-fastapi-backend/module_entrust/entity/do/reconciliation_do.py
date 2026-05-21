"""
对账系统模块 — SQLAlchemy ORM 模型
表名前缀 reconciliation_*，覆盖对账单、异常、调整、付款、结算、生产异常、审计日志等
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB

from config.database import Base


class ReconciliationStatement(Base):
    """对账单"""
    __tablename__ = 'reconciliation_statements'
    __table_args__ = (
        UniqueConstraint('statement_no', name='uk_reconciliation_statement_no'),
        Index('ix_reconciliation_stmt_supplier', 'supplier_id'),
        Index('ix_reconciliation_stmt_period', 'period_start', 'period_end'),
        Index('ix_reconciliation_stmt_status', 'status'),
        Index('ix_reconciliation_stmt_confirmation', 'confirmation_status'),
        {'comment': '对账单'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    statement_no = Column(String(64), nullable=False, comment='对账单编号 REC-{YYYYMM}-{supplier_id}-{seq}')
    supplier_id = Column(Integer, nullable=False, comment='供应商ID')
    period_start = Column(Date, nullable=False, comment='对账周期起始')
    period_end = Column(Date, nullable=False, comment='对账周期结束')

    # === 汇总字段 ===
    total_ordered_amount = Column(Numeric(14, 2), default=0, comment='订购总金额')
    total_received_value = Column(Numeric(14, 2), default=0, comment='实际收到总价值(含虚拟入库)')
    total_logistics_cost = Column(Numeric(14, 2), default=0, comment='物流总费用')
    total_variance = Column(Numeric(14, 2), default=0, comment='差异总金额')
    anomaly_count = Column(Integer, default=0, comment='异常笔数(variance!=0的行项数)')
    total_amount = Column(Numeric(14, 2), default=0, comment='应付金额(=total_received_value+total_logistics_cost)')

    status = Column(String(32), nullable=False, default='pending', comment='状态: pending/confirmed/disputed/timeout/paid')
    confirmation_status = Column(String(32), nullable=False, default='pending', comment='确认状态: pending/confirmed/disputed')
    confirmed_at = Column(DateTime, comment='确认时间')
    confirmed_by = Column(BigInteger, comment='确认人')
    dispute_reason = Column(Text, comment='争议说明')
    notified_at = Column(DateTime, comment='通知发送时间')
    timeout_at = Column(DateTime, comment='超时标记时间')
    created_by = Column(BigInteger, comment='创建人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class ReconciliationLineItem(Base):
    """对账单行项"""
    __tablename__ = 'reconciliation_line_items'
    __table_args__ = (
        Index('ix_reconciliation_li_statement', 'statement_id'),
        Index('ix_reconciliation_li_order', 'order_no'),
        {'comment': '对账单行项'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    statement_id = Column(Integer, nullable=False, comment='对账单ID')
    order_id = Column(Integer, comment='委外工单ID')
    order_no = Column(String(64), nullable=False, comment='委外单号')
    process_name = Column(String(200), comment='工序名称')
    part_no = Column(String(64), comment='零件编号')
    part_name = Column(String(255), comment='零件名称')

    # === 订购基准 ===
    ordered_quantity = Column(Integer, comment='订购数量')
    ordered_unit_price = Column(Numeric(14, 2), comment='订购单价')
    order_amount = Column(Numeric(14, 2), comment='订购金额 = ordered_quantity × ordered_unit_price')

    # === 实际交付 ===
    actual_delivered_qty = Column(Integer, comment='实际交付数量(质检合格)')
    actual_delivered_value = Column(Numeric(14, 2), default=0, comment='实际交付价值 = actual_delivered_qty × unit_price')

    # === 虚拟入库 ===
    virtual_inbound_value = Column(Numeric(14, 2), default=0, comment='虚拟入库价值(补发部分)')

    # === 异常扣除 ===
    anomaly_deduction_amount = Column(Numeric(14, 2), default=0, comment='异常扣除金额(不补发部分)')

    # === 物流费用 ===
    logistics_cost = Column(Numeric(14, 2), default=0, comment='物流费用')

    # === 差异计算结果 ===
    variance = Column(Numeric(14, 2), default=0, comment='差异金额 = order_amount - (actual + virtual - deduction + logistics)')
    has_mismatch = Column(Boolean, default=False, comment='是否货不对板(variance != 0)')
    variance_reasons = Column(JSONB, comment='差异原因列表(关联的异常记录摘要)')

    # === 保留字段 ===
    unit_price = Column(Numeric(14, 2), comment='单价(兼容旧数据)')
    quantity = Column(Integer, comment='数量(兼容旧数据)')
    total_amount = Column(Numeric(14, 2), comment='行项金额(=order_amount, 兼容)')
    is_frozen = Column(Boolean, default=False, comment='是否冻结(调整审批中)')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class SupplierClaim(Base):
    """供应商账单"""
    __tablename__ = 'reconciliation_supplier_claims'
    __table_args__ = (
        Index('ix_reconciliation_claim_statement', 'statement_id'),
        Index('ix_reconciliation_claim_supplier', 'supplier_id'),
        {'comment': '供应商账单'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    statement_id = Column(Integer, nullable=False, comment='对账单ID')
    supplier_id = Column(Integer, nullable=False, comment='供应商ID')
    claim_data = Column(JSONB, comment='供应商提交的账单明细JSON')
    submitted_at = Column(DateTime, default=datetime.now, comment='提交时间')
    submitted_by = Column(BigInteger, comment='提交人')


class Anomaly(Base):
    """异常记录"""
    __tablename__ = 'reconciliation_anomalies'
    __table_args__ = (
        Index('ix_reconciliation_anomaly_statement', 'statement_id'),
        Index('ix_reconciliation_anomaly_type', 'anomaly_type'),
        Index('ix_reconciliation_anomaly_status', 'status'),
        Index('ix_reconciliation_anomaly_severity', 'severity'),
        {'comment': '异常记录'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    statement_id = Column(Integer, nullable=False, comment='对账单ID')
    claim_id = Column(Integer, comment='供应商账单ID')
    line_item_id = Column(Integer, comment='对账单行项ID')
    anomaly_type = Column(String(32), nullable=False, comment='类型: amount_diff/supplier_missing/duplicate/quality_dispute')
    severity = Column(String(16), nullable=False, comment='严重程度: critical/warning/info')
    diff_amount = Column(Numeric(14, 2), comment='差异金额')
    description = Column(Text, comment='异常描述')
    status = Column(String(32), nullable=False, default='open', comment='状态: open/investigating/resolved/closed')
    resolved_at = Column(DateTime, comment='解决时间')
    resolved_by = Column(BigInteger, comment='解决人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class Adjustment(Base):
    """调整记录"""
    __tablename__ = 'reconciliation_adjustments'
    __table_args__ = (
        Index('ix_reconciliation_adj_anomaly', 'anomaly_id'),
        Index('ix_reconciliation_adj_statement', 'statement_id'),
        Index('ix_reconciliation_adj_status', 'approval_status'),
        {'comment': '调整记录'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    anomaly_id = Column(Integer, nullable=False, comment='异常记录ID')
    statement_id = Column(Integer, nullable=False, comment='对账单ID')
    line_item_id = Column(Integer, nullable=False, comment='行项ID')
    original_amount = Column(Numeric(14, 2), nullable=False, comment='原金额')
    adjusted_amount = Column(Numeric(14, 2), nullable=False, comment='调整后金额')
    adjustment_reason = Column(Text, nullable=False, comment='调整原因')
    approval_status = Column(String(32), nullable=False, default='pending_approval', comment='审批状态: pending_approval/approved/rejected/escalated')
    approval_level = Column(String(32), comment='审批层级: manager/director')
    approved_by = Column(BigInteger, comment='审批人')
    approved_at = Column(DateTime, comment='审批时间')
    reject_reason = Column(Text, comment='驳回原因')
    created_by = Column(BigInteger, nullable=False, comment='发起人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class PaymentRequest(Base):
    """付款申请"""
    __tablename__ = 'reconciliation_payment_requests'
    __table_args__ = (
        UniqueConstraint('statement_id', name='uk_reconciliation_pr_statement'),
        Index('ix_reconciliation_pr_supplier', 'supplier_id'),
        Index('ix_reconciliation_pr_status', 'payment_status'),
        {'comment': '付款申请'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    statement_id = Column(Integer, nullable=False, comment='对账单ID')
    supplier_id = Column(Integer, nullable=False, comment='供应商ID')
    statement_no = Column(String(64), comment='对账单编号')
    payable_amount = Column(Numeric(14, 2), nullable=False, comment='应付金额')
    paid_amount = Column(Numeric(14, 2), default=0, comment='已付金额')
    payment_status = Column(String(32), nullable=False, default='pending_payment', comment='付款状态: pending_payment/partially_paid/paid')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class PaymentRecord(Base):
    """付款记录"""
    __tablename__ = 'reconciliation_payment_records'
    __table_args__ = (
        Index('ix_reconciliation_pmr_request', 'request_id'),
        Index('ix_reconciliation_pmr_statement', 'statement_id'),
        {'comment': '付款记录'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    request_id = Column(Integer, nullable=False, comment='付款申请ID')
    statement_id = Column(Integer, nullable=False, comment='对账单ID')
    payment_amount = Column(Numeric(14, 2), nullable=False, comment='付款金额')
    payment_date = Column(Date, nullable=False, comment='付款日期')
    bank_reference = Column(String(128), comment='银行流水号')
    remark = Column(Text, comment='备注')
    created_by = Column(BigInteger, comment='录入人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class PaymentEvidence(Base):
    """支付凭证"""
    __tablename__ = 'reconciliation_payment_evidences'
    __table_args__ = (
        Index('ix_reconciliation_pe_related', 'related_type', 'related_id'),
        {'comment': '支付凭证'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    related_type = Column(String(32), nullable=False, comment='关联类型: payment_record/settlement_detail')
    related_id = Column(Integer, nullable=False, comment='关联ID')
    file_name = Column(String(255), nullable=False, comment='文件名')
    file_path = Column(String(512), nullable=False, comment='文件路径')
    file_size = Column(Integer, comment='文件大小(字节)')
    mime_type = Column(String(128), comment='MIME类型')
    uploaded_by = Column(BigInteger, comment='上传人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class SettlementDetail(Base):
    """结算明细"""
    __tablename__ = 'reconciliation_settlement_details'
    __table_args__ = (
        Index('ix_reconciliation_sd_order', 'order_id'),
        Index('ix_reconciliation_sd_supplier', 'supplier_id'),
        Index('ix_reconciliation_sd_status', 'status'),
        {'comment': '结算明细'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    order_id = Column(Integer, nullable=False, comment='委外工单ID')
    order_no = Column(String(64), nullable=False, comment='委外单号')
    supplier_id = Column(Integer, nullable=False, comment='供应商ID')
    statement_id = Column(Integer, comment='关联对账单ID')
    status = Column(String(32), nullable=False, default='draft', comment='状态: draft/finalized')

    # === 订购基准 ===
    ordered_quantity = Column(Integer, comment='订购数量')
    ordered_unit_price = Column(Numeric(14, 2), comment='订购单价')
    ordered_amount = Column(Numeric(14, 2), default=0, comment='订购总金额(下单花的钱)')

    # === 实际交付 ===
    actual_delivered_qty = Column(Integer, comment='实际交付数量')
    actual_delivered_amount = Column(Numeric(14, 2), default=0, comment='实际交付金额')

    # === 虚拟入库 ===
    virtual_inbound_amount = Column(Numeric(14, 2), default=0, comment='虚拟入库总金额(补发价值)')

    # === 异常扣除 ===
    anomaly_deduction_amount = Column(Numeric(14, 2), default=0, comment='异常扣除总金额')

    # === 物流费用 ===
    logistics_cost = Column(Numeric(14, 2), default=0, comment='物流费用')

    # === 差异 ===
    variance = Column(Numeric(14, 2), default=0, comment='差异金额 = ordered - (actual + virtual - deduction + logistics)')
    variance_reasons = Column(JSONB, comment='差异原因列表')

    # === 保留字段 ===
    total_cost = Column(Numeric(14, 2), default=0, comment='总成本')
    customer_payment = Column(Numeric(14, 2), default=0, comment='客户付款金额')
    net_profit = Column(Numeric(14, 2), default=0, comment='净利润')
    finalized_at = Column(DateTime, comment='确认时间')
    finalized_by = Column(BigInteger, comment='确认人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class SettlementLineItem(Base):
    """结算行项"""
    __tablename__ = 'reconciliation_settlement_line_items'
    __table_args__ = (
        Index('ix_reconciliation_sli_settlement', 'settlement_id'),
        {'comment': '结算行项'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    settlement_id = Column(Integer, nullable=False, comment='结算明细ID')
    item_type = Column(String(32), nullable=False, comment='类型: process_fee/logistics/re_shipment/deduction/rework/customer_payment')
    description = Column(String(255), comment='描述')
    amount = Column(Numeric(14, 2), nullable=False, comment='金额')
    is_income = Column(Boolean, default=False, comment='是否收入项')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class VirtualInbound(Base):
    """虚拟入库记录 — 因异常补发的材料/零件登记"""
    __tablename__ = 'reconciliation_virtual_inbounds'
    __table_args__ = (
        Index('ix_virtual_inbound_order', 'order_id'),
        Index('ix_virtual_inbound_type', 'inbound_type'),
        Index('ix_virtual_inbound_status', 'status'),
        {'comment': '虚拟入库记录'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    order_id = Column(Integer, ForeignKey('entrust_outsource_orders.id', name='fk_reconciliation_vi_order',
                                          use_alter=True, ondelete='RESTRICT'),
                      nullable=False, comment='关联委外工单ID')
    order_no = Column(String(64), comment='委外单号(冗余)')
    part_id = Column(Integer, ForeignKey('entrust_parts.id', name='fk_reconciliation_vi_part',
                                         use_alter=True, ondelete='SET NULL'),
                     comment='零件ID')
    part_no = Column(String(64), comment='零件编号')
    part_name = Column(String(255), comment='零件名称')

    # 入库类型
    inbound_type = Column(String(32), nullable=False,
                          comment='入库类型: re_shipment_in(补发入库) / anomaly_deduction(异常扣除)')

    # 数量与金额
    quantity = Column(Integer, nullable=False, comment='入库数量')
    unit_price = Column(Numeric(14, 2), nullable=False, comment='单价')
    amount = Column(Numeric(14, 2), nullable=False, comment='金额 = quantity × unit_price')

    # 异常追溯
    production_anomaly_id = Column(Integer, ForeignKey('reconciliation_production_anomalies.id',
                                                       name='fk_reconciliation_vi_anomaly',
                                                       ondelete='SET NULL'),
                                   comment='关联生产异常ID')
    re_shipment_id = Column(Integer, ForeignKey('reconciliation_re_shipments.id',
                                                name='fk_reconciliation_vi_reshipment',
                                                ondelete='SET NULL'),
                            comment='关联补发记录ID')
    anomaly_reason = Column(Text, nullable=False, comment='异常原因说明(必填)')
    responsible_party = Column(String(32), nullable=False, comment='责任方: material_supplier/processor')

    # 状态
    status = Column(String(32), default='pending',
                    comment='状态: pending/confirmed/linked_to_settlement/cancelled')

    # 元数据
    created_by = Column(BigInteger, comment='操作人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class LineItemVarianceReason(Base):
    """行项差异原因 — 记录每个差异行项的具体原因"""
    __tablename__ = 'reconciliation_line_item_variance_reasons'
    __table_args__ = (
        Index('ix_variance_reason_line_item', 'line_item_id'),
        {'comment': '行项差异原因'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    line_item_id = Column(Integer, ForeignKey('reconciliation_line_items.id',
                                              name='fk_reconciliation_vr_line_item',
                                              ondelete='CASCADE'),
                          nullable=False, comment='对账单行项ID')
    reason_type = Column(String(32), nullable=False,
                         comment='原因类型: material_damage/process_error/unusable/'
                                 'partial_delivery/virtual_inbound/anomaly_deduction')
    production_anomaly_id = Column(Integer, ForeignKey('reconciliation_production_anomalies.id',
                                                       name='fk_reconciliation_vr_anomaly',
                                                       ondelete='SET NULL'),
                                   comment='关联生产异常ID')
    virtual_inbound_id = Column(Integer, ForeignKey('reconciliation_virtual_inbounds.id',
                                                    name='fk_reconciliation_vr_virtual_inbound',
                                                    ondelete='SET NULL'),
                                comment='关联虚拟入库ID')
    deduction_id = Column(Integer, ForeignKey('reconciliation_deductions.id',
                                              name='fk_reconciliation_vr_deduction',
                                              ondelete='SET NULL'),
                          comment='关联扣款记录ID')
    description = Column(Text, comment='原因描述')
    impact_amount = Column(Numeric(14, 2), comment='影响金额')
    responsible_party = Column(String(32), comment='责任方')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class ProductionAnomaly(Base):
    """生产异常"""
    __tablename__ = 'reconciliation_production_anomalies'
    __table_args__ = (
        Index('ix_reconciliation_pa_order', 'order_id'),
        Index('ix_reconciliation_pa_status', 'status'),
        Index('ix_reconciliation_pa_liability', 'liability_type'),
        {'comment': '生产异常'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    order_id = Column(Integer, nullable=False, comment='委外工单ID')
    order_no = Column(String(64), comment='委外单号')
    part_id = Column(Integer, comment='零件ID')
    anomaly_type = Column(String(32), nullable=False, comment='异常类型: material_damage/process_error/unusable')
    description = Column(Text, comment='损失描述')
    occurred_at = Column(DateTime, nullable=False, comment='发生时间')
    liability_type = Column(String(32), comment='责任类型: material_supplier_fault/processor_fault')
    material_cost = Column(Numeric(14, 2), default=0, comment='材料成本')
    rework_cost = Column(Numeric(14, 2), default=0, comment='返工成本')
    delay_penalty = Column(Numeric(14, 2), default=0, comment='误工费')
    total_loss = Column(Numeric(14, 2), default=0, comment='总损失金额')
    status = Column(String(32), nullable=False, default='open', comment='状态: open/liability_confirmed/resolved/closed')
    created_by = Column(BigInteger, comment='创建人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class ReShipment(Base):
    """补发记录"""
    __tablename__ = 'reconciliation_re_shipments'
    __table_args__ = (
        Index('ix_reconciliation_rs_anomaly', 'production_anomaly_id'),
        Index('ix_reconciliation_rs_status', 'status'),
        {'comment': '补发记录'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    production_anomaly_id = Column(Integer, nullable=False, comment='生产异常ID')
    shipment_type = Column(String(32), nullable=False, comment='补发类型: material/part')
    responsible_party = Column(String(32), nullable=False, comment='责任方: material_supplier/processor')
    description = Column(Text, comment='补发说明')
    status = Column(String(32), nullable=False, default='pending', comment='状态: pending/shipped/received')
    created_by = Column(BigInteger, comment='创建人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class Deduction(Base):
    """扣款记录"""
    __tablename__ = 'reconciliation_deductions'
    __table_args__ = (
        Index('ix_reconciliation_ded_anomaly', 'production_anomaly_id'),
        Index('ix_reconciliation_ded_status', 'status'),
        {'comment': '扣款记录'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    production_anomaly_id = Column(Integer, nullable=False, comment='生产异常ID')
    order_id = Column(Integer, comment='委外工单ID')
    amount = Column(Numeric(14, 2), nullable=False, comment='扣款金额')
    reason = Column(Text, comment='扣款原因')
    status = Column(String(32), nullable=False, default='pending', comment='状态: pending/applied/cancelled')
    applied_to_settlement_id = Column(Integer, comment='已纳入的结算明细ID')
    created_by = Column(BigInteger, comment='创建人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class NegotiationRecord(Base):
    """协商记录"""
    __tablename__ = 'reconciliation_negotiation_records'
    __table_args__ = (
        Index('ix_reconciliation_nr_anomaly', 'production_anomaly_id'),
        {'comment': '协商记录'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    production_anomaly_id = Column(Integer, nullable=False, comment='生产异常ID')
    negotiation_time = Column(DateTime, nullable=False, comment='协商时间')
    participants = Column(Text, comment='参与方')
    result = Column(Text, comment='协商结果')
    created_by = Column(BigInteger, comment='记录人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class ReconciliationAuditLog(Base):
    """审计日志"""
    __tablename__ = 'reconciliation_audit_logs'
    __table_args__ = (
        Index('ix_reconciliation_al_entity', 'entity_type', 'entity_id'),
        Index('ix_reconciliation_al_action', 'action'),
        Index('ix_reconciliation_al_operator', 'operator_id'),
        Index('ix_reconciliation_al_created', 'created_at'),
        {'comment': '审计日志'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    entity_type = Column(String(64), nullable=False, comment='实体类型: statement/anomaly/adjustment/payment/settlement')
    entity_id = Column(Integer, nullable=False, comment='实体ID')
    action = Column(String(32), nullable=False, comment='操作: create/update/confirm/approve/reject/export/delete')
    operator_id = Column(BigInteger, nullable=False, comment='操作人ID')
    operator_name = Column(String(64), comment='操作人姓名')
    detail = Column(JSONB, comment='操作详情(变更前后值)')
    ip_address = Column(String(64), comment='IP地址')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class ConfirmationHistory(Base):
    """确认历史"""
    __tablename__ = 'reconciliation_confirmation_history'
    __table_args__ = (
        Index('ix_reconciliation_ch_statement', 'statement_id'),
        {'comment': '确认历史'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    statement_id = Column(Integer, nullable=False, comment='对账单ID')
    action = Column(String(32), nullable=False, comment='操作类型: confirm/dispute/withdraw')
    operator_id = Column(BigInteger, nullable=False, comment='操作人')
    operator_name = Column(String(64), comment='操作人姓名')
    remark = Column(Text, comment='备注/争议说明')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
