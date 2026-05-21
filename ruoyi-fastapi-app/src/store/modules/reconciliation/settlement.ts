// src/store/modules/reconciliation/settlement.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getSettlementList,
  getSettlementDetail,
  updateSettlementLineItems,
  finalizeSettlement,
  getSettlementPdf,
} from '@/api/reconciliation/settlement'
import type { SettlementDetailVO } from '@/types/reconciliation'

export const useSettlementStore = defineStore('settlement', () => {
  // 列表状态
  const list = ref<SettlementDetailVO[]>([])
  const total = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)
  const currentPage = ref(1)
  const pageSize = 20
  const hasMore = computed(() => list.value.length < total.value)

  // 当前详情
  const currentDetail = ref<SettlementDetailVO | null>(null)

  // 编辑模式
  const editMode = ref(false)

  // 列表操作
  async function fetchList(refresh = false) {
    if (refresh) {
      currentPage.value = 1
    }
    loading.value = refresh || !list.value.length
    loadingMore.value = !refresh && currentPage.value > 1

    try {
      const res = await getSettlementList({
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
      currentDetail.value = await getSettlementDetail(id)
    } finally {
      loading.value = false
    }
  }

  // 编辑行项
  async function updateLineItems(id: number, data: any) {
    await updateSettlementLineItems(id, data)
    await fetchDetail(id)
  }

  // 确认结算
  async function finalize(id: number) {
    await finalizeSettlement(id)
    await fetchDetail(id)
  }

  // 下载 PDF
  async function downloadPdf(id: number): Promise<ArrayBuffer> {
    return await getSettlementPdf(id)
  }

  function $reset() {
    list.value = []
    total.value = 0
    currentPage.value = 1
    currentDetail.value = null
    editMode.value = false
  }

  return {
    list, total, loading, loadingMore, hasMore,
    currentDetail, editMode,
    fetchList, loadMore, fetchDetail,
    updateLineItems, finalize, downloadPdf,
    $reset,
  }
})
