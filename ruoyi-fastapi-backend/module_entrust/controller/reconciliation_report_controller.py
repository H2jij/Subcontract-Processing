"""
对账系统 — 报表/仪表盘 Controller
=========================================
API 路由：
  GET  /entrust/reconciliation-report/dashboard          — 对账概览仪表盘
  GET  /entrust/reconciliation-report/supplier-summary   — 供应商汇总报表
  GET  /entrust/reconciliation-report/monthly-trend      — 月度趋势
  GET  /entrust/reconciliation-report/aging-analysis     — 账龄分析
  GET  /entrust/reconciliation-report/export/excel       — 导出 Excel
  GET  /entrust/reconciliation-report/export/pdf         — 导出 PDF
  GET  /entrust/reconciliation-report/export/anomaly-report — 导出异常报告

Requirements covered: 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.5
"""
from __future__ import annotations

import io
from typing import Annotated, Optional
from urllib.parse import quote

from fastapi import Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel
from exceptions.exception import ServiceException
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_entrust.service.reconciliation_export_service import (
    ReconciliationExportService,
)
from module_entrust.service.reconciliation_pdf_service import (
    ReconciliationPdfService,
)
from module_entrust.service.reconciliation_report_service import (
    ReconciliationReportService,
)
from utils.response_util import ResponseUtil

reconciliation_report_controller = APIRouterPro(
    prefix='/entrust/reconciliation-report',
    order_num=26,
    tags=['对账报表'],
    dependencies=[PreAuthDependency()],
)


# ── GET /dashboard — 对账概览仪表盘 ──────────────────────────────────────────

@reconciliation_report_controller.get(
    '/dashboard',
    summary='对账概览仪表盘',
    response_model=DataResponseModel,
)
async def get_dashboard(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    supplier_id: Optional[int] = Query(default=None, description='供应商ID'),
    status: Optional[str] = Query(default=None, description='状态筛选'),
    start_date: Optional[str] = Query(default=None, description='起始日期 YYYY-MM-DD'),
    end_date: Optional[str] = Query(default=None, description='结束日期 YYYY-MM-DD'),
):
    """对账概览仪表盘：对账单总数、已确认、有争议、待确认等统计指标。"""
    from datetime import date as date_type

    filters = _build_filters(supplier_id, status, start_date, end_date)
    if isinstance(filters, str):
        return ResponseUtil.failure(msg=filters)

    try:
        data = await ReconciliationReportService.get_dashboard(
            db=query_db, filters=filters
        )
        return ResponseUtil.success(data=data)
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── GET /supplier-summary — 供应商汇总报表 ───────────────────────────────────

@reconciliation_report_controller.get(
    '/supplier-summary',
    summary='供应商汇总报表',
    response_model=DataResponseModel,
)
async def get_supplier_summary(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    supplier_id: Optional[int] = Query(default=None, description='供应商ID'),
    status: Optional[str] = Query(default=None, description='状态筛选'),
    start_date: Optional[str] = Query(default=None, description='起始日期 YYYY-MM-DD'),
    end_date: Optional[str] = Query(default=None, description='结束日期 YYYY-MM-DD'),
):
    """按供应商维度汇总：对账总金额、已付金额、未付金额。"""
    from datetime import date as date_type

    filters = _build_filters(supplier_id, status, start_date, end_date)
    if isinstance(filters, str):
        return ResponseUtil.failure(msg=filters)

    try:
        data = await ReconciliationReportService.get_supplier_summary(
            db=query_db, filters=filters
        )
        return ResponseUtil.success(data=data)
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── GET /monthly-trend — 月度趋势 ───────────────────────────────────────────

@reconciliation_report_controller.get(
    '/monthly-trend',
    summary='月度趋势',
    response_model=DataResponseModel,
)
async def get_monthly_trend(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    months: int = Query(default=12, ge=1, le=24, description='查询月数'),
    supplier_id: Optional[int] = Query(default=None, description='供应商ID'),
    status: Optional[str] = Query(default=None, description='状态筛选'),
    start_date: Optional[str] = Query(default=None, description='起始日期 YYYY-MM-DD'),
    end_date: Optional[str] = Query(default=None, description='结束日期 YYYY-MM-DD'),
):
    """月度趋势：对账单数量、异常率、平均确认耗时。"""
    from datetime import date as date_type

    filters = _build_filters(supplier_id, status, start_date, end_date)
    if isinstance(filters, str):
        return ResponseUtil.failure(msg=filters)

    try:
        data = await ReconciliationReportService.get_monthly_trend(
            db=query_db, months=months, filters=filters
        )
        return ResponseUtil.success(data=data)
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── GET /aging-analysis — 账龄分析 ───────────────────────────────────────────

