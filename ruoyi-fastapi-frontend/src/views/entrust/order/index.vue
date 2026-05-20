<template>
   <div class="app-container">
      <el-form :inline="true" :model="queryParams" class="mb8">
         <el-form-item label="状态">
            <el-select v-model="queryParams.status" placeholder="全部" clearable style="width:160px">
               <el-option label="已选标" value="awarded" />
               <el-option label="已接受" value="accepted" />
               <el-option label="生产中" value="producing" />
               <el-option label="已交付" value="delivered" />
               <el-option label="已取消" value="cancelled" />
            </el-select>
         </el-form-item>
         <el-form-item>
            <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
            <el-button icon="Refresh" @click="resetQuery">重置</el-button>
         </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="orderList">
         <el-table-column label="工单号" prop="order_no" width="180" />
         <el-table-column label="供应商" prop="supplier_name" width="160" />
         <el-table-column label="项目名称" prop="project_name" :show-overflow-tooltip="true" />
         <el-table-column label="项目编号" prop="project_no" width="140" />
         <el-table-column label="总金额" width="120" align="center">
            <template #default="scope">
               <span v-if="scope.row.unit_price" style="color:#F56C6C;font-weight:bold">¥{{ scope.row.unit_price }}</span>
               <span v-else>-</span>
            </template>
         </el-table-column>
         <el-table-column label="交期" width="120" align="center">
            <template #default="scope">{{ scope.row.delivery_date || '-' }}</template>
         </el-table-column>
         <el-table-column label="状态" width="100" align="center">
            <template #default="scope">
               <el-tag v-if="scope.row.status === 'awarded'" type="success" size="small">已选标</el-tag>
               <el-tag v-else-if="scope.row.status === 'accepted'" size="small">已接受</el-tag>
               <el-tag v-else-if="scope.row.status === 'producing'" type="warning" size="small">生产中</el-tag>
               <el-tag v-else-if="scope.row.status === 'delivered'" type="success" size="small">已交付</el-tag>
               <el-tag v-else-if="scope.row.status === 'cancelled'" type="danger" size="small">已取消</el-tag>
            </template>
         </el-table-column>
         <el-table-column label="制单日期" width="180" align="center">
            <template #default="scope">
               {{ scope.row.created_at ? scope.row.created_at.replace('T', ' ').substring(0, 19) : '-' }}
            </template>
         </el-table-column>
         <el-table-column label="操作" align="center" width="160">
            <template #default="scope">
               <el-button link type="primary" icon="Download" @click="exportOrderPdf(scope.row)">导出工单</el-button>
            </template>
         </el-table-column>
      </el-table>

      <pagination v-show="total > 0" :total="total" v-model:page="queryParams.page_num" v-model:limit="queryParams.page_size" @pagination="getList" />
   </div>
</template>

<script setup name="Order">
import { ref } from 'vue'
import { listOrder } from '@/api/entrust/order'

const { proxy } = getCurrentInstance()

const loading = ref(false)
const orderList = ref([])
const total = ref(0)
const queryParams = ref({
   page_num: 1,
   page_size: 10,
   status: '',
})

function getList() {
   loading.value = true
   const params = { page_num: queryParams.value.page_num, page_size: queryParams.value.page_size }
   if (queryParams.value.status) params.status = queryParams.value.status
   listOrder(params).then(res => {
      orderList.value = res.rows || []
      total.value = res.total || 0
      loading.value = false
   }).catch(() => { loading.value = false })
}

function handleQuery() {
   queryParams.value.page_num = 1
   getList()
}

function resetQuery() {
   queryParams.value.status = ''
   queryParams.value.page_num = 1
   getList()
}

