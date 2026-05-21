"""
对账系统 — 生产异常 / 责任判定 Service
=========================================
职责（Requirements 9.1 ~ 9.7）：
  1. 记录生产过程中的材料损坏、加工失误或零件不可使用事件
  2. 判定责任方（material_supplier_fault / processor_fault）
  3. 根据责任方触发后续处理：
       - material_supplier_fault → 自动创建材料 Re_Shipment（要求材料方重新发货）
       - processor_fault         → 由业务人员选择创建零件 Re_Shipment 或扣款记录
  4. 记录协商过程
  5. 计算损失金额：total_loss = material_cost + rework_cost + delay_penalty
     （Property 13: Production anomaly loss calculation）

设计要点：
  - 状态机：open → liability_confirmed → resolved → closed
  - 异常类型枚举：material_damage / process_error / unusable
  - 创建生产异常时需绑定 委外工单 (order_id) 与 零件 (part_id)，并冗余存储 order_no
    便于结算 / 审计追溯（Requirement 9.6）
  - calculate_total_loss 会同步更新 ProductionAnomaly.total_loss 字段并落库
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceException
from module_entrust.entity.do.entrust_do import EntrustOutsourceOrder
from module_entrust.entity.do.reconciliation_do import (
    Deduction,
    NegotiationRecord,
    ProductionAnomaly,
    ReShipment,
)
from module_entrust.service.reconciliation_audit_service import (
    ACTION_CREATE,
    ACTION_UPDATE,
    ENTITY_TYPE_PRODUCTION_ANOMALY,
    ReconciliationAuditService,
)
from module_entrust.service.virtual_inbound_service import VirtualInboundService


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 生产异常类型
ANOMALY_TYPE_MATERIAL_DAMAGE = 'material_damage'
ANOMALY_TYPE_PROCESS_ERROR = 'process_error'
ANOMALY_TYPE_UNUSABLE = 'unusable'

VALID_ANOMALY_TYPES: frozenset[str] = frozenset({
    ANOMALY_TYPE_MATERIAL_DAMAGE,
    ANOMALY_TYPE_PROCESS_ERROR,
    ANOMALY_TYPE_UNUSABLE,
})

# 责任类型
LIABILITY_MATERIAL_SUPPLIER = 'material_supplier_fault'
LIABILITY_PROCESSOR = 'processor_fault'

VALID_LIABILITY_TYPES: frozenset[str] = frozenset({
    LIABILITY_MATERIAL_SUPPLIER,
    LIABILITY_PROCESSOR,
})

# 补发类型
SHIPMENT_TYPE_MATERIAL = 'material'
SHIPMENT_TYPE_PART = 'part'

VALID_SHIPMENT_TYPES: frozenset[str] = frozenset({
    SHIPMENT_TYPE_MATERIAL,
    SHIPMENT_TYPE_PART,
})

# 责任方（Re_Shipment.responsible_party）
RESPONSIBLE_PARTY_MATERIAL_SUPPLIER = 'material_supplier'
RESPONSIBLE_PARTY_PROCESSOR = 'processor'

VALID_RESPONSIBLE_PARTIES: frozenset[str] = frozenset({
    RESPONSIBLE_PARTY_MATERIAL_SUPPLIER,
    RESPONSIBLE_PARTY_PROCESSOR,
})

# 生产异常状态
STATUS_OPEN = 'open'
STATUS_LIABILITY_CONFIRMED = 'liability_confirmed'
STATUS_RESOLVED = 'resolved'
STATUS_CLOSED = 'closed'


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _to_decimal(value, default: Decimal = Decimal('0')) -> Decimal:
    """安全转换为 Decimal；None 返回 default。"""
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ProductionAnomalyService:
    """生产异常与责任判定服务。"""

    # ------------------------------------------------------------------
    # 1. 创建生产异常（Requirement 9.1, 9.6）
    # ------------------------------------------------------------------

    @staticmethod
    async def create_anomaly(
        db: AsyncSession,
        order_id: int,
        part_id: Optional[int],
        anomaly_type: str,
        description: Optional[str],
        occurred_at: datetime,
        material_cost: Optional[Decimal] = None,
        rework_cost: Optional[Decimal] = None,
        delay_penalty: Optional[Decimal] = None,
        created_by: int = 0,
    ) -> int:
        """
        创建生产异常记录。

        - 校验 anomaly_type 合法性
        - 校验关联的委外工单存在；冗余存储 order_no 便于追溯
        - 损失三项（material_cost / rework_cost / delay_penalty）此时可选；
          通常在责任判定后再补充并由 calculate_total_loss 计算汇总

        Args:
            order_id: 委外工单 ID
            part_id: 零件 ID（可空）
            anomaly_type: 异常类型 material_damage / process_error / unusable
            description: 损失描述
            occurred_at: 异常发生时间
            material_cost / rework_cost / delay_penalty: 损失三项（可选）
            created_by: 创建人

        Returns:
            新建生产异常 ID

        Raises:
            ServiceException: 异常类型非法 / 委外工单不存在 / 发生时间缺失
        """
        if anomaly_type not in VALID_ANOMALY_TYPES:
            raise ServiceException(
                message=(
                    f'无效的异常类型: {anomaly_type}，允许值: '
                    f'{sorted(VALID_ANOMALY_TYPES)}'
                )
            )
        if occurred_at is None:
            raise ServiceException(message='发生时间(occurred_at) 不能为空')

        order = await db.scalar(
            select(EntrustOutsourceOrder).where(
                EntrustOutsourceOrder.id == order_id
            )
        )
        if order is None:
            raise ServiceException(message=f'委外工单不存在: order_id={order_id}')

        anomaly = ProductionAnomaly(
            order_id=order_id,
            order_no=order.order_no,
            part_id=part_id,
            anomaly_type=anomaly_type,
            description=description,
            occurred_at=occurred_at,
            material_cost=_to_decimal(material_cost),
            rework_cost=_to_decimal(rework_cost),
            delay_penalty=_to_decimal(delay_penalty),
            total_loss=Decimal('0'),
            status=STATUS_OPEN,
            created_by=created_by,
        )
        # 若调用方一次性提供了三项成本，立即计算总损失
        anomaly.total_loss = (
            _to_decimal(anomaly.material_cost)
            + _to_decimal(anomaly.rework_cost)
            + _to_decimal(anomaly.delay_penalty)
        )

        db.add(anomaly)
        await db.flush()

        # 审计日志：生产异常创建（Requirement 8.1）
        await ReconciliationAuditService.log_action(
            db=db,
            entity_type=ENTITY_TYPE_PRODUCTION_ANOMALY,
            entity_id=anomaly.id,
            action=ACTION_CREATE,
            operator_id=int(created_by or 0),
            operator_name='system' if not created_by else None,
            detail={
                'order_id': order_id,
                'order_no': order.order_no,
                'part_id': part_id,
                'anomaly_type': anomaly_type,
                'occurred_at': occurred_at.isoformat() if occurred_at else None,
                'total_loss': str(anomaly.total_loss),
            },
        )

        await db.commit()

        logger.info(
            '[ProductionAnomalyService] 创建生产异常 id={} order_id={} order_no={} '
            'part_id={} type={} total_loss={}',
            anomaly.id, order_id, order.order_no, part_id,
            anomaly_type, anomaly.total_loss,
        )
        return anomaly.id

    # ------------------------------------------------------------------
    # 2. 判定责任方（Requirement 9.2, 9.3, 9.4）
    # ------------------------------------------------------------------

    @staticmethod
    async def set_liability(
        db: AsyncSession,
        anomaly_id: int,
        liability_type: str,
        operator_id: int = 0,
    ) -> dict:
        """
        判定生产异常的责任方。

        - liability_type=material_supplier_fault：自动创建材料 Re_Shipment
          （Requirement 9.3）
        - liability_type=processor_fault：不自动创建后续处理；由业务人员后续
          调用 create_re_shipment(part) 或 create_deduction（Requirement 9.4）

        判定后将 ProductionAnomaly.status 推进到 liability_confirmed。

        Args:
            anomaly_id: 生产异常 ID
            liability_type: material_supplier_fault / processor_fault
            operator_id: 操作人 ID

        Returns:
            {
              'anomaly_id': int,
              'liability_type': str,
              'auto_re_shipment_id': Optional[int]  # 仅材料方责任时返回
            }

        Raises:
            ServiceException: 异常不存在 / 责任类型非法
        """
        if liability_type not in VALID_LIABILITY_TYPES:
            raise ServiceException(
                message=(
                    f'无效的责任类型: {liability_type}，允许值: '
                    f'{sorted(VALID_LIABILITY_TYPES)}'
                )
            )

        anomaly = await db.scalar(
            select(ProductionAnomaly).where(ProductionAnomaly.id == anomaly_id)
        )
        if anomaly is None:
            raise ServiceException(
                message=f'生产异常不存在: anomaly_id={anomaly_id}'
            )

        anomaly.liability_type = liability_type
        # 状态机推进：open → liability_confirmed
        if anomaly.status == STATUS_OPEN:
            anomaly.status = STATUS_LIABILITY_CONFIRMED

        await db.flush()

        auto_re_shipment_id: Optional[int] = None
        if liability_type == LIABILITY_MATERIAL_SUPPLIER:
            # Requirement 9.3：自动创建材料补发请求
            re_shipment = ReShipment(
                production_anomaly_id=anomaly.id,
                shipment_type=SHIPMENT_TYPE_MATERIAL,
                responsible_party=RESPONSIBLE_PARTY_MATERIAL_SUPPLIER,
                description='系统自动创建：材料方责任，要求材料方重新发货',
                status='pending',
                created_by=operator_id,
            )
            db.add(re_shipment)
            await db.flush()
            auto_re_shipment_id = re_shipment.id
            logger.info(
                '[ProductionAnomalyService] 责任=材料方，自动创建材料补发 '
                'anomaly_id={} re_shipment_id={}',
                anomaly.id, auto_re_shipment_id,
            )

        # 审计日志：责任判定（Requirement 8.1）
        await ReconciliationAuditService.log_action(
            db=db,
            entity_type=ENTITY_TYPE_PRODUCTION_ANOMALY,
            entity_id=anomaly.id,
            action=ACTION_UPDATE,
            operator_id=int(operator_id or 0),
            detail={
                'sub_action': 'set_liability',
                'liability_type': liability_type,
                'status': anomaly.status,
                'auto_re_shipment_id': auto_re_shipment_id,
            },
        )

        await db.commit()
        logger.info(
            '[ProductionAnomalyService] 判定责任方 anomaly_id={} liability_type={} '
            'status={}',
            anomaly.id, liability_type, anomaly.status,
        )
        return {
            'anomaly_id': anomaly.id,
            'liability_type': liability_type,
            'auto_re_shipment_id': auto_re_shipment_id,
        }

    # ------------------------------------------------------------------
    # 3. 创建补发请求（Requirement 9.3, 9.4）
    # ------------------------------------------------------------------

    @staticmethod
    async def create_re_shipment(
        db: AsyncSession,
        anomaly_id: int,
        shipment_type: str,
        responsible_party: str,
        description: Optional[str] = None,
        created_by: int = 0,
    ) -> int:
        """
        创建补发请求（Re_Shipment）。

        典型场景：
          - 加工方责任时由业务人员选择补发零件（shipment_type=part,
            responsible_party=processor）
          - 也可手动补建材料补发记录

        Args:
            anomaly_id: 生产异常 ID
            shipment_type: material / part
            responsible_party: material_supplier / processor
            description: 补发说明
            created_by: 创建人

        Returns:
            新建 Re_Shipment 记录 ID

        Raises:
            ServiceException: 异常不存在 / 类型枚举非法
        """
        if shipment_type not in VALID_SHIPMENT_TYPES:
            raise ServiceException(
                message=(
                    f'无效的补发类型: {shipment_type}，允许值: '
                    f'{sorted(VALID_SHIPMENT_TYPES)}'
                )
            )
        if responsible_party not in VALID_RESPONSIBLE_PARTIES:
            raise ServiceException(
                message=(
                    f'无效的责任方: {responsible_party}，允许值: '
                    f'{sorted(VALID_RESPONSIBLE_PARTIES)}'
                )
            )

        anomaly = await db.scalar(
            select(ProductionAnomaly).where(ProductionAnomaly.id == anomaly_id)
        )
        if anomaly is None:
            raise ServiceException(
                message=f'生产异常不存在: anomaly_id={anomaly_id}'
            )

        re_shipment = ReShipment(
            production_anomaly_id=anomaly_id,
            shipment_type=shipment_type,
            responsible_party=responsible_party,
            description=description,
            status='pending',
            created_by=created_by,
        )
        db.add(re_shipment)
        await db.flush()
        await db.commit()

        logger.info(
            '[ProductionAnomalyService] 创建补发请求 id={} anomaly_id={} '
            'shipment_type={} responsible_party={}',
            re_shipment.id, anomaly_id, shipment_type, responsible_party,
        )
        return re_shipment.id

    # ------------------------------------------------------------------
    # 3b. 确认补发发货（Requirement 13.1）
    # ------------------------------------------------------------------

    @staticmethod
    async def confirm_shipment(
        db: AsyncSession,
        re_shipment_id: int,
        order_id: int,
        part_id: int,
        quantity: int,
        unit_price: Decimal,
        anomaly_reason: str,
        operator_id: int = 0,
    ) -> dict:
        """
        确认补发已发货，将 ReShipment 状态更新为 'shipped'，
        并自动调用 VirtualInboundService.auto_create_from_reshipment()
        创建虚拟入库记录（Requirement 13.1）。

        Args:
            db: AsyncSession
            re_shipment_id: 补发记录 ID
            order_id: 关联委外工单 ID
            part_id: 零件 ID
            quantity: 补发数量
            unit_price: 单价
            anomaly_reason: 异常原因说明
            operator_id: 操作人 ID

        Returns:
            {
              're_shipment_id': int,
              'status': 'shipped',
              'virtual_inbound_id': int,
            }

        Raises:
            ServiceException: 补发记录不存在 / 状态不允许
        """
        re_shipment = await db.scalar(
            select(ReShipment).where(ReShipment.id == re_shipment_id)
        )
        if re_shipment is None:
            raise ServiceException(
                message=f'补发记录不存在: re_shipment_id={re_shipment_id}'
            )
        if re_shipment.status == 'shipped':
            raise ServiceException(
                message=f'补发记录已发货，不可重复确认: re_shipment_id={re_shipment_id}'
            )

        # 更新状态为 shipped
        re_shipment.status = 'shipped'
        await db.flush()

        # 获取关联的 ProductionAnomaly 以确定 responsible_party
        anomaly = await db.scalar(
            select(ProductionAnomaly).where(
                ProductionAnomaly.id == re_shipment.production_anomaly_id
            )
        )
        responsible_party = (
            RESPONSIBLE_PARTY_MATERIAL_SUPPLIER
            if anomaly and anomaly.liability_type == LIABILITY_MATERIAL_SUPPLIER
            else RESPONSIBLE_PARTY_PROCESSOR
        )

        # Requirement 13.1：补发确认发货时自动创建虚拟入库
        virtual_inbound_id = await VirtualInboundService.auto_create_from_reshipment(
            db=db,
            re_shipment_id=re_shipment_id,
            order_id=order_id,
            part_id=part_id,
            quantity=quantity,
            unit_price=unit_price,
            anomaly_reason=anomaly_reason,
            responsible_party=responsible_party,
            production_anomaly_id=re_shipment.production_anomaly_id,
            created_by=operator_id,
        )

        logger.info(
            '[ProductionAnomalyService] 确认补发发货 re_shipment_id={} '
            'virtual_inbound_id={}',
            re_shipment_id, virtual_inbound_id,
        )
        return {
            're_shipment_id': re_shipment_id,
            'status': 'shipped',
            'virtual_inbound_id': virtual_inbound_id,
        }

    # ------------------------------------------------------------------
    # 4. 创建扣款记录（Requirement 9.4）
    # ------------------------------------------------------------------

    @staticmethod
    async def create_deduction(
        db: AsyncSession,
        anomaly_id: int,
        amount: Decimal,
        reason: Optional[str] = None,
        created_by: int = 0,
    ) -> int:
        """
        创建扣款记录（Deduction）。

        通常用于加工方责任场景：业务人员选择以扣款方式处理而非补发零件。

        Args:
            anomaly_id: 生产异常 ID
            amount: 扣款金额（必须 > 0）
            reason: 扣款原因
            created_by: 创建人

        Returns:
            新建 Deduction 记录 ID

        Raises:
            ServiceException: 异常不存在 / 金额无效
        """
        amount_dec = _to_decimal(amount)
        if amount_dec <= 0:
            raise ServiceException(message=f'扣款金额必须大于 0: {amount}')

        anomaly = await db.scalar(
            select(ProductionAnomaly).where(ProductionAnomaly.id == anomaly_id)
        )
        if anomaly is None:
            raise ServiceException(
                message=f'生产异常不存在: anomaly_id={anomaly_id}'
            )

        deduction = Deduction(
            production_anomaly_id=anomaly_id,
            order_id=anomaly.order_id,
            amount=amount_dec,
            reason=reason,
            status='pending',
            created_by=created_by,
        )
        db.add(deduction)
        await db.flush()
        await db.commit()

        logger.info(
            '[ProductionAnomalyService] 创建扣款记录 id={} anomaly_id={} amount={}',
            deduction.id, anomaly_id, amount_dec,
        )
        return deduction.id

    # ------------------------------------------------------------------
    # 5. 记录协商过程（Requirement 9.5）
    # ------------------------------------------------------------------

    @staticmethod
    async def record_negotiation(
        db: AsyncSession,
        anomaly_id: int,
        time: datetime,
        participants: Optional[str],
        result: Optional[str],
        created_by: int = 0,
    ) -> int:
        """
        记录一次协商过程。

        Args:
            anomaly_id: 生产异常 ID
            time: 协商时间
            participants: 参与方（自由文本）
            result: 协商结果（自由文本）
            created_by: 记录人

        Returns:
            新建 NegotiationRecord 记录 ID

        Raises:
            ServiceException: 异常不存在 / 协商时间缺失
        """
        if time is None:
            raise ServiceException(message='协商时间(time) 不能为空')

        anomaly = await db.scalar(
            select(ProductionAnomaly.id).where(ProductionAnomaly.id == anomaly_id)
        )
        if anomaly is None:
            raise ServiceException(
                message=f'生产异常不存在: anomaly_id={anomaly_id}'
            )

        record = NegotiationRecord(
            production_anomaly_id=anomaly_id,
            negotiation_time=time,
            participants=participants,
            result=result,
            created_by=created_by,
        )
        db.add(record)
        await db.flush()
        await db.commit()

        logger.info(
            '[ProductionAnomalyService] 记录协商 id={} anomaly_id={} time={}',
            record.id, anomaly_id, time,
        )
        return record.id

    # ------------------------------------------------------------------
    # 6. 计算总损失（Requirement 9.7 / Property 13）
    # ------------------------------------------------------------------

    @staticmethod
    async def calculate_total_loss(
        db: AsyncSession,
        anomaly_id: int,
    ) -> Decimal:
        """
        计算并落库生产异常的总损失金额。

        Property 13: total_loss = material_cost + rework_cost + delay_penalty

        Args:
            anomaly_id: 生产异常 ID

        Returns:
            最新 total_loss（Decimal）

        Raises:
            ServiceException: 异常不存在
        """
        anomaly = await db.scalar(
            select(ProductionAnomaly).where(ProductionAnomaly.id == anomaly_id)
        )
        if anomaly is None:
            raise ServiceException(
                message=f'生产异常不存在: anomaly_id={anomaly_id}'
            )

        material_cost = _to_decimal(anomaly.material_cost)
        rework_cost = _to_decimal(anomaly.rework_cost)
        delay_penalty = _to_decimal(anomaly.delay_penalty)

        total_loss = material_cost + rework_cost + delay_penalty
        anomaly.total_loss = total_loss

        await db.flush()
        await db.commit()

        logger.info(
            '[ProductionAnomalyService] 计算总损失 anomaly_id={} material={} '
            'rework={} delay={} total_loss={}',
            anomaly_id, material_cost, rework_cost, delay_penalty, total_loss,
        )
        return total_loss


__all__ = [
    'ProductionAnomalyService',
    # 异常类型
    'ANOMALY_TYPE_MATERIAL_DAMAGE',
    'ANOMALY_TYPE_PROCESS_ERROR',
    'ANOMALY_TYPE_UNUSABLE',
    'VALID_ANOMALY_TYPES',
    # 责任类型
    'LIABILITY_MATERIAL_SUPPLIER',
    'LIABILITY_PROCESSOR',
    'VALID_LIABILITY_TYPES',
    # 补发类型
    'SHIPMENT_TYPE_MATERIAL',
    'SHIPMENT_TYPE_PART',
    'VALID_SHIPMENT_TYPES',
    # 责任方
    'RESPONSIBLE_PARTY_MATERIAL_SUPPLIER',
    'RESPONSIBLE_PARTY_PROCESSOR',
    'VALID_RESPONSIBLE_PARTIES',
    # 状态
    'STATUS_OPEN',
    'STATUS_LIABILITY_CONFIRMED',
    'STATUS_RESOLVED',
    'STATUS_CLOSED',
]
