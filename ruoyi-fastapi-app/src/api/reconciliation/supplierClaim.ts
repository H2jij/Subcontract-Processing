// src/api/reconciliation/supplierClaim.ts
import request from '@/utils/request'
import type {
  ReconciliationStatementVO,
  PageResult,
  DisputeParams,
} from '@/types/reconciliation'

/** 供应商对账单列表 */
export function getSupplierStatements(params: { page: number; page_size: number }) {
  return request({
    url: '/entrust/supplier-claim/statements',
    method: 'get',
    params,
  }) as Promise<PageResult<ReconciliationStatementVO>>
}

/** 供应商对账单明细 */
export function getSupplierStatementDetail(id: number) {
  return request({
    url: `/entrust/supplier-claim/statements/${id}`,
    method: 'get',
  }) as Promise<ReconciliationStatementVO>
}

/** 供应商确认 */
export function confirmStatement(id: number) {
  return request({
    url: `/entrust/supplier-claim/statements/${id}/confirm`,
    method: 'post',
  }) as Promise<void>
}

/** 供应商提出争议 */
export function disputeStatement(id: number, data: DisputeParams) {
  return request({
    url: `/entrust/supplier-claim/statements/${id}/dispute`,
    method: 'post',
    data,
  }) as Promise<void>
}
