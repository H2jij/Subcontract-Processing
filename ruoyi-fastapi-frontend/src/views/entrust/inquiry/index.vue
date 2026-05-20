<template>
   <div class="app-container">
      <el-row :gutter="10" class="mb8">
         <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
      </el-row>

      <!-- 主表：按项目分组 -->
      <el-table ref="groupedTableRef" v-loading="loading" :data="groupedList" @expand-change="handleExpandChange">
         <el-table-column type="expand">
            <template #default="scope">
               <div style="padding: 12px 20px">
                  <div style="font-weight:bold;margin-bottom:8px">加工方报价排名</div>
                  <el-table :data="scope.row.suppliers" border size="small">
                     <el-table-column label="排名" width="70" align="center">
                        <template #default="s">
                           <span v-if="s.row.rank" style="font-weight:bold;color:#409EFF">#{{ s.row.rank }}</span>
                           <span v-else style="color:#999">-</span>
                        </template>
                     </el-table-column>
                     <el-table-column label="加工方" prop="supplier_name" width="160" />
                     <el-table-column label="地区" width="100" align="center">
                        <template #default="s">
                           <el-tag v-if="s.row.province === '山东' && s.row.city === '青岛'" type="success" size="small">同城</el-tag>
                           <el-tag v-else-if="s.row.province === '山东'" size="small">同省</el-tag>
                           <el-tag v-else type="info" size="small">外地</el-tag>
                        </template>
                     </el-table-column>
                     <el-table-column label="报价总额" width="120" align="center">
                        <template #default="s">
                           <span v-if="s.row.unit_price" style="color:#F56C6C;font-weight:bold">¥{{ s.row.unit_price }}</span>
                           <span v-else style="color:#999">-</span>
                        </template>
                     </el-table-column>
                     <el-table-column label="交付日期" width="120" align="center">
                        <template #default="s">
                           <span v-if="s.row.delivery_date">{{ s.row.delivery_date }}</span>
                           <span v-else style="color:#999">-</span>
                        </template>
                     </el-table-column>
                     <el-table-column label="状态" width="110" align="center">
                        <template #default="s">
                           <el-tag v-if="s.row.invitation_status === 'sent' || s.row.invitation_status === 'draft_quoted'" type="info" size="small">待回复</el-tag>
                           <el-tag v-else-if="s.row.invitation_status === 'quoted'" type="success" size="small">已报价</el-tag>
                           <el-tag v-else-if="s.row.invitation_status === 'declined'" type="danger" size="small">已拒绝</el-tag>
                        </template>
                     </el-table-column>
                     <el-table-column label="排名描述" min-width="140">
                        <template #default="s">
                           <span style="color:#999">{{ s.row.rank_description || '-' }}</span>
                        </template>
                     </el-table-column>
                     <el-table-column label="报价明细" min-width="200">
                        <template #default="s">
                           <template v-if="s.row.lines_json && s.row.lines_json.length">
                              <span v-for="(line, idx) in s.row.lines_json" :key="idx" style="margin-right:12px">
                                 {{ line.part_name || line.part_no }}：¥{{ line.total_price || 0 }}
                              </span>
                           </template>
                           <span v-else style="color:#999">-</span>
                        </template>
                     </el-table-column>
                     <el-table-column label="备注" width="140" :show-overflow-tooltip="true">
                        <template #default="s">{{ s.row.note || '-' }}</template>
                     </el-table-column>
                     <el-table-column label="操作" width="250" align="center">
                        <template #default="s">
                           <el-button link type="primary" @click="doAward(scope.row, s.row)" v-if="s.row.unit_price && !scope.row.has_order">选标</el-button>
                           <el-tag v-if="scope.row.has_order" type="info" size="small" style="margin-right:8px">已下单</el-tag>
                           <el-button link type="warning" @click="goChat(s.row)">对话</el-button>
                           <el-button link type="primary" @click="exportQuotationForSupplier(scope.row, s.row)" v-if="s.row.lines_json && s.row.lines_json.length">导出报价单</el-button>
                        </template>
                     </el-table-column>
                  </el-table>
               </div>
            </template>
         </el-table-column>
         <el-table-column label="项目编号" prop="project_no" width="140" />
         <el-table-column label="项目名称" prop="project_name" :show-overflow-tooltip="true" />
         <el-table-column label="询价次数" prop="inquiry_count" width="100" align="center" />
         <el-table-column label="已报价/总数" width="120" align="center">
            <template #default="scope">
               <span style="color:#67C23A;font-weight:bold">{{ scope.row.quoted_supplier_count }}</span>
               <span> / {{ scope.row.total_supplier_count }}</span>
            </template>
         </el-table-column>
         <el-table-column label="最近询价时间" prop="latest_inquiry_at" width="180" align="center">
            <template #default="scope">
               {{ scope.row.latest_inquiry_at ? scope.row.latest_inquiry_at.replace('T', ' ').substring(0, 19) : '-' }}
            </template>
         </el-table-column>
         <el-table-column label="操作" align="center" width="280" class-name="small-padding fixed-width">
            <template #default="scope">
               <el-button link type="primary" icon="Trophy" @click="handleAward(scope.row)" v-if="!scope.row.has_order">选标</el-button>
               <el-button link type="primary" icon="Refresh" @click="refreshGroup(scope.row)">刷新</el-button>
               <el-button link type="primary" icon="Download" @click="exportInquiryXlsx(scope.row)">导出询价单</el-button>
            </template>
         </el-table-column>
      </el-table>

      <pagination v-show="total > 0" :total="total" v-model:page="queryParams.page_num" v-model:limit="queryParams.page_size" @pagination="getList" />
   </div>
