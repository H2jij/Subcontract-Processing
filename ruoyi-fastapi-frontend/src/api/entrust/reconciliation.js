import request from '@/utils/request'

// 对账单列表
export function listStatements(query) {
  return request({ url: '/entrust/reconciliation/list', method: 'get', params: query })
}

// 对账单详情
export function getStatement(id) {
  return request({ url: `/entrust/reconciliation/${id}`, method: 'get' })
}

// 生成对账单
export function generateStatements(data) {
  return request({ url: '/entrust/reconciliation/generate', method: 'post', data })
}

// 重新计算差异
export function recalculateVariance(id) {
  return request({ url: `/entrust/reconciliation/${id}/recalculate`, method: 'post' })
}

// 仪表盘
export function getDashboard(query) {
  return request({ url: '/entrust/reconciliation-report/dashboard', method: 'get', params: query })
}

// 供应商汇总
export function getSupplierSummary(query) {
  return request({ url: '/entrust/reconciliation-report/supplier-summary', method: 'get', params: query })
}

// 异常列表
export function listAnomalies(query) {
  return request({ url: '/entrust/anomaly/list', method: 'get', params: query })
}

// 付款申请列表
export function listPaymentRequests(query) {
  return request({ url: '/entrust/payment/requests', method: 'get', params: query })
}

// 结算明细列表
export function listSettlements(query) {
  return request({ url: '/entrust/settlement/list', method: 'get', params: query })
}

// 虚拟入库列表
export function listVirtualInbounds(query) {
  return request({ url: '/entrust/virtual-inbound/list', method: 'get', params: query })
}

// 创建虚拟入库
export function createVirtualInbound(data) {
  return request({ url: '/entrust/virtual-inbound/', method: 'post', data })
}

// 生产异常列表
export function listProductionAnomalies(query) {
  return request({ url: '/entrust/production-anomaly/list', method: 'get', params: query })
}

// 账龄分析
export function getAgingAnalysis(query) {
  return request({ url: '/entrust/reconciliation-report/aging-analysis', method: 'get', params: query })
}
