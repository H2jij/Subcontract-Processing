// src/api/reconciliation/payment.ts
import request from '@/utils/request'
import type {
  PaymentRequestVO,
  PaymentEvidenceVO,
  PageResult,
  CreatePaymentRecordParams,
} from '@/types/reconciliation'

/** 付款申请列表 */
export function getPaymentRequests(params: { page: number; page_size: number }) {
  return request({
    url: '/entrust/payment/requests',
    method: 'get',
    params,
  }) as Promise<PageResult<PaymentRequestVO>>
}

/** 付款申请详情 */
export function getPaymentRequestDetail(id: number) {
  return request({
    url: `/entrust/payment/requests/${id}`,
    method: 'get',
  }) as Promise<PaymentRequestVO>
}

/** 录入付款记录 */
export function createPaymentRecord(requestId: number, data: CreatePaymentRecordParams) {
  return request({
    url: `/entrust/payment/requests/${requestId}/records`,
    method: 'post',
    data,
  }) as Promise<void>
}

/** 上传支付凭证 */
export function uploadEvidence(file: any) {
  return request({
    url: '/entrust/payment/evidences/upload',
    method: 'post',
    data: file,
    header: { 'Content-Type': 'multipart/form-data' },
  }) as Promise<PaymentEvidenceVO>
}

/** 删除凭证 */
export function deleteEvidence(id: number) {
  return request({
    url: `/entrust/payment/evidences/${id}`,
    method: 'delete',
  }) as Promise<void>
}
