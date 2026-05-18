<template>
   <div class="app-container">
      <!-- 未关联提示 -->
      <div v-if="!supplierInfo.id" style="text-align:center;padding:60px;color:#999">
         <el-icon size="48"><WarningFilled /></el-icon>
         <p style="margin-top:16px">当前账号未关联加工方信息，请联系管理员绑定</p>
      </div>

      <template v-else>
         <!-- 加工方信息 -->
         <el-card shadow="hover" class="mb16">
            <template #header>
               <span style="font-weight:bold">加工方工作台 — {{ supplierInfo.name }}</span>
            </template>
            <el-descriptions :column="3" border>
               <el-descriptions-item label="加工方名称">{{ supplierInfo.name }}</el-descriptions-item>
               <el-descriptions-item label="联系人">{{ supplierInfo.contact_name || '-' }}</el-descriptions-item>
               <el-descriptions-item label="电话">{{ supplierInfo.contact_phone || '-' }}</el-descriptions-item>
               <el-descriptions-item label="地区">{{ [supplierInfo.province, supplierInfo.city].filter(Boolean).join(' ') || '-' }}</el-descriptions-item>
               <el-descriptions-item label="地址">{{ supplierInfo.address || '-' }}</el-descriptions-item>
               <el-descriptions-item label="状态">
                  <el-tag v-if="supplierInfo.status === 'active'" type="success">正常</el-tag>
                  <el-tag v-else type="danger">停用</el-tag>
               </el-descriptions-item>
            </el-descriptions>
         </el-card>

         <!-- 统计卡片 -->
         <el-row :gutter="16" class="mb16">
            <el-col :span="6">
               <el-card shadow="hover" class="stat-card">
                  <div class="stat-num">{{ pendingInvitations }}</div>
                  <div class="stat-label">待报价</div>
               </el-card>
            </el-col>
            <el-col :span="6">
               <el-card shadow="hover" class="stat-card stat-primary">
                  <div class="stat-num">{{ quotedCount }}</div>
                  <div class="stat-label">已报价</div>
               </el-card>
            </el-col>
            <el-col :span="6">
               <el-card shadow="hover" class="stat-card stat-success">
                  <div class="stat-num">{{ stats.completedCount }}</div>
                  <div class="stat-label">已完成</div>
               </el-card>
            </el-col>
            <el-col :span="6">
               <router-link to="/entrust/chat">
                  <el-card shadow="hover" class="stat-card stat-danger" style="cursor:pointer">
                     <div class="stat-num">{{ recentSessions.length }}</div>
                     <div class="stat-label">会话</div>
                  </el-card>
               </router-link>
            </el-col>
         </el-row>

         <el-row :gutter="16">
            <!-- 待处理邀请 -->
            <el-col :span="12">
               <el-card shadow="hover">
                  <template #header>
                     <span style="font-weight:bold">待处理邀请</span>
                  </template>
                  <div v-if="pendingList.length">
                     <div v-for="inv in pendingList" :key="inv.invitation_id" class="task-item" @click="$router.push('/entrust/quotation')">
                        <div class="task-title">{{ inv.title }}</div>
                        <div class="task-meta">
                           <span>截止：{{ inv.deadline || '无' }}</span>
                           <el-tag type="warning" size="small" style="cursor:pointer">待报价 →</el-tag>
                        </div>
                     </div>
                  </div>
                  <div v-else class="empty-tip">暂无待处理邀请</div>
               </el-card>
            </el-col>

            <!-- 最近消息 -->
            <el-col :span="12">
               <el-card shadow="hover">
                  <template #header>
                     <div style="display:flex;justify-content:space-between;align-items:center">
                        <span style="font-weight:bold">最近消息</span>
                        <router-link to="/entrust/chat">
                           <el-button link type="primary">查看全部</el-button>
                        </router-link>
                     </div>
                  </template>
                  <div v-if="recentSessions.length">
                     <div v-for="s in recentSessions" :key="s.id" class="msg-item" @click="$router.push('/entrust/chat')">
                        <div class="msg-name">{{ s.ourUserName || '我方联系人' }}</div>
                        <div class="msg-preview">{{ s.lastMessage || '暂无消息' }}</div>
                     </div>
                  </div>
                  <div v-else class="empty-tip">暂无消息</div>
               </el-card>
            </el-col>
         </el-row>
      </template>
   </div>
</template>

<script setup name="Processor">
import { ref, computed, onMounted } from 'vue'
import { getCurrentSupplierProfile } from '@/api/entrust/supplier'
import { getMyInvitations } from '@/api/entrust/inquiry'
import { getChatSessions } from '@/api/entrust/chat'
import { WarningFilled } from '@element-plus/icons-vue'

const supplierInfo = ref({})
const stats = ref({
   completedCount: 0,
})
const recentSessions = ref([])
const allInvitations = ref([])

const pendingList = computed(() => allInvitations.value.filter(i => i.invitation_status === 'sent'))
const quotedList = computed(() => allInvitations.value.filter(i => i.invitation_status === 'quoted'))
const pendingInvitations = computed(() => pendingList.value.length)
const quotedCount = computed(() => quotedList.value.length)

onMounted(async () => {
   getCurrentSupplierProfile().then(res => {
      if (res.code === 200 && res.data) {
         supplierInfo.value = res.data
      }
   }).catch(() => {})

   try {
      const invRes = await getMyInvitations()
      if (invRes.code === 200) {
         allInvitations.value = invRes.data || []
      }
   } catch (e) {}

   try {
      const sRes = await getChatSessions()
      if (sRes.code === 200) {
         recentSessions.value = (sRes.data || []).slice(0, 5)
      }
   } catch (e) {}
})
</script>

<style scoped>
.mb16 { margin-bottom: 16px; }
.stat-card { text-align: center; padding: 20px 0; }
.stat-card .stat-num { font-size: 36px; font-weight: bold; color: #303133; }
.stat-card .stat-label { font-size: 14px; color: #909399; margin-top: 8px; }
.stat-card.stat-primary .stat-num { color: #409EFF; }
.stat-card.stat-success .stat-num { color: #67C23A; }
.stat-card.stat-danger .stat-num { color: #F56C6C; }
.task-item {
   padding: 10px 0; border-bottom: 1px solid #f2f3f5; cursor: pointer;
}
.task-item:hover { background: #f5f7fa; margin: 0 -20px; padding: 10px 20px; }
.task-item:last-child { border-bottom: none; }
.task-title { font-size: 14px; font-weight: 500; color: #303133; }
.task-meta { display: flex; justify-content: space-between; align-items: center; margin-top: 4px; font-size: 12px; color: #909399; }
.empty-tip { text-align: center; color: #c0c4cc; padding: 40px 0; }
.msg-item {
   padding: 10px 0; border-bottom: 1px solid #f2f3f5; cursor: pointer;
   position: relative; transition: background 0.2s;
}
.msg-item:hover { background: #f5f7fa; margin: 0 -20px; padding: 10px 20px; }
.msg-item:last-child { border-bottom: none; }
.msg-name { font-size: 14px; font-weight: 500; }
.msg-preview { font-size: 12px; color: #909399; margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.msg-badge { position: absolute; right: 0; top: 10px; }
</style>
