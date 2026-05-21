// src/utils/reconciliation/constants.ts

/** 差异金额 → 颜色 class 映射 */
export function getVarianceColorClass(variance: number): string {
  if (variance > 0) return 'text-red-500'
  if (variance < 0) return 'text-green-500'
  return 'text-gray-600'
}

/** 严重程度配置 */
export function getSeverityConfig(severity: string) {
  const map: Record<string, { class: string; label: string }> = {
    critical: { class: 'bg-red-100 text-red-700', label: '严重' },
    warning: { class: 'bg-orange-100 text-orange-700', label: '警告' },
    info: { class: 'bg-blue-100 text-blue-700', label: '提示' },
  }
  return map[severity] || map.info
}

/** 状态标签配置 */
export function getStatusConfig(status: string, type?: string) {
  const statementMap: Record<string, { class: string; label: string }> = {
    pending: { class: 'bg-gray-100 text-gray-600', label: '待确认' },
    confirmed: { class: 'bg-green-100 text-green-700', label: '已确认' },
    disputed: { class: 'bg-orange-100 text-orange-700', label: '有争议' },
    timeout: { class: 'bg-red-100 text-red-700', label: '已超时' },
    paid: { class: 'bg-blue-100 text-blue-700', label: '已付款' },
  }
  const settlementMap: Record<string, { class: string; label: string }> = {
    draft: { class: 'bg-gray-100 text-gray-600', label: '草稿' },
    finalized: { class: 'bg-green-100 text-green-700', label: '已确认' },
  }
  const paymentMap: Record<string, { class: string; label: string }> = {
    pending_payment: { class: 'bg-gray-100 text-gray-600', label: '待付款' },
    partially_paid: { class: 'bg-orange-100 text-orange-700', label: '部分付款' },
    paid: { class: 'bg-green-100 text-green-700', label: '已付清' },
  }

  if (type === 'settlement') return settlementMap[status] || settlementMap.draft
  if (type === 'payment') return paymentMap[status] || paymentMap.pending_payment
  return statementMap[status] || statementMap.pending
}

/** 角色 → 可见模块映射 */
export const ROLE_MODULE_MAP: Record<string, string[]> = {
  financial: [
    'statement', 'supplier-claim', 'anomaly', 'payment',
    'settlement', 'virtual-inbound', 'production-anomaly', 'report',
  ],
  supplier: ['supplier-claim'],
  business: ['virtual-inbound', 'production-anomaly'],
}

/** 入库类型标签 */
export const INBOUND_TYPE_LABELS: Record<string, string> = {
  re_shipment_in: '补发入库',
  anomaly_deduction: '异常扣除',
}

/** 责任方标签 */
export const RESPONSIBLE_PARTY_LABELS: Record<string, string> = {
  material_supplier: '材料供应商',
  processor: '加工方',
}

/** 生产异常类型标签 */
export const PRODUCTION_ANOMALY_TYPE_LABELS: Record<string, string> = {
  material_damage: '材料损坏',
  process_error: '加工错误',
  unusable: '不可用',
}

/** 账龄分桶计算 */
export function getAgingBucket(daysSinceCreation: number): '0-30' | '31-60' | '61-90' | '90+' {
  if (daysSinceCreation <= 30) return '0-30'
  if (daysSinceCreation <= 60) return '31-60'
  if (daysSinceCreation <= 90) return '61-90'
  return '90+'
}

/** 错误码 → 中文消息映射 */
export const ERROR_CODE_MESSAGES: Record<number, string> = {
  400: '请求参数错误',
  401: '登录已过期，请重新登录',
  403: '权限不足，无法执行此操作',
  404: '请求的资源不存在',
  409: '操作冲突，当前状态不允许此操作',
  422: '数据验证失败',
  429: '请求过于频繁，请稍后再试',
  500: '服务器内部错误，请稍后重试',
}
