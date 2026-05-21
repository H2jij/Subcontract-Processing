<template>
   <div class="app-container">
      <!-- 返回按钮 + 标题 -->
      <div class="page-header">
         <el-button icon="Back" @click="goBack">返回列表</el-button>
         <span class="header-title">对账单详情</span>
         <el-tag v-if="statement.status === 'pending'" type="info" size="large">待确认</el-tag>
         <el-tag v-else-if="statement.status === 'confirmed'" type="success" size="large">已确认</el-tag>
         <el-tag v-else-if="statement.status === 'disputed'" type="warning" size="large">有争议</el-tag>
         <el-tag v-else-if="statement.status === 'timeout'" type="danger" size="large">超时未确认</el-tag>
         <el-tag v-else-if="statement.status === 'paid'" size="large">已付款</el-tag>
      </div>

      <!-- 基本信息 -->
      <el-card shadow="never" class="mb16">
         <el-descriptions :column="3" border>
            <el-descriptions-item label="对账单编号">{{ statement.statement_no }}</el-descriptions-item>
            <el-descriptions-item label="供应商">{{ statement.supplier_name }}</el-descriptions-item>
            <el-descriptions-item label="对账周期">{{ statement.period_start }} ~ {{ statement.period_end }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatDateTime(statement.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="确认时间">{{ formatDateTime(statement.confirmed_at) || '-' }}</el-descriptions-item>
            <el-descriptions-item label="应付金额">
               <span style="color:#F56C6C;font-weight:bold;font-size:16px">¥{{ formatAmount(statement.total_amount) }}</span>
            </el-descriptions-item>
         </el-descriptions>
      </el-card>

      <!-- 汇总卡片 -->
      <el-row :gutter="16" class="mb16">
         <el-col :span="5">
            <el-card shadow="hover" class="summary-card">
               <div class="summary-label">订购总金额</div>
               <div class="summary-value">¥{{ formatAmount(statement.total_ordered_amount) }}</div>
            </el-card>
         </el-col>
         <el-col :span="5">
            <el-card shadow="hover" class="summary-card">
               <div class="summary-label">实际收到总价值</div>
               <div class="summary-value">¥{{ formatAmount(statement.total_received_value) }}</div>
            </el-card>
         </el-col>
         <el-col :span="5">
            <el-card shadow="hover" class="summary-card">
               <div class="summary-label">物流费用</div>
               <div class="summary-value">¥{{ formatAmount(statement.total_logistics_cost) }}</div>
            </el-card>
         </el-col>
         <el-col :span="5">
            <el-card shadow="hover" class="summary-card">
               <div class="summary-label">差异总金额</div>
               <div class="summary-value" :style="{ color: getVarianceColor(statement.total_variance) }">
                  {{ statement.total_variance > 0 ? '+' : '' }}¥{{ formatAmount(statement.total_variance) }}
               </div>
            </el-card>
         </el-col>
         <el-col :span="4">
            <el-card shadow="hover" class="summary-card">
               <div class="summary-label">货不对板数</div>
               <div class="summary-value" style="color:#F56C6C">{{ statement.mismatch_count || 0 }}</div>
            </el-card>
         </el-col>
      </el-row>

      <!-- 操作按钮 -->
      <div class="mb16">
         <el-button type="warning" icon="Refresh" :loading="recalculating" @click="handleRecalculate">重算差异</el-button>
      </div>

      <!-- 行项明细表 -->
      <el-card shadow="never">
         <template #header>
            <span style="font-weight:bold">行项明细</span>
         </template>
         <el-table
            v-loading="loading"
            :data="lineItems"
            :row-class-name="tableRowClassName"
            @row-click="handleRowClick"
            border
            style="width:100%"
         >
            <el-table-column label="委外单号" prop="order_no" min-width="140" />
            <el-table-column label="工序" prop="process_name" min-width="80" />
            <el-table-column label="零件" min-width="100" :show-overflow-tooltip="true">
               <template #default="scope">
                  {{ scope.row.part_name || scope.row.part_no || '-' }}
               </template>
            </el-table-column>
            <el-table-column label="订购金额" min-width="100" align="right">
               <template #default="scope">
                  ¥{{ formatAmount(scope.row.order_amount) }}
               </template>
            </el-table-column>
            <el-table-column label="实际交付" min-width="100" align="right">
               <template #default="scope">
                  ¥{{ formatAmount(scope.row.actual_delivered_value) }}
               </template>
            </el-table-column>
            <el-table-column label="虚拟入库" min-width="90" align="right">
               <template #default="scope">
                  <span :style="{ color: scope.row.virtual_inbound_value > 0 ? '#67C23A' : '' }">
                     ¥{{ formatAmount(scope.row.virtual_inbound_value) }}
                  </span>
               </template>
            </el-table-column>
            <el-table-column label="异常扣除" min-width="90" align="right">
               <template #default="scope">
                  <span :style="{ color: scope.row.anomaly_deduction_amount > 0 ? '#F56C6C' : '' }">
                     ¥{{ formatAmount(scope.row.anomaly_deduction_amount) }}
                  </span>
               </template>
            </el-table-column>
            <el-table-column label="差异金额" min-width="100" align="right">
               <template #default="scope">
                  <span :style="{ color: getVarianceColor(scope.row.variance), fontWeight: 'bold' }">
                     {{ scope.row.variance > 0 ? '+' : '' }}¥{{ formatAmount(scope.row.variance) }}
                  </span>
               </template>
            </el-table-column>
            <el-table-column label="货不对板" width="90" align="center" fixed="right">
               <template #default="scope">
                  <el-tag v-if="scope.row.has_mismatch" type="danger" size="small">货不对板</el-tag>
                  <span v-else>-</span>
               </template>
            </el-table-column>
         </el-table>
      </el-card>

      <!-- 差异原因展开面板 -->
      <el-dialog
         v-model="reasonDialogVisible"
         title="差异原因明细"
         width="700px"
         append-to-body
      >
         <el-descriptions :column="2" border class="mb16" v-if="currentRow">
            <el-descriptions-item label="委外单号">{{ currentRow.order_no }}</el-descriptions-item>
            <el-descriptions-item label="零件">{{ currentRow.part_no }} - {{ currentRow.part_name }}</el-descriptions-item>
         </el-descriptions>
         <el-table :data="currentRow ? currentRow.variance_reasons : []" border>
            <el-table-column label="原因类型" prop="reason_type" width="140" />
            <el-table-column label="描述" prop="description" :show-overflow-tooltip="true" />
            <el-table-column label="影响金额" width="120" align="right">
               <template #default="scope">
                  <span :style="{ color: getVarianceColor(scope.row.impact_amount), fontWeight: 'bold' }">
                     {{ scope.row.impact_amount > 0 ? '+' : '' }}¥{{ formatAmount(scope.row.impact_amount) }}
                  </span>
               </template>
            </el-table-column>
            <el-table-column label="责任方" prop="responsible_party" width="120" align="center" />
         </el-table>
      </el-dialog>
   </div>
</template>

<script setup name="ReconciliationDetail">
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getStatement, recalculateVariance } from '@/api/entrust/reconciliation'

const { proxy } = getCurrentInstance()
const route = useRoute()
const router = useRouter()
const id = route.params.id

const loading = ref(false)
const recalculating = ref(false)
const statement = reactive({
   statement_no: '',
   supplier_name: '',
   period_start: '',
   period_end: '',
   status: '',
   created_at: '',
   confirmed_at: '',
   total_ordered_amount: 0,
   total_received_value: 0,
   total_logistics_cost: 0,
   total_variance: 0,
   total_amount: 0,
   mismatch_count: 0
})
const lineItems = ref([])

// 差异原因弹窗
const reasonDialogVisible = ref(false)
const currentRow = ref(null)

/** 加载对账单详情 */
function loadDetail() {
   loading.value = true
   getStatement(id).then(res => {
      const data = res.data || res
      Object.assign(statement, data)
      lineItems.value = data.line_items || []
      loading.value = false
   }).catch(() => { loading.value = false })
}

/** 重算差异 */
function handleRecalculate() {
   proxy.$modal.confirm('确认要重新计算该对账单的差异吗？').then(() => {
      recalculating.value = true
      recalculateVariance(id).then(() => {
         proxy.$modal.msgSuccess('重算完成')
         recalculating.value = false
         loadDetail()
      }).catch(() => { recalculating.value = false })
   }).catch(() => {})
}

/** 返回列表 */
function goBack() {
   router.push({ path: '/entrust/reconciliation' })
}

/** 点击行展开差异原因 */
function handleRowClick(row) {
   if (row.has_mismatch && row.variance_reasons && row.variance_reasons.length > 0) {
      currentRow.value = row
      reasonDialogVisible.value = true
   }
}

/** 表格行样式 - 货不对板高亮 */
function tableRowClassName({ row }) {
   if (row.has_mismatch) {
      return 'mismatch-row'
   }
   return ''
}

/** 金额格式化 */
function formatAmount(val) {
   if (val === null || val === undefined) return '0.00'
   const num = Number(val)
   if (isNaN(num)) return '0.00'
   return Math.abs(num).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 差异金额颜色 */
function getVarianceColor(variance) {
   if (!variance || variance === 0) return '#606266'
   return variance > 0 ? '#F56C6C' : '#67C23A'
}

/** 日期时间格式化 */
function formatDateTime(val) {
   if (!val) return ''
   return val.replace('T', ' ').substring(0, 19)
}

onMounted(() => {
   loadDetail()
})
</script>

<style scoped>
.page-header {
   display: flex;
   align-items: center;
   gap: 12px;
   margin-bottom: 16px;
}
.header-title {
   font-size: 18px;
   font-weight: bold;
}
.mb16 { margin-bottom: 16px; }

.summary-card {
   text-align: center;
}
.summary-card :deep(.el-card__body) {
   padding: 16px 12px;
}
.summary-label {
   font-size: 12px;
   color: #909399;
   margin-bottom: 4px;
}
.summary-value {
   font-size: 20px;
   font-weight: bold;
   color: #303133;
}

:deep(.mismatch-row) {
   background-color: #FEF0F0 !important;
}
:deep(.mismatch-row:hover > td) {
   background-color: #FDE2E2 !important;
}
</style>
