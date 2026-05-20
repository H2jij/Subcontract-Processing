import request from '@/utils/request'

// 查询委外工单列表
export function listOrder(query) {
  return request({
    url: '/entrust/inquiry/order/list',
    method: 'get',
    params: query
  })
}
