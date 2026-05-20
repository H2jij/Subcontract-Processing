<template>
   <div class="app-container">
      <el-form :inline="true" :model="queryParams" class="mb8">
         <el-form-item label="状态">
            <el-select v-model="queryParams.status" placeholder="全部" clearable style="width:160px">
               <el-option label="待填写" value="sent" />
               <el-option label="填写中" value="draft_quoted" />
               <el-option label="已报价" value="quoted" />
               <el-option label="已拒绝" value="declined" />
            </el-select>
         </el-form-item>
         <el-form-item>
            <el-button type="primary" icon="Search" @click="loadList">搜索</el-button>
            <el-button icon="Refresh" @click="queryParams.status = ''; loadList()">重置</el-button>
         </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="filteredList">
         <el-table-column label="询价标题" prop="title" :show-overflow-tooltip="true" min-width="180" />
         <el-table-column label="客户" prop="customer_name" width="140" />
         <el-table-column label="订单号" prop="order_no" width="120" />
         <el-table-column label="询价日期" prop="inquiry_date" width="110" align="center" />
         <el-table-column label="截止日期" prop="deadline" width="110" align="center" />
         <el-table-column label="交付日期" prop="delivery_date" width="110" align="center" />
         <el-table-column label="备料情况" align="center" width="110">
            <template #default="scope">
               <el-tag v-if="scope.row.material_preparation === 'supplier'" type="warning" size="small">加工方备料</el-tag>
               <el-tag v-else type="success" size="small">我方备料</el-tag>
            </template>
         </el-table-column>
         <el-table-column label="状态" align="center" width="100">
            <template #default="scope">
               <el-tag v-if="scope.row.invitation_status === 'sent'" type="info">待填写</el-tag>
               <el-tag v-else-if="scope.row.invitation_status === 'draft_quoted'" type="warning">填写中</el-tag>
               <el-tag v-else-if="scope.row.invitation_status === 'quoted'" type="success">已报价</el-tag>
               <el-tag v-else-if="scope.row.invitation_status === 'declined'" type="danger">已拒绝</el-tag>
            </template>
         </el-table-column>
         <el-table-column label="导出" align="center" width="120">
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
         <el-table-column label="操作" align="center" width="280">
            <template #default="scope">
               <template v-if="scope.row.invitation_status === 'sent' || scope.row.invitation_status === 'draft_quoted'">
                  <el-button link type="primary" @click="openQuoteForm(scope.row)">填写报价</el-button>
                  <el-button link type="danger" @click="openDeclineDialog(scope.row)">拒绝</el-button>
               </template>
               <template v-if="scope.row.invitation_status === 'draft_quoted'">
                  <el-button link type="success" @click="doSendQuote(scope.row)">发送报价</el-button>
               </template>
               <template v-if="scope.row.invitation_status === 'quoted'">
                  <span style="color:#67C23A;margin-right:8px">已发送</span>
               </template>
               <template v-if="scope.row.invitation_status === 'declined'">
                  <span style="color:#F56C6C;margin-right:8px">已拒绝</span>
               </template>
               <el-button link type="warning" @click="goChat(scope.row)">对话</el-button>
            </template>
         </el-table-column>
      </el-table>

      <!-- 填写报价对话框 -->
      <el-dialog title="填写报价" v-model="quoteFormOpen" width="900px" append-to-body top="5vh">
         <el-descriptions :column="3" border size="small" class="mb16">
            <el-descriptions-item label="客户">{{ quoteFormInquiry.customer_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="订单号">{{ quoteFormInquiry.order_no || '-' }}</el-descriptions-item>
            <el-descriptions-item label="交付日期">{{ quoteFormInquiry.delivery_date || '-' }}</el-descriptions-item>
            <el-descriptions-item label="截止日期">{{ quoteFormInquiry.deadline || '-' }}</el-descriptions-item>
            <el-descriptions-item label="询价日期">{{ quoteFormInquiry.inquiry_date || '-' }}</el-descriptions-item>
            <el-descriptions-item label="备料情况">
               <el-tag v-if="quoteFormInquiry.material_preparation === 'supplier'" type="warning" size="small">加工方备料</el-tag>
               <el-tag v-else type="success" size="small">我方备料</el-tag>
            </el-descriptions-item>
         </el-descriptions>

         <!-- 报价明细表（单价 + 总计，手动输入） -->
         <div class="quote-table-wrap">
            <div class="qt-header">
               <span class="qc-mold-code">模具号</span>
               <span class="qc-part-no">零件编号</span>
               <span class="qc-part-name">零件名称</span>
               <span class="qc-material">材料</span>
               <span class="qc-qty">数量</span>
               <span class="qc-spec">规格</span>
               <span class="qc-process">所需工艺</span>
               <span class="qc-price">单价(元)</span>
               <span class="qc-total">总计(元)</span>
               <span class="qc-drawing">图纸</span>
            </div>
            <div v-for="(item, idx) in quoteLines" :key="idx" class="qt-row">
               <span class="qc-mold-code">{{ item.mold_code || '-' }}</span>
               <span class="qc-part-no">{{ item.part_no }}</span>
               <span class="qc-part-name">{{ item.part_name }}</span>
               <span class="qc-material">{{ item.material }}</span>
               <span class="qc-qty">{{ item.qty }}</span>
               <span class="qc-spec">{{ item.spec }}</span>
               <span class="qc-process">
                  <el-tag v-for="p in (item.processes || [])" :key="p" size="small" class="mr4">{{ p }}</el-tag>
               </span>
               <span class="qc-price">
                  <el-input-number v-model="item.unit_price" :min="0" :precision="2" size="small" controls-position="right" style="width:100%" placeholder="单价" />
               </span>
               <span class="qc-total">
                  <el-input-number v-model="item.total_price" :min="0" :precision="2" size="small" controls-position="right" style="width:100%" placeholder="总计" />
               </span>
               <span class="qc-drawing">
                  <el-button v-if="item._matchedDrawing" link type="primary" icon="Download" @click="downloadDrawing(item._matchedDrawing.id)">下载</el-button>
                  <span v-else style="color:#999;font-size:12px">无</span>
               </span>
            </div>
            <!-- 合计行 -->
            <div class="qt-row qt-total-row">
               <span class="qc-mold-code"></span>
               <span class="qc-part-no"></span>
               <span class="qc-part-name"></span>
               <span class="qc-material"></span>
               <span class="qc-qty"></span>
               <span class="qc-spec"></span>
               <span class="qc-process" style="font-weight:bold;text-align:right;padding-right:8px">合计：</span>
               <span class="qc-price" style="font-weight:bold">{{ quoteLines.reduce((s, l) => s + (l.unit_price || 0), 0).toFixed(2) }}</span>
               <span class="qc-total" style="font-weight:bold;font-size:15px;color:#F56C6C">{{ grandTotal }}</span>
               <span class="qc-drawing"></span>
            </div>
         </div>
         <div class="inquiry-note">
            <p>说明：1. 请在「单价(元)」列填写含税单价</p>
            <p>　　　2. 「总计(元)」请手动填写该零件的总金额</p>
            <p>　　　3. 如有疑问请点击「对话」进行咨询</p>
         </div>
         <el-form label-width="80px">
            <el-form-item label="备注">
               <el-input v-model="quoteNote" type="textarea" :rows="2" placeholder="备注信息（选填）" />
            </el-form-item>
         </el-form>
         <template #footer>
            <el-button type="success" @click="sendFromForm">发送报价</el-button>
            <el-button type="primary" @click="saveDraftQuote">保存草稿</el-button>
            <el-button @click="quoteFormOpen = false">关闭</el-button>
         </template>
      </el-dialog>

      <!-- 拒绝对话框 -->
      <el-dialog title="拒绝询价" v-model="declineOpen" width="450px" append-to-body>
         <el-form label-width="80px">
            <el-form-item label="拒绝备注">
               <el-input v-model="declineRemark" type="textarea" :rows="3" placeholder="请填写拒绝理由" />
            </el-form-item>
         </el-form>
         <template #footer>
            <el-button type="danger" @click="doDecline">确认拒绝</el-button>
            <el-button @click="declineOpen = false">取消</el-button>
         </template>
      </el-dialog>
   </div>
</template>

<script setup name="Quotation">
import { ref, computed, onMounted, onActivated, onDeactivated } from 'vue'
import { useRouter } from 'vue-router'
import { getMyInvitations, saveDraftQuote as apiSaveDraft, submitQuote, declineInvitation } from '@/api/entrust/inquiry'
import * as XLSX from 'xlsx-js-style'

const router = useRouter()
const { proxy } = getCurrentInstance()
const loading = ref(false)
const list = ref([])
const queryParams = ref({ status: '' })
let lastInvitationCount = 0

const filteredList = computed(() => {
   if (!queryParams.value.status) return list.value
   return list.value.filter(i => i.invitation_status === queryParams.value.status)
})

async function loadList(silent) {
   loading.value = !silent
   try {
      const res = await getMyInvitations()
      if (res.code === 200) {
         const newList = res.data || []
         // 弹窗提示：如果有新的待处理邀请
         const newPending = newList.filter(i => i.invitation_status === 'sent')
         if (lastInvitationCount > 0 && newPending.length > lastInvitationCount && silent) {
            ElNotification({
               title: '新询价通知',
               message: `您收到 ${newPending.length - lastInvitationCount} 条新的询价邀请，请及时处理`,
               type: 'warning',
               duration: 0,
            })
         }
         lastInvitationCount = newPending.length
         list.value = newList
      }
   } catch (e) {}
   loading.value = false
}

// 轮询检查新询价（每30秒）
let pollTimer = null
function startPolling() {
   pollTimer = setInterval(() => { loadList(true) }, 30000)
}
function stopPolling() {
   if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

// ---- 对话跳转 ----
function goChat(row) {
   // 传递 created_by（询价发送者 user_id），加工方自动连接到该用户
   router.push({ path: '/entrust/chat', query: { our_user_id: row.created_by } })
}

// ---- 下载图纸 ----
function downloadDrawing(drawingId) {
   import('@/utils/auth').then(({ getToken }) => {
      const baseURL = import.meta.env.VITE_APP_BASE_API
      const token = getToken()
      fetch(`${baseURL}/entrust/drawing/download/${drawingId}`, {
         headers: { 'Authorization': `Bearer ${token}` }
      }).then(res => {
         if (!res.ok) throw new Error('下载失败')
         const disposition = res.headers.get('Content-Disposition') || ''
         const filename = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^;"'\n]+)/)?.[1]
            || disposition.match(/filename="?([^";\n]+)"?/)?.[1]
            || 'drawing.dwg'
         return res.blob().then(blob => ({ blob, filename: decodeURIComponent(filename) }))
      }).then(({ blob, filename }) => {
         const url = URL.createObjectURL(blob)
         const a = document.createElement('a')
         a.href = url
         a.download = filename
         a.click()
         URL.revokeObjectURL(url)
      }).catch(() => {
         proxy.$modal.msgWarning('图纸下载失败')
      })
   })
}

// ---- 填写报价 ----
const quoteFormOpen = ref(false)
const quoteFormInquiry = ref({})
const quoteLines = ref([])
const quoteNote = ref('')
const currentInvitationId = ref(null)
const quoteFormDrawings = ref([])

const grandTotal = computed(() => {
   return quoteLines.value.reduce((sum, l) => {
      return sum + (l.total_price || 0)
   }, 0).toFixed(2)
})

function openQuoteForm(row) {
   currentInvitationId.value = row.invitation_id
   quoteFormInquiry.value = row
   quoteFormDrawings.value = row.project_drawings || []
   const drawings = row.project_drawings || []
   const scope = row.scope_json || []
   // 前缀匹配：为每个零件找到对应图纸
   const matchDrawing = (partNo) => {
      if (!partNo || !drawings.length) return null
      const upper = partNo.toUpperCase()
      return drawings.find(d => (d.part_code || '').toUpperCase().startsWith(upper)) || null
   }
   if (row.draft_quote_json && row.draft_quote_json.length) {
      quoteLines.value = scope.map(s => {
         const draft = row.draft_quote_json.find(d => d.part_no === s.part_no)
         return { ...s, unit_price: draft?.unit_price || 0, total_price: draft?.total_price || 0, _matchedDrawing: matchDrawing(s.part_no) }
      })
   } else {
      quoteLines.value = scope.map(s => ({ ...s, unit_price: 0, total_price: 0, _matchedDrawing: matchDrawing(s.part_no) }))
   }
   quoteNote.value = ''
   quoteFormOpen.value = true
}

async function saveDraftQuote() {
   const lines = quoteLines.value.map(l => ({
      part_no: l.part_no,
      part_name: l.part_name,
      qty: l.qty,
      unit_price: l.unit_price,
      total_price: l.total_price,
   }))
   try {
      await apiSaveDraft(currentInvitationId.value, { draft_quote_json: lines })
      proxy.$modal.msgSuccess('草稿已保存')
      loadList()
   } catch (e) {}
}

async function sendFromForm() {
   const lines = quoteLines.value.map(l => ({
      part_no: l.part_no,
      part_name: l.part_name,
      qty: l.qty,
      unit_price: l.unit_price,
      total_price: l.total_price,
   }))
   if (lines.every(l => !l.unit_price && !l.total_price)) {
      proxy.$modal.msgWarning('请至少填写一项单价或总计')
      return
   }
   try {
      await apiSaveDraft(currentInvitationId.value, { draft_quote_json: lines })
      const totalPrice = parseFloat(grandTotal.value)
      await submitQuote(currentInvitationId.value, {
         unit_price: totalPrice,
         lines: lines,
         note: quoteNote.value || '',
      })
      proxy.$modal.msgSuccess('报价已发送')
      quoteFormOpen.value = false
      loadList()
   } catch (e) {}
}

async function doSendQuote(row) {
   const inv = row || list.value.find(i => i.invitation_id === currentInvitationId.value)
   if (!inv) return
   const draftLines = inv.draft_quote_json || []
   if (draftLines.length === 0 || draftLines.every(l => !l.unit_price && !l.total_price)) {
      proxy.$modal.msgWarning('请先填写报价再发送')
      return
   }
   const totalPrice = draftLines.reduce((sum, l) => sum + (l.total_price || 0), 0)
   try {
      await submitQuote(inv.invitation_id, {
         unit_price: totalPrice,
         lines: draftLines,
         note: '',
      })
      proxy.$modal.msgSuccess('报价已发送')
      quoteFormOpen.value = false
      loadList()
   } catch (e) {}
}

// ---- 拒绝 ----
const declineOpen = ref(false)
const declineRemark = ref('')
const declineInvitationId = ref(null)

function openDeclineDialog(row) {
   declineInvitationId.value = row.invitation_id
   declineRemark.value = ''
   declineOpen.value = true
}

async function doDecline() {
   if (!declineRemark.value.trim()) {
      proxy.$modal.msgWarning('请填写拒绝备注')
      return
   }
   try {
      await declineInvitation(declineInvitationId.value, { decline_remark: declineRemark.value })
      proxy.$modal.msgSuccess('已拒绝该询价')
      declineOpen.value = false
      loadList()
   } catch (e) {}
}

// ---- 导出 XLSX（按行导出） ----
function handleExport(command, row) {
   if (command === 'inquiry') exportInquiryXlsx(row)
   else exportQuotationXlsx(row)
}

// XLSX 样式
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

function exportInquiryXlsx(row) {
   const wb = XLSX.utils.book_new()
   const inv = row
   const data = [
      ['询价单'],
      ['我方（客户）', inv.customer_name || '', '', '订单号', inv.order_no || ''],
      ['联系人', inv.customer_contact || '', '', '电话', inv.customer_phone || ''],
      ['询价日期', inv.inquiry_date || '', '', '截止日期', inv.deadline || ''],
      ['交付日期', inv.delivery_date || '', '', '备料情况', inv.material_preparation === 'supplier' ? '加工方备料' : '我方备料'],
      ['加工方', inv.supplier_name || ''],
      ['加工方联系人', inv.supplier_contact || '', '', '电话', inv.supplier_phone || ''],
      [],
      ['模具号', '零件编号', '零件名称', '材料', '数量', '规格', '所需工艺'],
   ]
   const headerRow = 9
   const parts = inv.scope_json || []
   for (const item of parts) {
      data.push([
         item.mold_code || '', item.part_no, item.part_name, item.material, item.qty, item.spec,
         (item.processes || []).join('、'),
      ])
   }
   const dataEndRow = headerRow + parts.length
   data.push([])
   data.push(['说明：1. 请在「单价(元)」列填写含税单价'])
   data.push(['　　　2. 如有疑问请联系我方进行咨询'])
   const ws = XLSX.utils.aoa_to_sheet(data)
   ws['!cols'] = [{ wch: 14 }, { wch: 12 }, { wch: 16 }, { wch: 10 }, { wch: 8 }, { wch: 18 }, { wch: 30 }]
   ws['!merges'] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 6 } }]
   ws['!rows'] = [{ hpt: 36 }]
   applyStyle(ws, headerRow, headerRow + 1, dataEndRow, 7)
   XLSX.utils.book_append_sheet(wb, ws, inv.title?.substring(0, 28) || '询价单')
   XLSX.writeFile(wb, '询价单_' + (inv.title || '').substring(0, 20) + '_' + new Date().toISOString().slice(0, 10) + '.xlsx')
}