</template>

<script setup name="Inquiry">
import { getGroupedInquiryList, awardInquiry } from "@/api/entrust/inquiry";
import { useRouter } from 'vue-router'
import { onActivated, onDeactivated } from 'vue'
import * as XLSX from 'xlsx-js-style'

const { proxy } = getCurrentInstance();
const router = useRouter();

const groupedList = ref([]);
const loading = ref(true);
const showSearch = ref(true);
const total = ref(0);
const groupedTableRef = ref(null);

const queryParams = ref({
   page_num: 1,
   page_size: 10,
});

function getList() {
   loading.value = true;
   getGroupedInquiryList(queryParams.value).then(response => {
      groupedList.value = response.rows || [];
      total.value = response.total || 0;
      loading.value = false;
   }).catch(() => {
      loading.value = false;
   });
}

function handleExpandChange(row, expandedRows) {}

function handleAward(row) {
   if (groupedTableRef.value) {
      groupedTableRef.value.toggleRowExpansion(row, true);
   }
}

function refreshGroup(row) {
   getList();
}

function doAward(groupRow, supplier) {
   const inquiryId = supplier.request_id
   const quotationId = supplier.quotation_id
   if (!inquiryId || !quotationId) {
      proxy.$modal.msgWarning('缺少询价单或报价单信息');
      return;
   }
   proxy.$modal.confirm('确认选择「' + supplier.supplier_name + '」为中标方？报价：¥' + (supplier.unit_price || '-')).then(() => {
      return awardInquiry(inquiryId, quotationId);
   }).then(() => {
      proxy.$modal.msgSuccess("选标成功，已生成委外工单，可在委外工单页面查看");
      getList();
   }).catch(() => {});
}

function goChat(supplier) {
   router.push({ path: '/entrust/chat', query: { supplier_id: supplier.supplier_id } })
}

