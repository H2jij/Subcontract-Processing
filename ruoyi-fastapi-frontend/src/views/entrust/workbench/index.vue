<template>
   <div class="app-container">
      <!-- 欢迎 -->
      <div class="welcome-bar">
         <div>
            <span style="font-size:18px;font-weight:bold">{{ greeting }}，{{ userStore.nickName || userStore.name }}</span>
            <span style="color:#909399;margin-left:12px">今天有 {{ totalPending }} 项待处理</span>
         </div>
      </div>

      <!-- 统计卡片 -->
      <el-row :gutter="16" class="mb16">
         <el-col :span="4">
            <el-card shadow="hover" class="stat-card" @click="goTo('project', 'pending_approval')">
               <div class="stat-num" style="color:#E6A23C">{{ pendingApproval }}</div>
               <div class="stat-label">待审批项目</div>
            </el-card>
         </el-col>
         <el-col :span="4">
            <el-card shadow="hover" class="stat-card" @click="goTo('inquiry', 'sent')">
               <div class="stat-num" style="color:#409EFF">{{ newQuotes }}</div>
               <div class="stat-label">收到新报价</div>
            </el-card>
         </el-col>
         <el-col :span="4">
            <el-card shadow="hover" class="stat-card" @click="goTo('inquiry')">
               <div class="stat-num" style="color:#909399">{{ myInquiries }}</div>
               <div class="stat-label">我发出的询价</div>
            </el-card>
         </el-col>
         <el-col :span="4">
            <el-card shadow="hover" class="stat-card" @click="goTo('project')">
               <div class="stat-num" style="color:#67C23A">{{ myProjects }}</div>
               <div class="stat-label">我负责的项目</div>
            </el-card>
         </el-col>
         <el-col :span="4">
            <el-card shadow="hover" class="stat-card" @click="goTo('chat')">
               <div class="stat-num" style="color:#F56C6C">{{ chatSessionCount }}</div>
               <div class="stat-label">会话</div>
            </el-card>
         </el-col>
         <el-col :span="4">
            <el-card shadow="hover" class="stat-card">
               <div class="stat-num" style="color:#c0c4cc">0</div>
               <div class="stat-label">待处理异常</div>
            </el-card>
         </el-col>
      </el-row>

      <el-row :gutter="16">
         <!-- 待审批项目 -->
         <el-col :span="12">
            <el-card shadow="hover">
               <template #header>
                  <div style="display:flex;justify-content:space-between;align-items:center">
                     <span style="font-weight:bold">待审批项目</span>
                     <el-button link type="primary" @click="goTo('project', 'pending_approval')">查看全部</el-button>
                  </div>
               </template>
               <div v-if="pendingProjects.length">
                  <div v-for="p in pendingProjects" :key="p.id" class="task-item" @click="goToProject(p.id)">
                     <div class="task-title">{{ p.name }}</div>
                     <div class="task-meta">
                        <span>{{ p.customer }}</span>
                        <el-tag type="warning" size="small">待审批</el-tag>
                     </div>
                  </div>
               </div>
               <div v-else class="empty-tip">暂无待审批项目</div>
            </el-card>
         </el-col>

         <!-- 最新报价 -->
         <el-col :span="12">
            <el-card shadow="hover">
               <template #header>
                  <div style="display:flex;justify-content:space-between;align-items:center">
                     <span style="font-weight:bold">最新报价</span>
                     <el-button link type="primary" @click="goTo('inquiry')">查看全部</el-button>
                  </div>
               </template>
               <div v-if="quotedInquiries.length">
                  <div v-for="q in quotedInquiries" :key="q.id" class="task-item">
                     <div class="task-title">{{ q.title }}</div>
                     <div class="task-meta">
                        <span>{{ q.status === 'sent' ? '已发送' : q.status }}</span>
                        <el-tag v-if="q.status === 'sent'" type="success" size="small">有报价</el-tag>
                     </div>
                  </div>
               </div>
               <div v-else class="empty-tip">暂无新报价</div>
            </el-card>
         </el-col>
      </el-row>

      <el-row :gutter="16" style="margin-top:16px">
         <!-- 我负责的项目 -->
         <el-col :span="12">
            <el-card shadow="hover">
               <template #header>
                  <div style="display:flex;justify-content:space-between;align-items:center">
                     <span style="font-weight:bold">我负责的项目</span>
                     <el-button link type="primary" @click="goTo('project')">查看全部</el-button>
                  </div>
               </template>
               <div v-if="myProjectList.length">
                  <div v-for="p in myProjectList" :key="p.id" class="task-item" @click="goToProject(p.id)">
                     <div class="task-title">{{ p.name }}</div>
                     <div class="task-meta">
                        <span>{{ p.customer }}</span>
                        <el-tag :type="statusTagType(p.status)" size="small">{{ statusLabel(p.status) }}</el-tag>
                     </div>
                  </div>
               </div>
               <div v-else class="empty-tip">暂无项目</div>
            </el-card>
         </el-col>

         <!-- 最近会话 -->
         <el-col :span="12">
            <el-card shadow="hover">
               <template #header>
                  <div style="display:flex;justify-content:space-between;align-items:center">
                     <span style="font-weight:bold">最近会话</span>
                     <el-button link type="primary" @click="goTo('chat')">查看全部</el-button>
                  </div>
               </template>
               <div v-if="recentSessions.length">
                  <div v-for="s in recentSessions" :key="s.id" class="task-item" @click="goTo('chat')">
                     <div class="task-title">{{ s.supplierName || s.ourUserName || '对话' }}</div>
                     <div class="task-meta">
                        <span class="preview-text">{{ s.lastMessage }}</span>
                        <el-tag v-if="s.status" size="small" type="info">{{ s.status }}</el-tag>
                     </div>
                  </div>
               </div>
               <div v-else class="empty-tip">暂无会话</div>
            </el-card>
         </el-col>
      </el-row>
   </div>