function exportQuotationXlsx(row) {
   const wb = XLSX.utils.book_new()
   const inv = row
   const draftLines = inv.draft_quote_json || []
   const scopeJson = inv.scope_json || []
   const data = [
      ['报价单'],
      ['我方（加工方）', inv.supplier_name || ''],
      ['联系人', inv.supplier_contact || '', '', '电话', inv.supplier_phone || ''],
      ['客户（询价方）', inv.customer_name || '', '', '订单号', inv.order_no || ''],
      ['客户联系人', inv.customer_contact || '', '', '电话', inv.customer_phone || ''],
      ['询价日期', inv.inquiry_date || '', '', '交付日期', inv.delivery_date || ''],
      ['备料情况', inv.material_preparation === 'supplier' ? '加工方备料' : '我方备料'],
      ['报价时间', inv.quoted_at || ''],
      [],
      ['模具号', '零件编号', '零件名称', '材料', '数量', '规格', '所需工艺', '单价(元)', '总计(元)'],
   ]
   const headerRow = 9
   for (const l of draftLines) {
      const scopeItem = scopeJson.find(s => s.part_no === l.part_no) || {}
      data.push([
         scopeItem.mold_code || l.mold_code || '', l.part_no, l.part_name, scopeItem.material || '', l.qty || 1,
         scopeItem.spec || '', (scopeItem.processes || []).join('、'),
         l.unit_price || 0, l.total_price || 0,
      ])
   }
   const dataEndRow = headerRow + draftLines.length
   const grandTotal = draftLines.reduce((s, l) => s + (l.total_price || 0), 0)
   data.push(['', '', '', '', '', '', '', '合计：', grandTotal.toFixed(2)])
   data.push([])
   data.push(['说明：1. 单价为含税单价'])
   data.push(['　　　2. 总计为该零件总金额'])
   const ws = XLSX.utils.aoa_to_sheet(data)
   ws['!cols'] = [{ wch: 14 }, { wch: 12 }, { wch: 16 }, { wch: 10 }, { wch: 8 }, { wch: 18 }, { wch: 28 }, { wch: 12 }, { wch: 12 }]
   ws['!merges'] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 8 } }]
   ws['!rows'] = [{ hpt: 36 }]
   applyStyle(ws, headerRow, headerRow + 1, dataEndRow, 9)
   // 合计行样式
   for (let c = 0; c < 9; c++) {
      const addr = XLSX.utils.encode_cell({ r: dataEndRow + 1, c })
      if (ws[addr]) ws[addr].s = TOTAL_STYLE
   }
   XLSX.utils.book_append_sheet(wb, ws, inv.title?.substring(0, 28) || '报价单')
   XLSX.writeFile(wb, '报价单_' + (inv.title || '').substring(0, 20) + '_' + new Date().toISOString().slice(0, 10) + '.xlsx')
}

