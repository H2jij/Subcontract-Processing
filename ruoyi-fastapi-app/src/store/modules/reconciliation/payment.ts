// src/store/modules/reconciliation/payment.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getPaymentRequests,
  getPaymentRequestDetail,
  createPaymentRecord,
  uploadEvidence as uploadEvidenceApi,
  deleteEvidence as deleteEvidenceApi,
} from '@/api/reconciliation/payment'
import type {
  PaymentRequestVO,
  PaymentEvidenceVO,
  CreatePaymentRecordParams,
} from '@/types/reconciliation'

export const usePaymentStore = defineStore('payment', () => {
  // 列表状态
  const list = ref<PaymentRequestVO[]>([])
  const total = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)
  const currentPage = ref(1)
  const pageSize = 20
  const hasMore = computed(() => list.value.length < total.value)

  // 当前详情
  const currentDetail = ref<PaymentRequestVO | null>(null)

  // 列表操作
  async function fetchList(refresh = false) {
    if (refresh) {
      currentPage.value = 1
    }
    loading.value = refresh || !list.value.length
    loadingMore.value = !refresh && currentPage.value > 1

    try {
      const res = await getPaymentRequests({
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
      currentDetail.value = await getPaymentRequestDetail(id)
    } finally {
      loading.value = false
    }
  }

  // 录入付款记录
  async function createRecord(requestId: number, params: CreatePaymentRecordParams) {
    await createPaymentRecord(requestId, params)
    await fetchDetail(requestId)
  }

  // 上传支付凭证
  async function uploadEvidence(file: any): Promise<PaymentEvidenceVO> {
    return await uploadEvidenceApi(file)
  }

  // 删除凭证
  async function deleteEvidence(id: number) {
    await deleteEvidenceApi(id)
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
    fetchList, loadMore, fetchDetail,
    createRecord, uploadEvidence, deleteEvidence,
    $reset,
  }
})