// ---- 导出委外工单 PDF ----
function exportOrderPdf(row) {
   const scopeJson = row.scope_json || []
   const quoteLines = row.lines_json || []
   const today = row.created_at ? row.created_at.substring(0, 10) : new Date().toISOString().slice(0, 10)

   let partsRows = ''
   for (let i = 0; i < scopeJson.length; i++) {
      const p = scopeJson[i]
      const quote = quoteLines.find(l => l.part_no === p.part_no) || {}
      partsRows += `
        <tr>
          <td>${i + 1}</td>
          <td>${p.part_no || ''}</td>
          <td>${p.part_name || ''}</td>
          <td>${p.material || ''}</td>
          <td>${p.qty || 1}</td>
          <td>${p.spec || ''}</td>
          <td>${(p.processes || []).join('、')}</td>
          <td>${quote.unit_price || ''}</td>
          <td>${quote.total_price || ''}</td>
        </tr>`
   }
   const grandTotal = quoteLines.reduce((s, l) => s + (l.total_price || 0), 0)

   const html = `
    <div style="font-family:'Microsoft YaHei','SimSun',sans-serif;width:700px;padding:30px 40px;color:#333;font-size:13px;">
      <div style="text-align:center;font-size:22px;font-weight:bold;letter-spacing:6px;margin-bottom:24px;">瑞利杰委外加工订单</div>
      <table style="width:100%;border-collapse:collapse;margin-bottom:12px;" cellpadding="4">
        <tr>
          <td style="width:15%;font-weight:bold;">供应商：</td>
          <td style="width:35%;">${row.supplier_name || ''}</td>
          <td style="width:15%;font-weight:bold;">订单组织：</td>
          <td style="width:35%;">青岛瑞利杰金属有限公司</td>
        </tr>
        <tr>
          <td style="font-weight:bold;">单号：</td>
          <td>${row.order_no || ''}</td>
          <td style="font-weight:bold;">制单日期：</td>
          <td>${today}</td>
        </tr>
        <tr>
          <td style="font-weight:bold;">整单备注：</td>
          <td>${row.project_name || ''}</td>
          <td style="font-weight:bold;">交期：</td>
          <td>${row.delivery_date || ''}</td>
        </tr>
        <tr>
          <td style="font-weight:bold;">币种：</td>
          <td>人民币</td>
          <td style="font-weight:bold;">备料情况：</td>
          <td>${row.material_preparation === 'supplier' ? '加工方备料' : '我方备料'}</td>
        </tr>
      </table>
      <table style="width:100%;border-collapse:collapse;margin-bottom:16px;" cellpadding="4" border="1" bordercolor="#999">
        <thead>
          <tr style="background:#409EFF;color:#fff;font-weight:bold;text-align:center;">
            <th style="width:30px;">序号</th>
            <th style="width:70px;">零件编号</th>
            <th style="width:80px;">零件名称</th>
            <th style="width:60px;">材料</th>
            <th style="width:40px;">数量</th>
            <th style="width:80px;">规格</th>
            <th style="width:100px;">所需工艺</th>
            <th style="width:60px;">单价(元)</th>
            <th style="width:60px;">总计(元)</th>
          </tr>
        </thead>
        <tbody>
          ${partsRows}
          <tr style="font-weight:bold;">
            <td colspan="7" style="text-align:right;padding-right:8px;">合计：</td>
            <td></td>
            <td style="color:#F56C6C;">${grandTotal.toFixed(2)}</td>
          </tr>
        </tbody>
      </table>
      <table style="width:100%;border-collapse:collapse;margin-top:40px;" cellpadding="4">
        <tr>
          <td style="width:50%;">
            <div style="margin-bottom:30px;">供方签字：__________________</div>
            <div>日期：__________________</div>
          </td>
          <td style="width:50%;">
            <div style="margin-bottom:30px;">需方签字：__________________</div>
            <div>日期：__________________</div>
          </td>
        </tr>
      </table>
    </div>
  `

   // 创建临时容器挂到 body 上
   const temp = document.createElement('div')
   temp.innerHTML = html
   document.body.appendChild(temp)

   const opt = {
      margin: [10, 10, 10, 10],
      filename: `委外工单_${row.order_no || ''}_${row.supplier_name || ''}.pdf`,
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: { scale: 2, useCORS: true },
      jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
   }

   import('html2pdf.js').then(module => {
      const html2pdf = module.default || module
      html2pdf().set(opt).from(temp.firstElementChild).save().then(() => {
         document.body.removeChild(temp)
      }).catch(err => {
         console.error('PDF export error:', err)
         proxy.$modal.msgError('PDF导出失败')
         document.body.removeChild(temp)
      })
   }).catch(err => {
      console.error('html2pdf load error:', err)
      proxy.$modal.msgError('PDF组件加载失败')
      document.body.removeChild(temp)
   })
}

getList()
</script>

<style scoped>
.mb8 { margin-bottom: 8px; }
</style>