onMounted(() => { loadList(); startPolling() })
onActivated(() => { loadList() })
onDeactivated(() => { stopPolling() })
</script>

<style scoped>
.mb16 { margin-bottom: 16px; }
.mb8 { margin-bottom: 8px; }
.mr4 { margin-right: 4px; }

/* 报价明细表 */
.quote-table-wrap { border: 1px solid #dcdfe6; border-radius: 4px; overflow: hidden; margin-bottom: 8px; }
.qt-header {
   display: flex; background: #409EFF; color: #fff; font-weight: bold; font-size: 13px; padding: 8px 0;
}
.qt-row {
   display: flex; border-top: 1px solid #ebeef5; font-size: 13px; padding: 8px 0; align-items: center;
}
.qt-row:nth-child(even) { background: #fafafa; }
.qt-total-row { background: #f5f7fa; font-size: 13px; }
.qc-mold-code { width: 110px; text-align: center; }
.qc-part-no { width: 90px; text-align: center; }
.qc-part-name { width: 100px; text-align: center; }
.qc-material { width: 80px; text-align: center; }
.qc-qty { width: 60px; text-align: center; }
.qc-spec { width: 100px; text-align: center; }
.qc-process { min-width: 120px; text-align: center; }
.qc-price { width: 130px; text-align: center; }
.qc-total { width: 130px; text-align: center; }
.qc-drawing { width: 70px; text-align: center; }

.inquiry-note { font-size: 12px; color: #909399; line-height: 1.8; padding: 4px 0 8px; }
</style>
