<template>
   <div>
   <!-- 加工方角色：首页即工作台 -->
   <ProcessorWorkbench v-if="isProcessor" />
   <!-- 其他角色：系统仪表盘 -->
   <div v-else class="app-container">
      <!-- 欢迎 -->
      <div class="welcome-bar">
         <div class="welcome-left">
            <div class="welcome-title">{{ greeting }}，{{ nickName }}</div>
            <div class="welcome-sub">委外加工管理系统</div>
         </div>
         <div class="welcome-right">
            <div class="mini-stat">
               <span class="mini-num">{{ stats.projectCount }}</span>
               <span class="mini-label">项目</span>
            </div>
            <div class="mini-stat">
               <span class="mini-num">{{ stats.supplierCount }}</span>
               <span class="mini-label">加工方</span>
            </div>
            <div class="mini-stat">
               <span class="mini-num">{{ stats.inquiryCount }}</span>
               <span class="mini-label">询价单</span>
            </div>
         </div>
      </div>

      <!-- 统计卡片 -->
      <el-row :gutter="16" class="mb16">
         <el-col :span="6">
            <el-card shadow="hover" class="stat-card">
               <div class="stat-num">{{ stats.projectCount }}</div>
               <div class="stat-label">项目总数</div>
            </el-card>
         </el-col>
         <el-col :span="6">
            <el-card shadow="hover" class="stat-card stat-warning">
               <div class="stat-num">{{ stats.pendingApproval }}</div>
               <div class="stat-label">待审批</div>
            </el-card>
         </el-col>
         <el-col :span="6">
            <el-card shadow="hover" class="stat-card stat-primary">
               <div class="stat-num">{{ stats.supplierCount }}</div>
               <div class="stat-label">加工方</div>
            </el-card>
         </el-col>
         <el-col :span="6">
            <el-card shadow="hover" class="stat-card stat-success">
               <div class="stat-num">{{ stats.inquiryCount }}</div>
               <div class="stat-label">询价单</div>
            </el-card>
         </el-col>
      </el-row>

      <el-row :gutter="16">
         <!-- 待审批项目 -->
         <el-col :span="12">
            <el-card shadow="hover">
               <template #header>
                  <span style="font-weight:bold">待审批项目</span>
                  <el-button link type="primary" style="float:right" @click="$router.push('/entrust/project')">查看全部</el-button>
               </template>
               <div v-if="pendingProjects.length === 0" style="text-align:center;color:#999;padding:20px">暂无待审批项目</div>
               <div v-for="p in pendingProjects" :key="p.id" class="list-item">
                  <div class="list-item-main">
                     <span class="list-item-title">{{ p.name }}</span>
                     <span class="list-item-sub">{{ p.customer }}</span>
                  </div>
                  <el-tag type="warning" size="small">待审批</el-tag>
               </div>
            </el-card>
         </el-col>

         <!-- 最近项目 -->
         <el-col :span="12">
            <el-card shadow="hover">
               <template #header>
                  <span style="font-weight:bold">最近项目</span>
                  <el-button link type="primary" style="float:right" @click="$router.push('/entrust/project')">查看全部</el-button>
               </template>
               <div v-if="recentProjects.length === 0" style="text-align:center;color:#999;padding:20px">暂无项目</div>
               <div v-for="p in recentProjects" :key="p.id" class="list-item">
                  <div class="list-item-main">
                     <span class="list-item-title">{{ p.name }}</span>
                     <span class="list-item-sub">{{ p.customer }} · {{ p.created_at?.substring(0, 10) }}</span>
                  </div>
                  <el-tag v-if="p.status === 'drafted'" type="info" size="small">草稿</el-tag>
                  <el-tag v-else-if="p.status === 'pending_approval'" type="warning" size="small">待审批</el-tag>
                  <el-tag v-else-if="p.status === 'confirmed'" type="success" size="small">已审批</el-tag>
                  <el-tag v-else-if="p.status === 'in_progress'" size="small">进行中</el-tag>
                  <el-tag v-else-if="p.status === 'completed'" type="success" size="small">已完成</el-tag>
               </div>
            </el-card>
         </el-col>
      </el-row>
   </div>
   </div>
</template>

<script setup>
defineOptions({ name: 'Index' })

import { ref, computed, onMounted, defineAsyncComponent } from 'vue'
import { listProject } from '@/api/entrust/project'
import { listSupplier } from '@/api/entrust/supplier'
import { listInquiry } from '@/api/entrust/inquiry'
import useUserStore from '@/store/modules/user'

// 懒加载加工方工作台组件
const ProcessorWorkbench = defineAsyncComponent(() => import('@/views/entrust/processor/index.vue'))

const userStore = useUserStore()
const isProcessor = computed(() => (userStore.roles || []).includes('processor'))
const nickName = computed(() => userStore.nickName || userStore.name || '用户')

const greeting = computed(() => {
   const h = new Date().getHours()
   if (h < 6) return '夜深了'
   if (h < 9) return '早上好'
   if (h < 12) return '上午好'
   if (h < 14) return '中午好'
   if (h < 18) return '下午好'
   return '晚上好'
})

const stats = ref({
   projectCount: 0,
   pendingApproval: 0,
   supplierCount: 0,
   inquiryCount: 0,
})
const pendingProjects = ref([])
const recentProjects = ref([])

function loadDashboard() {
   listProject({ page_num: 1, page_size: 100 }).then(res => {
      const rows = res.rows || []
      stats.value.projectCount = res.total || rows.length
      stats.value.pendingApproval = rows.filter(r => r.status === 'pending_approval').length
      pendingProjects.value = rows.filter(r => r.status === 'pending_approval').slice(0, 5)
      recentProjects.value = rows.slice(0, 8)
   })
   listSupplier({ page_num: 1, page_size: 100 }).then(res => {
      stats.value.supplierCount = res.total || 0
   })
   listInquiry({ page_num: 1, page_size: 100 }).then(res => {
      stats.value.inquiryCount = res.total || 0
   })
}

onMounted(() => {
   if (!isProcessor.value) {
      loadDashboard()
   }
})
</script>

<style scoped>
.mb16 { margin-bottom: 16px; }

.welcome-bar {
   display: flex;
   justify-content: space-between;
   align-items: center;
   padding: 20px 24px;
   margin-bottom: 16px;
   background: #fff;
   border-radius: 8px;
   box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.welcome-title { font-size: 20px; font-weight: 600; color: #303133; }
.welcome-sub { font-size: 14px; color: #909399; margin-top: 4px; }
.welcome-right { display: flex; gap: 32px; }
.mini-stat { text-align: center; }
.mini-num { display: block; font-size: 28px; font-weight: 700; color: #409EFF; }
.mini-label { font-size: 12px; color: #909399; }

.stat-card { text-align: center; padding: 20px 0; }
.stat-card .stat-num { font-size: 36px; font-weight: bold; color: #303133; }
.stat-card .stat-label { font-size: 14px; color: #909399; margin-top: 8px; }
.stat-card.stat-warning .stat-num { color: #E6A23C; }
.stat-card.stat-primary .stat-num { color: #409EFF; }
.stat-card.stat-success .stat-num { color: #67C23A; }

.list-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #EBEEF5; }
.list-item:last-child { border-bottom: none; }
.list-item-main { display: flex; flex-direction: column; }
.list-item-title { font-size: 14px; color: #303133; font-weight: 500; }
.list-item-sub { font-size: 12px; color: #909399; margin-top: 4px; }
</style>
