<template>
   <div class="app-container">
      <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
         <el-form-item label="状态" prop="status">
            <el-select v-model="queryParams.status" placeholder="询价状态" clearable style="width: 200px">
               <el-option label="草稿" value="draft" />
               <el-option label="已发送" value="sent" />
               <el-option label="已报价" value="quoted" />
               <el-option label="已选标" value="awarded" />
               <el-option label="已关闭" value="closed" />
            </el-select>
         </el-form-item>
         <el-form-item>
            <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
            <el-button icon="Refresh" @click="resetQuery">重置</el-button>
         </el-form-item>
      </el-form>

      <el-row :gutter="10" class="mb8">
         <el-col :span="1.5">
            <el-button type="primary" plain icon="Plus" @click="handleAdd">新增询价</el-button>
         </el-col>
         <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
      </el-row>

      <el-table ref="inquiryTableRef" v-loading="loading" :data="inquiryList" @expand-change="handleExpandChange">
         <el-table-column type="expand">
            <template #default="scope">
               <div style="padding: 12px 20px">
                  <!-- 询价零件明细 -->
                  <div v-if="scope.row.scope_json && scope.row.scope_json.length">
                     <div style="font-weight:bold;margin-bottom:8px">询价零件明细</div>
                     <el-table :data="scope.row.scope_json" border size="small" style="margin-bottom:12px">
                        <el-table-column label="零件编号" prop="part_no" width="120" />
                        <el-table-column label="零件名称" prop="part_name" />
                        <el-table-column label="数量" prop="qty" width="80" align="center" />
                        <el-table-column label="材料" prop="material" width="100" />
                        <el-table-column label="所需工艺">
                           <template #default="s">
                              <el-tag v-for="p in (s.row.processes || [])" :key="p" size="small" class="mr4">{{ p }}</el-tag>
                           </template>
                        </el-table-column>
                     </el-table>
                  </div>
                  <!-- 报价列表 -->
                  <div style="font-weight:bold;margin-bottom:8px">报价列表</div>
                  <el-table :data="expandInvitations[scope.row.id] || []" v-loading="expandLoading[scope.row.id]" border size="small">
                     <el-table-column label="加工方" align="center" prop="supplier_name" width="140" />
                     <el-table-column label="单价" align="center" width="120">
                        <template #default="s">
                           <span v-if="s.row.quotation && s.row.quotation.unit_price">¥{{ s.row.quotation.unit_price }}</span>
                           <span v-else style="color:#999">-</span>
                        </template>
                     </el-table-column>
                     <el-table-column label="报价明细" align="center">
                        <template #default="s">
                           <template v-if="s.row.draft_quote_json && s.row.draft_quote_json.length">
                              <span v-for="(line, idx) in s.row.draft_quote_json" :key="idx" style="margin-right:12px">
                                 {{ line.part_name || line.part_no }}：¥{{ line.total_price || 0 }}
                              </span>
                           </template>
                           <span v-else style="color:#999">-</span>
                        </template>
                     </el-table-column>
                     <el-table-column label="备注" align="center" :show-overflow-tooltip="true" width="160">
                        <template #default="s">
                           <span v-if="s.row.status === 'declined' && s.row.decline_remark" style="color:#F56C6C">{{ s.row.decline_remark }}</span>
                           <span v-else>{{ s.row.quotation?.note || '-' }}</span>
                        </template>
                     </el-table-column>
                     <el-table-column label="状态" align="center" width="100">
                        <template #default="s">
                           <el-tag v-if="s.row.status === 'sent'" type="info">待回复</el-tag>
                           <el-tag v-else-if="s.row.status === 'draft_quoted'" type="warning">填写中</el-tag>
                           <el-tag v-else-if="s.row.status === 'quoted'" type="success">已报价</el-tag>
                           <el-tag v-else-if="s.row.status === 'declined'" type="danger">已拒绝</el-tag>
                        </template>
                     </el-table-column>
                     <el-table-column label="操作" align="center" width="140">
                        <template #default="s">
                           <el-button link type="primary" @click="doAward(s.row)" v-if="s.row.quotation && s.row.quotation.unit_price">选标</el-button>
                           <el-button link type="warning" @click="goChat(s.row)">对话</el-button>
                        </template>
                     </el-table-column>
                  </el-table>
               </div>
            </template>
         </el-table-column>
         <el-table-column label="询价单号" align="center" prop="id" width="100" />
         <el-table-column label="标题" prop="title" :show-overflow-tooltip="true" />
         <el-table-column label="关联项目" align="center" width="160">
            <template #default="scope">
               <span v-if="scope.row.project_name">{{ scope.row.project_name }}</span>
               <span v-else style="color:#999">#{{ scope.row.project_id }}</span>
            </template>
         </el-table-column>
         <el-table-column label="截止日期" align="center" prop="deadline" width="120" />
         <el-table-column label="状态" align="center" prop="status" width="100">
            <template #default="scope">
               <el-tag v-if="scope.row.status === 'draft'" type="info">草稿</el-tag>
               <el-tag v-else-if="scope.row.status === 'sent'">已发送</el-tag>
               <el-tag v-else-if="scope.row.status === 'quoted'" type="warning">已报价</el-tag>
               <el-tag v-else-if="scope.row.status === 'awarded'" type="success">已选标</el-tag>
               <el-tag v-else-if="scope.row.status === 'closed'" type="danger">已关闭</el-tag>
               <el-tag v-else type="warning">{{ scope.row.status }}</el-tag>
            </template>
         </el-table-column>
         <el-table-column label="创建时间" align="center" prop="created_at" width="180" />
         <el-table-column label="导出" align="center" width="140" class-name="small-padding fixed-width">
            <template #default="scope">
               <el-dropdown @command="(cmd) => handleExport(cmd, scope.row)">
                  <el-button link type="primary" icon="Download">导出<el-icon class="el-icon--right"><arrow-down /></el-icon></el-button>
                  <template #dropdown>
                     <el-dropdown-menu>
                        <el-dropdown-item command="inquiry">询价单</el-dropdown-item>
                        <el-dropdown-item command="quotation">报价单</el-dropdown-item>
                     </el-dropdown-menu>
                  </template>
               </el-dropdown>
            </template>
         </el-table-column>
         <el-table-column label="操作" align="center" width="240" class-name="small-padding fixed-width">
            <template #default="scope">
               <el-button link type="primary" icon="Promotion" @click="handleSend(scope.row)" v-if="scope.row.status === 'draft'">发送</el-button>
               <el-button link type="primary" icon="Trophy" @click="handleAward(scope.row)" v-if="scope.row.status === 'quoted'">选标</el-button>
               <el-button link type="primary" icon="Delete" @click="handleDelete(scope.row)">删除</el-button>
            </template>
         </el-table-column>
      </el-table>

      <pagination v-show="total > 0" :total="total" v-model:page="queryParams.page_num" v-model:limit="queryParams.page_size" @pagination="getList" />

      <!-- 新增询价对话框 -->
      <el-dialog title="创建询价单" v-model="open" width="650px" append-to-body>
         <el-form ref="inquiryRef" :model="form" :rules="rules" label-width="100px">
            <el-form-item label="关联项目" prop="project_id">
               <el-select v-model="form.project_id" filterable placeholder="请选择项目" style="width: 100%" @change="onProjectChange">
                  <el-option v-for="p in projectOptions" :key="p.id" :label="p.project_no + ' - ' + p.name" :value="p.id" />
               </el-select>
            </el-form-item>
            <el-form-item label="询价标题" prop="title">
               <el-input v-model="form.title" placeholder="请输入询价标题" />
            </el-form-item>
            <el-form-item label="截止日期" prop="deadline">
               <el-date-picker v-model="form.deadline" type="date" value-format="YYYY-MM-DD" placeholder="选择截止日期" style="width: 100%" />
            </el-form-item>
            <el-form-item label="询价范围" prop="scope_json">
               <el-input v-model="form.scope_json_str" type="textarea" :rows="4" placeholder='请输入询价范围 JSON，如: [{"part_id":1,"process":"车削","qty":100}]' />
            </el-form-item>
         </el-form>
         <template #footer>
            <div class="dialog-footer">
               <el-button type="primary" @click="submitForm">确 定</el-button>
               <el-button @click="cancel">取 消</el-button>
            </div>
         </template>
      </el-dialog>

      <!-- 发送询价对话框 -->
      <el-dialog title="发送询价邀请" v-model="sendOpen" width="500px" append-to-body>
         <el-form label-width="100px">
            <el-form-item label="选择加工方">
               <el-select v-model="selectedSupplierIds" multiple filterable placeholder="请选择要邀请的加工方" style="width: 100%">
                  <el-option v-for="s in supplierOptions" :key="s.id" :label="s.name + (s.province ? ' (' + s.province + s.city + ')' : '')" :value="s.id" />
               </el-select>
            </el-form-item>
         </el-form>
         <template #footer>
            <div class="dialog-footer">
               <el-button type="primary" @click="submitSend">发 送</el-button>
               <el-button @click="sendOpen = false">取 消</el-button>
            </div>
         </template>
      </el-dialog>
   </div>
