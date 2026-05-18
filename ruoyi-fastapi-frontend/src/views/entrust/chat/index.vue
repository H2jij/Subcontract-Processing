<template>
   <div class="chat-container" @click="hideContextMenu">
      <!-- 左侧会话列表 -->
      <div class="chat-sidebar">
         <div class="sidebar-header">
            <span style="font-weight:bold;font-size:16px">会话列表</span>
            <span v-if="wsStatus === 'disconnected'" style="color:#f56c6c;font-size:12px;margin-left:8px">已断开</span>
            <span v-else-if="wsStatus === 'connecting'" style="color:#e6a23c;font-size:12px;margin-left:8px">连接中...</span>
         </div>
         <div class="session-list">
            <div
               v-for="s in sessions"
               :key="s.id"
               :class="['session-item', { active: currentSession && currentSession.id === s.id }]"
               @click="openSession(s)"
               @contextmenu.prevent="showContextMenu($event, s)"
            >
               <div class="session-info">
                  <div class="session-name">
                     <span v-if="s.isPinned" class="pin-icon">&#128204;</span>
                     <span>{{ isProcessor ? (s.ourUserName || '我方') : (s.supplierName || '加工方') }}</span>
                     <span v-if="s.status && s.status !== 'inquiring'" class="session-status">{{ statusLabel(s.status) }}</span>
                     <span v-if="s.unread > 0" class="unread-badge">{{ s.unread > 99 ? '99+' : s.unread }}</span>
                  </div>
                  <div class="session-preview">{{ s.lastMessage || '暂无消息' }}</div>
                  <div class="session-time">{{ formatTime(s.lastMessageAt) }}</div>
               </div>
            </div>
            <div v-if="!sessions.length" style="text-align:center;color:#999;padding:40px">
               暂无会话
            </div>
         </div>
      </div>

      <!-- Right-click context menu -->
      <div
         v-if="contextMenu.visible"
         class="context-menu"
         :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      >
         <div class="context-menu-item" @click.stop="handlePin">
            {{ contextMenu.session?.isPinned ? '取消置顶' : '置顶会话' }}
         </div>
         <div class="context-menu-item" @click.stop="handleClear">清空聊天记录</div>
         <div class="context-menu-item danger" @click.stop="handleDelete">删除会话</div>
      </div>

      <!-- 右侧聊天窗口 -->
      <div class="chat-main">
         <template v-if="currentSession || pendingSupplierId">
            <div class="chat-header">
               <span style="font-weight:bold">
                  {{ chatTargetName }}
               </span>
            </div>
            <div class="chat-messages" ref="messagesRef">
               <div
                  v-for="msg in messages"
                  :key="msg.id"
                  :class="['message-row', msg.senderType === mySenderType ? 'message-right' : 'message-left']"
               >
                  <div class="message-bubble">
                     <!-- text -->
                     <div v-if="!msg.messageType || msg.messageType === 'text'" class="message-content">{{ msg.content }}</div>
                     <!-- quotation card -->
                     <div v-else-if="msg.messageType === 'quotation'" class="message-card quotation">
                        <div class="card-title">报价信息</div>
                        <div>单价：¥{{ msg.extraData?.unitPrice }}</div>
                        <div>交期：{{ msg.extraData?.leadTimeDays }} 天</div>
                        <div v-if="msg.content" class="card-note">{{ msg.content }}</div>
                     </div>
                     <!-- inquiry card -->
                     <div v-else-if="msg.messageType === 'inquiry'" class="message-card inquiry">
                        <div class="card-title">询价信息</div>
                        <div v-if="msg.extraData?.title">{{ msg.extraData.title }}</div>
                        <div v-if="msg.content" class="card-note">{{ msg.content }}</div>
                     </div>
                     <!-- file card -->
                     <div v-else-if="msg.messageType === 'file'" class="message-card file">
                        <span>{{ msg.content }}</span>
                        <a v-if="msg.extraData?.fileUrl" :href="baseURL + msg.extraData.fileUrl" target="_blank" class="file-download">下载</a>
                     </div>
                     <div class="message-time">{{ formatTime(msg.createdAt) }}</div>
                  </div>
               </div>
               <div v-if="!messages.length" style="text-align:center;color:#999;padding:40px">
                  发送第一条消息开始对话
               </div>
            </div>
            <div class="chat-input">
               <el-input
                  v-model="inputText"
                  type="textarea"
                  :rows="2"
                  placeholder="输入消息，Enter 发送，Shift+Enter 换行"
                  resize="none"
                  @keydown="handleKeydown"
               />
               <el-button type="primary" @click="sendMessage" :disabled="!inputText.trim() || (!currentSession && !pendingSupplierId)" style="margin-left:12px;height:100%">
                  发送
               </el-button>
            </div>
         </template>
         <div v-else style="display:flex;align-items:center;justify-content:center;height:100%;color:#999">
            选择一个会话开始聊天
         </div>
      </div>
   </div>