// ---- XLSX 样式辅助 ----
const TITLE_STYLE = {
   font: { bold: true, sz: 16, name: '微软雅黑' },
   alignment: { horizontal: 'center', vertical: 'center' },
}
const HEADER_STYLE = {
   font: { bold: true, sz: 11, color: { rgb: 'FFFFFF' }, name: '微软雅黑' },
   fill: { fgColor: { rgb: '409EFF' } },
   alignment: { horizontal: 'center', vertical: 'center' },
   border: {
      top: { style: 'thin', color: { rgb: 'CCCCCC' } },
      bottom: { style: 'thin', color: { rgb: 'CCCCCC' } },
      left: { style: 'thin', color: { rgb: 'CCCCCC' } },
      right: { style: 'thin', color: { rgb: 'CCCCCC' } },
   },
}
const CELL_STYLE = {
   font: { sz: 11, name: '微软雅黑' },
   alignment: { vertical: 'center' },
   border: {
      top: { style: 'thin', color: { rgb: 'CCCCCC' } },
      bottom: { style: 'thin', color: { rgb: 'CCCCCC' } },
      left: { style: 'thin', color: { rgb: 'CCCCCC' } },
      right: { style: 'thin', color: { rgb: 'CCCCCC' } },
   },
}
const TOTAL_STYLE = {
   font: { bold: true, sz: 11, name: '微软雅黑' },
   alignment: { horizontal: 'right', vertical: 'center' },
   border: {
      top: { style: 'thin', color: { rgb: 'CCCCCC' } },
      bottom: { style: 'thin', color: { rgb: 'CCCCCC' } },
      left: { style: 'thin', color: { rgb: 'CCCCCC' } },
      right: { style: 'thin', color: { rgb: 'CCCCCC' } },
   },
}

function applyStyle(ws, headerRow, dataStartRow, dataEndRow, totalCols) {
   for (let c = 0; c < totalCols; c++) {
      const addr = XLSX.utils.encode_cell({ r: 0, c })
      if (ws[addr]) ws[addr].s = TITLE_STYLE
   }
   for (let c = 0; c < totalCols; c++) {
      const addr = XLSX.utils.encode_cell({ r: headerRow, c })
      if (ws[addr]) ws[addr].s = HEADER_STYLE
   }
   for (let r = dataStartRow; r <= dataEndRow; r++) {
      for (let c = 0; c < totalCols; c++) {
         const addr = XLSX.utils.encode_cell({ r, c })
         if (ws[addr]) ws[addr].s = CELL_STYLE
      }
   }
}

// ---- 合并所有询价单的零件信息 ----
function mergeScopeJson(inquiries) {
   const allParts = []
   for (const inv of inquiries) {
      if (inv.scope_json && inv.scope_json.length) {
         for (const p of inv.scope_json) {
            if (!allParts.find(x => x.part_no === p.part_no && x.part_name === p.part_name)) {
               allParts.push(p)
            }
         }
      }
   }
   return allParts
}

// ---- 导出询价单 ----
function exportInquiryXlsx(row) {
   const wb = XLSX.utils.book_new()
   const inquiries = row.inquiries || []
   if (!inquiries.length) {
      proxy.$modal.msgWarning('暂无询价单数据')
      return
   }
   const latest = inquiries[inquiries.length - 1]
   const allParts = mergeScopeJson(inquiries)

   const data = [
      ['询价单'],
      ['客户', latest.customer_name || '', '', '订单号', latest.order_no || ''],
      ['联系人', latest.customer_contact || '', '', '电话', latest.customer_phone || ''],
      ['询价日期', latest.inquiry_date || '', '', '截止日期', latest.deadline || ''],
      ['交付日期', latest.delivery_date || '', '', '备料情况', latest.material_preparation === 'supplier' ? '加工方备料' : '我方备料'],
      [],
      ['零件编号', '零件名称', '材料', '数量', '规格', '所需工艺'],
   ]
   const headerRow = 6
   for (const item of allParts) {
      data.push([
         item.part_no, item.part_name, item.material, item.qty, item.spec,
         (item.processes || []).join('、'),
      ])
   }
   const dataEndRow = headerRow + allParts.length
   data.push([])
   data.push(['说明：1. 请在「单价(元)」列填写含税单价'])
   data.push(['　　　2. 如有疑问请点击对话进行咨询'])

   const ws = XLSX.utils.aoa_to_sheet(data)
   ws['!cols'] = [{ wch: 14 }, { wch: 18 }, { wch: 12 }, { wch: 8 }, { wch: 20 }, { wch: 30 }]
   ws['!merges'] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 5 } }]
   ws['!rows'] = [{ hpt: 36 }]
   applyStyle(ws, headerRow, headerRow + 1, dataEndRow, 6)
   XLSX.utils.book_append_sheet(wb, ws, '询价单')
   XLSX.writeFile(wb, '询价单_' + (latest.order_no || row.project_name || '').substring(0, 30) + '.xlsx')
}

