// src/store/modules/reconciliation/anomaly.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getAnomalyList,
  getAnomalyDetail,
  createAdjustment,
  getPendingApprovals,
  approveAdjustment,
  rejectAdjustment,
} from '@/api/reconciliation/anomaly'
import type {
  AnomalyVO,
  AdjustmentVO,
  AnomalyFilterParams,
  CreateAdjustmentParams,
} from '@/types/reconciliation'

export const useAnomalyStore = defineStore('anomaly', () => {
  // 列表状态
  const list = ref<AnomalyVO[]>([])
  const total = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)
  const currentPage = ref(1)
  const pageSize = 20
  const hasMore = computed(() => list.value.length < total.value)

  // 筛选条件
  const filters = ref<AnomalyFilterParams>({
    page: 1,
    page_size: pageSize,
  })

  // 当前详情
  const currentDetail = ref<AnomalyVO | null>(null)

  // 待审批列表
  const pendingApprovals = ref<AdjustmentVO[]>([])

  // 列表操作
  async function fetchList(refresh = false) {
    if (refresh) {
      currentPage.value = 1
      filters.value.page = 1
    }
    loading.value = refresh || !list.value.length
    loadingMore.value = !refresh && currentPage.value > 1

    try {
      const res = await getAnomalyList(filters.value)
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
      currentDetail.value = await getAnomalyDetail(id)
    } finally {
      loading.value = false
    }
  }

  // 创建调整
  async function createAdjustmentAction(id: number, params: CreateAdjustmentParams) {
    await createAdjustment(id, params)
  }

  // 获取待审批列表
  async function fetchPendingApprovals() {
    loading.value = true
    try {
      const res = await getPendingApprovals({ page: 1, page_size: pageSize })
      pendingApprovals.value = res.rows
    } finally {
      loading.value = false
    }
  }

  // 审批通过
  async function approve(id: number) {
    await approveAdjustment(id)
    await fetchPendingApprovals()
  }

  // 审批驳回
  async function reject(id: number, reason: string) {
    await rejectAdjustment(id, { reject_reason: reason })
    await fetchPendingApprovals()
  }

  // 设置筛选条件
  function setFilters(newFilters: Partial<AnomalyFilterParams>) {
    Object.assign(filters.value, newFilters)
  }

  function $reset() {
    list.value = []
    total.value = 0
    currentPage.value = 1
    currentDetail.value = null
    pendingApprovals.value = []
  }

  return {
    list, total, loading, loadingMore, hasMore, filters,
    currentDetail, pendingApprovals,
    fetchList, loadMore, fetchDetail,
    createAdjustment: createAdjustmentAction,
    fetchPendingApprovals, approve, reject,
    setFilters, $reset,
  }
})
