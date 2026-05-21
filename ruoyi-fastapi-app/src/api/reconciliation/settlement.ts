// src/api/reconciliation/settlement.ts
import request from '@/utils/request'
import type {
  SettlementDetailVO,
  PageResult,
} from '@/types/reconciliation'

/** 结算明细列表 */
export function getSettlementList(params: { page: number; page_size: number }) {
  return request({
    url: '/entrust/settlement/list',
    method: 'get',
    params,
  }) as Promise<PageResult<SettlementDetailVO>>
}

/** 结算明细详情 */
export function getSettlementDetail(id: number) {
  return request({
    url: `/entrust/settlement/${id}`,
    method: 'get',
  }) as Promise<SettlementDetailVO>
}

/** 编辑行项 */
export function updateSettlementLineItems(id: number, data: any) {
  return request({
    url: `/entrust/settlement/${id}/line-items`,
    method: 'put',
    data,
  }) as Promise<void>
}

/** 确认结算 */
export function finalizeSettlement(id: number) {
  return request({
    url: `/entrust/settlement/${id}/finalize`,
    method: 'post',
  }) as Promise<void>
}

/** 下载 PDF */
export function getSettlementPdf(id: number) {
  return request({
    url: `/entrust/settlement/${id}/pdf`,
    method: 'get',
    responseType: 'arraybuffer',
  }) as Promise<ArrayBuffer>
}

/** 差异原因明细 */
export function getVarianceDetail(id: number) {
  return request({
    url: `/entrust/settlement/${id}/variance-detail`,
    method: 'get',
  }) as Promise<any>
}
