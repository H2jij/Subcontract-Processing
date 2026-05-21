"""create reconciliation tables

Revision ID: 20240101_0001
Revises:
Create Date: 2024-01-01 00:00:00

创建对账系统全部 16 张表，包含外键约束与索引。
对应 SQLAlchemy 模型: ``module_entrust/entity/do/reconciliation_do.py``。

涵盖表：
    1. reconciliation_statements          对账单
    2. reconciliation_line_items          对账单行项
    3. reconciliation_supplier_claims     供应商账单
    4. reconciliation_anomalies           异常记录
    5. reconciliation_adjustments         调整记录
    6. reconciliation_payment_requests    付款申请
    7. reconciliation_payment_records     付款记录
    8. reconciliation_payment_evidences   支付凭证
    9. reconciliation_settlement_details  结算明细
   10. reconciliation_settlement_line_items 结算行项
   11. reconciliation_production_anomalies 生产异常
   12. reconciliation_re_shipments        补发记录
   13. reconciliation_deductions          扣款记录
   14. reconciliation_negotiation_records 协商记录
   15. reconciliation_audit_logs          审计日志
   16. reconciliation_confirmation_history 确认历史
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '20240101_0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# 关联到既有业务表的外键命名（使用 use_alter=True 让 Alembic 在 ALTER 阶段创建，
# 避免目标库未先建好 entrust_* 表时阻塞。）
# ---------------------------------------------------------------------------
_FK_KW = {'ondelete': 'RESTRICT'}


def upgrade() -> None:
    # ------------------------------------------------------------------ 1
    op.create_table(
        'reconciliation_statements',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('statement_no', sa.String(length=64), nullable=False, comment='对账单编号 REC-{YYYYMM}-{supplier_id}-{seq}'),
        sa.Column('supplier_id', sa.Integer(), nullable=False, comment='供应商ID'),
        sa.Column('period_start', sa.Date(), nullable=False, comment='对账周期起始'),
        sa.Column('period_end', sa.Date(), nullable=False, comment='对账周期结束'),
        sa.Column('total_amount', sa.Numeric(14, 2), server_default=sa.text('0'), comment='汇总金额'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default=sa.text("'pending'"), comment='状态: pending/confirmed/disputed/timeout/paid'),
        sa.Column('confirmation_status', sa.String(length=32), nullable=False, server_default=sa.text("'pending'"), comment='确认状态: pending/confirmed/disputed'),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True, comment='确认时间'),
        sa.Column('confirmed_by', sa.BigInteger(), nullable=True, comment='确认人'),
        sa.Column('dispute_reason', sa.Text(), nullable=True, comment='争议说明'),
        sa.Column('notified_at', sa.DateTime(), nullable=True, comment='通知发送时间'),
        sa.Column('timeout_at', sa.DateTime(), nullable=True, comment='超时标记时间'),
        sa.Column('created_by', sa.BigInteger(), nullable=True, comment='创建人'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='更新时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_statements'),
        sa.UniqueConstraint('statement_no', name='uk_reconciliation_statement_no'),
        sa.ForeignKeyConstraint(['supplier_id'], ['entrust_suppliers.id'], name='fk_reconciliation_stmt_supplier', use_alter=True, **_FK_KW),
        comment='对账单',
    )
    op.create_index('ix_reconciliation_stmt_supplier', 'reconciliation_statements', ['supplier_id'])
    op.create_index('ix_reconciliation_stmt_period', 'reconciliation_statements', ['period_start', 'period_end'])
    op.create_index('ix_reconciliation_stmt_status', 'reconciliation_statements', ['status'])
    op.create_index('ix_reconciliation_stmt_confirmation', 'reconciliation_statements', ['confirmation_status'])

    # ------------------------------------------------------------------ 2
    op.create_table(
        'reconciliation_line_items',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('statement_id', sa.Integer(), nullable=False, comment='对账单ID'),
        sa.Column('order_id', sa.Integer(), nullable=True, comment='委外工单ID'),
        sa.Column('order_no', sa.String(length=64), nullable=False, comment='委外单号'),
        sa.Column('process_name', sa.String(length=200), nullable=True, comment='工序名称'),
        sa.Column('part_no', sa.String(length=64), nullable=True, comment='零件编号'),
        sa.Column('part_name', sa.String(length=255), nullable=True, comment='零件名称'),
        sa.Column('unit_price', sa.Numeric(14, 2), nullable=True, comment='单价'),
        sa.Column('quantity', sa.Integer(), nullable=True, comment='数量'),
        sa.Column('total_amount', sa.Numeric(14, 2), nullable=True, comment='行项金额'),
        sa.Column('is_frozen', sa.Boolean(), server_default=sa.text('false'), comment='是否冻结(调整审批中)'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='更新时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_line_items'),
        sa.ForeignKeyConstraint(['statement_id'], ['reconciliation_statements.id'], name='fk_reconciliation_li_statement', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_id'], ['entrust_outsource_orders.id'], name='fk_reconciliation_li_order', use_alter=True, ondelete='SET NULL'),
        comment='对账单行项',
    )
    op.create_index('ix_reconciliation_li_statement', 'reconciliation_line_items', ['statement_id'])
    op.create_index('ix_reconciliation_li_order', 'reconciliation_line_items', ['order_no'])

    # ------------------------------------------------------------------ 3
    op.create_table(
        'reconciliation_supplier_claims',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('statement_id', sa.Integer(), nullable=False, comment='对账单ID'),
        sa.Column('supplier_id', sa.Integer(), nullable=False, comment='供应商ID'),
        sa.Column('claim_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='供应商提交的账单明细JSON'),
        sa.Column('submitted_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='提交时间'),
        sa.Column('submitted_by', sa.BigInteger(), nullable=True, comment='提交人'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_supplier_claims'),
        sa.ForeignKeyConstraint(['statement_id'], ['reconciliation_statements.id'], name='fk_reconciliation_claim_statement', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supplier_id'], ['entrust_suppliers.id'], name='fk_reconciliation_claim_supplier', use_alter=True, **_FK_KW),
        comment='供应商账单',
    )
    op.create_index('ix_reconciliation_claim_statement', 'reconciliation_supplier_claims', ['statement_id'])
    op.create_index('ix_reconciliation_claim_supplier', 'reconciliation_supplier_claims', ['supplier_id'])

    # ------------------------------------------------------------------ 4
    op.create_table(
        'reconciliation_anomalies',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('statement_id', sa.Integer(), nullable=False, comment='对账单ID'),
        sa.Column('claim_id', sa.Integer(), nullable=True, comment='供应商账单ID'),
        sa.Column('line_item_id', sa.Integer(), nullable=True, comment='对账单行项ID'),
        sa.Column('anomaly_type', sa.String(length=32), nullable=False, comment='类型: amount_diff/supplier_missing/duplicate/quality_dispute'),
        sa.Column('severity', sa.String(length=16), nullable=False, comment='严重程度: critical/warning/info'),
        sa.Column('diff_amount', sa.Numeric(14, 2), nullable=True, comment='差异金额'),
        sa.Column('description', sa.Text(), nullable=True, comment='异常描述'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default=sa.text("'open'"), comment='状态: open/investigating/resolved/closed'),
        sa.Column('resolved_at', sa.DateTime(), nullable=True, comment='解决时间'),
        sa.Column('resolved_by', sa.BigInteger(), nullable=True, comment='解决人'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='更新时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_anomalies'),
        sa.ForeignKeyConstraint(['statement_id'], ['reconciliation_statements.id'], name='fk_reconciliation_anomaly_statement', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['claim_id'], ['reconciliation_supplier_claims.id'], name='fk_reconciliation_anomaly_claim', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['line_item_id'], ['reconciliation_line_items.id'], name='fk_reconciliation_anomaly_line_item', ondelete='SET NULL'),
        comment='异常记录',
    )
    op.create_index('ix_reconciliation_anomaly_statement', 'reconciliation_anomalies', ['statement_id'])
    op.create_index('ix_reconciliation_anomaly_type', 'reconciliation_anomalies', ['anomaly_type'])
    op.create_index('ix_reconciliation_anomaly_status', 'reconciliation_anomalies', ['status'])
    op.create_index('ix_reconciliation_anomaly_severity', 'reconciliation_anomalies', ['severity'])

    # ------------------------------------------------------------------ 5
    op.create_table(
        'reconciliation_adjustments',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('anomaly_id', sa.Integer(), nullable=False, comment='异常记录ID'),
        sa.Column('statement_id', sa.Integer(), nullable=False, comment='对账单ID'),
        sa.Column('line_item_id', sa.Integer(), nullable=False, comment='行项ID'),
        sa.Column('original_amount', sa.Numeric(14, 2), nullable=False, comment='原金额'),
        sa.Column('adjusted_amount', sa.Numeric(14, 2), nullable=False, comment='调整后金额'),
        sa.Column('adjustment_reason', sa.Text(), nullable=False, comment='调整原因'),
        sa.Column('approval_status', sa.String(length=32), nullable=False, server_default=sa.text("'pending_approval'"), comment='审批状态: pending_approval/approved/rejected/escalated'),
        sa.Column('approval_level', sa.String(length=32), nullable=True, comment='审批层级: manager/director'),
        sa.Column('approved_by', sa.BigInteger(), nullable=True, comment='审批人'),
        sa.Column('approved_at', sa.DateTime(), nullable=True, comment='审批时间'),
        sa.Column('reject_reason', sa.Text(), nullable=True, comment='驳回原因'),
        sa.Column('created_by', sa.BigInteger(), nullable=False, comment='发起人'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='更新时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_adjustments'),
        sa.ForeignKeyConstraint(['anomaly_id'], ['reconciliation_anomalies.id'], name='fk_reconciliation_adj_anomaly', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['statement_id'], ['reconciliation_statements.id'], name='fk_reconciliation_adj_statement', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['line_item_id'], ['reconciliation_line_items.id'], name='fk_reconciliation_adj_line_item', ondelete='CASCADE'),
        comment='调整记录',
    )
    op.create_index('ix_reconciliation_adj_anomaly', 'reconciliation_adjustments', ['anomaly_id'])
    op.create_index('ix_reconciliation_adj_statement', 'reconciliation_adjustments', ['statement_id'])
    op.create_index('ix_reconciliation_adj_status', 'reconciliation_adjustments', ['approval_status'])

    # ------------------------------------------------------------------ 6
    op.create_table(
        'reconciliation_payment_requests',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('statement_id', sa.Integer(), nullable=False, comment='对账单ID'),
        sa.Column('supplier_id', sa.Integer(), nullable=False, comment='供应商ID'),
        sa.Column('statement_no', sa.String(length=64), nullable=True, comment='对账单编号'),
        sa.Column('payable_amount', sa.Numeric(14, 2), nullable=False, comment='应付金额'),
        sa.Column('paid_amount', sa.Numeric(14, 2), server_default=sa.text('0'), comment='已付金额'),
        sa.Column('payment_status', sa.String(length=32), nullable=False, server_default=sa.text("'pending_payment'"), comment='付款状态: pending_payment/partially_paid/paid'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='更新时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_payment_requests'),
        sa.UniqueConstraint('statement_id', name='uk_reconciliation_pr_statement'),
        sa.ForeignKeyConstraint(['statement_id'], ['reconciliation_statements.id'], name='fk_reconciliation_pr_statement', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supplier_id'], ['entrust_suppliers.id'], name='fk_reconciliation_pr_supplier', use_alter=True, **_FK_KW),
        comment='付款申请',
    )
    op.create_index('ix_reconciliation_pr_supplier', 'reconciliation_payment_requests', ['supplier_id'])
    op.create_index('ix_reconciliation_pr_status', 'reconciliation_payment_requests', ['payment_status'])

    # ------------------------------------------------------------------ 7
    op.create_table(
        'reconciliation_payment_records',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('request_id', sa.Integer(), nullable=False, comment='付款申请ID'),
        sa.Column('statement_id', sa.Integer(), nullable=False, comment='对账单ID'),
        sa.Column('payment_amount', sa.Numeric(14, 2), nullable=False, comment='付款金额'),
        sa.Column('payment_date', sa.Date(), nullable=False, comment='付款日期'),
        sa.Column('bank_reference', sa.String(length=128), nullable=True, comment='银行流水号'),
        sa.Column('remark', sa.Text(), nullable=True, comment='备注'),
        sa.Column('created_by', sa.BigInteger(), nullable=True, comment='录入人'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_payment_records'),
        sa.ForeignKeyConstraint(['request_id'], ['reconciliation_payment_requests.id'], name='fk_reconciliation_pmr_request', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['statement_id'], ['reconciliation_statements.id'], name='fk_reconciliation_pmr_statement', ondelete='CASCADE'),
        comment='付款记录',
    )
    op.create_index('ix_reconciliation_pmr_request', 'reconciliation_payment_records', ['request_id'])
    op.create_index('ix_reconciliation_pmr_statement', 'reconciliation_payment_records', ['statement_id'])

    # ------------------------------------------------------------------ 8
    op.create_table(
        'reconciliation_payment_evidences',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('related_type', sa.String(length=32), nullable=False, comment='关联类型: payment_record/settlement_detail'),
        sa.Column('related_id', sa.Integer(), nullable=False, comment='关联ID'),
        sa.Column('file_name', sa.String(length=255), nullable=False, comment='文件名'),
        sa.Column('file_path', sa.String(length=512), nullable=False, comment='文件路径'),
        sa.Column('file_size', sa.Integer(), nullable=True, comment='文件大小(字节)'),
        sa.Column('mime_type', sa.String(length=128), nullable=True, comment='MIME类型'),
        sa.Column('uploaded_by', sa.BigInteger(), nullable=True, comment='上传人'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_payment_evidences'),
        comment='支付凭证',
    )
    op.create_index('ix_reconciliation_pe_related', 'reconciliation_payment_evidences', ['related_type', 'related_id'])

    # ------------------------------------------------------------------ 9
    op.create_table(
        'reconciliation_settlement_details',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('order_id', sa.Integer(), nullable=False, comment='委外工单ID'),
        sa.Column('order_no', sa.String(length=64), nullable=False, comment='委外单号'),
        sa.Column('supplier_id', sa.Integer(), nullable=False, comment='供应商ID'),
        sa.Column('statement_id', sa.Integer(), nullable=True, comment='关联对账单ID'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default=sa.text("'draft'"), comment='状态: draft/finalized'),
        sa.Column('total_cost', sa.Numeric(14, 2), server_default=sa.text('0'), comment='总成本'),
        sa.Column('customer_payment', sa.Numeric(14, 2), server_default=sa.text('0'), comment='客户付款金额'),
        sa.Column('net_profit', sa.Numeric(14, 2), server_default=sa.text('0'), comment='净利润'),
        sa.Column('finalized_at', sa.DateTime(), nullable=True, comment='确认时间'),
        sa.Column('finalized_by', sa.BigInteger(), nullable=True, comment='确认人'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='更新时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_settlement_details'),
        sa.ForeignKeyConstraint(['order_id'], ['entrust_outsource_orders.id'], name='fk_reconciliation_sd_order', use_alter=True, **_FK_KW),
        sa.ForeignKeyConstraint(['supplier_id'], ['entrust_suppliers.id'], name='fk_reconciliation_sd_supplier', use_alter=True, **_FK_KW),
        sa.ForeignKeyConstraint(['statement_id'], ['reconciliation_statements.id'], name='fk_reconciliation_sd_statement', ondelete='SET NULL'),
        comment='结算明细',
    )
    op.create_index('ix_reconciliation_sd_order', 'reconciliation_settlement_details', ['order_id'])
    op.create_index('ix_reconciliation_sd_supplier', 'reconciliation_settlement_details', ['supplier_id'])
    op.create_index('ix_reconciliation_sd_status', 'reconciliation_settlement_details', ['status'])

    # ------------------------------------------------------------------ 10
    op.create_table(
        'reconciliation_settlement_line_items',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('settlement_id', sa.Integer(), nullable=False, comment='结算明细ID'),
        sa.Column('item_type', sa.String(length=32), nullable=False, comment='类型: process_fee/logistics/re_shipment/deduction/rework/customer_payment'),
        sa.Column('description', sa.String(length=255), nullable=True, comment='描述'),
        sa.Column('amount', sa.Numeric(14, 2), nullable=False, comment='金额'),
        sa.Column('is_income', sa.Boolean(), server_default=sa.text('false'), comment='是否收入项'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_settlement_line_items'),
        sa.ForeignKeyConstraint(['settlement_id'], ['reconciliation_settlement_details.id'], name='fk_reconciliation_sli_settlement', ondelete='CASCADE'),
        comment='结算行项',
    )
    op.create_index('ix_reconciliation_sli_settlement', 'reconciliation_settlement_line_items', ['settlement_id'])

    # ------------------------------------------------------------------ 11
    op.create_table(
        'reconciliation_production_anomalies',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('order_id', sa.Integer(), nullable=False, comment='委外工单ID'),
        sa.Column('order_no', sa.String(length=64), nullable=True, comment='委外单号'),
        sa.Column('part_id', sa.Integer(), nullable=True, comment='零件ID'),
        sa.Column('anomaly_type', sa.String(length=32), nullable=False, comment='异常类型: material_damage/process_error/unusable'),
        sa.Column('description', sa.Text(), nullable=True, comment='损失描述'),
        sa.Column('occurred_at', sa.DateTime(), nullable=False, comment='发生时间'),
        sa.Column('liability_type', sa.String(length=32), nullable=True, comment='责任类型: material_supplier_fault/processor_fault'),
        sa.Column('material_cost', sa.Numeric(14, 2), server_default=sa.text('0'), comment='材料成本'),
        sa.Column('rework_cost', sa.Numeric(14, 2), server_default=sa.text('0'), comment='返工成本'),
        sa.Column('delay_penalty', sa.Numeric(14, 2), server_default=sa.text('0'), comment='误工费'),
        sa.Column('total_loss', sa.Numeric(14, 2), server_default=sa.text('0'), comment='总损失金额'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default=sa.text("'open'"), comment='状态: open/liability_confirmed/resolved/closed'),
        sa.Column('created_by', sa.BigInteger(), nullable=True, comment='创建人'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='更新时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_production_anomalies'),
        sa.ForeignKeyConstraint(['order_id'], ['entrust_outsource_orders.id'], name='fk_reconciliation_pa_order', use_alter=True, **_FK_KW),
        sa.ForeignKeyConstraint(['part_id'], ['entrust_parts.id'], name='fk_reconciliation_pa_part', use_alter=True, ondelete='SET NULL'),
        comment='生产异常',
    )
    op.create_index('ix_reconciliation_pa_order', 'reconciliation_production_anomalies', ['order_id'])
    op.create_index('ix_reconciliation_pa_status', 'reconciliation_production_anomalies', ['status'])
    op.create_index('ix_reconciliation_pa_liability', 'reconciliation_production_anomalies', ['liability_type'])

    # ------------------------------------------------------------------ 12
    op.create_table(
        'reconciliation_re_shipments',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('production_anomaly_id', sa.Integer(), nullable=False, comment='生产异常ID'),
        sa.Column('shipment_type', sa.String(length=32), nullable=False, comment='补发类型: material/part'),
        sa.Column('responsible_party', sa.String(length=32), nullable=False, comment='责任方: material_supplier/processor'),
        sa.Column('description', sa.Text(), nullable=True, comment='补发说明'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default=sa.text("'pending'"), comment='状态: pending/shipped/received'),
        sa.Column('created_by', sa.BigInteger(), nullable=True, comment='创建人'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='更新时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_re_shipments'),
        sa.ForeignKeyConstraint(['production_anomaly_id'], ['reconciliation_production_anomalies.id'], name='fk_reconciliation_rs_anomaly', ondelete='CASCADE'),
        comment='补发记录',
    )
    op.create_index('ix_reconciliation_rs_anomaly', 'reconciliation_re_shipments', ['production_anomaly_id'])
    op.create_index('ix_reconciliation_rs_status', 'reconciliation_re_shipments', ['status'])

    # ------------------------------------------------------------------ 13
    op.create_table(
        'reconciliation_deductions',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('production_anomaly_id', sa.Integer(), nullable=False, comment='生产异常ID'),
        sa.Column('order_id', sa.Integer(), nullable=True, comment='委外工单ID'),
        sa.Column('amount', sa.Numeric(14, 2), nullable=False, comment='扣款金额'),
        sa.Column('reason', sa.Text(), nullable=True, comment='扣款原因'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default=sa.text("'pending'"), comment='状态: pending/applied/cancelled'),
        sa.Column('applied_to_settlement_id', sa.Integer(), nullable=True, comment='已纳入的结算明细ID'),
        sa.Column('created_by', sa.BigInteger(), nullable=True, comment='创建人'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_deductions'),
        sa.ForeignKeyConstraint(['production_anomaly_id'], ['reconciliation_production_anomalies.id'], name='fk_reconciliation_ded_anomaly', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_id'], ['entrust_outsource_orders.id'], name='fk_reconciliation_ded_order', use_alter=True, ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['applied_to_settlement_id'], ['reconciliation_settlement_details.id'], name='fk_reconciliation_ded_settlement', ondelete='SET NULL'),
        comment='扣款记录',
    )
    op.create_index('ix_reconciliation_ded_anomaly', 'reconciliation_deductions', ['production_anomaly_id'])
    op.create_index('ix_reconciliation_ded_status', 'reconciliation_deductions', ['status'])

    # ------------------------------------------------------------------ 14
    op.create_table(
        'reconciliation_negotiation_records',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('production_anomaly_id', sa.Integer(), nullable=False, comment='生产异常ID'),
        sa.Column('negotiation_time', sa.DateTime(), nullable=False, comment='协商时间'),
        sa.Column('participants', sa.Text(), nullable=True, comment='参与方'),
        sa.Column('result', sa.Text(), nullable=True, comment='协商结果'),
        sa.Column('created_by', sa.BigInteger(), nullable=True, comment='记录人'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_negotiation_records'),
        sa.ForeignKeyConstraint(['production_anomaly_id'], ['reconciliation_production_anomalies.id'], name='fk_reconciliation_nr_anomaly', ondelete='CASCADE'),
        comment='协商记录',
    )
    op.create_index('ix_reconciliation_nr_anomaly', 'reconciliation_negotiation_records', ['production_anomaly_id'])

    # ------------------------------------------------------------------ 15
    op.create_table(
        'reconciliation_audit_logs',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('entity_type', sa.String(length=64), nullable=False, comment='实体类型: statement/anomaly/adjustment/payment/settlement'),
        sa.Column('entity_id', sa.Integer(), nullable=False, comment='实体ID'),
        sa.Column('action', sa.String(length=32), nullable=False, comment='操作: create/update/confirm/approve/reject/export/delete'),
        sa.Column('operator_id', sa.BigInteger(), nullable=False, comment='操作人ID'),
        sa.Column('operator_name', sa.String(length=64), nullable=True, comment='操作人姓名'),
        sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='操作详情(变更前后值)'),
        sa.Column('ip_address', sa.String(length=64), nullable=True, comment='IP地址'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_audit_logs'),
        comment='审计日志',
    )
    op.create_index('ix_reconciliation_al_entity', 'reconciliation_audit_logs', ['entity_type', 'entity_id'])
    op.create_index('ix_reconciliation_al_action', 'reconciliation_audit_logs', ['action'])
    op.create_index('ix_reconciliation_al_operator', 'reconciliation_audit_logs', ['operator_id'])
    op.create_index('ix_reconciliation_al_created', 'reconciliation_audit_logs', ['created_at'])

    # ------------------------------------------------------------------ 16
    op.create_table(
        'reconciliation_confirmation_history',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('statement_id', sa.Integer(), nullable=False, comment='对账单ID'),
        sa.Column('action', sa.String(length=32), nullable=False, comment='操作类型: confirm/dispute/withdraw'),
        sa.Column('operator_id', sa.BigInteger(), nullable=False, comment='操作人'),
        sa.Column('operator_name', sa.String(length=64), nullable=True, comment='操作人姓名'),
        sa.Column('remark', sa.Text(), nullable=True, comment='备注/争议说明'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_confirmation_history'),
        sa.ForeignKeyConstraint(['statement_id'], ['reconciliation_statements.id'], name='fk_reconciliation_ch_statement', ondelete='CASCADE'),
        comment='确认历史',
    )
    op.create_index('ix_reconciliation_ch_statement', 'reconciliation_confirmation_history', ['statement_id'])


def downgrade() -> None:
    # 反向顺序删除表（先删除依赖外键的子表）
    op.drop_index('ix_reconciliation_ch_statement', table_name='reconciliation_confirmation_history')
    op.drop_table('reconciliation_confirmation_history')

    op.drop_index('ix_reconciliation_al_created', table_name='reconciliation_audit_logs')
    op.drop_index('ix_reconciliation_al_operator', table_name='reconciliation_audit_logs')
    op.drop_index('ix_reconciliation_al_action', table_name='reconciliation_audit_logs')
    op.drop_index('ix_reconciliation_al_entity', table_name='reconciliation_audit_logs')
    op.drop_table('reconciliation_audit_logs')

    op.drop_index('ix_reconciliation_nr_anomaly', table_name='reconciliation_negotiation_records')
    op.drop_table('reconciliation_negotiation_records')

    op.drop_index('ix_reconciliation_ded_status', table_name='reconciliation_deductions')
    op.drop_index('ix_reconciliation_ded_anomaly', table_name='reconciliation_deductions')
    op.drop_table('reconciliation_deductions')

    op.drop_index('ix_reconciliation_rs_status', table_name='reconciliation_re_shipments')
    op.drop_index('ix_reconciliation_rs_anomaly', table_name='reconciliation_re_shipments')
    op.drop_table('reconciliation_re_shipments')

    op.drop_index('ix_reconciliation_pa_liability', table_name='reconciliation_production_anomalies')
    op.drop_index('ix_reconciliation_pa_status', table_name='reconciliation_production_anomalies')
    op.drop_index('ix_reconciliation_pa_order', table_name='reconciliation_production_anomalies')
    op.drop_table('reconciliation_production_anomalies')

    op.drop_index('ix_reconciliation_sli_settlement', table_name='reconciliation_settlement_line_items')
    op.drop_table('reconciliation_settlement_line_items')

    op.drop_index('ix_reconciliation_sd_status', table_name='reconciliation_settlement_details')
    op.drop_index('ix_reconciliation_sd_supplier', table_name='reconciliation_settlement_details')
    op.drop_index('ix_reconciliation_sd_order', table_name='reconciliation_settlement_details')
    op.drop_table('reconciliation_settlement_details')

    op.drop_index('ix_reconciliation_pe_related', table_name='reconciliation_payment_evidences')
    op.drop_table('reconciliation_payment_evidences')

    op.drop_index('ix_reconciliation_pmr_statement', table_name='reconciliation_payment_records')
    op.drop_index('ix_reconciliation_pmr_request', table_name='reconciliation_payment_records')
    op.drop_table('reconciliation_payment_records')

    op.drop_index('ix_reconciliation_pr_status', table_name='reconciliation_payment_requests')
    op.drop_index('ix_reconciliation_pr_supplier', table_name='reconciliation_payment_requests')
    op.drop_table('reconciliation_payment_requests')

    op.drop_index('ix_reconciliation_adj_status', table_name='reconciliation_adjustments')
    op.drop_index('ix_reconciliation_adj_statement', table_name='reconciliation_adjustments')
    op.drop_index('ix_reconciliation_adj_anomaly', table_name='reconciliation_adjustments')
    op.drop_table('reconciliation_adjustments')

    op.drop_index('ix_reconciliation_anomaly_severity', table_name='reconciliation_anomalies')
    op.drop_index('ix_reconciliation_anomaly_status', table_name='reconciliation_anomalies')
    op.drop_index('ix_reconciliation_anomaly_type', table_name='reconciliation_anomalies')
    op.drop_index('ix_reconciliation_anomaly_statement', table_name='reconciliation_anomalies')
    op.drop_table('reconciliation_anomalies')

    op.drop_index('ix_reconciliation_claim_supplier', table_name='reconciliation_supplier_claims')
    op.drop_index('ix_reconciliation_claim_statement', table_name='reconciliation_supplier_claims')
    op.drop_table('reconciliation_supplier_claims')

    op.drop_index('ix_reconciliation_li_order', table_name='reconciliation_line_items')
    op.drop_index('ix_reconciliation_li_statement', table_name='reconciliation_line_items')
    op.drop_table('reconciliation_line_items')

    op.drop_index('ix_reconciliation_stmt_confirmation', table_name='reconciliation_statements')
    op.drop_index('ix_reconciliation_stmt_status', table_name='reconciliation_statements')
    op.drop_index('ix_reconciliation_stmt_period', table_name='reconciliation_statements')
    op.drop_index('ix_reconciliation_stmt_supplier', table_name='reconciliation_statements')
    op.drop_table('reconciliation_statements')
