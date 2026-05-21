/**
 * 格式化金额为 ¥X,XXX.XX 格式
 */
export function formatAmount(value: number | null | undefined): string {
  if (value == null) return '¥0.00'
  return `¥${value.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

/**
 * 格式化日期为 YYYY-MM-DD 格式
 */
export function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return dateStr.slice(0, 10)
}

/**
 * 格式化对账周期
 */
export function formatPeriod(start: string, end: string): string {
  return `${formatDate(start)} ~ ${formatDate(end)}`
}

/**
 * 格式化日期时间为 YYYY-MM-DD HH:mm 格式
 */
export function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '-'
  return dateStr.slice(0, 16).replace('T', ' ')
}
