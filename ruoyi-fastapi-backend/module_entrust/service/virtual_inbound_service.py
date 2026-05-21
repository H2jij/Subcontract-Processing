"""
对账系统 — 虚拟入库 Service
=========================================
覆盖需求 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8

职责：
  1. 创建虚拟入库记录（强制要求 anomaly_reason）
  2. 计算指定工单的虚拟入库总价值
  3. 按工单查询虚拟入库记录
  4. 列表查询（支持按工单号、零件、入库类型、责任方、时间范围筛选）
  5. 修改虚拟入库记录（检查关联 SettlementDetail 非 finalized）
  6. 删除虚拟入库记录（检查关联 SettlementDetail 非 finalized）
  7. 补发确认发货时自动创建虚拟入库

设计约束：
  - 遵循 module_entrust 现有 service 模式（static async methods, AsyncSession）
  - 使用 ReconciliationAuditService.log_action_safe 记录审计日志
  - amount = quantity × unit_price（自动计算）
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from loguru import logger
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceException
from module_entrust.entity.do.entrust_do import (
    EntrustOutsourceOrder,
    EntrustPart,
)
from module_entrust.entity.do.reconciliation_do import (
    ReShipment,
    SettlementDetail,
    VirtualInbound,
)
from module_entrust.service.reconciliation_audit_service import (
    ReconciliationAuditService,
)


# ---------------------------------------------------------------------------
# 内部常量
# ---------------------------------------------------------------------------

# 审计日志 entity_type（virtual_inbound 暂未加入白名单，使用 settlement 代替）
_AUDIT_ENTITY_TYPE = 'settlement'


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class VirtualInboundService:
    """虚拟入库服务"""

    # ------------------------------------------------------------------
    # 创建虚拟入库记录 (Requirement 13.2, 13.4)
    # ------------------------------------------------------------------

    @staticmethod
    async def create_virtual_inbound(
        db: AsyncSession,
        order_id: int,
        part_id: int,
        inbound_type: str,
        quantity: int,
        unit_price: Decimal,
        anomaly_reason: str,
        responsible_party: str,
        re_shipment_id: Optional[int] = None,
        production_anomaly_id: Optional[int] = None,
        created_by: int = 0,
    ) -> int:
        """
        创建虚拟入库记录。

        Args:
            db: AsyncSession
            order_id: 关联委外工单ID
            part_id: 零件ID
            inbound_type: 入库类型 (re_shipment_in / anomaly_deduction)
            quantity: 入库数量
            unit_price: 单价
            anomaly_reason: 异常原因说明（必填，不能为空）
            responsible_party: 责任方 (material_supplier / processor)
            re_shipment_id: 关联补发记录ID（可选）
            production_anomaly_id: 关联生产异常ID（可选）
            created_by: 操作人ID

        Returns:
            新建虚拟入库记录 ID

        Raises:
            ServiceException: 参数校验失败
        """
        # 1. 校验 anomaly_reason 必填 (Requirement 13.4)
        if not anomaly_reason or not anomaly_reason.strip():
            raise ServiceException(message='异常原因说明(anomaly_reason)为必填项')

        # 2. 校验 inbound_type
        if inbound_type not in ('re_shipment_in', 'anomaly_deduction'):
            raise ServiceException(
                message=f'非法的入库类型: {inbound_type}；允许值: re_shipment_in, anomaly_deduction'
            )

        # 3. 校验 responsible_party
        if responsible_party not in ('material_supplier', 'processor'):
            raise ServiceException(
                message=f'非法的责任方: {responsible_party}；允许值: material_supplier, processor'
            )

        # 4. 校验数量和单价
        if quantity is None or quantity <= 0:
            raise ServiceException(message='入库数量必须大于 0')
        unit_price_dec = Decimal(str(unit_price))
        if unit_price_dec < Decimal('0'):
            raise ServiceException(message='单价不能为负数')

        # 5. 计算金额
        amount = Decimal(str(quantity)) * unit_price_dec

        # 6. 查询工单信息（获取 order_no 冗余字段）
        order = await db.scalar(
            select(EntrustOutsourceOrder).where(EntrustOutsourceOrder.id == order_id)
        )
        if not order:
            raise ServiceException(message=f'委外工单 {order_id} 不存在')
        order_no = order.order_no

        # 7. 查询零件信息（获取 part_no, part_name 冗余字段）
        part_no: Optional[str] = None
        part_name: Optional[str] = None
        if part_id:
            part = await db.scalar(
                select(EntrustPart).where(EntrustPart.id == part_id)
            )
            if part:
                part_no = part.part_no
                part_name = part.part_name

        # 8. 创建记录
        record = VirtualInbound(
            order_id=order_id,
            order_no=order_no,
            part_id=part_id,
            part_no=part_no,
            part_name=part_name,
            inbound_type=inbound_type,
            quantity=quantity,
            unit_price=unit_price_dec,
            amount=amount,
            production_anomaly_id=production_anomaly_id,
            re_shipment_id=re_shipment_id,
            anomaly_reason=anomaly_reason.strip(),
            responsible_party=responsible_party,
            status='pending',
            created_by=created_by,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.add(record)
        await db.flush()

        # 9. 审计日志
        await ReconciliationAuditService.log_action_safe(
            db=db,
            entity_type=_AUDIT_ENTITY_TYPE,
            entity_id=record.id,
            action='create',
            operator_id=created_by,
            detail={
                'type': 'virtual_inbound',
                'order_id': order_id,
                'order_no': order_no,
                'inbound_type': inbound_type,
                'quantity': quantity,
                'unit_price': str(unit_price_dec),
                'amount': str(amount),
                'anomaly_reason': anomaly_reason.strip(),
                'responsible_party': responsible_party,
            },
        )

        await db.commit()
        logger.info(
            '[VirtualInboundService] 创建虚拟入库 id={} order_no={} type={} amount={}',
            record.id, order_no, inbound_type, amount,
        )
        return record.id

    # ------------------------------------------------------------------
    # 计算指定工单的虚拟入库总价值 (Requirement 13.5)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_inbound_value_for_order(
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
    # 按工单查询虚拟入库记录
    # ------------------------------------------------------------------

    @staticmethod
    async def list_by_order(
        db: AsyncSession, order_id: int
    ) -> list[VirtualInbound]:
        """查询指定工单的所有虚拟入库记录（按创建时间降序）。"""
        stmt = (
            select(VirtualInbound)
            .where(VirtualInbound.order_id == order_id)
            .order_by(VirtualInbound.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # 列表查询 (Requirement 13.6)
    # ------------------------------------------------------------------

    @staticmethod
    async def list_virtual_inbounds(
        db: AsyncSession,
        order_id: Optional[int] = None,
        order_no: Optional[str] = None,
        part_no: Optional[str] = None,
        inbound_type: Optional[str] = None,
        responsible_party: Optional[str] = None,
        status: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page_num: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """
        虚拟入库记录列表查询（支持筛选+分页）。

        支持筛选：
          - order_id: 工单ID
          - order_no: 工单号（模糊匹配）
          - part_no: 零件编号（模糊匹配）
          - inbound_type: 入库类型
          - responsible_party: 责任方
          - status: 状态
          - start_time / end_time: 创建时间范围

        返回：
          {
              'total': int,
              'page_num': int,
              'page_size': int,
              'rows': list[VirtualInbound],
          }
        """
        if page_num < 1:
            page_num = 1
        if page_size < 1 or page_size > 500:
            page_size = 20

        # 组装过滤条件
        conds = []
        if order_id is not None:
            conds.append(VirtualInbound.order_id == order_id)
        if order_no:
            conds.append(VirtualInbound.order_no.ilike(f'%{order_no}%'))
        if part_no:
            conds.append(VirtualInbound.part_no.ilike(f'%{part_no}%'))
        if inbound_type:
            conds.append(VirtualInbound.inbound_type == inbound_type)
        if responsible_party:
            conds.append(VirtualInbound.responsible_party == responsible_party)
        if status:
            conds.append(VirtualInbound.status == status)
        if start_time:
            conds.append(VirtualInbound.created_at >= start_time)
        if end_time:
            conds.append(VirtualInbound.created_at <= end_time)

        where_clause = and_(*conds) if conds else None

        # 查询总数
        count_stmt = select(func.count()).select_from(VirtualInbound)
        if where_clause is not None:
            count_stmt = count_stmt.where(where_clause)
        total = (await db.execute(count_stmt)).scalar_one()

        # 查询数据
        stmt = select(VirtualInbound)
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        stmt = (
            stmt.order_by(
                VirtualInbound.created_at.desc(),
                VirtualInbound.id.desc(),
            )
            .offset((page_num - 1) * page_size)
            .limit(page_size)
        )
        rows = list((await db.execute(stmt)).scalars().all())

        return {
            'total': int(total or 0),
            'page_num': page_num,
            'page_size': page_size,
            'rows': rows,
        }

    # ------------------------------------------------------------------
    # 修改虚拟入库记录 (Requirement 13.8)
    # ------------------------------------------------------------------

    @staticmethod
    async def update_virtual_inbound(
        db: AsyncSession,
        record_id: int,
        update_data: dict[str, Any],
        operator_id: int = 0,
    ) -> None:
        """
        修改虚拟入库记录。

        检查关联的 SettlementDetail（通过 order_id）是否已 finalized，
        如果已 finalized 则拒绝修改。

        Args:
            db: AsyncSession
            record_id: 虚拟入库记录ID
            update_data: 要更新的字段字典
            operator_id: 操作人ID

        Raises:
            ServiceException: 记录不存在 / 关联结算已确认 / 参数非法
        """
        # 1. 查询记录
        record = await db.scalar(
            select(VirtualInbound).where(VirtualInbound.id == record_id)
        )
        if not record:
            raise ServiceException(message=f'虚拟入库记录 {record_id} 不存在')

        # 2. 检查关联 SettlementDetail 是否 finalized
        await VirtualInboundService._check_settlement_not_finalized(db, record.order_id)

        # 3. 记录变更前值（用于审计）
        old_values: dict[str, Any] = {}

        # 4. 允许更新的字段
        allowed_fields = {
            'quantity', 'unit_price', 'anomaly_reason', 'responsible_party',
            'inbound_type', 'status', 'production_anomaly_id', 're_shipment_id',
        }

        for key, value in update_data.items():
            if key not in allowed_fields:
                continue
            old_values[key] = getattr(record, key, None)
            setattr(record, key, value)

        # 5. 如果 quantity 或 unit_price 变更，重新计算 amount
        if 'quantity' in update_data or 'unit_price' in update_data:
            qty = Decimal(str(record.quantity or 0))
            price = Decimal(str(record.unit_price or 0))
            record.amount = qty * price

        # 6. 校验 anomaly_reason 不为空
        if record.anomaly_reason is not None and not record.anomaly_reason.strip():
            raise ServiceException(message='异常原因说明(anomaly_reason)不能为空')

        record.updated_at = datetime.now()
        await db.flush()

        # 7. 审计日志
        await ReconciliationAuditService.log_action_safe(
            db=db,
            entity_type=_AUDIT_ENTITY_TYPE,
            entity_id=record_id,
            action='update',
            operator_id=operator_id,
            detail={
                'type': 'virtual_inbound',
                'old_values': {k: str(v) for k, v in old_values.items()},
                'new_values': {k: str(v) for k, v in update_data.items() if k in allowed_fields},
            },
        )

        await db.commit()
        logger.info(
            '[VirtualInboundService] 更新虚拟入库 id={} fields={}',
            record_id, list(update_data.keys()),
        )

    # ------------------------------------------------------------------
    # 删除虚拟入库记录 (Requirement 13.8)
    # ------------------------------------------------------------------

    @staticmethod
    async def delete_virtual_inbound(
        db: AsyncSession,
        record_id: int,
        operator_id: int = 0,
    ) -> None:
        """
        删除虚拟入库记录。

        检查关联的 SettlementDetail（通过 order_id）是否已 finalized，
        如果已 finalized 则拒绝删除。

        Args:
            db: AsyncSession
            record_id: 虚拟入库记录ID
            operator_id: 操作人ID

        Raises:
            ServiceException: 记录不存在 / 关联结算已确认
        """
        # 1. 查询记录
        record = await db.scalar(
            select(VirtualInbound).where(VirtualInbound.id == record_id)
        )
        if not record:
            raise ServiceException(message=f'虚拟入库记录 {record_id} 不存在')

        # 2. 检查关联 SettlementDetail 是否 finalized
        await VirtualInboundService._check_settlement_not_finalized(db, record.order_id)

        # 3. 审计日志（删除前记录）
        await ReconciliationAuditService.log_action_safe(
            db=db,
            entity_type=_AUDIT_ENTITY_TYPE,
            entity_id=record_id,
            action='delete',
            operator_id=operator_id,
            detail={
                'type': 'virtual_inbound',
                'order_id': record.order_id,
                'order_no': record.order_no,
                'inbound_type': record.inbound_type,
                'quantity': record.quantity,
                'unit_price': str(record.unit_price),
                'amount': str(record.amount),
            },
        )

        # 4. 删除记录
        await db.delete(record)
        await db.commit()
        logger.info('[VirtualInboundService] 删除虚拟入库 id={}', record_id)

    # ------------------------------------------------------------------
    # 补发确认发货时自动创建虚拟入库 (Requirement 13.1)
    # ------------------------------------------------------------------

    @staticmethod
    async def auto_create_from_reshipment(
        db: AsyncSession,
        re_shipment_id: int,
        order_id: int,
        part_id: int,
        quantity: int,
        unit_price: Decimal,
        anomaly_reason: str,
        responsible_party: str,
        production_anomaly_id: Optional[int] = None,
        created_by: int = 0,
    ) -> int:
        """
        补发确认发货时自动创建虚拟入库记录。

        当 ReShipment 状态变为 'shipped' 时调用此方法，
        自动创建一条 inbound_type='re_shipment_in' 的虚拟入库记录。

        Args:
            db: AsyncSession
            re_shipment_id: 补发记录ID
            order_id: 关联委外工单ID
            part_id: 零件ID
            quantity: 补发数量
            unit_price: 单价
            anomaly_reason: 异常原因说明
            responsible_party: 责任方
            production_anomaly_id: 关联生产异常ID（可选）
            created_by: 操作人ID

        Returns:
            新建虚拟入库记录 ID

        Raises:
            ServiceException: 补发记录不存在 / 参数校验失败
        """
        # 1. 校验补发记录存在
        reshipment = await db.scalar(
            select(ReShipment).where(ReShipment.id == re_shipment_id)
        )
        if not reshipment:
            raise ServiceException(message=f'补发记录 {re_shipment_id} 不存在')

        # 2. 委托 create_virtual_inbound 完成创建
        record_id = await VirtualInboundService.create_virtual_inbound(
            db=db,
            order_id=order_id,
            part_id=part_id,
            inbound_type='re_shipment_in',
            quantity=quantity,
            unit_price=unit_price,
            anomaly_reason=anomaly_reason,
            responsible_party=responsible_party,
            re_shipment_id=re_shipment_id,
            production_anomaly_id=production_anomaly_id,
            created_by=created_by,
        )

        logger.info(
            '[VirtualInboundService] 补发自动创建虚拟入库 re_shipment_id={} '
            'virtual_inbound_id={}',
            re_shipment_id, record_id,
        )
        return record_id

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    async def _check_settlement_not_finalized(
        db: AsyncSession, order_id: int
    ) -> None:
        """
        检查关联的 SettlementDetail 是否已 finalized。
        如果已 finalized 则抛出异常，禁止修改/删除。
        """
        stmt = select(SettlementDetail).where(
            SettlementDetail.order_id == order_id,
            SettlementDetail.status == 'finalized',
        )
        finalized = await db.scalar(stmt)
        if finalized:
            raise ServiceException(
                message='关联的结算明细已确认(finalized)，禁止修改或删除虚拟入库记录'
            )
