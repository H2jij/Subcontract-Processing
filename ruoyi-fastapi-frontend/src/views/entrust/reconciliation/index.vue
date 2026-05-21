<template>
   <div class="app-container">
      <!-- KPI 统计卡片 -->
      <el-row :gutter="16" class="mb16">
         <el-col :span="4">
            <el-card shadow="hover" class="kpi-card">
               <el-statistic title="对账单总数" :value="dashboard.total_count || 0" />
            </el-card>
         </el-col>
         <el-col :span="4">
            <el-card shadow="hover" class="kpi-card">
               <el-statistic title="已确认" :value="dashboard.confirmed_count || 0" />
            </el-card>
         </el-col>
         <el-col :span="4">
            <el-card shadow="hover" class="kpi-card">
               <el-statistic title="有争议" :value="dashboard.disputed_count || 0" />
            </el-card>
         </el-col>
         <el-col :span="4">
            <el-card shadow="hover" class="kpi-card">
               <el-statistic title="待确认" :value="dashboard.pending_count || 0" />
            </el-card>
         </el-col>
         <el-col :span="4">
            <el-card shadow="hover" class="kpi-card">
               <el-statistic title="货不对板数" :value="dashboard.mismatch_count || 0" />
            </el-card>
         </el-col>
         <el-col :span="4">
            <el-card shadow="hover" class="kpi-card">
               <div class="kpi-amount">
                  <div class="kpi-amount-label">差异总金额</div>
                  <div class="kpi-amount-value">¥{{ formatAmount(dashboard.total_variance || 0) }}</div>
               </div>
            </el-card>
         </el-col>
      </el-row>

      <!-- 筛选表单 -->
      <el-form :inline="true" :model="queryParams" class="mb8">
         <el-form-item label="供应商">
            <el-select v-model="queryParams.supplier_id" placeholder="全部供应商" clearable style="width:180px">
               <el-option
                  v-for="item in supplierList"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
               />
            </el-select>
         </el-form-item>
         <el-form-item label="状态">
            <el-select v-model="queryParams.status" placeholder="全部" clearable style="width:140px">
               <el-option label="待确认" value="pending" />
               <el-option label="已确认" value="confirmed" />
               <el-option label="有争议" value="disputed" />
               <el-option label="超时未确认" value="timeout" />
               <el-option label="已付款" value="paid" />
            </el-select>
         </el-form-item>
         <el-form-item label="对账周期">
            <el-date-picker
               v-model="queryParams.period"
               type="month"
               placeholder="选择月份"
               value-format="YYYY-MM"
               style="width:160px"
            />
         </el-form-item>
         <el-form-item>
            <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
            <el-button icon="Refresh" @click="resetQuery">重置</el-button>
         </el-form-item>
         <el-form-item style="float:right">
            <el-button type="success" icon="Plus" @click="openGenerateDialog">生成对账单</el-button>
         </el-form-item>
      </el-form>

      <!-- 对账单列表 -->
      <el-table v-loading="loading" :data="statementList" :row-class-name="tableRowClassName" border style="width:100%">
         <el-table-column label="对账单编号" prop="statement_no" min-width="180" />
         <el-table-column label="供应商" prop="supplier_name" min-width="120" />
         <el-table-column label="对账周期" min-width="160" align="center">
            <template #default="scope">
               {{ scope.row.period_start }} ~ {{ scope.row.period_end }}
            </template>
         </el-table-column>
         <el-table-column label="订购总金额" min-width="120" align="right">
            <template #default="scope">
               <span style="font-weight:bold">¥{{ formatAmount(scope.row.total_ordered_amount) }}</span>
            </template>
         </el-table-column>
         <el-table-column label="实际收到总价值" min-width="130" align="right">
            <template #default="scope">
               <span>¥{{ formatAmount(scope.row.total_received_value) }}</span>
            </template>
         </el-table-column>
         <el-table-column label="差异金额" min-width="110" align="right">
            <template #default="scope">
               <span :style="{ color: getVarianceColor(scope.row.total_variance), fontWeight: 'bold' }">
                  {{ scope.row.total_variance > 0 ? '+' : '' }}¥{{ formatAmount(scope.row.total_variance) }}
               </span>
            </template>
         </el-table-column>
         <el-table-column label="状态" width="100" align="center">
            <template #default="scope">
               <el-tag v-if="scope.row.status === 'pending'" type="info" size="small">待确认</el-tag>
               <el-tag v-else-if="scope.row.status === 'confirmed'" type="success" size="small">已确认</el-tag>
               <el-tag v-else-if="scope.row.status === 'disputed'" type="warning" size="small">有争议</el-tag>
               <el-tag v-else-if="scope.row.status === 'timeout'" type="danger" size="small">超时未确认</el-tag>
               <el-tag v-else-if="scope.row.status === 'paid'" size="small">已付款</el-tag>
            </template>
         </el-table-column>
         <el-table-column label="操作" align="center" width="160" fixed="right">
            <template #default="scope">
               <el-button link type="primary" icon="View" @click="handleView(scope.row)">查看详情</el-button>
               <el-button link type="warning" icon="Refresh" @click="handleRecalculate(scope.row)">重算差异</el-button>
            </template>
         </el-table-column>
      </el-table>

      <pagination
         v-show="total > 0"
         :total="total"
         v-model:page="queryParams.page_num"
         v-model:limit="queryParams.page_size"
         @pagination="getList"
      />

      <!-- 生成对账单对话框 -->
      <el-dialog v-model="generateDialogVisible" title="生成对账单" width="500px" append-to-body>
         <el-form :model="generateForm" label-width="100px">
            <el-form-item label="对账周期" required>
               <el-date-picker
                  v-model="generateForm.period_start"
                  type="date"
                  placeholder="起始日期"
                  value-format="YYYY-MM-DD"
                  style="width:180px"
               />
               <span style="margin:0 8px">至</span>
               <el-date-picker
                  v-model="generateForm.period_end"
                  type="date"
                  placeholder="结束日期"
                  value-format="YYYY-MM-DD"
                  style="width:180px"
               />
            </el-form-item>
            <el-form-item label="供应商">
               <el-select v-model="generateForm.supplier_id" placeholder="全部供应商（可选）" clearable style="width:100%">
                  <el-option
                     v-for="item in supplierList"
                     :key="item.id"
                     :label="item.name"
                     :value="item.id"
                  />
               </el-select>
            </el-form-item>
         </el-form>
         <template #footer>
            <el-button @click="generateDialogVisible = false">取 消</el-button>
            <el-button type="primary" :loading="generateLoading" @click="handleGenerate">确 定</el-button>
         </template>
      </el-dialog>
   </div>
