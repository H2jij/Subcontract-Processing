<template>
  <div class="app-container">
    <!-- 搜索栏 -->
    <el-form :inline="true" :model="queryParams" class="mb8">
      <el-form-item label="模具编号">
        <el-input v-model="queryParams.mold_code" placeholder="请输入模具编号" clearable style="width: 200px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="零件编号">
        <el-input v-model="queryParams.part_code" placeholder="请输入零件编号" clearable style="width: 200px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleQuery">搜索</el-button>
        <el-button @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <!-- 操作栏 -->
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" @click="showSplitDialog">手动拆图</el-button>
      </el-col>
    </el-row>

    <!-- 图纸列表 -->
    <el-table v-loading="loading" :data="drawingList" border>
      <el-table-column label="模具编号" prop="moldCode" min-width="140" />
      <el-table-column label="零件编号" prop="partCode" min-width="120" />
      <el-table-column label="文件名" prop="fileName" min-width="180" show-overflow-tooltip />
      <el-table-column label="版本" prop="version" width="70" align="center">
        <template #default="{ row }">
          <el-tag size="small">v{{ row.version }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最新版" prop="isLatest" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.isLatest ? 'success' : 'info'" size="small">
            {{ row.isLatest ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="文件大小" width="100" align="center">
        <template #default="{ row }">
          {{ row.fileSizeKb ? (row.fileSizeKb > 1024 ? (row.fileSizeKb / 1024).toFixed(1) + ' MB' : row.fileSizeKb + ' KB') : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="来源" prop="sourceType" width="100" align="center">
        <template #default="{ row }">
          {{ row.sourceType === 'manual' ? '手动上传' : '自动拆分' }}
        </template>
      </el-table-column>
      <el-table-column label="拆分时间" prop="splitAt" width="170" />
      <el-table-column label="操作" width="150" fixed="right" align="center">
        <template #default="{ row }">
          <el-button link type="primary" @click="handleDownload(row)">下载</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <el-pagination
      v-model:current-page="queryParams.page_num"
      v-model:page-size="queryParams.page_size"
      :total="total"
      :page-sizes="[20, 50, 100]"
      layout="total, sizes, prev, pager, next"
      class="mt10"
      @size-change="getList"
      @current-change="getList"
    />

    <!-- 手动拆图弹窗 -->
    <el-dialog v-model="splitDialogVisible" title="手动拆图" width="600px" destroy-on-close>
      <el-steps :active="splitStep" align-center class="mb20">
        <el-step title="输入模具号" />
        <el-step title="预览零件" />
        <el-step title="执行拆图" />
      </el-steps>

      <!-- Step1: 输入模具号 -->
      <div v-if="splitStep === 0">
        <el-form label-width="100px">
          <el-form-item label="模具编号">
            <el-input v-model="splitForm.mold_code" placeholder="如 M250247-P6" />
          </el-form-item>
        </el-form>
        <div style="text-align: right">
          <el-button @click="splitDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="previewLoading" @click="doPreview">预览零件列表</el-button>
        </div>
      </div>

      <!-- Step2: 选择零件 -->
      <div v-if="splitStep === 1">
        <p style="margin-bottom: 10px">原图：<b>{{ previewData.sourceDwg }}</b></p>
        <p style="margin-bottom: 10px">共识别到 <b>{{ previewData.total }}</b> 个零件：</p>
        <el-checkbox-group v-model="splitForm.selected_parts">
          <el-checkbox v-for="name in previewData.subDrawings" :key="name" :label="name" :value="name" style="width: 150px; margin-bottom: 5px" />
        </el-checkbox-group>
        <div style="text-align: right; margin-top: 15px">
          <el-button @click="splitStep = 0">上一步</el-button>
          <el-button type="primary" :disabled="splitForm.selected_parts.length === 0" @click="doSplit">执行拆图</el-button>
        </div>
      </div>

      <!-- Step3: 拆图结果 -->
      <div v-if="splitStep === 2">
        <el-table :data="splitResults" border size="small">
          <el-table-column label="零件编号" prop="part_code" />
          <el-table-column label="结果" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.success ? 'success' : 'danger'" size="small">
                {{ row.success ? '成功' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="说明" prop="message" />
        </el-table>
        <div style="text-align: right; margin-top: 15px">
          <el-button type="primary" @click="splitDialogVisible = false">完成</el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listDrawings, previewAssembly, manualSplit, deleteDrawing } from '@/api/entrust/drawing'
import { getToken } from '@/utils/auth'

const loading = ref(false)
const drawingList = ref([])
const total = ref(0)
const queryParams = reactive({
  mold_code: '',
  part_code: '',
  page_num: 1,
  page_size: 20,
})

// 拆图弹窗
const splitDialogVisible = ref(false)
const splitStep = ref(0)
const previewLoading = ref(false)
const splitLoading = ref(false)
const splitForm = reactive({
  mold_code: '',
  selected_parts: [],
})
const previewData = reactive({
  sourceDwg: '',
  subDrawings: [],
  total: 0,
})
const splitResults = ref([])

function getList() {
  loading.value = true
  listDrawings(queryParams).then(res => {
    drawingList.value = res.data?.rows || res.data?.data || []
    total.value = res.data?.total || 0
  }).finally(() => {
    loading.value = false
  })
}

function handleQuery() {
  queryParams.page_num = 1
  getList()
}

function resetQuery() {
  queryParams.mold_code = ''
  queryParams.part_code = ''
  handleQuery()
}

function showSplitDialog() {
  splitStep.value = 0
  splitForm.mold_code = ''
  splitForm.selected_parts = []
  previewData.sourceDwg = ''
  previewData.subDrawings = []
  previewData.total = 0
  splitResults.value = []
  splitDialogVisible.value = true
}

async function doPreview() {
  if (!splitForm.mold_code) {
    ElMessage.warning('请输入模具编号')
    return
  }
  previewLoading.value = true
  try {
    const res = await previewAssembly(splitForm.mold_code)
    const data = res.data?.data || res.data || {}
    if (data.success) {
      previewData.sourceDwg = data.source_dwg || ''
      previewData.subDrawings = data.sub_drawings || []
      previewData.total = data.total || 0
      splitStep.value = 1
    } else {
      ElMessage.error(data.message || '预览失败')
    }
  } catch (e) {
    ElMessage.error('预览失败: ' + (e.message || e))
  } finally {
    previewLoading.value = false
  }
}

async function doSplit() {
  splitLoading.value = true
  try {
    const res = await manualSplit({
      mold_code: splitForm.mold_code,
      part_codes: splitForm.selected_parts.join(','),
    })
    splitResults.value = res.data?.data || []
    splitStep.value = 2
    getList()
  } catch (e) {
    ElMessage.error('拆图失败: ' + (e.message || e))
  } finally {
    splitLoading.value = false
  }
}

function handleDownload(row) {
  const token = getToken()
  if (!token) {
    ElMessage.warning('请先登录')
    return
  }
  const baseURL = import.meta.env.VITE_APP_BASE_API
  fetch(`${baseURL}/entrust/drawing/download/${row.id}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  }).then(res => {
    if (!res.ok) throw new Error('下载失败')
    const disposition = res.headers.get('Content-Disposition') || ''
    const filename = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^;"'\n]+)/)?.[1]
      || disposition.match(/filename="?([^";\n]+)"?/)?.[1]
      || row.fileName || 'drawing.dwg'
    return res.blob().then(blob => ({ blob, filename: decodeURIComponent(filename) }))
  }).then(({ blob, filename }) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }).catch(() => {
    ElMessage.error('图纸下载失败')
  })
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除图纸 ${row.moldCode}/${row.partCode} v${row.version}？`, '提示', { type: 'warning' })
    await deleteDrawing(row.id)
    ElMessage.success('删除成功')
    getList()
  } catch {
    // 取消
  }
}

// 初始化
getList()
</script>