</template>

<script setup name="Inquiry">
import { listInquiry, getInquiry, addInquiry, sendInquiry, getInvitations, awardInquiry, deleteInquiry } from "@/api/entrust/inquiry";
import { listSupplier } from "@/api/entrust/supplier";
import { listProject } from "@/api/entrust/project";
import { useRouter } from 'vue-router'
import { onActivated, onDeactivated } from 'vue'
import * as XLSX from 'xlsx-js-style'

const { proxy } = getCurrentInstance();
const router = useRouter();

const inquiryList = ref([]);
const open = ref(false);
const loading = ref(true);
const showSearch = ref(true);
const total = ref(0);
const sendOpen = ref(false);
const selectedSupplierIds = ref([]);
const supplierOptions = ref([]);
const currentInquiryId = ref(null);
const inquiryTableRef = ref(null);

// 展开行数据
const expandInvitations = ref({})
const expandLoading = ref({})

// 项目选项
const projectOptions = ref([]);

function loadProjects() {
   listProject({ page_num: 1, page_size: 100 }).then(res => {
      projectOptions.value = res.rows || [];
   });
}
loadProjects();

function onProjectChange(projectId) {
   const proj = projectOptions.value.find(p => p.id === projectId);
   if (proj && !form.value.title) {
      form.value.title = proj.name + ' - 加工询价';
   }
}