</template>

<script setup name="Chat">
import { ref, computed, onMounted, onUnmounted, onActivated, onDeactivated, nextTick, watch, reactive } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import useUserStore from '@/store/modules/user'
import useChatStore from '@/store/modules/chat'
import { getChatSessions, getChatMessages, createChatSession, deleteChatSession, clearChatMessages, toggleChatPin, markChatRead } from '@/api/entrust/chat'
import { getSupplier } from '@/api/entrust/supplier'
import chatWS from '@/utils/chatWebSocket'

const route = useRoute()
const userStore = useUserStore()
const chatStore = useChatStore()

const sessions = ref([])
const currentSession = ref(null)
const messages = ref([])
const inputText = ref('')
const messagesRef = ref(null)
const wsStatus = ref('disconnected')
const pendingSupplierId = ref(null)
const pendingSupplierName = ref('')

// Context menu state
const contextMenu = reactive({
   visible: false,
   x: 0,
   y: 0,
   session: null,
})

function showContextMenu(e, session) {
   contextMenu.visible = true
   contextMenu.x = e.clientX
   contextMenu.y = e.clientY
   contextMenu.session = session
}

function hideContextMenu() {
   contextMenu.visible = false
}

async function handlePin() {
   hideContextMenu()
   const s = contextMenu.session
   if (!s) return
   try {
      const res = await toggleChatPin(s.id)
      if (res.code === 200) {
         ElMessage.success(res.data ? '已置顶' : '已取消置顶')
         await loadSessions()
      }
   } catch (e) { /* ignore */ }
}

async function handleClear() {
   hideContextMenu()
   const s = contextMenu.session
   if (!s) return
   try {
      await ElMessageBox.confirm('确定清空该会话的所有聊天记录？此操作不可恢复。', '清空聊天记录', {
         confirmButtonText: '确定',
         cancelButtonText: '取消',
         type: 'warning',
      })
      const res = await clearChatMessages(s.id)
      if (res.code === 200) {
         ElMessage.success('聊天记录已清空')
         // If viewing this session, clear local messages too
         if (currentSession.value && currentSession.value.id === s.id) {
            messages.value = []
         }
         await loadSessions()
      }
   } catch (e) {
      // User cancelled or error
   }
}

async function handleDelete() {
   hideContextMenu()
   const s = contextMenu.session
   if (!s) return
   try {
      await ElMessageBox.confirm('确定删除该会话？删除后将从列表中移除。', '删除会话', {
         confirmButtonText: '确定',
         cancelButtonText: '取消',
         type: 'warning',
      })
      const res = await deleteChatSession(s.id)
      if (res.code === 200) {
         ElMessage.success('会话已删除')
         // If viewing this session, clear it
         if (currentSession.value && currentSession.value.id === s.id) {
            currentSession.value = null
            messages.value = []
         }
         await loadSessions()
      }
   } catch (e) {
      // User cancelled or error
   }
}

const baseURL = import.meta.env.VITE_APP_BASE_API

const isProcessor = computed(() => (userStore.roles || []).includes('processor'))
const mySenderType = computed(() => isProcessor.value ? 'supplier' : 'our')

const chatTargetName = computed(() => {
   if (currentSession.value) {
      return isProcessor.value
         ? (currentSession.value.ourUserName || '我方联系人')
         : (currentSession.value.supplierName || '加工方')
   }
   return pendingSupplierName.value || '加工方'
})

// Watch supplier_id query param changes (switching suppliers without remounting)
watch(() => route.query.supplier_id, async (newSid) => {
   if (!newSid || isProcessor.value) return
   const supplierId = Number(newSid)
   // Check if already viewing this supplier
   if (currentSession.value && currentSession.value.supplierId === supplierId) return
   if (pendingSupplierId.value === supplierId) return

   // Reset state for new supplier
   const found = sessions.value.find(s => s.supplierId === supplierId)
   if (found) {
      await openSession(found)
      pendingSupplierId.value = null
      pendingSupplierName.value = ''
   } else {
      currentSession.value = null
      messages.value = []
      pendingSupplierId.value = supplierId
      try {
         const res = await getSupplier(supplierId)
         if (res.code === 200 && res.data) {
            pendingSupplierName.value = res.data.name || '加工方'
         }
      } catch (e) { /* ignore */ }
   }
})

