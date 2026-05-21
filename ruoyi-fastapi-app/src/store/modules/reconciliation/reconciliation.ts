// src/store/modules/reconciliation/reconciliation.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getStatementList,
  getStatementDetail,
  getVarianceSummary,
  generateStatement,
  recalculateVariance,
} from '@/api/reconciliation/reconciliation'
import type {
  ReconciliationStatementVO,
  VarianceSummaryVO,
  StatementFilterParams,
  GenerateStatementParams,
} from '@/types/reconciliation'

export const useReconciliationStore = defineStore('reconciliation', () => {
  // 列表状态
  const list = ref<ReconciliationStatementVO[]>([])
  const total = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)
  const currentPage = ref(1)
  const pageSize = 20
  const hasMore = computed(() => list.value.length < total.value)

  // 筛选条件
  const filters = ref<StatementFilterParams>({
    page: 1,
    page_size: pageSize,
  })

  // 当前详情
  const currentDetail = ref<ReconciliationStatementVO | null>(null)
  const varianceSummary = ref<VarianceSummaryVO | null>(null)

  // 列表操作
  async function fetchList(refresh = false) {
    if (refresh) {
      currentPage.value = 1
      filters.value.page = 1
    }
    loading.value = refresh || !list.value.length
    loadingMore.value = !refresh && currentPage.value > 1

    try {
      const res = await getStatementList(filters.value)
      if (refresh) {
        list.value = res.rows
      } else {
        list.value.push(...res.rows)
      }
      total.value = res.total
    } finally {
      loading.value = false
      loadingMore.value = false
    }
  }

  async function loadMore() {
    if (!hasMore.value || loadingMore.value) return
    currentPage.value++
    filters.value.page = currentPage.value
    await fetchList()
  }

  // 详情操作
  async function fetchDetail(id: number) {
    loading.value = true
    try {
      currentDetail.value = await getStatementDetail(id)
      varianceSummary.value = await getVarianceSummary(id)
    } finally {
      loading.value = false
    }
  }

  // 生成对账单
  async function generate(params: GenerateStatementParams) {
    return await generateStatement(params)
  }

  // 重新计算差异
  async function recalculate(id: number) {
    await recalculateVariance(id)
    await fetchDetail(id)
  }

  // 设置筛选条件
  function setFilters(newFilters: Partial<StatementFilterParams>) {
    Object.assign(filters.value, newFilters)
  }

  function $reset() {
    list.value = []
    total.value = 0
    currentPage.value = 1
    currentDetail.value = null
    varianceSummary.value = null
  }

  return {
    list, total, loading, loadingMore, hasMore, currentPage, filters,
    currentDetail, varianceSummary,
    fetchList, loadMore, fetchDetail, generate, recalculate,
    setFilters, $reset,
  }
})
