"""
对账系统 — 报表与统计 Service
=========================================
覆盖需求 6.1 ~ 6.6

职责：
  1. get_dashboard()：对账概览仪表盘统计（总数、已确认、有争议、待确认）
  2. get_supplier_summary(filters)：按供应商维度汇总（对账总金额、已付、未付）
  3. get_monthly_trend(months, filters)：月度趋势（数量、异常率、平均确认耗时）
  4. get_aging_analysis(filters)：账龄分析（0-30天、31-60天、61-90天、90天以上）

所有方法支持按时间范围、供应商、状态筛选（Requirements 6.5）。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import case, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_entrust.entity.do.reconciliation_do import (
    Anomaly,
    PaymentRequest,
    ReconciliationStatement,
)


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _to_decimal(value) -> Decimal:
    """安全地将数值转换为 Decimal；None 视作 0。"""
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _apply_filters(query, filters: Optional[dict] = None):
    """
    对 ReconciliationStatement 查询应用通用筛选条件。

    支持的 filters 键：
      - supplier_id: int — 按供应商筛选
      - status: str — 按对账单状态筛选
      - confirmation_status: str — 按确认状态筛选
      - start_date: date — 对账周期起始 >= start_date
      - end_date: date — 对账周期结束 <= end_date
    """
    if not filters:
        return query

    if filters.get('supplier_id'):
        query = query.where(
            ReconciliationStatement.supplier_id == filters['supplier_id']
        )
    if filters.get('status'):
        query = query.where(
            ReconciliationStatement.status == filters['status']
        )
    if filters.get('confirmation_status'):
        query = query.where(
            ReconciliationStatement.confirmation_status == filters['confirmation_status']
        )
    if filters.get('start_date'):
        query = query.where(
            ReconciliationStatement.period_start >= filters['start_date']
        )
    if filters.get('end_date'):
        query = query.where(
            ReconciliationStatement.period_end <= filters['end_date']
        )

    return query


def _apply_payment_filters(query, filters: Optional[dict] = None):
    """
    对 PaymentRequest 查询应用通用筛选条件。

    支持的 filters 键：
      - supplier_id: int — 按供应商筛选
      - start_date: date — created_at >= start_date
      - end_date: date — created_at <= end_date
    """
    if not filters:
        return query

    if filters.get('supplier_id'):
        query = query.where(
            PaymentRequest.supplier_id == filters['supplier_id']
        )
    if filters.get('start_date'):
        query = query.where(
            PaymentRequest.created_at >= filters['start_date']
        )
    if filters.get('end_date'):
        query = query.where(
            PaymentRequest.created_at <= filters['end_date']
        )

    return query


# ---------------------------------------------------------------------------
# 账龄分桶辅助（Property 12）
# ---------------------------------------------------------------------------

def compute_aging_bucket(days: int) -> str:
    """
    根据天数计算账龄分桶。

    规则：
      - 0 <= days <= 30  -> '0-30'
      - 31 <= days <= 60 -> '31-60'
      - 61 <= days <= 90 -> '61-90'
      - days > 90        -> '90+'

    Args:
        days: 自付款申请创建以来的天数

    Returns:
        账龄分桶标签
    """
    if days <= 30:
        return '0-30'
    elif days <= 60:
        return '31-60'
    elif days <= 90:
        return '61-90'
    else:
        return '90+'


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ReconciliationReportService:
    """对账报表与统计服务。"""

    # ------------------------------------------------------------------
    # 对账概览仪表盘（Requirement 6.1）
    # ------------------------------------------------------------------

    @staticmethod
    async def get_dashboard(
        db: AsyncSession,
        filters: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        对账概览统计：对账单总数、已确认数量、有争议数量、待确认数量。

        Args:
            db: AsyncSession
            filters: 可选筛选条件 (supplier_id, status, start_date, end_date)

        Returns:
            {
                'total': int,
                'confirmed': int,
                'disputed': int,
                'pending': int,
            }
        """
        # 总数
        total_query = select(func.count(ReconciliationStatement.id))
        total_query = _apply_filters(total_query, filters)
        total = await db.scalar(total_query) or 0

        # 按 confirmation_status 分组统计
        group_query = select(
            ReconciliationStatement.confirmation_status,
            func.count(ReconciliationStatement.id).label('cnt'),
        ).group_by(ReconciliationStatement.confirmation_status)
        group_query = _apply_filters(group_query, filters)

        result = await db.execute(group_query)
        status_counts = {row[0]: row[1] for row in result.all()}

        return {
            'total': total,
            'confirmed': status_counts.get('confirmed', 0),
            'disputed': status_counts.get('disputed', 0),
            'pending': status_counts.get('pending', 0),
        }

    # ------------------------------------------------------------------
    # 供应商汇总报表（Requirement 6.2）
    # ------------------------------------------------------------------

    @staticmethod
    async def get_supplier_summary(
        db: AsyncSession,
        filters: Optional[dict] = None,
    ) -> list[dict[str, Any]]:
        """
        按供应商维度汇总：对账总金额、已付金额、未付金额。

        通过 join PaymentRequest 获取已付/未付信息。

        Args:
            db: AsyncSession
            filters: 可选筛选条件 (supplier_id, status, start_date, end_date)

        Returns:
            [
                {
                    'supplier_id': int,
                    'total_amount': Decimal,
                    'paid_amount': Decimal,
                    'unpaid_amount': Decimal,
                },
                ...
            ]
        """
        # 使用子查询：先按供应商汇总对账单金额
        stmt_query = (
            select(
                ReconciliationStatement.supplier_id,
                func.coalesce(
                    func.sum(ReconciliationStatement.total_amount), 0
                ).label('total_amount'),
            )
            .group_by(ReconciliationStatement.supplier_id)
        )
        stmt_query = _apply_filters(stmt_query, filters)

        # 按供应商汇总已付金额（从 PaymentRequest）
        paid_query = (
            select(
                PaymentRequest.supplier_id,
                func.coalesce(
                    func.sum(PaymentRequest.paid_amount), 0
                ).label('paid_amount'),
            )
            .group_by(PaymentRequest.supplier_id)
        )
        paid_query = _apply_payment_filters(paid_query, filters)

        # 执行两个查询
        stmt_result = await db.execute(stmt_query)
        stmt_rows = {row[0]: _to_decimal(row[1]) for row in stmt_result.all()}

        paid_result = await db.execute(paid_query)
        paid_rows = {row[0]: _to_decimal(row[1]) for row in paid_result.all()}

        # 合并结果
        summaries = []
        for supplier_id, total_amount in stmt_rows.items():
            paid_amount = paid_rows.get(supplier_id, Decimal('0'))
            unpaid_amount = total_amount - paid_amount
            summaries.append({
                'supplier_id': supplier_id,
                'total_amount': total_amount,
                'paid_amount': paid_amount,
                'unpaid_amount': unpaid_amount,
            })

        # 按 supplier_id 排序
        summaries.sort(key=lambda x: x['supplier_id'])
        return summaries

    # ------------------------------------------------------------------
    # 月度趋势（Requirement 6.3）
    # ------------------------------------------------------------------

    @staticmethod
    async def get_monthly_trend(
        db: AsyncSession,
        months: int = 12,
        filters: Optional[dict] = None,
    ) -> list[dict[str, Any]]:
        """
        月度趋势：对账单数量、异常率、平均确认耗时。

        - 数量：按 created_at 的年月分组统计对账单数
        - 异常率：该月对账单中有异常记录的比例
        - 平均确认耗时：confirmed_at - created_at 的平均天数

        Args:
            db: AsyncSession
            months: 回溯月数（默认 12 个月）
            filters: 可选筛选条件 (supplier_id, status, start_date, end_date)

        Returns:
            [
                {
                    'year': int,
                    'month': int,
                    'statement_count': int,
                    'anomaly_rate': float,  # 0.0 ~ 1.0
                    'avg_confirmation_days': float | None,
                },
                ...
            ]
        """
        # 计算起始日期
        now = datetime.now()
        start_date = date(now.year, now.month, 1) - timedelta(days=(months - 1) * 31)
        # 调整到月初
        start_date = date(start_date.year, start_date.month, 1)

        # 对账单按月统计
        stmt_query = (
            select(
                extract('year', ReconciliationStatement.created_at).label('yr'),
                extract('month', ReconciliationStatement.created_at).label('mo'),
                func.count(ReconciliationStatement.id).label('stmt_count'),
                func.avg(
                    case(
                        (
                            ReconciliationStatement.confirmed_at.isnot(None),
                            func.extract(
                                'epoch',
                                ReconciliationStatement.confirmed_at
                                - ReconciliationStatement.created_at,
                            ) / 86400.0,
                        ),
                        else_=None,
                    )
                ).label('avg_days'),
            )
            .where(ReconciliationStatement.created_at >= start_date)
            .group_by('yr', 'mo')
            .order_by('yr', 'mo')
        )
        stmt_query = _apply_filters(stmt_query, filters)

        stmt_result = await db.execute(stmt_query)
        stmt_rows = stmt_result.all()

        # 异常统计：按月统计有异常的对账单数
        anomaly_query = (
            select(
                extract('year', ReconciliationStatement.created_at).label('yr'),
                extract('month', ReconciliationStatement.created_at).label('mo'),
                func.count(func.distinct(Anomaly.statement_id)).label('anomaly_stmt_count'),
            )
            .select_from(Anomaly)
            .join(
                ReconciliationStatement,
                ReconciliationStatement.id == Anomaly.statement_id,
            )
            .where(ReconciliationStatement.created_at >= start_date)
            .group_by('yr', 'mo')
        )
        if filters and filters.get('supplier_id'):
            anomaly_query = anomaly_query.where(
                ReconciliationStatement.supplier_id == filters['supplier_id']
            )

        anomaly_result = await db.execute(anomaly_query)
        anomaly_map = {
            (int(row[0]), int(row[1])): int(row[2])
            for row in anomaly_result.all()
        }

        # 组装结果
        trends = []
        for row in stmt_rows:
            yr = int(row[0])
            mo = int(row[1])
            stmt_count = int(row[2])
            avg_days = float(row[3]) if row[3] is not None else None

            anomaly_count = anomaly_map.get((yr, mo), 0)
            anomaly_rate = (
                anomaly_count / stmt_count if stmt_count > 0 else 0.0
            )

            trends.append({
                'year': yr,
                'month': mo,
                'statement_count': stmt_count,
                'anomaly_rate': round(anomaly_rate, 4),
                'avg_confirmation_days': (
                    round(avg_days, 2) if avg_days is not None else None
                ),
            })

        return trends

    # ------------------------------------------------------------------
    # 账龄分析（Requirement 6.4 / Property 12）
    # ------------------------------------------------------------------

    @staticmethod
    async def get_aging_analysis(
        db: AsyncSession,
        filters: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        账龄分析：将未付款项按账龄分组展示。

        账龄计算：当前日期 - PaymentRequest.created_at 的天数
        分桶：0-30天、31-60天、61-90天、90天以上

        仅统计 payment_status != 'paid' 的付款申请。

        Args:
            db: AsyncSession
            filters: 可选筛选条件 (supplier_id, start_date, end_date)

        Returns:
            {
                'buckets': [
                    {'range': '0-30', 'count': int, 'amount': Decimal},
                    {'range': '31-60', 'count': int, 'amount': Decimal},
                    {'range': '61-90', 'count': int, 'amount': Decimal},
                    {'range': '90+', 'count': int, 'amount': Decimal},
                ],
                'total_unpaid_count': int,
                'total_unpaid_amount': Decimal,
            }
        """
        # 查询所有未付清的付款申请
        query = (
            select(
                PaymentRequest.id,
                PaymentRequest.created_at,
                PaymentRequest.payable_amount,
                PaymentRequest.paid_amount,
            )
            .where(PaymentRequest.payment_status != 'paid')
        )
        query = _apply_payment_filters(query, filters)

        result = await db.execute(query)
        rows = result.all()

        # 分桶统计
        buckets = {
            '0-30': {'count': 0, 'amount': Decimal('0')},
            '31-60': {'count': 0, 'amount': Decimal('0')},
            '61-90': {'count': 0, 'amount': Decimal('0')},
            '90+': {'count': 0, 'amount': Decimal('0')},
        }

        today = date.today()
        total_count = 0
        total_amount = Decimal('0')

        for row in rows:
            created_at = row[1]
            payable = _to_decimal(row[2])
            paid = _to_decimal(row[3])
            unpaid = payable - paid

            # 计算天数
            if isinstance(created_at, datetime):
                days = (today - created_at.date()).days
            else:
                days = (today - created_at).days

            # 确保天数非负
            days = max(days, 0)

            bucket_key = compute_aging_bucket(days)
            buckets[bucket_key]['count'] += 1
            buckets[bucket_key]['amount'] += unpaid

            total_count += 1
            total_amount += unpaid

        # 格式化输出
        bucket_list = [
            {'range': key, 'count': data['count'], 'amount': data['amount']}
            for key, data in buckets.items()
        ]

        return {
            'buckets': bucket_list,
            'total_unpaid_count': total_count,
            'total_unpaid_amount': total_amount,
        }


__all__ = [
    'ReconciliationReportService',
    'compute_aging_bucket',
]