// Watch our_user_id query param (processor navigating from quotation page)
watch(() => route.query.our_user_id, async (newUid) => {
   if (!newUid || !isProcessor.value) return
   const ourUserId = Number(newUid)
   // Find session with this our_user_id
   const found = sessions.value.find(s => s.ourUserId === ourUserId)
   if (found) {
      await openSession(found)
   }
   // If not found, the processor doesn't have a session with this buyer yet
   // They'll need to wait for the buyer to initiate or create one manually
})

// Status label mapping
function statusLabel(status) {
   const map = {
      inquiring: '询价中',
      quoted: '已报价',
      negotiating: '协商中',
      confirmed: '已确认',
      completed: '已完成',
   }
   return map[status] || status
}

// Load session list
async function loadSessions() {
   try {
      const res = await getChatSessions()
      if (res.code === 200) {
         sessions.value = res.data || []
         // Sync global unread count for sidebar badge
         const total = sessions.value.reduce((sum, s) => sum + (s.unread || 0), 0)
         chatStore.setTotalUnread(total)
         if (total === 0) stopTitleFlash()
      }
   } catch (e) { /* ignore */ }
}

// Open a session
async function openSession(s) {
   currentSession.value = s
   pendingSupplierId.value = null
   // Mark as read
   if (s.unread > 0) {
      s.unread = 0
      markChatRead(s.id).catch(() => {})
   }
   await loadMessages()
}

// Load messages (initial / history)
async function loadMessages() {
   if (!currentSession.value) return
   try {
      const res = await getChatMessages(currentSession.value.id)
      if (res.code === 200) {
         messages.value = res.data || []
         await nextTick()
         scrollToBottom()
      }
   } catch (e) { /* ignore */ }
}

// Incremental pull: fetch messages after the last known id (for reconnect)
async function pullIncrementalMessages() {
   if (!currentSession.value) return
   const LIMIT = 100
   let lastId = messages.value.length ? messages.value[messages.value.length - 1].id : 0
   let hasMore = true

   while (hasMore) {
      try {
         const res = await getChatMessages(currentSession.value.id, { after_id: lastId, limit: LIMIT })
         if (res.code === 200 && res.data?.length) {
            messages.value.push(...res.data)
            lastId = res.data[res.data.length - 1].id
            hasMore = res.data.length === LIMIT
         } else {
            hasMore = false
         }
      } catch (e) {
         hasMore = false
      }
   }
   await nextTick()
   scrollToBottom()
}

// Send message via WebSocket
async function sendMessage() {
   const text = inputText.value.trim()
   if (!text) return

   // Check WebSocket connection
   if (wsStatus.value !== 'connected') {
      ElMessage.warning('连接中，请稍候发送')
      return
   }

   // If no session yet (pending state), create one first via REST
   if (!currentSession.value) {
      if (!pendingSupplierId.value) return
      try {
         const res = await createChatSession(pendingSupplierId.value)
         if (res.code === 200 && res.data) {
            // Refresh sessions and find the new one
            await loadSessions()
            const found = sessions.value.find(s => s.supplierId === pendingSupplierId.value)
            if (found) {
               currentSession.value = found
               pendingSupplierId.value = null
            } else {
               return
            }
         } else {
            return
         }
      } catch (e) {
         console.error('创建会话失败', e)
         return
      }
   }

   // Optimistically add our message to the array
   messages.value.push({
      id: 'temp_' + Date.now(),
      sessionId: currentSession.value.id,
      senderType: mySenderType.value,
      content: text,
      messageType: 'text',
      createdAt: new Date().toISOString(),
   })
   nextTick(() => scrollToBottom())

   chatWS.sendMessage({
      session_id: currentSession.value.id,
      content: text,
      message_type: 'text',
   })
   inputText.value = ''

   // Refresh session list to update last message
   loadSessions()
}

// Keyboard shortcut: Enter to send, Shift+Enter for newline
function handleKeydown(e) {
   if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
   }
}

// Scroll to bottom
function scrollToBottom() {
   if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
   }
}

