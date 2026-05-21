// src/store/modules/reconciliation/report.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getDashboard,
  getSupplierSummary,
  getMonthlyTrend,
  getAgingAnalysis,
  exportExcel as exportExcelApi,
  exportPdf as exportPdfApi,
} from '@/api/reconciliation/report'
import type {
  DashboardVO,
  SupplierSummaryVO,
  MonthlyTrendVO,
  AgingAnalysisVO,
} from '@/types/reconciliation'

export const useReportStore = defineStore('report', () => {
  // 状态
  const dashboard = ref<DashboardVO | null>(null)
  const supplierSummary = ref<SupplierSummaryVO[]>([])
  const monthlyTrend = ref<MonthlyTrendVO[]>([])
  const agingAnalysis = ref<AgingAnalysisVO | null>(null)
  const loading = ref(false)

  // 获取仪表盘数据
  async function fetchDashboard(params?: { start_date?: string; end_date?: string }) {
    loading.value = true
    try {
      dashboard.value = await getDashboard(params)
    } finally {
      loading.value = false
    }
  }

  // 获取供应商汇总
  async function fetchSupplierSummary(params?: { start_date?: string; end_date?: string }) {
    loading.value = true
    try {
      supplierSummary.value = await getSupplierSummary(params)
    } finally {
      loading.value = false
    }
  }

  // 获取月度趋势
  async function fetchMonthlyTrend(params?: { months?: number }) {
    loading.value = true
    try {
      monthlyTrend.value = await getMonthlyTrend(params)
    } finally {
      loading.value = false
    }
  }

  // 获取账龄分析
  async function fetchAgingAnalysis() {
    loading.value = true
    try {
      agingAnalysis.value = await getAgingAnalysis()
    } finally {
      loading.value = false
    }
  }

  // 导出 Excel
  async function exportExcel(params?: { start_date?: string; end_date?: string }): Promise<ArrayBuffer> {
    return await exportExcelApi(params)
  }

  // 导出 PDF
  async function exportPdf(params?: { start_date?: string; end_date?: string }): Promise<ArrayBuffer> {
    return await exportPdfApi(params)
  }

  function $reset() {
    dashboard.value = null
    supplierSummary.value = []
    monthlyTrend.value = []
    agingAnalysis.value = null
  }

  return {
    dashboard, supplierSummary, monthlyTrend, agingAnalysis, loading,
    fetchDashboard, fetchSupplierSummary, fetchMonthlyTrend, fetchAgingAnalysis,
    exportExcel, exportPdf,
    $reset,
  }
})
