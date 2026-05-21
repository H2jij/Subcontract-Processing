// src/api/reconciliation/report.ts
import request from '@/utils/request'
import type {
  DashboardVO,
  SupplierSummaryVO,
  MonthlyTrendVO,
  AgingAnalysisVO,
} from '@/types/reconciliation'

/** 仪表盘概览 */
export function getDashboard(params?: { start_date?: string; end_date?: string }) {
  return request({
    url: '/entrust/reconciliation-report/dashboard',
    method: 'get',
    params,
  }) as Promise<DashboardVO>
}

/** 供应商汇总 */
export function getSupplierSummary(params?: { start_date?: string; end_date?: string }) {
  return request({
    url: '/entrust/reconciliation-report/supplier-summary',
    method: 'get',
    params,
  }) as Promise<SupplierSummaryVO[]>
}

/** 月度趋势 */
export function getMonthlyTrend(params?: { months?: number }) {
  return request({
    url: '/entrust/reconciliation-report/monthly-trend',
    method: 'get',
    params,
  }) as Promise<MonthlyTrendVO[]>
}

/** 账龄分析 */
export function getAgingAnalysis() {
  return request({
    url: '/entrust/reconciliation-report/aging-analysis',
    method: 'get',
  }) as Promise<AgingAnalysisVO>
}

/** 导出 Excel */
export function exportExcel(params?: { start_date?: string; end_date?: string }) {
  return request({
    url: '/entrust/reconciliation-report/export/excel',
    method: 'get',
    params,
    responseType: 'arraybuffer',
  }) as Promise<ArrayBuffer>
}

/** 导出 PDF */
export function exportPdf(params?: { start_date?: string; end_date?: string }) {
  return request({
    url: '/entrust/reconciliation-report/export/pdf',
    method: 'get',
    params,
    responseType: 'arraybuffer',
  }) as Promise<ArrayBuffer>
}