// Time formatting
function formatTime(dt) {
   if (!dt) return ''
   const d = new Date(dt)
   const now = new Date()
   const pad = n => String(n).padStart(2, '0')
   const time = pad(d.getHours()) + ':' + pad(d.getMinutes())

   if (d.toDateString() === now.toDateString()) return time
   const yesterday = new Date(now)
   yesterday.setDate(yesterday.getDate() - 1)
   if (d.toDateString() === yesterday.toDateString()) return '昨天 ' + time
   return (d.getMonth() + 1) + '/' + d.getDate() + ' ' + time
}

// ---- WebSocket event handlers ----

function onNewMessage(msg) {
   if (!msg) return

   // Only add messages from the other person (our own are shown optimistically)
   if (currentSession.value && msg.sessionId === currentSession.value.id) {
      if (msg.senderType !== mySenderType.value) {
         if (!messages.value.find(m => m.id === msg.id)) {
            messages.value.push(msg)
            nextTick(() => scrollToBottom())
         }
         // Auto mark as read when viewing this session
         markChatRead(currentSession.value.id).catch(() => {})
      }
   } else if (msg.senderType !== mySenderType.value) {
      // Message for another session — browser notification
      showNotification(msg)
   }

   // Refresh session list to update last message / status / unread
   loadSessions()
}

// Browser notification & title flash
let _titleFlashTimer = null
const _originalTitle = document.title

function showNotification(msg) {
   // Title flash
   if (!_titleFlashTimer) {
      let toggle = false
      _titleFlashTimer = setInterval(() => {
         document.title = toggle ? `[新消息] ${_originalTitle}` : _originalTitle
         toggle = !toggle
      }, 800)
      // Stop flashing after 10s
      setTimeout(() => {
         clearInterval(_titleFlashTimer)
         _titleFlashTimer = null
         document.title = _originalTitle
      }, 10000)
   }

   // Browser Notification API
   if (Notification.permission === 'granted') {
      const sender = msg.senderName || '用户'
      const text = msg.messageType === 'text' ? msg.content : `[${msg.messageType}]`
      new Notification(`${sender} 发来新消息`, { body: text, tag: 'chat-msg' })
   } else if (Notification.permission !== 'denied') {
      Notification.requestPermission()
   }
}

function stopTitleFlash() {
   if (_titleFlashTimer) {
      clearInterval(_titleFlashTimer)
      _titleFlashTimer = null
      document.title = _originalTitle
   }
}

function onConnected() {
   wsStatus.value = 'connected'
   // Refresh session list
   loadSessions().then(() => {
      // If we have a current session, pull incremental messages
      if (currentSession.value) {
         pullIncrementalMessages()
      }
   })
}

function onAuthFailed() {
   wsStatus.value = 'disconnected'
   ElMessage.error('WebSocket认证失败，请重新登录')
}

function onReconnectFailed() {
   wsStatus.value = 'disconnected'
   ElMessage.warning('WebSocket连接已断开，请刷新页面重试')
}

// ---- Lifecycle ----

const isFirstMount = ref(true)

function registerWSHandlers() {
   chatWS.on('new_message', onNewMessage)
   chatWS.on('connected', onConnected)
   chatWS.on('auth_failed', onAuthFailed)
   chatWS.on('reconnect_failed', onReconnectFailed)
}

function unregisterWSHandlers() {
   chatWS.off('new_message', onNewMessage)
   chatWS.off('connected', onConnected)
   chatWS.off('auth_failed', onAuthFailed)
   chatWS.off('reconnect_failed', onReconnectFailed)
}

function connectWS() {
   const token = userStore.token
   if (token) {
      wsStatus.value = 'connecting'
      chatWS.connect(token)
   }
}

onMounted(async () => {
   const sid = route.query.supplier_id
   const ouid = route.query.our_user_id

   // Load session list first
   await loadSessions()

   if (sid && !isProcessor.value) {
      const supplierId = Number(sid)
      const found = sessions.value.find(s => s.supplierId === supplierId)
      if (found) {
         await openSession(found)
      } else {
         pendingSupplierId.value = supplierId
         try {
            const res = await getSupplier(supplierId)
            if (res.code === 200 && res.data) {
               pendingSupplierName.value = res.data.name || '加工方'
            }
         } catch (e) { /* ignore */ }
      }
   } else if (ouid && isProcessor.value) {
      // Processor navigating from quotation page — auto-connect to buyer
      const ourUserId = Number(ouid)
      const found = sessions.value.find(s => s.ourUserId === ourUserId)
      if (found) {
         await openSession(found)
      }
   }
})

// keep-alive: activated on first mount AND every subsequent revisit
onActivated(() => {
   if (isFirstMount.value) {
      isFirstMount.value = false
   } else {
      loadSessions()
   }
   registerWSHandlers()
   connectWS()
})