</template>

<script setup name="Reconciliation">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listStatements, generateStatements, recalculateVariance, getDashboard } from '@/api/entrust/reconciliation'
import { listSupplier } from '@/api/entrust/supplier'

const { proxy } = getCurrentInstance()
const router = useRouter()

const loading = ref(false)
const statementList = ref([])
const total = ref(0)
const supplierList = ref([])
const dashboard = reactive({
   total_count: 0,
   confirmed_count: 0,
   disputed_count: 0,
   pending_count: 0,
   mismatch_count: 0,
   total_variance: 0
})

const queryParams = ref({
   page_num: 1,
   page_size: 10,
   supplier_id: '',
   status: '',
   period: ''
})

// 生成对账单对话框
const generateDialogVisible = ref(false)
const generateLoading = ref(false)
const generateForm = reactive({
   period_start: '',
   period_end: '',
   supplier_id: ''
})

/** 获取对账单列表 */
function getList() {
   loading.value = true
   const params = {
      page_num: queryParams.value.page_num,
      page_size: queryParams.value.page_size
   }
   if (queryParams.value.supplier_id) params.supplier_id = queryParams.value.supplier_id
   if (queryParams.value.status) params.status = queryParams.value.status
   if (queryParams.value.period) params.period = queryParams.value.period
   listStatements(params).then(res => {
      statementList.value = res.rows || []
      total.value = res.total || 0
      loading.value = false
   }).catch(() => { loading.value = false })
}

/** 获取仪表盘数据 */
function loadDashboard() {
   getDashboard({}).then(res => {
      if (res.data) {
         Object.assign(dashboard, res.data)
      }
   }).catch(() => {})
}

/** 搜索 */
function handleQuery() {
   queryParams.value.page_num = 1
   getList()
}

/** 重置 */
function resetQuery() {
   queryParams.value.supplier_id = ''
   queryParams.value.status = ''
   queryParams.value.period = ''
   queryParams.value.page_num = 1
   getList()
}

/** 查看详情 */
function handleView(row) {
   router.push({ path: '/entrust/reconciliation/detail/' + row.id })
}

/** 重算差异 */
function handleRecalculate(row) {
   proxy.$modal.confirm('确认要重新计算该对账单的差异吗？').then(() => {
      recalculateVariance(row.id).then(() => {
         proxy.$modal.msgSuccess('重算完成')
         getList()
         loadDashboard()
      })
   }).catch(() => {})
}

/** 打开生成对账单对话框 */
function openGenerateDialog() {
   generateForm.period_start = ''
   generateForm.period_end = ''
   generateForm.supplier_id = ''
   generateDialogVisible.value = true
}

/** 生成对账单 */
function handleGenerate() {
   if (!generateForm.period_start || !generateForm.period_end) {
      proxy.$modal.msgWarning('请选择对账周期的起止日期')
      return
   }
   generateLoading.value = true
   const data = {
      period_start: generateForm.period_start,
      period_end: generateForm.period_end
   }
   if (generateForm.supplier_id) data.supplier_id = generateForm.supplier_id
   generateStatements(data).then(res => {
      proxy.$modal.msgSuccess('对账单生成成功')
      generateDialogVisible.value = false
      generateLoading.value = false
      getList()
      loadDashboard()
   }).catch(() => { generateLoading.value = false })
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

/** 表格行样式 - 货不对板高亮 */
function tableRowClassName({ row }) {
   if (row.anomaly_count > 0 || row.total_variance !== 0) {
      return 'mismatch-row'
   }
   return ''
}

/** 加载供应商列表 */
function loadSuppliers() {
   listSupplier({ page_num: 1, page_size: 100 }).then(res => {
      supplierList.value = res.rows || []
   }).catch(() => {})
}

onMounted(() => {
   loadSuppliers()
})

getList()
loadDashboard()
</script>

<style scoped>
.mb8 { margin-bottom: 8px; }
.mb16 { margin-bottom: 16px; }

.kpi-card {
   text-align: center;
}
.kpi-card :deep(.el-card__body) {
   padding: 16px 12px;
}

.kpi-amount {
   text-align: center;
}
.kpi-amount-label {
   font-size: 12px;
   color: #909399;
   margin-bottom: 4px;
}
.kpi-amount-value {
   font-size: 22px;
   font-weight: bold;
   color: #F56C6C;
}

:deep(.mismatch-row) {
   background-color: #FEF0F0 !important;
}

:deep(.el-table) {
   width: 100% !important;
}
</style>