const data = reactive({
   form: {},
   queryParams: {
      page_num: 1,
      page_size: 10,
      status: undefined,
   },
   rules: {
      project_id: [{ required: true, message: "请选择项目", trigger: "change" }],
      title: [{ required: true, message: "询价标题不能为空", trigger: "blur" }],
   },
});

const { queryParams, form, rules } = toRefs(data);

function getList() {
   loading.value = true;
   listInquiry(queryParams.value).then(response => {
      inquiryList.value = response.rows;
      total.value = response.total;
      loading.value = false;
   });
}

function cancel() {
   open.value = false;
   reset();
}

function reset() {
   form.value = {
      project_id: undefined,
      title: undefined,
      deadline: undefined,
      scope_json_str: undefined,
   };
   proxy.resetForm("inquiryRef");
}

function handleQuery() {
   queryParams.value.page_num = 1;
   getList();
}

function resetQuery() {
   proxy.resetForm("queryRef");
   handleQuery();
}

function handleAdd() {
   reset();
   open.value = true;
}

function submitForm() {
   proxy.$refs["inquiryRef"].validate(valid => {
      if (valid) {
         const submitData = { ...form.value };
         if (submitData.scope_json_str) {
            try {
               submitData.scope_json = JSON.parse(submitData.scope_json_str);
            } catch {
               proxy.$modal.msgWarning("询价范围 JSON 格式不正确");
               return;
            }
         }
         delete submitData.scope_json_str;
         addInquiry(submitData).then(() => {
            proxy.$modal.msgSuccess("创建成功");
            open.value = false;
            getList();
         });
      }
   });
}

