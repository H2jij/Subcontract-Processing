// src/api/reconciliation/anomaly.ts
import request from '@/utils/request'
import type {
  AnomalyVO,
  AdjustmentVO,
  PageResult,
  AnomalyFilterParams,
  CreateAdjustmentParams,
} from '@/types/reconciliation'

/** 异常记录列表 */
export function getAnomalyList(params: AnomalyFilterParams) {
  return request({
    url: '/entrust/anomaly/list',
    method: 'get',
    params,
  }) as Promise<PageResult<AnomalyVO>>
}

/** 异常详情 */
export function getAnomalyDetail(id: number) {
  return request({
    url: `/entrust/anomaly/${id}`,
    method: 'get',
  }) as Promise<AnomalyVO>
}

/** 提出金额调整 */
export function createAdjustment(id: number, data: CreateAdjustmentParams) {
  return request({
    url: `/entrust/anomaly/${id}/adjustment`,
    method: 'post',
    data,
  }) as Promise<void>
}

/** 待审批列表 */
export function getPendingApprovals(params: { page: number; page_size: number }) {
  return request({
    url: '/entrust/anomaly/adjustments/pending',
    method: 'get',
    params,
  }) as Promise<PageResult<AdjustmentVO>>
}

/** 审批通过 */
export function approveAdjustment(id: number) {
  return request({
    url: `/entrust/anomaly/adjustments/${id}/approve`,
    method: 'post',
  }) as Promise<void>
}

/** 审批驳回 */
export function rejectAdjustment(id: number, data: { reject_reason: string }) {
  return request({
    url: `/entrust/anomaly/adjustments/${id}/reject`,
    method: 'post',
    data,
  }) as Promise<void>
}
