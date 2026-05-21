// src/store/modules/reconciliation/supplierClaim.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getSupplierStatements,
  getSupplierStatementDetail,
  confirmStatement,
  disputeStatement,
} from '@/api/reconciliation/supplierClaim'
import type {
  ReconciliationStatementVO,
  DisputeParams,
} from '@/types/reconciliation'

export const useSupplierClaimStore = defineStore('supplierClaim', () => {
  // 列表状态
  const list = ref<ReconciliationStatementVO[]>([])
  const total = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)
  const currentPage = ref(1)
  const pageSize = 20
  const hasMore = computed(() => list.value.length < total.value)

  // 当前详情
  const currentDetail = ref<ReconciliationStatementVO | null>(null)

  // 列表操作
  async function fetchList(refresh = false) {
    if (refresh) {
      currentPage.value = 1
    }
    loading.value = refresh || !list.value.length
    loadingMore.value = !refresh && currentPage.value > 1

    try {
      const res = await getSupplierStatements({
        page: currentPage.value,
        page_size: pageSize,
      })
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
    await fetchList()
  }

  // 详情操作
  async function fetchDetail(id: number) {
    loading.value = true
    try {
      currentDetail.value = await getSupplierStatementDetail(id)
    } finally {
      loading.value = false
    }
  }

  // 供应商确认
  async function confirm(id: number) {
    await confirmStatement(id)
    await fetchDetail(id)
  }

  // 供应商争议
  async function dispute(id: number, params: DisputeParams) {
    await disputeStatement(id, params)
    await fetchDetail(id)
  }

  function $reset() {
    list.value = []
    total.value = 0
    currentPage.value = 1
    currentDetail.value = null
  }

  return {
    list, total, loading, loadingMore, hasMore,
    currentDetail,
    fetchList, loadMore, fetchDetail, confirm, dispute,
    $reset,
  }
})
