// src/api/reconciliation/virtualInbound.ts
import request from '@/utils/request'
import type {
  VirtualInboundVO,
  PageResult,
  VirtualInboundFilterParams,
  CreateVirtualInboundParams,
  UpdateVirtualInboundParams,
} from '@/types/reconciliation'

/** 虚拟入库列表 */
export function getVirtualInboundList(params: VirtualInboundFilterParams) {
  return request({
    url: '/entrust/virtual-inbound/list',
    method: 'get',
    params,
  }) as Promise<PageResult<VirtualInboundVO>>
}

/** 虚拟入库详情 */
export function getVirtualInboundDetail(id: number) {
  return request({
    url: `/entrust/virtual-inbound/${id}`,
    method: 'get',
  }) as Promise<VirtualInboundVO>
}

/** 创建虚拟入库 */
export function createVirtualInbound(data: CreateVirtualInboundParams) {
  return request({
    url: '/entrust/virtual-inbound/',
    method: 'post',
    data,
  }) as Promise<{ id: number }>
}

/** 修改虚拟入库 */
export function updateVirtualInbound(id: number, data: UpdateVirtualInboundParams) {
  return request({
    url: `/entrust/virtual-inbound/${id}`,
    method: 'put',
    data,
  }) as Promise<void>
}

/** 删除虚拟入库 */
export function deleteVirtualInbound(id: number) {
  return request({
    url: `/entrust/virtual-inbound/${id}`,
    method: 'delete',
  }) as Promise<void>
}

/** 按工单查询 */
export function getVirtualInboundByOrder(orderId: number) {
  return request({
    url: `/entrust/virtual-inbound/by-order/${orderId}`,
    method: 'get',
  }) as Promise<VirtualInboundVO[]>
}
