"""
对账系统 — 对账单生成与管理 Service
=========================================
功能：
  1. 按对账周期 + 供应商生成对账单（ReconciliationStatement + LineItems）
  2. 查询合格工单（status=delivered & quality_status=pass）
  3. 生成对账单编号 REC-{YYYYMM}-{supplier_id}-{NNN}
  4. 以订购单为基准，逐单计算差异并关联差异原因
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceException
from module_entrust.entity.do.entrust_do import EntrustOutsourceOrder, EntrustPart
from module_entrust.entity.do.reconciliation_do import (
    LineItemVarianceReason,
    ReconciliationLineItem,
    ReconciliationStatement,
)
from module_entrust.service.reconciliation_audit_service import (
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_UPDATE,
    ENTITY_TYPE_STATEMENT,
    ReconciliationAuditService,
)
from module_entrust.service.variance_calculation_service import VarianceCalculationService


class ReconciliationService:
    """对账单生成与管理服务"""

    # ------------------------------------------------------------------
    # 对账单编号
    # ------------------------------------------------------------------

    @staticmethod
    def generate_statement_no(period_end: date, supplier_id: int, seq: int) -> str:
        """
        生成对账单编号

        格式: REC-{YYYYMM}-{supplier_id}-{NNN}
        示例: REC-202401-5-001
        """
        return f"REC-{period_end.strftime('%Y%m')}-{supplier_id}-{seq:03d}"

    @staticmethod
    async def _next_sequence(
        db: AsyncSession, period_end: date, supplier_id: int
    ) -> int:
        """
        计算指定 (YYYYMM + supplier_id) 范围内的下一个对账单序号
        """
        prefix = f"REC-{period_end.strftime('%Y%m')}-{supplier_id}-"
        count_stmt = (
            select(func.count())
            .select_from(ReconciliationStatement)
            .where(ReconciliationStatement.statement_no.like(f'{prefix}%'))
        )
        existing = (await db.execute(count_stmt)).scalar() or 0
        return existing + 1

    # ------------------------------------------------------------------
    # 合格工单查询
    # ------------------------------------------------------------------

    @staticmethod
    async def get_eligible_orders(
        db: AsyncSession,
        period_start: date,
        period_end: date,
        supplier_id: Optional[int] = None,
    ) -> list[EntrustOutsourceOrder]:
        """
        查询指定周期内的合格工单

        合格条件:
          - status == 'delivered'
          - quality_status == 'pass'
          - actual_delivery_date 落在 [period_start, period_end] 范围内（包含两端整天）

        Args:
            period_start: 对账周期起始日期
            period_end: 对账周期结束日期
            supplier_id: 可选，指定供应商；为空则查全部供应商
        """
        if period_start > period_end:
            raise ServiceException(message='对账周期起始日期不能晚于结束日期')

        period_start_dt = datetime.combine(period_start, datetime.min.time())
        period_end_dt = datetime.combine(period_end, datetime.max.time())

        stmt = select(EntrustOutsourceOrder).where(
            EntrustOutsourceOrder.status == 'delivered',
            EntrustOutsourceOrder.quality_status == 'pass',
            EntrustOutsourceOrder.actual_delivery_date.isnot(None),
            EntrustOutsourceOrder.actual_delivery_date >= period_start_dt,
            EntrustOutsourceOrder.actual_delivery_date <= period_end_dt,
        )
        if supplier_id is not None:
            stmt = stmt.where(EntrustOutsourceOrder.supplier_id == supplier_id)

        stmt = stmt.order_by(
            EntrustOutsourceOrder.supplier_id.asc(),
            EntrustOutsourceOrder.actual_delivery_date.asc(),
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def _load_part_info(
        db: AsyncSession, part_ids: set[int]
    ) -> dict[int, EntrustPart]:
        """批量加载零件信息（part_no, part_name），用于回填行项字段"""
        if not part_ids:
            return {}
        stmt = select(EntrustPart).where(EntrustPart.id.in_(part_ids))
        rows = (await db.execute(stmt)).scalars().all()
        return {p.id: p for p in rows}

    # ------------------------------------------------------------------
    # 对账单生成
    # ------------------------------------------------------------------

    @staticmethod
    async def generate_statements(
        db: AsyncSession,
        period_start: date,
        period_end: date,
        supplier_id: Optional[int] = None,
        created_by: int = 0,
    ) -> list[int]:
        """
        生成对账单 — 以订购单为基准，逐单计算差异。

        - 查询合格工单 (delivered + pass)
        - 按 supplier_id 分组生成 ReconciliationStatement
        - 为每条工单调用 VarianceCalculationService 计算差异数据
        - 创建 ReconciliationLineItem 并填充差异字段
        - variance != 0 的行项自动创建 LineItemVarianceReason 记录
        - 计算对账单汇总：total_ordered_amount, total_received_value,
          total_logistics_cost, total_variance, anomaly_count, total_amount
        - 无合格工单的供应商不生成对账单

        Args:
            period_start: 对账周期起始日期
            period_end: 对账周期结束日期
            supplier_id: 可选，指定单个供应商
            created_by: 创建人ID

        Returns:
            生成的对账单 ID 列表（按供应商ID升序）
        """
        if period_start > period_end:
            raise ServiceException(message='对账周期起始日期不能晚于结束日期')

        orders = await ReconciliationService.get_eligible_orders(
            db, period_start, period_end, supplier_id
        )

        if not orders:
            logger.info(
                f'[ReconciliationService] 未找到合格工单 '
                f'period={period_start}~{period_end} supplier_id={supplier_id}'
            )
            return []

        # 按 supplier_id 分组
        grouped: dict[int, list[EntrustOutsourceOrder]] = {}
        for o in orders:
            grouped.setdefault(o.supplier_id, []).append(o)

        # 批量加载零件信息
        part_ids = {o.part_id for o in orders if o.part_id is not None}
        part_map = await ReconciliationService._load_part_info(db, part_ids)

        statement_ids: list[int] = []

        # 按 supplier_id 升序生成，保证编号序号稳定
        for sup_id in sorted(grouped.keys()):
            sup_orders = grouped[sup_id]

            # 生成编号
            seq = await ReconciliationService._next_sequence(db, period_end, sup_id)
            statement_no = ReconciliationService.generate_statement_no(
                period_end, sup_id, seq
            )

            # 先创建对账单（汇总字段稍后填充）
            statement = ReconciliationStatement(
                statement_no=statement_no,
                supplier_id=sup_id,
                period_start=period_start,
                period_end=period_end,
                total_ordered_amount=Decimal('0'),
                total_received_value=Decimal('0'),
                total_logistics_cost=Decimal('0'),
                total_variance=Decimal('0'),
                anomaly_count=0,
                total_amount=Decimal('0'),
                status='pending',
                confirmation_status='pending',
                created_by=created_by,
            )
            db.add(statement)
            await db.flush()  # 获取 statement.id

            # 汇总累加器
            sum_ordered_amount = Decimal('0')
            sum_received_value = Decimal('0')
            sum_logistics_cost = Decimal('0')
            sum_variance = Decimal('0')
            mismatch_count = 0

            # 创建行项：逐单计算差异
            for o in sup_orders:
                part = part_map.get(o.part_id) if o.part_id else None

                # 调用差异计算引擎
                variance_data: dict[str, Any] = (
                    await VarianceCalculationService.compute_line_item_variance(db, o)
                )

                order_amount = variance_data['order_amount']
                actual_delivered_qty = variance_data['actual_delivered_qty']
                actual_delivered_value = variance_data['actual_delivered_value']
                virtual_inbound_value = variance_data['virtual_inbound_value']
                anomaly_deduction_amount = variance_data['anomaly_deduction_amount']
                logistics_cost = variance_data['logistics_cost']
                variance = variance_data['variance']
                has_mismatch = variance_data['has_mismatch']
                variance_reasons = variance_data['variance_reasons']

                line = ReconciliationLineItem(
                    statement_id=statement.id,
                    order_id=o.id,
                    order_no=o.order_no,
                    process_name=o.process_name,
                    part_no=part.part_no if part else None,
                    part_name=part.part_name if part else None,
                    # 订购基准
                    ordered_quantity=o.quantity,
                    ordered_unit_price=o.unit_price,
                    order_amount=order_amount,
                    # 实际交付
                    actual_delivered_qty=actual_delivered_qty,
                    actual_delivered_value=actual_delivered_value,
                    # 虚拟入库
                    virtual_inbound_value=virtual_inbound_value,
                    # 异常扣除
                    anomaly_deduction_amount=anomaly_deduction_amount,
                    # 物流费用
                    logistics_cost=logistics_cost,
                    # 差异计算结果
                    variance=variance,
                    has_mismatch=has_mismatch,
                    variance_reasons=variance_reasons if variance_reasons else None,
                    # 保留字段（兼容旧数据）
                    unit_price=o.unit_price,
                    quantity=o.quantity,
                    total_amount=order_amount,
                    is_frozen=False,
                )
                db.add(line)
                await db.flush()  # 获取 line.id

                # 如果有差异，创建 LineItemVarianceReason 记录
                if has_mismatch and variance_reasons:
                    for reason in variance_reasons:
                        reason_record = LineItemVarianceReason(
                            line_item_id=line.id,
                            reason_type=reason.get('reason_type', 'unknown'),
                            production_anomaly_id=reason.get('production_anomaly_id'),
                            virtual_inbound_id=reason.get('virtual_inbound_id'),
                            deduction_id=reason.get('deduction_id'),
                            description=reason.get('description'),
                            impact_amount=(
                                Decimal(reason['impact_amount'])
                                if reason.get('impact_amount') is not None
                                else None
                            ),
                            responsible_party=reason.get('responsible_party'),
                        )
                        db.add(reason_record)

                # 累加汇总
                sum_ordered_amount += order_amount
                sum_received_value += (
                    actual_delivered_value + virtual_inbound_value - anomaly_deduction_amount
                )
                sum_logistics_cost += logistics_cost
                sum_variance += variance
                if has_mismatch:
                    mismatch_count += 1

            # 更新对账单汇总字段
            statement.total_ordered_amount = sum_ordered_amount
            statement.total_received_value = sum_received_value
            statement.total_logistics_cost = sum_logistics_cost
            statement.total_variance = sum_variance
            statement.anomaly_count = mismatch_count
            # 应付金额 = 实际收到总价值 + 物流总费用
            statement.total_amount = sum_received_value + sum_logistics_cost

            await db.flush()
            statement_ids.append(statement.id)

            # 审计日志：对账单创建（Requirement 8.1）
            await ReconciliationAuditService.log_action(
                db=db,
                entity_type=ENTITY_TYPE_STATEMENT,
                entity_id=statement.id,
                action=ACTION_CREATE,
                operator_id=created_by or 0,
                operator_name='system' if not created_by else None,
                detail={
                    'statement_no': statement_no,
                    'supplier_id': sup_id,
                    'period_start': str(period_start),
                    'period_end': str(period_end),
                    'total_ordered_amount': str(sum_ordered_amount),
                    'total_received_value': str(sum_received_value),
                    'total_logistics_cost': str(sum_logistics_cost),
                    'total_variance': str(sum_variance),
                    'anomaly_count': mismatch_count,
                    'total_amount': str(sum_received_value + sum_logistics_cost),
                    'line_item_count': len(sup_orders),
                },
            )

            logger.info(
                f'[ReconciliationService] 已生成对账单 statement_no={statement_no} '
                f'supplier_id={sup_id} orders={len(sup_orders)} '
                f'total_ordered={sum_ordered_amount} variance={sum_variance} '
                f'mismatch_count={mismatch_count}'
            )

        await db.commit()
        logger.info(
            f'[ReconciliationService] 共生成 {len(statement_ids)} 份对账单 '
            f'period={period_start}~{period_end}'
        )
        return statement_ids

    # ------------------------------------------------------------------
    # 行项管理（line item management）
    # ------------------------------------------------------------------

    # 仅 pending 状态允许行项增删改（Property 4 / Requirements 1.6, 8.3）
    _MUTABLE_STATUSES: frozenset[str] = frozenset({'pending'})

    # 编辑行项时允许覆盖的字段
    _LINE_ITEM_UPDATABLE_FIELDS: tuple[str, ...] = (
        'order_id',
        'order_no',
        'process_name',
        'part_no',
        'part_name',
        'unit_price',
        'quantity',
        'total_amount',
    )

    # 创建行项必填字段
    _LINE_ITEM_REQUIRED_FIELDS: tuple[str, ...] = ('order_no',)

    @staticmethod
    async def _load_statement_for_modification(
        db: AsyncSession, statement_id: int
    ) -> ReconciliationStatement:
        """
        加载对账单并校验是否允许修改。

        - 不存在 → ServiceException
        - 状态不在 pending → ServiceException（confirmed/paid/timeout/disputed 等均拒绝）
        """
        stmt = select(ReconciliationStatement).where(
            ReconciliationStatement.id == statement_id
        )
        statement = (await db.execute(stmt)).scalar_one_or_none()
        if statement is None:
            raise ServiceException(message=f'对账单不存在: id={statement_id}')

        if statement.status not in ReconciliationService._MUTABLE_STATUSES:
            raise ServiceException(
                message=(
                    f'对账单当前状态为 {statement.status}，不允许修改行项；'
                    f'仅 pending 状态可编辑'
                )
            )
        return statement

    @staticmethod
    async def _load_line_item(
        db: AsyncSession, statement_id: int, item_id: int
    ) -> ReconciliationLineItem:
        """加载行项并校验归属对账单"""
        stmt = select(ReconciliationLineItem).where(
            ReconciliationLineItem.id == item_id,
            ReconciliationLineItem.statement_id == statement_id,
        )
        line = (await db.execute(stmt)).scalar_one_or_none()
        if line is None:
            raise ServiceException(
                message=f'行项不存在或不属于该对账单: statement_id={statement_id}, item_id={item_id}'
            )
        return line

    @staticmethod
    def _ensure_line_item_unfrozen(line: ReconciliationLineItem) -> None:
        """冻结的行项（存在待审批 Adjustment）禁止修改"""
        if bool(line.is_frozen):
            raise ServiceException(
                message=(
                    f'行项已冻结（存在待审批的金额调整），暂不允许修改: '
                    f'item_id={line.id}'
                )
            )

    @staticmethod
    async def calculate_summary(db: AsyncSession, statement_id: int) -> dict:
        """
        重新计算对账单汇总字段（扩展版）。

        汇总公式：
        - total_ordered_amount = Σ(line_items.order_amount)
        - total_received_value = Σ(actual_delivered_value + virtual_inbound_value - anomaly_deduction_amount)
        - total_logistics_cost = Σ(line_items.logistics_cost)
        - total_variance = Σ(line_items.variance)
        - anomaly_count = count(has_mismatch=True)
        - total_amount = total_received_value + total_logistics_cost（实际应付）

        计算后更新 ReconciliationStatement 对应字段并 flush。

        Args:
            statement_id: 对账单 ID

        Returns:
            包含所有汇总字段的字典

        Raises:
            ServiceException: 对账单不存在
        """
        stmt = select(ReconciliationStatement).where(
            ReconciliationStatement.id == statement_id
        )
        statement = (await db.execute(stmt)).scalar_one_or_none()
        if statement is None:
            raise ServiceException(message=f'对账单不存在: id={statement_id}')

        # 查询所有行项进行汇总计算
        line_items_stmt = select(ReconciliationLineItem).where(
            ReconciliationLineItem.statement_id == statement_id
        )
        result = await db.execute(line_items_stmt)
        line_items = list(result.scalars().all())

        sum_ordered_amount = Decimal('0')
        sum_received_value = Decimal('0')
        sum_logistics_cost = Decimal('0')
        sum_variance = Decimal('0')
        mismatch_count = 0

        for li in line_items:
            order_amount = Decimal(str(li.order_amount or 0))
            actual_delivered_value = Decimal(str(li.actual_delivered_value or 0))
            virtual_inbound_value = Decimal(str(li.virtual_inbound_value or 0))
            anomaly_deduction_amount = Decimal(str(li.anomaly_deduction_amount or 0))
            logistics_cost = Decimal(str(li.logistics_cost or 0))
            variance = Decimal(str(li.variance or 0))

            sum_ordered_amount += order_amount
            sum_received_value += (
                actual_delivered_value + virtual_inbound_value - anomaly_deduction_amount
            )
            sum_logistics_cost += logistics_cost
            sum_variance += variance
            if li.has_mismatch:
                mismatch_count += 1

        total_amount = sum_received_value + sum_logistics_cost

        # 更新对账单汇总字段
        statement.total_ordered_amount = sum_ordered_amount
        statement.total_received_value = sum_received_value
        statement.total_logistics_cost = sum_logistics_cost
        statement.total_variance = sum_variance
        statement.anomaly_count = mismatch_count
        statement.total_amount = total_amount
        await db.flush()

        logger.info(
            f'[ReconciliationService] 重算对账单汇总 statement_id={statement_id} '
            f'total_ordered={sum_ordered_amount} received={sum_received_value} '
            f'logistics={sum_logistics_cost} variance={sum_variance} '
            f'anomaly_count={mismatch_count} total_amount={total_amount}'
        )
        return {
            'total_ordered_amount': sum_ordered_amount,
            'total_received_value': sum_received_value,
            'total_logistics_cost': sum_logistics_cost,
            'total_variance': sum_variance,
            'anomaly_count': mismatch_count,
            'total_amount': total_amount,
        }

    @staticmethod
    async def add_line_item(
        db: AsyncSession, statement_id: int, data: dict, operator_id: int = 0
    ) -> int:
        """
        新增对账单行项（仅 pending 状态允许）。

        - 校验对账单存在且处于 pending 状态
        - 校验必填字段（order_no）
        - 创建 ReconciliationLineItem 记录
        - 自动计算差异字段（如提供了 order_id 则调用 VarianceCalculationService）
        - 调用 calculate_summary 重算汇总

        Args:
            statement_id: 对账单 ID
            data: 行项字段字典，支持 order_id, order_no, process_name, part_no,
                  part_name, unit_price, quantity, total_amount,
                  ordered_quantity, ordered_unit_price, order_amount,
                  actual_delivered_qty, actual_delivered_value,
                  virtual_inbound_value, anomaly_deduction_amount,
                  logistics_cost
            operator_id: 操作人 ID

        Returns:
            新建行项 ID

        Raises:
            ServiceException: 对账单不存在 / 状态非 pending / 缺必填字段
        """
        await ReconciliationService._load_statement_for_modification(db, statement_id)

        # 必填字段校验
        for field in ReconciliationService._LINE_ITEM_REQUIRED_FIELDS:
            if data.get(field) in (None, ''):
                raise ServiceException(message=f'新增行项缺少必填字段: {field}')

        # 仅取允许字段，避免外部注入 is_frozen / statement_id 等内部字段
        payload = {
            k: data[k]
            for k in ReconciliationService._LINE_ITEM_UPDATABLE_FIELDS
            if k in data
        }

        line = ReconciliationLineItem(
            statement_id=statement_id,
            is_frozen=False,
            **payload,
        )
        db.add(line)
        await db.flush()  # 获取 line.id

        # 如果提供了 order_id，尝试通过 VarianceCalculationService 计算差异
        if line.order_id:
            order_stmt = select(EntrustOutsourceOrder).where(
                EntrustOutsourceOrder.id == line.order_id
            )
            order = (await db.execute(order_stmt)).scalar_one_or_none()
            if order:
                variance_data = await VarianceCalculationService.compute_line_item_variance(db, order)
                line.ordered_quantity = order.quantity
                line.ordered_unit_price = order.unit_price
                line.order_amount = variance_data['order_amount']
                line.actual_delivered_qty = variance_data['actual_delivered_qty']
                line.actual_delivered_value = variance_data['actual_delivered_value']
                line.virtual_inbound_value = variance_data['virtual_inbound_value']
                line.anomaly_deduction_amount = variance_data['anomaly_deduction_amount']
                line.logistics_cost = variance_data['logistics_cost']
                line.variance = variance_data['variance']
                line.has_mismatch = variance_data['has_mismatch']
                line.variance_reasons = variance_data['variance_reasons'] if variance_data['variance_reasons'] else None
                line.total_amount = variance_data['order_amount']
                await db.flush()

        # 重算汇总（Requirements 1.7: 行项变更后自动触发汇总重算）
        await ReconciliationService.calculate_summary(db, statement_id)

        # 审计日志：行项新增（Requirement 8.1）
        await ReconciliationAuditService.log_action(
            db=db,
            entity_type=ENTITY_TYPE_STATEMENT,
            entity_id=statement_id,
            action=ACTION_UPDATE,
            operator_id=int(operator_id or 0),
            detail={
                'sub_action': 'add_line_item',
                'line_item_id': line.id,
                'order_no': line.order_no,
                'order_amount': str(line.order_amount) if line.order_amount is not None else None,
                'variance': str(line.variance) if line.variance is not None else None,
            },
        )
        await db.commit()
        logger.info(
            f'[ReconciliationService] 新增行项 statement_id={statement_id} '
            f'item_id={line.id} order_no={line.order_no} '
            f'order_amount={line.order_amount} variance={line.variance}'
        )
        return line.id

    @staticmethod
    async def update_line_item(
        db: AsyncSession, statement_id: int, item_id: int, data: dict, operator_id: int = 0
    ) -> bool:
        """
        更新对账单行项（仅 pending 状态允许且行项未冻结）。

        - 校验对账单状态、行项归属、is_frozen
        - 仅更新白名单字段
        - 行项变更后自动重新计算差异和汇总

        Args:
            statement_id: 对账单 ID
            item_id: 行项 ID
            data: 待更新字段字典（仅白名单字段生效）
            operator_id: 操作人 ID

        Returns:
            True 表示更新成功

        Raises:
            ServiceException: 对账单不存在 / 状态非 pending / 行项不存在或被冻结
        """
        await ReconciliationService._load_statement_for_modification(db, statement_id)
        line = await ReconciliationService._load_line_item(db, statement_id, item_id)
        ReconciliationService._ensure_line_item_unfrozen(line)

        applied = 0
        for field in ReconciliationService._LINE_ITEM_UPDATABLE_FIELDS:
            if field in data:
                setattr(line, field, data[field])
                applied += 1

        await db.flush()

        # 如果行项关联了 order_id，重新计算差异字段
        if line.order_id:
            order_stmt = select(EntrustOutsourceOrder).where(
                EntrustOutsourceOrder.id == line.order_id
            )
            order = (await db.execute(order_stmt)).scalar_one_or_none()
            if order:
                variance_data = await VarianceCalculationService.compute_line_item_variance(db, order)
                line.ordered_quantity = order.quantity
                line.ordered_unit_price = order.unit_price
                line.order_amount = variance_data['order_amount']
                line.actual_delivered_qty = variance_data['actual_delivered_qty']
                line.actual_delivered_value = variance_data['actual_delivered_value']
                line.virtual_inbound_value = variance_data['virtual_inbound_value']
                line.anomaly_deduction_amount = variance_data['anomaly_deduction_amount']
                line.logistics_cost = variance_data['logistics_cost']
                line.variance = variance_data['variance']
                line.has_mismatch = variance_data['has_mismatch']
                line.variance_reasons = variance_data['variance_reasons'] if variance_data['variance_reasons'] else None
                line.total_amount = variance_data['order_amount']
                await db.flush()

        # 重算汇总（Requirements 1.7: 行项变更后自动触发汇总重算）
        await ReconciliationService.calculate_summary(db, statement_id)

        # 审计日志：行项更新（Requirement 8.1）
        await ReconciliationAuditService.log_action(
            db=db,
            entity_type=ENTITY_TYPE_STATEMENT,
            entity_id=statement_id,
            action=ACTION_UPDATE,
            operator_id=int(operator_id or 0),
            detail={
                'sub_action': 'update_line_item',
                'line_item_id': item_id,
                'fields_updated': applied,
                'updated_fields': {
                    k: (str(data[k]) if data[k] is not None else None)
                    for k in ReconciliationService._LINE_ITEM_UPDATABLE_FIELDS
                    if k in data
                },
            },
        )

        await db.commit()
        logger.info(
            f'[ReconciliationService] 更新行项 statement_id={statement_id} '
            f'item_id={item_id} fields_updated={applied}'
        )
        return True

    @staticmethod
    async def delete_line_item(
        db: AsyncSession, statement_id: int, item_id: int, operator_id: int = 0
    ) -> bool:
        """
        删除对账单行项（仅 pending 状态允许且行项未冻结）。

        - 校验对账单状态、行项归属、is_frozen
        - 删除行项及关联的 LineItemVarianceReason 记录
        - 行项变更后自动重新计算汇总

        Args:
            statement_id: 对账单 ID
            item_id: 行项 ID
            operator_id: 操作人 ID

        Returns:
            True 表示删除成功

        Raises:
            ServiceException: 对账单不存在 / 状态非 pending / 行项不存在或被冻结
        """
        await ReconciliationService._load_statement_for_modification(db, statement_id)
        line = await ReconciliationService._load_line_item(db, statement_id, item_id)
        ReconciliationService._ensure_line_item_unfrozen(line)

        # 删除关联的差异原因记录
        reason_del_stmt = select(LineItemVarianceReason).where(
            LineItemVarianceReason.line_item_id == item_id
        )
        reasons = (await db.execute(reason_del_stmt)).scalars().all()
        for reason in reasons:
            await db.delete(reason)

        await db.delete(line)
        await db.flush()

        # 重算汇总（Requirements 1.7: 行项变更后自动触发汇总重算）
        await ReconciliationService.calculate_summary(db, statement_id)

        # 审计日志：行项删除（Requirement 8.1, 8.3）
        await ReconciliationAuditService.log_action(
            db=db,
            entity_type=ENTITY_TYPE_STATEMENT,
            entity_id=statement_id,
            action=ACTION_DELETE,
            operator_id=int(operator_id or 0),
            detail={
                'sub_action': 'delete_line_item',
                'line_item_id': item_id,
                'order_no': line.order_no,
                'order_amount': str(line.order_amount) if line.order_amount is not None else None,
                'variance': str(line.variance) if line.variance is not None else None,
            },
        )

        await db.commit()
        logger.info(
            f'[ReconciliationService] 删除行项 statement_id={statement_id} '
            f'item_id={item_id}'
        )
        return True

    # ------------------------------------------------------------------
    # 差异重算（手动触发）
    # ------------------------------------------------------------------

    @staticmethod
    async def recalculate_variance(
        db: AsyncSession, statement_id: int, operator_id: int = 0
    ) -> dict:
        """
        手动触发对账单差异重算（Requirements 1.10, 8.3）。

        当底层数据（虚拟入库、扣款记录等）发生变化后，可手动触发此方法
        重新计算每个行项的差异字段，并更新对账单汇总。

        流程：
        1. 校验对账单存在且处于 pending 状态
        2. 遍历所有行项，对关联了 order_id 的行项重新调用
           VarianceCalculationService.compute_line_item_variance
        3. 更新行项差异字段（variance, has_mismatch, variance_reasons 等）
        4. 重新计算对账单汇总

        Args:
            statement_id: 对账单 ID
            operator_id: 操作人 ID

        Returns:
            包含汇总字段的字典（同 calculate_summary 返回值）

        Raises:
            ServiceException: 对账单不存在 / 状态非 pending
        """
        await ReconciliationService._load_statement_for_modification(db, statement_id)

        # 查询所有行项
        line_items_stmt = select(ReconciliationLineItem).where(
            ReconciliationLineItem.statement_id == statement_id
        )
        result = await db.execute(line_items_stmt)
        line_items = list(result.scalars().all())

        recalculated_count = 0

        for line in line_items:
            if not line.order_id:
                continue

            # 加载关联的工单
            order_stmt = select(EntrustOutsourceOrder).where(
                EntrustOutsourceOrder.id == line.order_id
            )
            order = (await db.execute(order_stmt)).scalar_one_or_none()
            if order is None:
                continue

            # 重新计算差异
            variance_data = await VarianceCalculationService.compute_line_item_variance(
                db, order
            )

            # 更新行项差异字段
            line.ordered_quantity = order.quantity
            line.ordered_unit_price = order.unit_price
            line.order_amount = variance_data['order_amount']
            line.actual_delivered_qty = variance_data['actual_delivered_qty']
            line.actual_delivered_value = variance_data['actual_delivered_value']
            line.virtual_inbound_value = variance_data['virtual_inbound_value']
            line.anomaly_deduction_amount = variance_data['anomaly_deduction_amount']
            line.logistics_cost = variance_data['logistics_cost']
            line.variance = variance_data['variance']
            line.has_mismatch = variance_data['has_mismatch']
            line.variance_reasons = (
                variance_data['variance_reasons']
                if variance_data['variance_reasons']
                else None
            )
            line.total_amount = variance_data['order_amount']
            recalculated_count += 1

        await db.flush()

        # 重算汇总
        summary = await ReconciliationService.calculate_summary(db, statement_id)

        # 审计日志：差异重算（Requirement 8.1）
        await ReconciliationAuditService.log_action(
            db=db,
            entity_type=ENTITY_TYPE_STATEMENT,
            entity_id=statement_id,
            action=ACTION_UPDATE,
            operator_id=int(operator_id or 0),
            detail={
                'sub_action': 'recalculate_variance',
                'recalculated_line_items': recalculated_count,
                'total_line_items': len(line_items),
                'summary': {
                    k: str(v) for k, v in summary.items()
                },
            },
        )

        await db.commit()
        logger.info(
            f'[ReconciliationService] 差异重算完成 statement_id={statement_id} '
            f'recalculated={recalculated_count}/{len(line_items)} '
            f'variance={summary["total_variance"]} anomaly_count={summary["anomaly_count"]}'
        )
        return summary
