import request from '@/utils/request'

// 获取会话列表
export function getChatSessions() {
  return request({
    url: '/entrust/chat/sessions',
    method: 'get'
  })
}

// 创建/获取会话
export function createChatSession(supplierId) {
  return request({
    url: '/entrust/chat/sessions',
    method: 'post',
    params: { supplier_id: supplierId }
  })
}

// 获取消息列表
export function getChatMessages(sessionId, params) {
  return request({
    url: '/entrust/chat/messages/' + sessionId,
    method: 'get',
    params: params
  })
}

// 删除会话（隐藏）
export function deleteChatSession(sessionId) {
  return request({
    url: '/entrust/chat/sessions/' + sessionId,
    method: 'delete'
  })
}

// 清空聊天记录
export function clearChatMessages(sessionId) {
  return request({
    url: '/entrust/chat/messages/' + sessionId,
    method: 'delete'
  })
}

// 置顶/取消置顶
export function toggleChatPin(sessionId) {
  return request({
    url: '/entrust/chat/sessions/' + sessionId + '/pin',
    method: 'put'
  })
}

// 标记会话已读
export function markChatRead(sessionId) {
  return request({
    url: '/entrust/chat/sessions/' + sessionId + '/read',
    method: 'put'
  })
}
