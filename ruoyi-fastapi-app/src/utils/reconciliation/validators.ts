/** 验证必填字段（非空、非纯空白） */
export function validateRequired(value: any): boolean {
  if (value == null) return false
  if (typeof value === 'string') return value.trim().length > 0
  return true
}

/** 验证金额字段（正数，最多2位小数） */
export function validateAmount(value: any): boolean {
  if (value == null || value === '') return false
  const num = Number(value)
  if (isNaN(num) || num <= 0) return false
  const parts = String(value).split('.')
  return parts.length <= 2 && (!parts[1] || parts[1].length <= 2)
}

/** 验证数量字段（正整数） */
export function validateQuantity(value: any): boolean {
  if (value == null || value === '') return false
  const num = Number(value)
  return Number.isInteger(num) && num > 0
}

/** 验证付款金额（正数且不超过剩余应付） */
export function validatePaymentAmount(value: any, remaining: number): boolean {
  if (!validateAmount(value)) return false
  return Number(value) <= remaining
}

/** 验证文件上传（类型+大小） */
export function validateFileUpload(
  fileName: string,
  fileSize: number,
  maxSize = 10 * 1024 * 1024
): { valid: boolean; error?: string } {
  const ext = fileName.split('.').pop()?.toLowerCase()
  const allowedExts = ['jpg', 'jpeg', 'png', 'pdf']
  if (!ext || !allowedExts.includes(ext)) {
    return { valid: false, error: `仅支持 ${allowedExts.join('/')} 格式` }
  }
  if (fileSize > maxSize) {
    return { valid: false, error: '文件大小不能超过 10MB' }
  }
  return { valid: true }
}
