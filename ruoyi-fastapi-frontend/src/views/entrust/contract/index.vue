<template>
  <div class="app-container">

    <!-- 搜索栏 -->
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch">
      <el-form-item label="供应商类型" prop="supplier_type">
        <el-select v-model="queryParams.supplier_type" placeholder="全部" clearable style="width:120px">
          <el-option label="加工方" value="processor" />
          <el-option label="材料方" value="material" />
        </el-select>
      </el-form-item>
      <el-form-item label="发送状态" prop="status">
        <el-select v-model="queryParams.status" placeholder="全部" clearable style="width:120px">
          <el-option label="待发送" value="pending" />
          <el-option label="已发送" value="sent" />
          <el-option label="已延迟" value="deferred" />
          <el-option label="已拒绝" value="rejected" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
    </el-row>

    <!-- 任务列表 -->
    <el-table v-loading="loading" :data="taskList" row-key="id"
              :row-class-name="getRowClass">
      <el-table-column label="供应商" prop="supplier_name" min-width="180">
        <template #default="{ row }">
          <span :class="{ 'highlight-pending': row.status === 'pending' }">
            {{ row.supplier_name }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="类型" align="center" width="80">
        <template #default="{ row }">
          <el-tag :type="row.supplier_type === 'processor' ? 'primary' : 'warning'" size="small">
            {{ row.supplier_type === 'processor' ? '加工方' : '材料方' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="法定代表人" align="center" prop="legal_rep" width="100" />
      <el-table-column label="收件邮箱" prop="contact_email" min-width="180" show-overflow-tooltip />

      <el-table-column label="发送状态" align="center" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small" effect="dark">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="发送次数" align="center" width="80" prop="send_count" />

      <el-table-column label="最近发送" align="center" width="160">
        <template #default="{ row }">
          <span v-if="row.last_sent_at" style="font-size:12px;color:#666">
            {{ row.last_sent_at.slice(0, 16) }}
          </span>
          <el-tag v-else type="warning" size="small" effect="plain">未发送</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="备注" prop="note" min-width="120" show-overflow-tooltip />

      <el-table-column label="操作" align="center" width="280" fixed="right">
        <template #default="{ row }">
          <!-- 预览 -->
          <el-button link type="primary" icon="View" @click="handlePreview(row)">预览</el-button>
          <!-- 发送 -->
          <el-button link type="success" icon="Position" @click="handleSend(row)">
            {{ row.send_count > 0 ? '重新发送' : '发送' }}
          </el-button>
          <!-- 更多操作 -->
          <el-dropdown trigger="click" @command="(cmd) => handleCommand(cmd, row)">
            <el-button link type="info" icon="More">更多</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="history" icon="Clock">发送历史</el-dropdown-item>
                <el-dropdown-item command="defer" icon="Timer">延迟发送</el-dropdown-item>
                <el-dropdown-item v-if="row.status !== 'pending'" command="reset" icon="Refresh">重置待发送</el-dropdown-item>
                <el-dropdown-item command="reject" icon="CircleClose" style="color:#f56c6c">拒绝发送</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total > 0" :total="total"
                v-model:page="queryParams.page_num"
                v-model:limit="queryParams.page_size"
                @pagination="getList" />

    <!-- ── 发送确认对话框 ── -->
    <el-dialog title="发送框架合同" v-model="sendDialogVisible" width="520px" append-to-body>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="供应商">{{ currentRow?.supplier_name }}</el-descriptions-item>
        <el-descriptions-item label="法定代表人">{{ currentRow?.legal_rep || '—' }}</el-descriptions-item>
        <el-descriptions-item label="统一社会信用代码">{{ currentRow?.credit_code || '—' }}</el-descriptions-item>
        <el-descriptions-item label="发送次数">{{ currentRow?.send_count }}次</el-descriptions-item>
      </el-descriptions>
      <el-divider />
      <el-form :model="sendForm" label-width="100px">
        <el-form-item label="收件邮箱">
          <el-input v-model="sendForm.recipient_email" placeholder="留空则从档案自动获取" clearable />
          <div style="color:#999;font-size:12px;margin-top:4px">
            档案邮箱：{{ currentRow?.contact_email || '未配置' }}
          </div>
        </el-form-item>
        <el-form-item label="合同额度">
          <el-input v-model="sendForm.extra_values['合同额度']" placeholder="如：500,000 元（留空用档案值）" />
        </el-form-item>
        <el-form-item label="合同止期">
          <el-date-picker
            v-model="sendForm.contractEndDate"
            type="date" value-format="YYYY-MM-DD"
            placeholder="选择合同终止日期"
            style="width:100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="sendDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="sending" @click="submitSend">确认发送</el-button>
      </template>
    </el-dialog>

    <!-- ── 延迟发送对话框 ── -->
    <el-dialog title="延迟发送" v-model="deferDialogVisible" width="420px" append-to-body>
      <el-form :model="deferForm" label-width="100px">
        <el-form-item label="延迟到">
          <el-date-picker
            v-model="deferForm.deferred_until"
            type="datetime" value-format="YYYY-MM-DD HH:mm:ss"
            placeholder="选择发送时间"
            style="width:100%"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="deferForm.note" placeholder="延迟原因（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deferDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitDefer">确认</el-button>
      </template>
    </el-dialog>

    <!-- ── 拒绝发送对话框 ── -->
    <el-dialog title="拒绝发送" v-model="rejectDialogVisible" width="420px" append-to-body>
      <el-form :model="rejectForm" label-width="100px">
        <el-form-item label="拒绝原因">
          <el-input v-model="rejectForm.note" type="textarea" placeholder="填写拒绝原因（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rejectDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="submitReject">确认拒绝</el-button>
      </template>
    </el-dialog>

    <!-- ── 发送历史抽屉 ── -->
    <el-drawer title="发送历史" v-model="historyDrawerVisible" size="480px">
      <div style="margin-bottom:12px;color:#666;font-size:13px">
        供应商：<strong>{{ currentRow?.supplier_name }}</strong>
        &nbsp;共发送 <strong>{{ currentRow?.send_count }}</strong> 次
      </div>
      <el-timeline>
        <el-timeline-item
          v-for="r in historyRecords"
          :key="r.id"
          :type="r.status === 'sent' ? 'success' : 'danger'"
          :timestamp="r.sent_at?.slice(0, 16)"
          placement="top"
        >
          <el-card shadow="never" style="font-size:13px">
            <div>
              <el-tag :type="r.status === 'sent' ? 'success' : 'danger'" size="small">
                {{ r.status === 'sent' ? '发送成功' : '发送失败' }}
              </el-tag>
              <span style="margin-left:8px;color:#666">{{ r.recipient_email }}</span>
            </div>
            <div v-if="r.smtp_message_id" style="margin-top:6px;color:#999;font-size:11px">
              Message-ID: {{ r.smtp_message_id }}
            </div>
            <div v-if="r.error_message" style="margin-top:6px;color:#f56c6c">
              {{ r.error_message }}
            </div>
          </el-card>
        </el-timeline-item>
        <el-timeline-item v-if="!historyRecords.length" type="info">
          <span style="color:#999">暂无发送记录</span>
        </el-timeline-item>
      </el-timeline>
    </el-drawer>

  </div>
</template>

<script setup name="ContractDistribution">
import {
  listContractTasks, sendContract, deferContract,
  rejectContract, resetContract, getContractRecords, previewContract
} from '@/api/entrust/contract'

const { proxy } = getCurrentInstance()

const taskList = ref([])
const loading = ref(false)
const total = ref(0)
const showSearch = ref(true)

const queryParams = reactive({
  page_num: 1,
  page_size: 20,
  status: undefined,
  supplier_type: undefined,
})

// ── 对话框状态 ──────────────────────────────────────────────────────────────
const currentRow = ref(null)
const sendDialogVisible = ref(false)
const deferDialogVisible = ref(false)
const rejectDialogVisible = ref(false)
const historyDrawerVisible = ref(false)
const sending = ref(false)
const historyRecords = ref([])

const sendForm = reactive({
  recipient_email: '',
  extra_values: { '合同额度': '', },
  contractEndDate: '',
})

const deferForm = reactive({ deferred_until: '', note: '' })
const rejectForm = reactive({ note: '' })

// ── 工具方法 ────────────────────────────────────────────────────────────────
function statusLabel(s) {
  return { pending: '待发送', sent: '已发送', deferred: '已延迟', rejected: '已拒绝' }[s] || s
}
function statusTagType(s) {
  return { pending: 'warning', sent: 'success', deferred: 'info', rejected: 'danger' }[s] || ''
}
function getRowClass({ row }) {
  return row.status === 'pending' ? 'pending-row' : ''
}

// ── 列表 ────────────────────────────────────────────────────────────────────
async function getList() {
  loading.value = true
  try {
    const res = await listContractTasks(queryParams)
    taskList.value = res.rows || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

function handleQuery() { queryParams.page_num = 1; getList() }
function resetQuery() {
  queryParams.status = undefined
  queryParams.supplier_type = undefined
  queryParams.page_num = 1
  getList()
}

// ── 操作 ────────────────────────────────────────────────────────────────────
function handleSend(row) {
  currentRow.value = row
  sendForm.recipient_email = ''
  sendForm.extra_values['合同额度'] = ''
  sendForm.contractEndDate = ''
  sendDialogVisible.value = true
}

async function submitSend() {
  sending.value = true
  try {
    const extra = { ...sendForm.extra_values }
    if (sendForm.contractEndDate) {
      const [y, m, d] = sendForm.contractEndDate.split('-')
      extra['合同期限_止_年'] = y
      extra['合同期限_止_月'] = m
      extra['合同期限_止_日'] = d
    }
    // 清空空值
    Object.keys(extra).forEach(k => { if (!extra[k]) delete extra[k] })

    await sendContract(currentRow.value.id, {
      recipient_email: sendForm.recipient_email || null,
      extra_values: Object.keys(extra).length ? extra : null,
    })
    proxy.$modal.msgSuccess('合同发送成功')
    sendDialogVisible.value = false
    getList()
  } catch (e) {
    proxy.$modal.msgError('发送失败：' + (e.message || ''))
  } finally {
    sending.value = false
  }
}

function handleCommand(cmd, row) {
  currentRow.value = row
  if (cmd === 'history') loadHistory(row)
  else if (cmd === 'defer') { deferForm.deferred_until = ''; deferForm.note = ''; deferDialogVisible.value = true }
  else if (cmd === 'reject') { rejectForm.note = ''; rejectDialogVisible.value = true }
  else if (cmd === 'reset') handleReset(row)
}

async function loadHistory(row) {
  historyRecords.value = []
  historyDrawerVisible.value = true
  const res = await getContractRecords(row.id)
  historyRecords.value = res.data || []
}

async function submitDefer() {
  if (!deferForm.deferred_until) { proxy.$modal.msgWarning('请选择延迟时间'); return }
  await deferContract(currentRow.value.id, deferForm)
  proxy.$modal.msgSuccess('已标记为延迟发送')
  deferDialogVisible.value = false
  getList()
}

async function submitReject() {
  await rejectContract(currentRow.value.id, rejectForm)
  proxy.$modal.msgSuccess('已拒绝发送')
  rejectDialogVisible.value = false
  getList()
}

async function handleReset(row) {
  await proxy.$modal.confirm(`确认将「${row.supplier_name}」重置为待发送？`)
  await resetContract(row.id)
  proxy.$modal.msgSuccess('已重置')
  getList()
}

async function handlePreview(row) {
  try {
    const res = await previewContract(row.id)
    const url = URL.createObjectURL(new Blob([res], {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    }))
    const a = document.createElement('a')
    a.href = url
    a.download = `年度采购框架合同_${row.supplier_name}.docx`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    proxy.$modal.msgError('预览失败')
  }
}

getList()
</script>

<style scoped>
:deep(.pending-row) {
  background-color: #fffbe6 !important;
}
:deep(.pending-row:hover td) {
  background-color: #fff3b0 !important;
}
.highlight-pending {
  color: #e6a23c;
  font-weight: 600;
}
</style>
