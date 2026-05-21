import request from '@/utils/request'

// 查询项目列表
export function listProject(query) {
  return request({
    url: '/entrust/project/list',
    method: 'get',
    params: query
  })
}

// 查询项目详情
export function getProject(projectId) {
  return request({
    url: '/entrust/project/' + projectId,
    method: 'get'
  })
}

// 新增项目
export function addProject(data) {
  return request({
    url: '/entrust/project',
    method: 'post',
    data: data
  })
}

// 修改项目
export function updateProject(projectId, data) {
  return request({
    url: '/entrust/project/' + projectId,
    method: 'put',
    data: data
  })
}

// 删除项目
export function delProject(projectId) {
  return request({
    url: '/entrust/project/' + projectId,
    method: 'delete'
  })
}

// 获取模具套列表
export function listMold(projectId) {
  return request({
    url: '/entrust/project/' + projectId + '/molds',
    method: 'get'
  })
}

// 创建模具套
export function addMold(projectId, data) {
  return request({
    url: '/entrust/project/' + projectId + '/molds',
    method: 'post',
    data: data
  })
}

// 获取零件列表
export function listPart(projectId) {
  return request({
    url: '/entrust/project/' + projectId + '/parts',
    method: 'get'
  })
}

// 创建零件
export function addPart(projectId, data) {
  return request({
    url: '/entrust/project/' + projectId + '/parts',
    method: 'post',
    data: data
  })
}

// 更新零件
export function updatePart(partId, data) {
  return request({
    url: '/entrust/project/parts/' + partId,
    method: 'put',
    data: data
  })
}

// 删除零件
export function delPart(partId) {
  return request({
    url: '/entrust/project/parts/' + partId,
    method: 'delete'
  })
}

// 删除模具套
export function delMold(moldId) {
  return request({
    url: '/entrust/project/molds/' + moldId,
    method: 'delete'
  })
}

// 获取工艺方法列表
export function listProcessMethods() {
  return request({
    url: '/entrust/project/process-methods',
    method: 'get'
  })
}

// 提交项目（决策）
export function submitProject(projectId) {
  return request({
    url: '/entrust/project/' + projectId + '/submit',
    method: 'post',
    timeout: 60000
  })
}

// 审批通过项目（触发匹配）
export function approveProject(projectId) {
  return request({
    url: '/entrust/project/' + projectId + '/approve',
    method: 'post'
  })
}

// 审批驳回项目
export function rejectProject(projectId) {
  return request({
    url: '/entrust/project/' + projectId + '/reject',
    method: 'post'
  })
}

// 获取项目匹配结果
export function getMatchResult(projectId) {
  return request({
    url: '/entrust/project/' + projectId + '/match-result',
    method: 'get'
  })
}

// 批量创建询价单并发送
export function batchCreateInquiry(projectId, data) {
  return request({
    url: '/entrust/project/' + projectId + '/batch-inquiry',
    method: 'post',
    data: data
  })
}
