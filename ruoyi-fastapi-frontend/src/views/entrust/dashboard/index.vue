<template>
   <div class="app-container">
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
               <div class="stat-num">{{ stats.confirmedCount }}</div>
               <div class="stat-label">已审批</div>
            </el-card>
         </el-col>
         <el-col :span="6">
            <el-card shadow="hover" class="stat-card stat-success">
               <div class="stat-num">{{ stats.completedCount }}</div>
               <div class="stat-label">已完成</div>
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
</template>

<script setup name="Dashboard">
import { ref, onMounted } from 'vue'
import { listProject } from '@/api/entrust/project'

const stats = ref({
   projectCount: 0,
   pendingApproval: 0,
   confirmedCount: 0,
   completedCount: 0,
})
const pendingProjects = ref([])
const recentProjects = ref([])

function loadDashboard() {
   // 获取所有项目统计
   listProject({ page_num: 1, page_size: 100 }).then(res => {
      const rows = res.rows || []
      stats.value.projectCount = res.total || rows.length
      stats.value.pendingApproval = rows.filter(r => r.status === 'pending_approval').length
      stats.value.confirmedCount = rows.filter(r => r.status === 'confirmed').length
      stats.value.completedCount = rows.filter(r => r.status === 'completed').length

      // 待审批列表
      pendingProjects.value = rows.filter(r => r.status === 'pending_approval').slice(0, 5)

      // 最近项目
      recentProjects.value = rows.slice(0, 8)
   })
}

onMounted(() => {
   loadDashboard()
})
</script>

<style scoped>
.mb16 { margin-bottom: 16px; }
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
