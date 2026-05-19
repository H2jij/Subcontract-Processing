import request from '@/utils/request'

// 查询询价单列表
export function listInquiry(query) {
  return request({
    url: '/entrust/inquiry/list',
    method: 'get',
    params: query
  })
}

// 查询询价单详情
export function getInquiry(inquiryId) {
  return request({
    url: '/entrust/inquiry/' + inquiryId,
    method: 'get'
  })
}

// 创建询价单
export function addInquiry(data) {
  return request({
    url: '/entrust/inquiry',
    method: 'post',
    data: data
  })
}

// 发送询价邀请
export function sendInquiry(inquiryId, supplierIds) {
  return request({
    url: '/entrust/inquiry/' + inquiryId + '/send',
    method: 'post',
    data: { supplier_ids: supplierIds }
  })
}

// 获取询价邀请列表（含报价）
export function getInvitations(inquiryId) {
  return request({
    url: '/entrust/inquiry/' + inquiryId + '/invitations',
    method: 'get'
  })
}

// 加工方保存报价草稿
export function saveDraftQuote(invitationId, data) {
  return request({
    url: '/entrust/inquiry/invitation/' + invitationId + '/save-draft',
    method: 'post',
    data: data
  })
}

// 加工方提交报价
export function submitQuote(invitationId, data) {
  return request({
    url: '/entrust/inquiry/invitation/' + invitationId + '/quote',
    method: 'post',
    data: data
  })
}

// 加工方拒绝询价
export function declineInvitation(invitationId, data) {
  return request({
    url: '/entrust/inquiry/invitation/' + invitationId + '/decline',
    method: 'post',
    data: data
  })
}

// 删除询价单
export function deleteInquiry(inquiryId) {
  return request({
    url: '/entrust/inquiry/' + inquiryId,
    method: 'delete'
  })
}

// 选标
export function awardInquiry(inquiryId, quotationId) {
  return request({
    url: '/entrust/inquiry/' + inquiryId + '/award/' + quotationId,
    method: 'post'
  })
}

// 加工方查看收到的询价邀请
export function getMyInvitations(params) {
  return request({
    url: '/entrust/inquiry/my-invitations',
    method: 'get',
    params: params
  })
}

// 按项目分组的询价汇总列表
export function getGroupedInquiryList(params) {
  return request({
    url: '/entrust/inquiry/grouped-list',
    method: 'get',
    params: params
  })
}
