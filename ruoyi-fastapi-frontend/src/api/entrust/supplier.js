import request from '@/utils/request'

// 查询加工方列表
export function listSupplier(query) {
  return request({
    url: '/entrust/supplier/list',
    method: 'get',
    params: query
  })
}

// 查询加工方详情
export function getSupplier(supplierId) {
  return request({
    url: '/entrust/supplier/' + supplierId,
    method: 'get'
  })
}

// 新增加工方
export function addSupplier(data) {
  return request({
    url: '/entrust/supplier',
    method: 'post',
    data: data
  })
}

// 修改加工方
export function updateSupplier(supplierId, data) {
  return request({
    url: '/entrust/supplier/' + supplierId,
    method: 'put',
    data: data
  })
}

// 删除加工方
export function delSupplier(supplierId) {
  return request({
    url: '/entrust/supplier/' + supplierId,
    method: 'delete'
  })
}

// 获取加工方能力标签
export function getCapabilities(supplierId) {
  return request({
    url: '/entrust/supplier/' + supplierId + '/capabilities',
    method: 'get'
  })
}

// 设置加工方能力标签
export function setCapabilities(supplierId, processNames) {
  return request({
    url: '/entrust/supplier/' + supplierId + '/capabilities',
    method: 'put',
    data: processNames
  })
}

// 获取当前登录加工方的信息
export function getCurrentSupplierProfile() {
  return request({
    url: '/entrust/supplier/current/profile',
    method: 'get'
  })
}

// 关联加工方登录账号
export function linkSupplierUser(supplierId, userId) {
  return request({
    url: '/entrust/supplier/' + supplierId + '/link-user',
    method: 'post',
    data: { user_id: userId }
  })
}
