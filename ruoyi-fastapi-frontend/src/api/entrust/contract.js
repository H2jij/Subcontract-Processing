import request from '@/utils/request'

// 获取合同发送任务列表
export function listContractTasks(query) {
  return request({ url: '/entrust/contract-tasks/list', method: 'get', params: query })
}

// 发送合同
export function sendContract(taskId, data) {
  return request({ url: `/entrust/contract-tasks/${taskId}/send`, method: 'post', data })
}

// 延迟发送
export function deferContract(taskId, data) {
  return request({ url: `/entrust/contract-tasks/${taskId}/defer`, method: 'post', data })
}

// 拒绝发送
export function rejectContract(taskId, data) {
  return request({ url: `/entrust/contract-tasks/${taskId}/reject`, method: 'post', data })
}

// 重置为待发送
export function resetContract(taskId) {
  return request({ url: `/entrust/contract-tasks/${taskId}/reset`, method: 'post' })
}

// 获取发送历史
export function getContractRecords(taskId) {
  return request({ url: `/entrust/contract-tasks/${taskId}/records`, method: 'get' })
}

// 预览/下载合同
export function previewContract(taskId) {
  return request({
    url: `/entrust/contract-tasks/${taskId}/preview`,
    method: 'get',
    responseType: 'blob'
  })
}