// ---- 单个加工商导出报价单 ----
function exportQuotationForSupplier(groupRow, supplier) {
   const inquiries = groupRow.inquiries || []
   const allParts = mergeScopeJson(inquiries)
   const latest = inquiries.length ? inquiries[inquiries.length - 1] : {}
   const quoteLines = supplier.lines_json || []
   if (!quoteLines.length) {
      proxy.$modal.msgWarning('该加工方暂无报价数据')
      return
   }

   const wb = XLSX.utils.book_new()
   const data = [
      ['报价单'],
      ['我方（客户）', latest.customer_name || '', '', '订单号', latest.order_no || ''],
      ['联系人', latest.customer_contact || '', '', '电话', latest.customer_phone || ''],
      ['询价日期', latest.inquiry_date || '', '', '截止日期', latest.deadline || ''],
      ['交付日期', latest.delivery_date || '', '', '备料情况', latest.material_preparation === 'supplier' ? '加工方备料' : '我方备料'],
      ['加工方', supplier.supplier_name || ''],
      ['报价时间', supplier.quoted_at ? supplier.quoted_at.replace('T', ' ').substring(0, 19) : ''],
      [],
      ['零件编号', '零件名称', '材料', '数量', '规格', '所需工艺', '单价(元)', '总计(元)'],
   ]
   const headerRow = 9
   for (const l of quoteLines) {
      const scopeItem = allParts.find(s => s.part_no === l.part_no) || {}
      data.push([
         l.part_no, l.part_name, scopeItem.material || l.material || '', l.qty || 1,
         scopeItem.spec || l.spec || '', (scopeItem.processes || []).join('、'),
         l.unit_price || 0, l.total_price || 0,
      ])
   }
   const dataEndRow = headerRow + quoteLines.length
   const lineTotal = quoteLines.reduce((s, l) => s + (l.total_price || 0), 0)
   data.push(['', '', '', '', '', '', '合计：', lineTotal.toFixed(2)])
   data.push([])
   data.push(['说明：1. 单价为含税单价'])
   data.push(['　　　2. 总计为该零件总金额'])

   const ws = XLSX.utils.aoa_to_sheet(data)
   ws['!cols'] = [{ wch: 12 }, { wch: 16 }, { wch: 10 }, { wch: 8 }, { wch: 18 }, { wch: 28 }, { wch: 12 }, { wch: 12 }]
   ws['!merges'] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 7 } }]
   ws['!rows'] = [{ hpt: 36 }]
   applyStyle(ws, headerRow, headerRow + 1, dataEndRow, 8)
   for (let c = 0; c < 8; c++) {
      const addr = XLSX.utils.encode_cell({ r: dataEndRow + 1, c })
      if (ws[addr]) ws[addr].s = TOTAL_STYLE
   }

   XLSX.utils.book_append_sheet(wb, ws, (supplier.supplier_name || '报价').substring(0, 28))
   XLSX.writeFile(wb, '报价单_' + (supplier.supplier_name || '') + '_' + (groupRow.project_name || '').substring(0, 20) + '.xlsx')
}

// 轮询状态更新
let pollTimer = null
function startPolling() {
   pollTimer = setInterval(() => {
      getGroupedInquiryList({ page_num: 1, page_size: 100 }).then(res => {
         const newRows = res.rows || []
         for (const newRow of newRows) {
            const oldRow = groupedList.value.find(g => g.project_id === newRow.project_id)
            if (oldRow && oldRow.quoted_supplier_count < newRow.quoted_supplier_count) {
               ElNotification({ title: '报价通知', message: '项目「' + newRow.project_name + '」收到新的加工方报价', type: 'success', duration: 0 })
            }
         }
         if (JSON.stringify(newRows.map(r => r.project_id + ':' + r.quoted_supplier_count)) !==
             JSON.stringify(groupedList.value.map(r => r.project_id + ':' + r.quoted_supplier_count))) {
            groupedList.value = newRows
            total.value = res.total || 0
         }
      })
   }, 30000)
}

onActivated(() => { getList() })
onDeactivated(() => { if (pollTimer) { clearInterval(pollTimer); pollTimer = null } })

getList();
startPolling();
</script>

<style scoped>
.mr4 { margin-right: 4px; }
.mb8 { margin-bottom: 8px; }
</style>