// keep-alive: deactivated when navigating away
onDeactivated(() => {
   unregisterWSHandlers()
   chatWS.disconnect()
   wsStatus.value = 'disconnected'
})

onUnmounted(() => {
   unregisterWSHandlers()
   chatWS.disconnect()
   wsStatus.value = 'disconnected'
})
</script>

<style scoped>
.chat-container {
   display: flex;
   height: calc(100vh - 140px);
   background: #fff;
   border-radius: 4px;
}

.chat-sidebar {
   width: 280px;
   border-right: 1px solid #e4e7ed;
   display: flex;
   flex-direction: column;
}

.sidebar-header {
   padding: 16px;
   border-bottom: 1px solid #e4e7ed;
   display: flex;
   align-items: center;
}

.session-list {
   flex: 1;
   overflow-y: auto;
}

.session-item {
   padding: 12px 16px;
   cursor: pointer;
   border-bottom: 1px solid #f2f3f5;
   transition: background 0.2s;
}

.session-item:hover {
   background: #f5f7fa;
}

.session-item.active {
   background: #ecf5ff;
}

.session-name {
   font-weight: bold;
   font-size: 14px;
   display: flex;
   align-items: center;
   gap: 8px;
}

.session-status {
   font-size: 11px;
   color: #409eff;
   background: #ecf5ff;
   padding: 1px 6px;
   border-radius: 4px;
}

.session-preview {
   color: #909399;
   font-size: 12px;
   margin-top: 4px;
   white-space: nowrap;
   overflow: hidden;
   text-overflow: ellipsis;
}

.session-time {
   color: #c0c4cc;
   font-size: 11px;
   margin-top: 4px;
}

.chat-main {
   flex: 1;
   display: flex;
   flex-direction: column;
}

.chat-header {
   padding: 16px;
   border-bottom: 1px solid #e4e7ed;
   font-size: 16px;
}

.chat-messages {
   flex: 1;
   overflow-y: auto;
   padding: 16px;
}

.message-row {
   margin-bottom: 16px;
   display: flex;
}

.message-left {
   justify-content: flex-start;
}

.message-right {
   justify-content: flex-end;
}

.message-bubble {
   max-width: 60%;
   padding: 10px 14px;
   border-radius: 8px;
   word-break: break-word;
}

.message-left .message-bubble {
   background: #f4f4f5;
   color: #303133;
}

.message-right .message-bubble {
   background: #409eff;
   color: #fff;
}

.message-sender {
   font-size: 12px;
   margin-bottom: 4px;
   opacity: 0.7;
}

.message-content {
   font-size: 14px;
   line-height: 1.6;
}

.message-time {
   font-size: 11px;
   margin-top: 4px;
   opacity: 0.5;
   text-align: right;
}

.message-card {
   font-size: 14px;
   line-height: 1.6;
}

.message-card .card-title {
   font-weight: bold;
   margin-bottom: 4px;
}

.message-card.quotation {
   color: #e6a23c;
}

.message-card.quotation .card-title {
   color: #e6a23c;
}

.message-card.inquiry {
   color: #409eff;
}

.message-card.inquiry .card-title {
   color: #409eff;
}

.message-card.file {
   color: #67c23a;
}

.card-note {
   margin-top: 4px;
   font-size: 12px;
   opacity: 0.8;
}

.file-download {
   margin-left: 8px;
   color: inherit;
   text-decoration: underline;
}

.chat-input {
   padding: 12px 16px;
   border-top: 1px solid #e4e7ed;
   display: flex;
   align-items: stretch;
}

.context-menu {
   position: fixed;
   z-index: 9999;
   background: #fff;
   border: 1px solid #e4e7ed;
   border-radius: 4px;
   box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
   padding: 4px 0;
   min-width: 140px;
}

.context-menu-item {
   padding: 8px 16px;
   cursor: pointer;
   font-size: 13px;
   color: #303133;
   transition: background 0.15s;
}

.context-menu-item:hover {
   background: #f5f7fa;
}

.context-menu-item.danger {
   color: #f56c6c;
}

.context-menu-item.danger:hover {
   background: #fef0f0;
}

.pin-icon {
   font-size: 12px;
}

.unread-badge {
   background: #f56c6c;
   color: #fff;
   font-size: 11px;
   font-weight: bold;
   padding: 1px 6px;
   border-radius: 10px;
   margin-left: auto;
   min-width: 18px;
   text-align: center;
}
</style>
