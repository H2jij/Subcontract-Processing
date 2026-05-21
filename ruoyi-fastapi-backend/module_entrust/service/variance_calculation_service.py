"""
对账系统 — 差异计算引擎 Service
=========================================
功能：
  1. 计算单个订单的对账差异（纯函数）
  2. 计算实际交付价值
  3. 聚合虚拟入库价值
  4. 聚合异常扣除金额
  5. 组合计算完整行项差异数据
  6. 关联差异原因（Production_Anomaly + VirtualInbound + Deduction）

核心公式：
  variance = order_amount - (actual_delivered_value + virtual_inbound_value
                             - anomaly_deduction_amount + logistics_cost)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_entrust.entity.do.entrust_do import EntrustOutsourceOrder
from module_entrust.entity.do.reconciliation_do import (
    Deduction,
    ProductionAnomaly,
    VirtualInbound,
)


class VarianceCalculationService:
    """差异计算引擎 — 核心对账逻辑"""

    # ------------------------------------------------------------------
    # 纯函数：差异计算
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_order_variance(
        order_amount: Decimal,
        actual_delivered_value: Decimal,
        virtual_inbound_value: Decimal,
        anomaly_deduction_amount: Decimal,
        logistics_cost: Decimal,
    ) -> Decimal:
        """
        计算单个订单的对账差异（纯函数，无 IO）。

        公式：
            variance = order_amount - (actual_delivered_value + virtual_inbound_value
                                       - anomaly_deduction_amount + logistics_cost)

        含义：
        - 差异 > 0：花的钱比收到的东西多（供应商欠我们）
        - 差异 < 0：收到的东西比花的钱多（我们欠供应商，通常不应发生）
        - 差异 = 0：账目平衡

        注意：anomaly_deduction_amount 是减项（扣除后不需要供应商交付）
        """
        received_total = (
            actual_delivered_value
            + virtual_inbound_value
            - anomaly_deduction_amount
            + logistics_cost
        )
        return order_amount - received_total

    # ------------------------------------------------------------------
    # 异步方法：实际交付价值
    # ------------------------------------------------------------------

    @staticmethod
    async def compute_actual_delivered_value(
        db: AsyncSession, order: EntrustOutsourceOrder
    ) -> tuple[int, Decimal]:
        """
        计算实际交付价值。

        当前实现：
        - 如果工单 status=delivered 且 quality_status=pass，
          默认 actual_delivered_qty = order.quantity（全部交付合格）
        - actual_delivered_value = actual_delivered_qty × unit_price

        未来可扩展：支持部分交付场景（actual_delivered_qty < ordered_quantity）
        """
        if order.status == 'delivered' and order.quality_status == 'pass':
            actual_qty = order.quantity or 0
            unit_price = Decimal(str(order.unit_price or 0))
            actual_value = Decimal(str(actual_qty)) * unit_price
            return actual_qty, actual_value

        # 未交付或质检未通过，实际交付为 0
        return 0, Decimal('0')

    # ------------------------------------------------------------------
    # 异步方法：虚拟入库价值聚合
    # ------------------------------------------------------------------

    @staticmethod
    async def get_virtual_inbound_value(
        db: AsyncSession, order_id: int
    ) -> Decimal:
        """
        计算指定工单的虚拟入库总价值。

        仅统计 inbound_type='re_shipment_in' 且 status != 'cancelled' 的记录。
        anomaly_deduction 类型的记录不计入虚拟入库价值（它们计入 anomaly_deduction_amount）。
        """
        stmt = select(
            func.coalesce(func.sum(VirtualInbound.amount), 0)
        ).where(
            VirtualInbound.order_id == order_id,
            VirtualInbound.inbound_type == 're_shipment_in',
            VirtualInbound.status != 'cancelled',
        )
        result = await db.execute(stmt)
        return Decimal(str(result.scalar_one()))

    # ------------------------------------------------------------------
    # 异步方法：异常扣除金额聚合
    # ------------------------------------------------------------------

    @staticmethod
    async def get_anomaly_deduction_amount(
        db: AsyncSession, order_id: int
    ) -> Decimal:
        """
        计算指定工单的异常扣除总金额。

        统计 status='applied' 的 Deduction 记录金额之和。
        """
        stmt = select(
            func.coalesce(func.sum(Deduction.amount), 0)
        ).where(
            Deduction.order_id == order_id,
            Deduction.status == 'applied',
        )
        result = await db.execute(stmt)
        return Decimal(str(result.scalar_one()))

    # ------------------------------------------------------------------
    # 异步方法：组合计算完整行项差异
    # ------------------------------------------------------------------

    @staticmethod
    async def compute_line_item_variance(
        db: AsyncSession, order: EntrustOutsourceOrder
    ) -> dict[str, Any]:
        """
        计算单个工单的完整差异数据。

        返回字典包含：
        - order_amount: 订购金额
        - actual_delivered_qty: 实际交付数量
        - actual_delivered_value: 实际交付价值
        - virtual_inbound_value: 虚拟入库价值
        - anomaly_deduction_amount: 异常扣除金额
        - logistics_cost: 物流费用
        - variance: 差异金额
        - has_mismatch: 是否货不对板
        - variance_reasons: 差异原因列表
        """
        # 1. 计算订购金额
        ordered_qty = order.quantity or 0
        unit_price = Decimal(str(order.unit_price or 0))
        order_amount = Decimal(str(ordered_qty)) * unit_price

        # 2. 计算实际交付价值
        actual_qty, actual_delivered_value = (
            await VarianceCalculationService.compute_actual_delivered_value(db, order)
        )

        # 3. 聚合虚拟入库价值
        virtual_inbound_value = (
            await VarianceCalculationService.get_virtual_inbound_value(db, order.id)
        )

        # 4. 聚合异常扣除金额
        anomaly_deduction_amount = (
            await VarianceCalculationService.get_anomaly_deduction_amount(db, order.id)
        )

        # 5. 物流费用（当前默认为 0，后续可从物流表获取）
        logistics_cost = Decimal('0')

        # 6. 计算差异
        variance = VarianceCalculationService.calculate_order_variance(
            order_amount=order_amount,
            actual_delivered_value=actual_delivered_value,
            virtual_inbound_value=virtual_inbound_value,
            anomaly_deduction_amount=anomaly_deduction_amount,
            logistics_cost=logistics_cost,
        )

        # 7. 关联差异原因
        has_mismatch = variance != Decimal('0')
        variance_reasons: list[dict[str, Any]] = []
        if has_mismatch:
            variance_reasons = await VarianceCalculationService.link_variance_reasons(
                db, order.id, variance
            )

        return {
            'order_amount': order_amount,
            'actual_delivered_qty': actual_qty,
            'actual_delivered_value': actual_delivered_value,
            'virtual_inbound_value': virtual_inbound_value,
            'anomaly_deduction_amount': anomaly_deduction_amount,
            'logistics_cost': logistics_cost,
            'variance': variance,
            'has_mismatch': has_mismatch,
            'variance_reasons': variance_reasons,
        }

    # ------------------------------------------------------------------
    # 异步方法：关联差异原因
    # ------------------------------------------------------------------

    @staticmethod
    async def link_variance_reasons(
        db: AsyncSession, order_id: int, variance: Decimal
    ) -> list[dict[str, Any]]:
        """
        当 variance != 0 时，自动关联导致差异的记录。

        查找逻辑：
        1. 查询该工单的所有 ProductionAnomaly（非 closed 状态）
        2. 查询该工单的所有 VirtualInbound（re_shipment_in 类型，非 cancelled）
        3. 查询该工单的所有 Deduction（applied 状态）

        每条原因包含：
        - reason_type: 原因类型
        - description: 描述
        - impact_amount: 影响金额
        - responsible_party: 责任方
        - production_anomaly_id / virtual_inbound_id / deduction_id: 关联记录ID
        """
        if variance == Decimal('0'):
            return []

        reasons: list[dict[str, Any]] = []

        # 1. 生产异常
        anomaly_stmt = select(ProductionAnomaly).where(
            ProductionAnomaly.order_id == order_id,
            ProductionAnomaly.status != 'closed',
        )
        anomaly_result = await db.execute(anomaly_stmt)
        for anomaly in anomaly_result.scalars():
            reasons.append({
                'reason_type': anomaly.anomaly_type,
                'description': anomaly.description,
                'impact_amount': str(anomaly.total_loss or Decimal('0')),
                'responsible_party': anomaly.liability_type,
                'production_anomaly_id': anomaly.id,
            })

        # 2. 虚拟入库（补发）
        inbound_stmt = select(VirtualInbound).where(
            VirtualInbound.order_id == order_id,
            VirtualInbound.inbound_type == 're_shipment_in',
            VirtualInbound.status != 'cancelled',
        )
        inbound_result = await db.execute(inbound_stmt)
        for vi in inbound_result.scalars():
            reasons.append({
                'reason_type': 'virtual_inbound',
                'description': vi.anomaly_reason,
                'impact_amount': str(vi.amount or Decimal('0')),
                'responsible_party': vi.responsible_party,
                'virtual_inbound_id': vi.id,
            })

        # 3. 扣款记录
        deduction_stmt = select(Deduction).where(
            Deduction.order_id == order_id,
            Deduction.status == 'applied',
        )
        deduction_result = await db.execute(deduction_stmt)
        for d in deduction_result.scalars():
            reasons.append({
                'reason_type': 'anomaly_deduction',
                'description': d.reason,
                'impact_amount': str(d.amount or Decimal('0')),
                'deduction_id': d.id,
            })

        return reasons