</template>

<script setup name="Workbench">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { listProject } from '@/api/entrust/project'
import { listInquiry } from '@/api/entrust/inquiry'
import { getChatSessions } from '@/api/entrust/chat'

const router = useRouter()
const userStore = useUserStore()

const pendingApproval = ref(0)
const newQuotes = ref(0)
const myInquiries = ref(0)
const myProjects = ref(0)
const chatSessionCount = ref(0)
const pendingProjects = ref([])
const quotedInquiries = ref([])
const myProjectList = ref([])
const recentSessions = ref([])

const totalPending = computed(() => pendingApproval.value)

const greeting = computed(() => {
   const h = new Date().getHours()
   if (h < 6) return '凌晨好'
   if (h < 12) return '上午好'
   if (h < 14) return '中午好'
   if (h < 18) return '下午好'
   return '晚上好'
})

const statusMap = {
   drafted: '草稿', pending_approval: '待审批', approved: '已审批',
   confirmed: '已确认', in_progress: '进行中', completed: '已完成',
   rejected: '已驳回',
}
const statusTagMap = {
   drafted: 'info', pending_approval: 'warning', approved: 'success',
   confirmed: '', in_progress: '', completed: 'success', rejected: 'danger',
}
function statusLabel(s) { return statusMap[s] || s }
function statusTagType(s) { return statusTagMap[s] || 'info' }

function goTo(page, query) {
   const routeMap = {
      project: '/entrust/project',
      inquiry: '/entrust/inquiry',
      chat: '/entrust/chat',
   }
   const q = query ? { status: query } : {}
   router.push({ path: routeMap[page], query: q })
}

function goToProject(id) {
   router.push({ path: '/entrust/project', query: { id } })
}

onMounted(async () => {
   try {
      // pending approval projects
      const pRes = await listProject({ status: 'pending_approval', page_num: 1, page_size: 10 })
      if (pRes.code === 200) {
         pendingApproval.value = pRes.total || 0
         pendingProjects.value = (pRes.rows || []).slice(0, 5)
      }
   } catch (e) { /* ignore */ }

   try {
      // my projects (created_by = me, all statuses)
      const mpRes = await listProject({ page_num: 1, page_size: 10 })
      if (mpRes.code === 200) {
         myProjects.value = mpRes.total || 0
         myProjectList.value = (mpRes.rows || []).slice(0, 5)
      }
   } catch (e) { /* ignore */ }

   try {
      // inquiries (sent status = has quotes)
      const iRes = await listInquiry({ status: 'sent', page_num: 1, page_size: 10 })
      if (iRes.code === 200) {
         newQuotes.value = iRes.total || 0
         quotedInquiries.value = (iRes.rows || []).slice(0, 5)
      }
   } catch (e) { /* ignore */ }

   try {
      // all my inquiries
      const aiRes = await listInquiry({ page_num: 1, page_size: 1 })
      if (aiRes.code === 200) {
         myInquiries.value = aiRes.total || 0
      }
   } catch (e) { /* ignore */ }

   try {
      // chat sessions
      const sRes = await getChatSessions()
      if (sRes.code === 200) {
         const all = sRes.data || []
         chatSessionCount.value = all.length
         recentSessions.value = all.slice(0, 5)
      }
   } catch (e) { /* ignore */ }
})
</script>

<style scoped>
.mb16 { margin-bottom: 16px; }
.welcome-bar {
   display: flex; justify-content: space-between; align-items: center;
   padding: 16px 20px; background: #fff; border-radius: 4px; margin-bottom: 16px;
}
.stat-card { text-align: center; padding: 16px 0; cursor: pointer; transition: transform 0.2s; }
.stat-card:hover { transform: translateY(-2px); }
.stat-card .stat-num { font-size: 32px; font-weight: bold; }
.stat-card .stat-label { font-size: 13px; color: #909399; margin-top: 6px; }
.task-item {
   padding: 10px 0; border-bottom: 1px solid #f2f3f5; cursor: pointer;
   transition: background 0.2s;
}
.task-item:hover { background: #f5f7fa; margin: 0 -20px; padding: 10px 20px; }
.task-item:last-child { border-bottom: none; }
.task-title { font-size: 14px; font-weight: 500; color: #303133; }
.task-meta { display: flex; justify-content: space-between; align-items: center; margin-top: 4px; font-size: 12px; color: #909399; }
.preview-text { max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.empty-tip { text-align: center; color: #c0c4cc; padding: 30px 0; }
</style>
