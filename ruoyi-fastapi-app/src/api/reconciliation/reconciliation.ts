// src/api/reconciliation/reconciliation.ts
import request from '@/utils/request'
import type {
  ReconciliationStatementVO,
  VarianceSummaryVO,
  PageResult,
  StatementFilterParams,
  GenerateStatementParams,
} from '@/types/reconciliation'

/** 对账单列表（分页+筛选） */
export function getStatementList(params: StatementFilterParams) {
  return request({
    url: '/entrust/reconciliation/list',
    method: 'get',
    params,
  }) as Promise<PageResult<ReconciliationStatementVO>>
}

/** 对账单详情 */
export function getStatementDetail(id: number) {
  return request({
    url: `/entrust/reconciliation/${id}`,
    method: 'get',
  }) as Promise<ReconciliationStatementVO>
}

/** 对账单差异汇总 */
export function getVarianceSummary(id: number) {
  return request({
    url: `/entrust/reconciliation/${id}/variance-summary`,
    method: 'get',
  }) as Promise<VarianceSummaryVO>
}

/** 生成对账单 */
export function generateStatement(data: GenerateStatementParams) {
  return request({
    url: '/entrust/reconciliation/generate',
    method: 'post',
    data,
  }) as Promise<{ statement_ids: number[] }>
}

/** 重新计算差异 */
export function recalculateVariance(id: number) {
  return request({
    url: `/entrust/reconciliation/${id}/recalculate`,
    method: 'post',
  }) as Promise<void>
}

/** 发送对账通知 */
export function notifySupplier(id: number) {
  return request({
    url: `/entrust/reconciliation/${id}/notify`,
    method: 'post',
  }) as Promise<void>
}
