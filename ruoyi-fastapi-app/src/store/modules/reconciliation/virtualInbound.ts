// src/store/modules/reconciliation/virtualInbound.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getVirtualInboundList,
  getVirtualInboundDetail,
  createVirtualInbound,
  updateVirtualInbound,
  deleteVirtualInbound,
  getVirtualInboundByOrder,
} from '@/api/reconciliation/virtualInbound'
import type {
  VirtualInboundVO,
  VirtualInboundFilterParams,
  CreateVirtualInboundParams,
  UpdateVirtualInboundParams,
} from '@/types/reconciliation'

export const useVirtualInboundStore = defineStore('virtualInbound', () => {
  // 列表状态
  const list = ref<VirtualInboundVO[]>([])
  const total = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)
  const currentPage = ref(1)
  const pageSize = 20
  const hasMore = computed(() => list.value.length < total.value)

  // 筛选条件
  const filters = ref<VirtualInboundFilterParams>({
    page: 1,
    page_size: pageSize,
  })

  // 当前详情
  const currentDetail = ref<VirtualInboundVO | null>(null)

  // 按工单查询结果
  const orderInbounds = ref<VirtualInboundVO[]>([])

  // 列表操作
  async function fetchList(refresh = false) {
    if (refresh) {
      currentPage.value = 1
      filters.value.page = 1
    }
    loading.value = refresh || !list.value.length
    loadingMore.value = !refresh && currentPage.value > 1

    try {
      const res = await getVirtualInboundList(filters.value)
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
      currentDetail.value = await getVirtualInboundDetail(id)
    } finally {
      loading.value = false
    }
  }

  // 创建虚拟入库
  async function create(params: CreateVirtualInboundParams) {
    return await createVirtualInbound(params)
  }

  // 修改虚拟入库
  async function update(id: number, params: UpdateVirtualInboundParams) {
    await updateVirtualInbound(id, params)
    await fetchDetail(id)
  }

  // 删除虚拟入库
  async function remove(id: number) {
    await deleteVirtualInbound(id)
  }

  // 按工单查询
  async function fetchByOrder(orderId: number) {
    orderInbounds.value = await getVirtualInboundByOrder(orderId)
  }

  // 设置筛选条件
  function setFilters(newFilters: Partial<VirtualInboundFilterParams>) {
    Object.assign(filters.value, newFilters)
  }

  function $reset() {
    list.value = []
    total.value = 0
    currentPage.value = 1
    currentDetail.value = null
    orderInbounds.value = []
  }

  return {
    list, total, loading, loadingMore, hasMore, filters,
    currentDetail, orderInbounds,
    fetchList, loadMore, fetchDetail,
    create, update, delete: remove, fetchByOrder,
    setFilters, $reset,
  }
})
