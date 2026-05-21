// src/api/reconciliation/productionAnomaly.ts
import request from '@/utils/request'
import type {
  ProductionAnomalyVO,
  PageResult,
  CreateProductionAnomalyParams,
  LiabilityParams,
  ReShipmentParams,
  DeductionParams,
  NegotiationParams,
} from '@/types/reconciliation'

/** 生产异常列表 */
export function getProductionAnomalyList(params: { page: number; page_size: number }) {
  return request({
    url: '/entrust/production-anomaly/list',
    method: 'get',
    params,
  }) as Promise<PageResult<ProductionAnomalyVO>>
}

/** 生产异常详情 */
export function getProductionAnomalyDetail(id: number) {
  return request({
    url: `/entrust/production-anomaly/${id}`,
    method: 'get',
  }) as Promise<ProductionAnomalyVO>
}

/** 创建生产异常 */
export function createProductionAnomaly(data: CreateProductionAnomalyParams) {
  return request({
    url: '/entrust/production-anomaly/',
    method: 'post',
    data,
  }) as Promise<{ id: number }>
}

/** 责任判定 */
export function setLiability(id: number, data: LiabilityParams) {
  return request({
    url: `/entrust/production-anomaly/${id}/liability`,
    method: 'put',
    data,
  }) as Promise<void>
}

/** 创建补发 */
export function createReShipment(id: number, data: ReShipmentParams) {
  return request({
    url: `/entrust/production-anomaly/${id}/re-shipment`,
    method: 'post',
    data,
  }) as Promise<void>
}

/** 创建扣款 */
export function createDeduction(id: number, data: DeductionParams) {
  return request({
    url: `/entrust/production-anomaly/${id}/deduction`,
    method: 'post',
    data,
  }) as Promise<void>
}

/** 记录协商 */
export function addNegotiation(id: number, data: NegotiationParams) {
  return request({
    url: `/entrust/production-anomaly/${id}/negotiation`,
    method: 'post',
    data,
  }) as Promise<void>
}
