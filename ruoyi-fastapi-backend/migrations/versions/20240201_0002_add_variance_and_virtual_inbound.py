"""add variance calculation fields and virtual inbound tables

Revision ID: 20240201_0002
Revises: 20240101_0001
Create Date: 2024-02-01 00:00:00

增量迁移：
  - 新增 reconciliation_virtual_inbounds 表（虚拟入库记录）
  - 新增 reconciliation_line_item_variance_reasons 表（行项差异原因）
  - 修改 reconciliation_line_items 表：添加订购基准、实际交付、差异计算字段
  - 修改 reconciliation_statements 表：添加汇总字段
  - 修改 reconciliation_settlement_details 表：添加订购vs实际对比字段
  - 数据回填：旧数据兼容处理
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '20240201_0002'
down_revision: Union[str, Sequence[str], None] = '20240101_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==================================================================
    # 1. 新增 reconciliation_virtual_inbounds 表
    # ==================================================================
    op.create_table(
        'reconciliation_virtual_inbounds',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('order_id', sa.Integer(), nullable=False, comment='关联委外工单ID'),
        sa.Column('order_no', sa.String(length=64), nullable=True, comment='委外单号(冗余)'),
        sa.Column('part_id', sa.Integer(), nullable=True, comment='零件ID'),
        sa.Column('part_no', sa.String(length=64), nullable=True, comment='零件编号'),
        sa.Column('part_name', sa.String(length=255), nullable=True, comment='零件名称'),
        sa.Column('inbound_type', sa.String(length=32), nullable=False,
                  comment='入库类型: re_shipment_in(补发入库) / anomaly_deduction(异常扣除)'),
        sa.Column('quantity', sa.Integer(), nullable=False, comment='入库数量'),
        sa.Column('unit_price', sa.Numeric(14, 2), nullable=False, comment='单价'),
        sa.Column('amount', sa.Numeric(14, 2), nullable=False,
                  comment='金额 = quantity × unit_price'),
        sa.Column('production_anomaly_id', sa.Integer(), nullable=True, comment='关联生产异常ID'),
        sa.Column('re_shipment_id', sa.Integer(), nullable=True, comment='关联补发记录ID'),
        sa.Column('anomaly_reason', sa.Text(), nullable=False, comment='异常原因说明(必填)'),
        sa.Column('responsible_party', sa.String(length=32), nullable=False,
                  comment='责任方: material_supplier/processor'),
        sa.Column('status', sa.String(length=32), nullable=False,
                  server_default=sa.text("'pending'"),
                  comment='状态: pending/confirmed/linked_to_settlement/cancelled'),
        sa.Column('created_by', sa.BigInteger(), nullable=True, comment='操作人'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'),
                  comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'),
                  comment='更新时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_virtual_inbounds'),
        sa.ForeignKeyConstraint(
            ['order_id'], ['entrust_outsource_orders.id'],
            name='fk_reconciliation_vi_order', use_alter=True, ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(
            ['part_id'], ['entrust_parts.id'],
            name='fk_reconciliation_vi_part', use_alter=True, ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['production_anomaly_id'], ['reconciliation_production_anomalies.id'],
            name='fk_reconciliation_vi_anomaly', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['re_shipment_id'], ['reconciliation_re_shipments.id'],
            name='fk_reconciliation_vi_reshipment', ondelete='SET NULL'),
        comment='虚拟入库记录',
    )
    op.create_index('ix_virtual_inbound_order', 'reconciliation_virtual_inbounds', ['order_id'])
    op.create_index('ix_virtual_inbound_type', 'reconciliation_virtual_inbounds', ['inbound_type'])
    op.create_index('ix_virtual_inbound_status', 'reconciliation_virtual_inbounds', ['status'])

    # ==================================================================
    # 2. 新增 reconciliation_line_item_variance_reasons 表
    # ==================================================================
    op.create_table(
        'reconciliation_line_item_variance_reasons',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
        sa.Column('line_item_id', sa.Integer(), nullable=False, comment='对账单行项ID'),
        sa.Column('reason_type', sa.String(length=32), nullable=False,
                  comment='原因类型: material_damage/process_error/unusable/'
                          'partial_delivery/virtual_inbound/anomaly_deduction'),
        sa.Column('production_anomaly_id', sa.Integer(), nullable=True, comment='关联生产异常ID'),
        sa.Column('virtual_inbound_id', sa.Integer(), nullable=True, comment='关联虚拟入库ID'),
        sa.Column('deduction_id', sa.Integer(), nullable=True, comment='关联扣款记录ID'),
        sa.Column('description', sa.Text(), nullable=True, comment='原因描述'),
        sa.Column('impact_amount', sa.Numeric(14, 2), nullable=True, comment='影响金额'),
        sa.Column('responsible_party', sa.String(length=32), nullable=True, comment='责任方'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'),
                  comment='创建时间'),
        sa.PrimaryKeyConstraint('id', name='pk_reconciliation_line_item_variance_reasons'),
        sa.ForeignKeyConstraint(
            ['line_item_id'], ['reconciliation_line_items.id'],
            name='fk_reconciliation_vr_line_item', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['production_anomaly_id'], ['reconciliation_production_anomalies.id'],
            name='fk_reconciliation_vr_anomaly', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['virtual_inbound_id'], ['reconciliation_virtual_inbounds.id'],
            name='fk_reconciliation_vr_virtual_inbound', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['deduction_id'], ['reconciliation_deductions.id'],
            name='fk_reconciliation_vr_deduction', ondelete='SET NULL'),
        comment='行项差异原因',
    )
    op.create_index('ix_variance_reason_line_item', 'reconciliation_line_item_variance_reasons',
                    ['line_item_id'])

    # ==================================================================
    # 3. 修改 reconciliation_line_items 表：添加差异计算相关字段
    # ==================================================================
    # 订购基准
    op.add_column('reconciliation_line_items',
                  sa.Column('ordered_quantity', sa.Integer(), nullable=True,
                            comment='订购数量'))
    op.add_column('reconciliation_line_items',
                  sa.Column('ordered_unit_price', sa.Numeric(14, 2), nullable=True,
                            comment='订购单价'))
    op.add_column('reconciliation_line_items',
                  sa.Column('order_amount', sa.Numeric(14, 2), nullable=True,
                            comment='订购金额 = ordered_quantity × ordered_unit_price'))
    # 实际交付
    op.add_column('reconciliation_line_items',
                  sa.Column('actual_delivered_qty', sa.Integer(), nullable=True,
                            comment='实际交付数量(质检合格)'))
    op.add_column('reconciliation_line_items',
                  sa.Column('actual_delivered_value', sa.Numeric(14, 2),
                            server_default=sa.text('0'), nullable=True,
                            comment='实际交付价值 = actual_delivered_qty × unit_price'))
    # 虚拟入库
    op.add_column('reconciliation_line_items',
                  sa.Column('virtual_inbound_value', sa.Numeric(14, 2),
                            server_default=sa.text('0'), nullable=True,
                            comment='虚拟入库价值(补发部分)'))
    # 异常扣除
    op.add_column('reconciliation_line_items',
                  sa.Column('anomaly_deduction_amount', sa.Numeric(14, 2),
                            server_default=sa.text('0'), nullable=True,
                            comment='异常扣除金额(不补发部分)'))
    # 物流费用
    op.add_column('reconciliation_line_items',
                  sa.Column('logistics_cost', sa.Numeric(14, 2),
                            server_default=sa.text('0'), nullable=True,
                            comment='物流费用'))
    # 差异计算结果
    op.add_column('reconciliation_line_items',
                  sa.Column('variance', sa.Numeric(14, 2),
                            server_default=sa.text('0'), nullable=True,
                            comment='差异金额 = order_amount - (actual + virtual - deduction + logistics)'))
    op.add_column('reconciliation_line_items',
                  sa.Column('has_mismatch', sa.Boolean(),
                            server_default=sa.text('false'), nullable=True,
                            comment='是否货不对板(variance != 0)'))
    op.add_column('reconciliation_line_items',
                  sa.Column('variance_reasons', postgresql.JSONB(astext_type=sa.Text()),
                            nullable=True,
                            comment='差异原因列表(关联的异常记录摘要)'))

    # ==================================================================
    # 4. 修改 reconciliation_statements 表：添加汇总字段
    # ==================================================================
    op.add_column('reconciliation_statements',
                  sa.Column('total_ordered_amount', sa.Numeric(14, 2),
                            server_default=sa.text('0'), nullable=True,
                            comment='订购总金额'))
    op.add_column('reconciliation_statements',
                  sa.Column('total_received_value', sa.Numeric(14, 2),
                            server_default=sa.text('0'), nullable=True,
                            comment='实际收到总价值(含虚拟入库)'))
    op.add_column('reconciliation_statements',
                  sa.Column('total_logistics_cost', sa.Numeric(14, 2),
                            server_default=sa.text('0'), nullable=True,
                            comment='物流总费用'))
    op.add_column('reconciliation_statements',
                  sa.Column('total_variance', sa.Numeric(14, 2),
                            server_default=sa.text('0'), nullable=True,
                            comment='差异总金额'))
    op.add_column('reconciliation_statements',
                  sa.Column('anomaly_count', sa.Integer(),
                            server_default=sa.text('0'), nullable=True,
                            comment='异常笔数(variance!=0的行项数)'))

    # ==================================================================
    # 5. 修改 reconciliation_settlement_details 表：添加订购vs实际对比字段
    # ==================================================================
    op.add_column('reconciliation_settlement_details',
                  sa.Column('ordered_quantity', sa.Integer(), nullable=True,
                            comment='订购数量'))
    op.add_column('reconciliation_settlement_details',
                  sa.Column('ordered_unit_price', sa.Numeric(14, 2), nullable=True,
                            comment='订购单价'))
    op.add_column('reconciliation_settlement_details',
                  sa.Column('ordered_amount', sa.Numeric(14, 2),
                            server_default=sa.text('0'), nullable=True,
                            comment='订购总金额(下单花的钱)'))
    op.add_column('reconciliation_settlement_details',
                  sa.Column('actual_delivered_qty', sa.Integer(), nullable=True,
                            comment='实际交付数量'))
    op.add_column('reconciliation_settlement_details',
                  sa.Column('actual_delivered_amount', sa.Numeric(14, 2),
                            server_default=sa.text('0'), nullable=True,
                            comment='实际交付金额'))
    op.add_column('reconciliation_settlement_details',
                  sa.Column('virtual_inbound_amount', sa.Numeric(14, 2),
                            server_default=sa.text('0'), nullable=True,
                            comment='虚拟入库总金额(补发价值)'))
    op.add_column('reconciliation_settlement_details',
                  sa.Column('anomaly_deduction_amount', sa.Numeric(14, 2),
                            server_default=sa.text('0'), nullable=True,
                            comment='异常扣除总金额'))
    op.add_column('reconciliation_settlement_details',
                  sa.Column('logistics_cost', sa.Numeric(14, 2),
                            server_default=sa.text('0'), nullable=True,
                            comment='物流费用'))
    op.add_column('reconciliation_settlement_details',
                  sa.Column('variance', sa.Numeric(14, 2),
                            server_default=sa.text('0'), nullable=True,
                            comment='差异金额 = ordered - (actual + virtual - deduction + logistics)'))
    op.add_column('reconciliation_settlement_details',
                  sa.Column('variance_reasons', postgresql.JSONB(astext_type=sa.Text()),
                            nullable=True,
                            comment='差异原因列表'))

    # ==================================================================
    # 6. 数据回填：旧数据兼容处理
    # ==================================================================
    # reconciliation_line_items: 用现有 unit_price/quantity/total_amount 回填新字段
    op.execute("""
        UPDATE reconciliation_line_items
        SET
            ordered_quantity = quantity,
            ordered_unit_price = unit_price,
            order_amount = COALESCE(unit_price, 0) * COALESCE(quantity, 0),
            actual_delivered_qty = quantity,
            actual_delivered_value = COALESCE(total_amount, 0),
            virtual_inbound_value = 0,
            anomaly_deduction_amount = 0,
            logistics_cost = 0,
            variance = 0,
            has_mismatch = false
        WHERE order_amount IS NULL
    """)

    # reconciliation_statements: 初始化新汇总字段
    op.execute("""
        UPDATE reconciliation_statements
        SET
            total_ordered_amount = COALESCE(total_amount, 0),
            total_received_value = COALESCE(total_amount, 0),
            total_logistics_cost = 0,
            total_variance = 0,
            anomaly_count = 0
        WHERE total_ordered_amount IS NULL
    """)

    # reconciliation_settlement_details: 用现有 total_cost 回填
    op.execute("""
        UPDATE reconciliation_settlement_details
        SET
            ordered_amount = COALESCE(total_cost, 0),
            actual_delivered_amount = COALESCE(total_cost, 0),
            virtual_inbound_amount = 0,
            anomaly_deduction_amount = 0,
            logistics_cost = 0,
            variance = 0
        WHERE ordered_amount IS NULL
    """)


def downgrade() -> None:
    # ==================================================================
    # 反向操作：删除新增列和新增表
    # ==================================================================

    # 5. 删除 reconciliation_settlement_details 新增列
    op.drop_column('reconciliation_settlement_details', 'variance_reasons')
    op.drop_column('reconciliation_settlement_details', 'variance')
    op.drop_column('reconciliation_settlement_details', 'logistics_cost')
    op.drop_column('reconciliation_settlement_details', 'anomaly_deduction_amount')
    op.drop_column('reconciliation_settlement_details', 'virtual_inbound_amount')
    op.drop_column('reconciliation_settlement_details', 'actual_delivered_amount')
    op.drop_column('reconciliation_settlement_details', 'actual_delivered_qty')
    op.drop_column('reconciliation_settlement_details', 'ordered_amount')
    op.drop_column('reconciliation_settlement_details', 'ordered_unit_price')
    op.drop_column('reconciliation_settlement_details', 'ordered_quantity')

    # 4. 删除 reconciliation_statements 新增列
    op.drop_column('reconciliation_statements', 'anomaly_count')
    op.drop_column('reconciliation_statements', 'total_variance')
    op.drop_column('reconciliation_statements', 'total_logistics_cost')
    op.drop_column('reconciliation_statements', 'total_received_value')
    op.drop_column('reconciliation_statements', 'total_ordered_amount')

    # 3. 删除 reconciliation_line_items 新增列
    op.drop_column('reconciliation_line_items', 'variance_reasons')
    op.drop_column('reconciliation_line_items', 'has_mismatch')
    op.drop_column('reconciliation_line_items', 'variance')
    op.drop_column('reconciliation_line_items', 'logistics_cost')
    op.drop_column('reconciliation_line_items', 'anomaly_deduction_amount')
    op.drop_column('reconciliation_line_items', 'virtual_inbound_value')
    op.drop_column('reconciliation_line_items', 'actual_delivered_value')
    op.drop_column('reconciliation_line_items', 'actual_delivered_qty')
    op.drop_column('reconciliation_line_items', 'order_amount')
    op.drop_column('reconciliation_line_items', 'ordered_unit_price')
    op.drop_column('reconciliation_line_items', 'ordered_quantity')

    # 2. 删除 reconciliation_line_item_variance_reasons 表
    op.drop_index('ix_variance_reason_line_item',
                  table_name='reconciliation_line_item_variance_reasons')
    op.drop_table('reconciliation_line_item_variance_reasons')

    # 1. 删除 reconciliation_virtual_inbounds 表
    op.drop_index('ix_virtual_inbound_status', table_name='reconciliation_virtual_inbounds')
    op.drop_index('ix_virtual_inbound_type', table_name='reconciliation_virtual_inbounds')
    op.drop_index('ix_virtual_inbound_order', table_name='reconciliation_virtual_inbounds')
    op.drop_table('reconciliation_virtual_inbounds')