@reconciliation_report_controller.get(
    '/aging-analysis',
    summary='账龄分析',
    response_model=DataResponseModel,
)
async def get_aging_analysis(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    supplier_id: Optional[int] = Query(default=None, description='供应商ID'),
    start_date: Optional[str] = Query(default=None, description='起始日期 YYYY-MM-DD'),
    end_date: Optional[str] = Query(default=None, description='结束日期 YYYY-MM-DD'),
):
    """账龄分析：将未付款项按账龄分组展示（0-30天、31-60天、61-90天、90天以上）。"""
    from datetime import date as date_type

    filters = _build_filters(supplier_id, None, start_date, end_date)
    if isinstance(filters, str):
        return ResponseUtil.failure(msg=filters)

    try:
        data = await ReconciliationReportService.get_aging_analysis(
            db=query_db, filters=filters
        )
        return ResponseUtil.success(data=data)
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── GET /export/excel — 导出 Excel ───────────────────────────────────────────

@reconciliation_report_controller.get(
    '/export/excel',
    summary='导出 Excel',
    response_class=StreamingResponse,
    responses={
        200: {
            'content': {
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': {}
            },
            'description': '对账单 Excel 文件',
        }
    },
)
async def export_excel(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    statement_id: int = Query(..., description='对账单ID'),
):
    """导出单份对账单 Excel 文件（.xlsx）。"""
    try:
        operator_id = current_user.user.user_id if current_user.user else 0
        result = await ReconciliationExportService.export_statement_excel(
            db=query_db,
            statement_id=statement_id,
            operator_id=operator_id,
        )
        encoded_name = quote(result.file_name, safe='')
        return StreamingResponse(
            io.BytesIO(result.content),
            media_type=result.mime_type,
            headers={
                'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_name}",
            },
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── GET /export/pdf — 导出 PDF ───────────────────────────────────────────────

@reconciliation_report_controller.get(
    '/export/pdf',
    summary='导出 PDF',
    response_class=StreamingResponse,
    responses={
        200: {
            'content': {'application/pdf': {}},
            'description': '对账单 PDF 文件',
        }
    },
)
async def export_pdf(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    statement_id: int = Query(..., description='对账单ID'),
):
    """导出对账单 PDF 文件（正式格式，含公司印章区域和签名栏位）。"""
    try:
        operator_id = current_user.user.user_id if current_user.user else 0
        operator_name = ''
        if current_user.user:
            operator_name = getattr(current_user.user, 'nick_name', '') or ''

        pdf_path = await ReconciliationPdfService.generate_statement_pdf(
            db=query_db,
            statement_id=statement_id,
            operator_id=operator_id,
            operator_name=operator_name,
        )

        # 读取生成的 PDF 文件并返回 StreamingResponse
        import os
        file_name = os.path.basename(pdf_path)
        encoded_name = quote(file_name, safe='')

        with open(pdf_path, 'rb') as f:
            content = f.read()

        return StreamingResponse(
            io.BytesIO(content),
            media_type='application/pdf',
            headers={
                'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_name}",
            },
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── GET /export/anomaly-report — 导出异常报告 ────────────────────────────────

@reconciliation_report_controller.get(
    '/export/anomaly-report',
    summary='导出异常报告',
    response_class=StreamingResponse,
    responses={
        200: {
            'content': {
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': {}
            },
            'description': '异常报告 Excel 文件',
        }
    },
)
async def export_anomaly_report(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    statement_id: int = Query(..., description='对账单ID'),
):
    """导出对账单异常报告 Excel 文件（.xlsx），包含所有异常记录详细信息及处理状态。"""
    try:
        operator_id = current_user.user.user_id if current_user.user else 0
        result = await ReconciliationExportService.export_anomaly_report(
            db=query_db,
            statement_id=statement_id,
            operator_id=operator_id,
        )
        encoded_name = quote(result.file_name, safe='')
        return StreamingResponse(
            io.BytesIO(result.content),
            media_type=result.mime_type,
            headers={
                'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_name}",
            },
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── 内部辅助 ─────────────────────────────────────────────────────────────────

def _build_filters(
    supplier_id: Optional[int],
    status: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> dict | str:
    """
    构建筛选条件字典。

    返回 dict 表示成功，返回 str 表示错误消息。
    """
    from datetime import date as date_type

    filters: dict = {}

    if supplier_id is not None:
        filters['supplier_id'] = supplier_id
    if status is not None:
        filters['status'] = status
    if start_date is not None:
        try:
            filters['start_date'] = date_type.fromisoformat(start_date)
        except ValueError:
            return 'start_date 格式错误，应为 YYYY-MM-DD'
    if end_date is not None:
        try:
            filters['end_date'] = date_type.fromisoformat(end_date)
        except ValueError:
            return 'end_date 格式错误，应为 YYYY-MM-DD'

    return filters
