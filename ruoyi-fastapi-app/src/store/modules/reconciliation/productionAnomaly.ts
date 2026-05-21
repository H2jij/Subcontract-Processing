// src/store/modules/reconciliation/productionAnomaly.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getProductionAnomalyList,
  getProductionAnomalyDetail,
  createProductionAnomaly,
  setLiability as setLiabilityApi,
  createReShipment as createReShipmentApi,
  createDeduction as createDeductionApi,
  addNegotiation as addNegotiationApi,
} from '@/api/reconciliation/productionAnomaly'
import type {
  ProductionAnomalyVO,
  CreateProductionAnomalyParams,
  LiabilityParams,
  ReShipmentParams,
  DeductionParams,
  NegotiationParams,
} from '@/types/reconciliation'

export const useProductionAnomalyStore = defineStore('productionAnomaly', () => {
  // 列表状态
  const list = ref<ProductionAnomalyVO[]>([])
  const total = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)
  const currentPage = ref(1)
  const pageSize = 20
  const hasMore = computed(() => list.value.length < total.value)

  // 当前详情
  const currentDetail = ref<ProductionAnomalyVO | null>(null)

  // 列表操作
  async function fetchList(refresh = false) {
    if (refresh) {
      currentPage.value = 1
    }
    loading.value = refresh || !list.value.length
    loadingMore.value = !refresh && currentPage.value > 1

    try {
      const res = await getProductionAnomalyList({
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
      currentDetail.value = await getProductionAnomalyDetail(id)
    } finally {
      loading.value = false
    }
  }

  // 创建生产异常
  async function create(params: CreateProductionAnomalyParams) {
    return await createProductionAnomaly(params)
  }

  // 责任判定
  async function setLiability(id: number, params: LiabilityParams) {
    await setLiabilityApi(id, params)
    await fetchDetail(id)
  }

  // 创建补发
  async function createReShipment(id: number, params: ReShipmentParams) {
    await createReShipmentApi(id, params)
    await fetchDetail(id)
  }

  // 创建扣款
  async function createDeduction(id: number, params: DeductionParams) {
    await createDeductionApi(id, params)
    await fetchDetail(id)
  }

  // 记录协商
  async function addNegotiation(id: number, params: NegotiationParams) {
    await addNegotiationApi(id, params)
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
    fetchList, loadMore, fetchDetail,
    create, setLiability, createReShipment, createDeduction, addNegotiation,
    $reset,
  }
})