function handleSend(row) {
   currentInquiryId.value = row.id;
   selectedSupplierIds.value = [];
   listSupplier({ page_num: 1, page_size: 200, status: 'active' }).then(response => {
      supplierOptions.value = response.rows || [];
      sendOpen.value = true;
   }).catch(() => {
      proxy.$modal.msgError('加载加工方列表失败');
   });
}

function submitSend() {
   if (selectedSupplierIds.value.length === 0) {
      proxy.$modal.msgWarning("请至少选择一个加工方");
      return;
   }
   sendInquiry(currentInquiryId.value, selectedSupplierIds.value).then(() => {
      proxy.$modal.msgSuccess("发送成功");
      sendOpen.value = false;
      getList();
   });
}

// ---- 展开行加载报价 ----
function handleExpandChange(row, expandedRows) {
   if (expandInvitations.value[row.id]) return // 已加载过
   expandLoading.value[row.id] = true
   getInvitations(row.id).then(res => {
      expandInvitations.value[row.id] = res.data || []
      expandLoading.value[row.id] = false
   }).catch(() => {
      expandLoading.value[row.id] = false
   })
}

function handleAward(row) {
   // 先加载报价数据，再展开行
   getInvitations(row.id).then(res => {
      expandInvitations.value[row.id] = res.data || []
      // 展开该行
      if (inquiryTableRef.value) {
         inquiryTableRef.value.toggleRowExpansion(row, true)
      }
   })
}

function doAward(invitation) {
   const inquiryId = invitation.request_id || invitation.inquiry_id
   proxy.$modal.confirm('确认选择该报价为中标方？').then(() => {
      return awardInquiry(inquiryId, invitation.quotation?.id || invitation.quote_id);
   }).then(() => {
      proxy.$modal.msgSuccess("选标成功，已生成委外工单");
      getList();
   }).catch(() => {});
}

function handleDelete(row) {
   proxy.$modal.confirm('是否确认删除询价单"' + row.title + '"？').then(() => {
      return deleteInquiry(row.id);
   }).then(() => {
      getList();
      proxy.$modal.msgSuccess("删除成功");
   }).catch(() => {});
}

function goChat(invitation) {
   router.push({ path: '/entrust/chat', query: { supplier_id: invitation.supplier_id } })
}

// ---- XLSX 样式辅助函数 ----
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
   // 标题行样式
   for (let c = 0; c < totalCols; c++) {
      const addr = XLSX.utils.encode_cell({ r: 0, c })
      if (ws[addr]) ws[addr].s = TITLE_STYLE
   }
   // 表头行样式
   for (let c = 0; c < totalCols; c++) {
      const addr = XLSX.utils.encode_cell({ r: headerRow, c })
      if (ws[addr]) ws[addr].s = HEADER_STYLE
   }
   // 数据行样式
   for (let r = dataStartRow; r <= dataEndRow; r++) {
      for (let c = 0; c < totalCols; c++) {
         const addr = XLSX.utils.encode_cell({ r, c })
         if (ws[addr]) ws[addr].s = CELL_STYLE
      }
   }
}

// ---- 导出 XLSX ----
function handleExport(command, row) {
   if (command === 'inquiry') exportInquiryXlsx(row)
   else exportQuotationXlsx(row)
}

function exportInquiryXlsx(row) {
   const wb = XLSX.utils.book_new()
   const d = row
   const data = [
      ['询价单'],
      ['客户', d.customer_name || '', '', '订单号', d.order_no || ''],
      ['联系人', d.customer_contact || '', '', '电话', d.customer_phone || ''],
      ['询价日期', d.inquiry_date || '', '', '截止日期', d.deadline || ''],
      ['交付日期', d.delivery_date || ''],
      [],
      ['零件编号', '零件名称', '材料', '数量', '规格', '所需工艺'],
   ]
   const headerRow = 6
   const parts = d.scope_json || []
   for (const item of parts) {
      data.push([
         item.part_no, item.part_name, item.material, item.qty, item.spec,
         (item.processes || []).join('、'),
      ])
   }
   const dataEndRow = headerRow + parts.length
   data.push([])
   data.push(['说明：1. 请在「单价(元)」列填写含税单价'])
   data.push(['　　　2. 如有疑问请点击对话进行咨询'])
   const ws = XLSX.utils.aoa_to_sheet(data)
   ws['!cols'] = [{ wch: 14 }, { wch: 18 }, { wch: 12 }, { wch: 8 }, { wch: 20 }, { wch: 30 }]
   ws['!merges'] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 5 } }]
   ws['!rows'] = [{ hpt: 36 }] // 标题行高
   applyStyle(ws, headerRow, headerRow + 1, dataEndRow, 6)
   XLSX.utils.book_append_sheet(wb, ws, '询价单')
   XLSX.writeFile(wb, '询价单_' + (d.order_no || d.title || '').substring(0, 30) + '.xlsx')
}

async function exportQuotationXlsx(row) {
   let invitations = []
   try {
      const res = await getInvitations(row.id)
      invitations = res.data || []
   } catch (e) { return }
   if (!invitations.length) {
      proxy.$modal.msgWarning('该询价单暂无报价数据')
      return
   }
   const scopeJson = row.scope_json || []
   const wb = XLSX.utils.book_new()
   const usedSheetNames = new Set()
   for (const inv of invitations) {
      if (inv.status !== 'quoted' && inv.status !== 'draft_quoted') continue
      // 优先用 draft_quote_json，没有则用 quotation.lines_json（加工方可能直接提交未保存草稿）
      let quoteLines = inv.draft_quote_json || []
      if (!quoteLines.length && inv.quotation && inv.quotation.lines_json) {
         quoteLines = inv.quotation.lines_json
      }
      if (!quoteLines.length) continue
      const data = [
         ['报价单'],
         ['我方（客户）', row.customer_name || '', '', '订单号', row.order_no || ''],
         ['联系人', row.customer_contact || '', '', '电话', row.customer_phone || ''],
         ['询价日期', row.inquiry_date || '', '', '截止日期', row.deadline || ''],
         ['交付日期', row.delivery_date || ''],
         ['加工方', inv.supplier_name || ''],
         ['加工方联系人', inv.supplier_contact || '', '', '电话', inv.supplier_phone || ''],
         ['报价时间', inv.quoted_at || ''],
         [],
         ['零件编号', '零件名称', '材料', '数量', '规格', '所需工艺', '单价(元)', '总计(元)'],
      ]
      const headerRow = 10
      for (const l of quoteLines) {
         const scopeItem = scopeJson.find(s => s.part_no === l.part_no) || {}
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
      // Sheet 名称去重
      let sheetName = (inv.supplier_name || '报价').substring(0, 28)
      if (usedSheetNames.has(sheetName)) {
         sheetName = sheetName.substring(0, 25) + '_' + inv.supplier_id
      }
      usedSheetNames.add(sheetName)
      XLSX.utils.book_append_sheet(wb, ws, sheetName)
   }
   if (wb.SheetNames.length === 0) {
      proxy.$modal.msgWarning('暂无已填写的报价数据')
      return
   }
   XLSX.writeFile(wb, '报价单_' + (row.order_no || row.title || '').substring(0, 30) + '.xlsx')
}

// 轮询状态更新（检测加工方回复）
let pollTimer = null
let lastStatusMap = {}
function startPolling() {
   pollTimer = setInterval(() => {
      listInquiry({ page_num: 1, page_size: 100 }).then(res => {
         const rows = res.rows || []
         for (const r of rows) {
            const prev = lastStatusMap[r.id]
            if (prev && prev !== r.status) {
               if ((prev === 'sent' || prev === 'draft') && (r.status === 'quoted' || r.status === 'awarded')) {
                  ElNotification({ title: '报价通知', message: '询价单「' + r.title + '」已收到加工方回复', type: 'success', duration: 0 })
               }
            }
            lastStatusMap[r.id] = r.status
         }
         // 刷新列表
         if (JSON.stringify(rows.map(r => r.id + ':' + r.status)) !== JSON.stringify(inquiryList.value.map(r => r.id + ':' + r.status))) {
            inquiryList.value = rows
            total.value = res.total
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
