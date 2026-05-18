<template>
   <div class="app-container">

      <!-- ========== 项目列表视图 ========== -->
      <div v-if="!detailVisible">
         <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
            <el-form-item label="项目名称" prop="name">
               <el-input v-model="queryParams.name" placeholder="请输入项目名称" clearable style="width: 200px" @keyup.enter="handleQuery" />
            </el-form-item>
            <el-form-item label="客户名称" prop="customer">
               <el-input v-model="queryParams.customer" placeholder="请输入客户名称" clearable style="width: 200px" @keyup.enter="handleQuery" />
            </el-form-item>
            <el-form-item label="状态" prop="status">
               <el-select v-model="queryParams.status" placeholder="项目状态" clearable style="width: 200px">
                  <el-option label="草稿" value="drafted" />
                  <el-option label="待审批" value="pending_approval" />
                  <el-option label="已审批" value="confirmed" />
                  <el-option label="进行中" value="in_progress" />
                  <el-option label="已完成" value="completed" />
               </el-select>
            </el-form-item>
            <el-form-item>
               <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
               <el-button icon="Refresh" @click="resetQuery">重置</el-button>
            </el-form-item>
         </el-form>

         <el-row :gutter="10" class="mb8">
            <el-col :span="1.5">
               <el-button type="primary" plain icon="Plus" @click="handleAdd">新增项目</el-button>
            </el-col>
            <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
         </el-row>

         <el-table v-loading="loading" :data="projectList">
            <el-table-column label="项目编号" align="center" prop="project_no" width="140" />
            <el-table-column label="项目名称" align="center" prop="name" :show-overflow-tooltip="true" />
            <el-table-column label="客户名称" align="center" prop="customer" :show-overflow-tooltip="true" />
            <el-table-column label="截止日期" align="center" prop="deadline" width="120" />
            <el-table-column label="状态" align="center" prop="status" width="100">
               <template #default="scope">
                  <el-tag v-if="scope.row.status === 'drafted'" type="info">草稿</el-tag>
                  <el-tag v-else-if="scope.row.status === 'pending_approval'" type="warning">待审批</el-tag>
                  <el-tag v-else-if="scope.row.status === 'confirmed'" type="success">已审批</el-tag>
                  <el-tag v-else-if="scope.row.status === 'in_progress'">进行中</el-tag>
                  <el-tag v-else-if="scope.row.status === 'completed'" type="success">已完成</el-tag>
               </template>
            </el-table-column>
            <el-table-column label="创建时间" align="center" prop="created_at" width="180" />
            <el-table-column label="操作" align="center" width="400" class-name="small-padding fixed-width">
               <template #default="scope">
                  <el-button link type="primary" icon="View" @click="openDetail(scope.row)">详情</el-button>
                  <el-button v-if="scope.row.status === 'drafted'" link type="primary" icon="Edit" @click="handleUpdate(scope.row)">修改</el-button>
                  <el-button v-if="scope.row.status === 'drafted'" link type="warning" icon="Promotion" @click="handleSubmit(scope.row)">提交</el-button>
                  <el-button v-if="scope.row.status === 'pending_approval' && canApprove" link type="success" icon="Check" @click="handleApprove(scope.row)">审批</el-button>
                  <el-button v-if="scope.row.status === 'pending_approval' && canApprove" link type="danger" icon="Close" @click="handleReject(scope.row)">驳回</el-button>
                  <el-button v-if="scope.row.status === 'drafted' || isAdmin" link type="danger" icon="Delete" @click="handleDelete(scope.row)">删除</el-button>
               </template>
            </el-table-column>
         </el-table>

         <pagination v-show="total > 0" :total="total" v-model:page="queryParams.page_num" v-model:limit="queryParams.page_size" @pagination="getList" />

         <!-- 新增/修改项目对话框 -->
         <el-dialog :title="title" v-model="open" width="600px" append-to-body>
            <el-form ref="projectRef" :model="form" :rules="rules" label-width="100px">
               <el-form-item label="项目名称" prop="name">
                  <el-input v-model="form.name" placeholder="请输入项目名称" />
               </el-form-item>
               <el-form-item label="客户名称" prop="customer">
                  <el-input v-model="form.customer" placeholder="请输入客户名称" />
               </el-form-item>
               <el-form-item label="截止日期" prop="deadline">
                  <el-date-picker v-model="form.deadline" type="date" value-format="YYYY-MM-DD" placeholder="选择截止日期" style="width: 100%" />
               </el-form-item>
               <el-form-item label="数量" prop="quantity">
                  <el-input-number v-model="form.quantity" :min="1" />
               </el-form-item>
               <el-form-item label="描述" prop="description">
                  <el-input v-model="form.description" type="textarea" placeholder="请输入项目描述" />
               </el-form-item>
            </el-form>
            <template #footer>
               <el-button type="primary" @click="submitForm">确 定</el-button>
               <el-button @click="cancel">取 消</el-button>
            </template>
         </el-dialog>
      </div>

      <!-- ========== 项目详情视图 ========== -->
      <div v-if="detailVisible">
         <!-- 返回 + 项目信息 -->
         <el-page-header @back="closeDetail" content="项目详情" class="mb8" />
         <el-descriptions :column="3" border class="mb8" v-if="currentProject">
            <el-descriptions-item label="项目编号">{{ currentProject.project_no }}</el-descriptions-item>
            <el-descriptions-item label="项目名称">{{ currentProject.name }}</el-descriptions-item>
            <el-descriptions-item label="客户">{{ currentProject.customer }}</el-descriptions-item>
            <el-descriptions-item label="截止日期">{{ currentProject.deadline }}</el-descriptions-item>
            <el-descriptions-item label="状态">
               <el-tag v-if="currentProject.status === 'drafted'" type="info">草稿</el-tag>
               <el-tag v-else-if="currentProject.status === 'pending_approval'" type="warning">待审批</el-tag>
               <el-tag v-else-if="currentProject.status === 'confirmed'" type="success">已审批</el-tag>
               <el-tag v-else-if="currentProject.status === 'in_progress'">进行中</el-tag>
               <el-tag v-else-if="currentProject.status === 'completed'" type="success">已完成</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="描述">{{ currentProject.description || '-' }}</el-descriptions-item>
         </el-descriptions>

         <!-- Tabs: 模具 / 零件 / 图纸 -->
         <el-tabs v-model="activeTab">
            <!-- 模具套 Tab -->
            <el-tab-pane label="模具套" name="molds">
               <el-button type="primary" plain icon="Plus" @click="moldDialogVisible = true" class="mb8">添加模具套</el-button>
               <el-table :data="moldList" v-loading="moldLoading" border>
                  <el-table-column label="ID" prop="id" width="80" />
                  <el-table-column label="模具套名称" prop="name" />
                  <el-table-column label="排序号" prop="sort_no" width="100" />
                  <el-table-column label="备注" prop="remark" :show-overflow-tooltip="true" />
                  <el-table-column label="操作" width="100" align="center">
                     <template #default="scope">
                        <el-button link type="danger" icon="Delete" @click="handleDeleteMold(scope.row)">删除</el-button>
                     </template>
                  </el-table-column>
               </el-table>
               <el-dialog title="添加模具套" v-model="moldDialogVisible" width="400px" append-to-body>
                  <el-form :model="moldForm" label-width="100px">
                     <el-form-item label="名称">
                        <el-input v-model="moldForm.name" placeholder="如：冲压模P4" />
                     </el-form-item>
                     <el-form-item label="排序号">
                        <el-input-number v-model="moldForm.sort_no" :min="0" />
                     </el-form-item>
                     <el-form-item label="备注">
                        <el-input v-model="moldForm.remark" type="textarea" />
                     </el-form-item>
                  </el-form>
                  <template #footer>
                     <el-button type="primary" @click="submitMold">确 定</el-button>
                     <el-button @click="moldDialogVisible = false">取 消</el-button>
                  </template>
               </el-dialog>
            </el-tab-pane>

            <!-- 零件 Tab -->
            <el-tab-pane label="零件" name="parts">
               <el-button type="primary" plain icon="Plus" @click="openPartDialog()" class="mb8">添加零件</el-button>
               <el-table :data="partList" v-loading="partLoading" border>
                  <el-table-column label="ID" prop="id" width="60" />
                  <el-table-column label="零件编号" prop="part_no" width="140" />
                  <el-table-column label="零件名称" prop="part_name" />
                  <el-table-column label="材料" prop="material" width="100" />
                  <el-table-column label="数量" prop="qty" width="70" />
                  <el-table-column label="所需工艺" min-width="200">
                     <template #default="scope">
                        <el-tag v-for="pm in (scope.row.process_method_ids || [])" :key="pm" size="small" class="mr4">
                           {{ getProcessName(pm) }}
                        </el-tag>
                        <span v-if="!scope.row.process_method_ids || scope.row.process_method_ids.length === 0" style="color:#999">未设置</span>
                     </template>
                  </el-table-column>
                  <el-table-column label="操作" width="140" align="center">
                     <template #default="scope">
                        <el-button link type="primary" icon="Edit" @click="openPartDialog(scope.row)">编辑</el-button>
                        <el-button link type="danger" icon="Delete" @click="handleDeletePart(scope.row)">删除</el-button>
                     </template>
                  </el-table-column>
               </el-table>

               <!-- 零件对话框 -->
               <el-dialog :title="partDialogTitle" v-model="partDialogVisible" width="600px" append-to-body>
                  <el-form ref="partFormRef" :model="partForm" :rules="partRules" label-width="100px">
                     <el-row :gutter="20">
                        <el-col :span="12">
                           <el-form-item label="零件编号" prop="part_no">
                              <el-input v-model="partForm.part_no" placeholder="如 B2-02" />
                           </el-form-item>
                        </el-col>
                        <el-col :span="12">
                           <el-form-item label="零件名称" prop="part_name">
                              <el-input v-model="partForm.part_name" placeholder="如 下模板" />
                           </el-form-item>
                        </el-col>
                     </el-row>
                     <el-row :gutter="20">
                        <el-col :span="12">
                           <el-form-item label="材料">
                              <el-input v-model="partForm.material" placeholder="如 Cr12mov" />
                           </el-form-item>
                        </el-col>
                        <el-col :span="12">
                           <el-form-item label="数量" prop="qty">
                              <el-input-number v-model="partForm.qty" :min="1" style="width: 100%" />
                           </el-form-item>
                        </el-col>
                     </el-row>
                     <el-form-item label="所属模具">
                        <el-select v-model="partForm.mold_id" placeholder="选择模具套（可选）" clearable style="width: 100%">
                           <el-option v-for="m in moldList" :key="m.id" :label="m.name" :value="m.id" />
                        </el-select>
                     </el-form-item>
                     <el-form-item label="规格">
                        <el-input v-model="partForm.spec" placeholder="如 1330 x 1130 x 76" />
                     </el-form-item>
                     <el-form-item label="所需工艺" prop="process_method_ids">
                        <el-select v-model="partForm.process_method_ids" multiple filterable placeholder="选择需要的加工工序" style="width: 100%">
                           <el-option v-for="pm in processMethodOptions" :key="pm.id" :label="pm.name" :value="pm.id" />
                        </el-select>
                     </el-form-item>
                  </el-form>
                  <template #footer>
                     <el-button type="primary" @click="submitPart">确 定</el-button>
                     <el-button @click="partDialogVisible = false">取 消</el-button>
                  </template>
               </el-dialog>
            </el-tab-pane>

            <!-- 图纸 Tab -->
            <el-tab-pane label="图纸/附件" name="attachments">
               <el-upload
                  :action="uploadUrl"
                  :headers="uploadHeaders"
                  :data="{ category: 'drawing', related_type: 'project' }"
                  :on-success="handleUploadSuccess"
                  :on-error="handleUploadError"
                  :show-file-list="false"
                  multiple
                  class="mb8"
               >
                  <el-button type="primary" plain icon="Upload">上传图纸</el-button>
               </el-upload>
               <el-table :data="attachmentList" v-loading="attachmentLoading" border>
                  <el-table-column label="文件名" prop="file_name" :show-overflow-tooltip="true" />
                  <el-table-column label="大小" width="120" align="center">
                     <template #default="scope">{{ formatFileSize(scope.row.file_size) }}</template>
                  </el-table-column>
                  <el-table-column label="上传时间" prop="created_at" width="180" align="center" />
               </el-table>
            </el-tab-pane>

            <!-- 候选加工商 Tab -->
            <el-tab-pane label="候选加工商" name="match">
               <div v-if="currentProject.status === 'drafted' || currentProject.status === 'pending_approval'" style="text-align:center;padding:40px;color:#999">
                  <template v-if="currentProject.status === 'drafted'">项目尚未提交，请先在列表页点击"提交"按钮</template>
                  <template v-else>项目已提交，等待经理审批通过后将展示候选加工方</template>
               </div>
               <div v-else>
                  <el-button type="primary" plain icon="Refresh" @click="loadMatchResult" class="mb8">刷新匹配</el-button>
                  <el-button v-if="noPriceSuppliers.length > 0" type="warning" plain icon="Promotion" @click="openBatchInquiry" class="mb8">批量询价（{{ noPriceSuppliers.length }}个无价格加工方）</el-button>

                  <!-- 所需工艺摘要 -->
                  <div v-if="matchResult.required_processes && matchResult.required_processes.length" class="mb8">
                     <span style="font-weight:bold">本项目所需工艺：</span>
                     <el-tag v-for="p in matchResult.required_processes" :key="p.id" size="small" class="mr4">{{ p.name }}</el-tag>
                  </div>

                  <!-- A组：全覆盖 -->
                  <div v-if="matchResult.groups && matchResult.groups.A && matchResult.groups.A.length">
                     <h4 style="color:#67C23A">可完成所有工艺</h4>
                     <el-table :data="matchResult.groups.A" border size="small" class="mb8">
                        <el-table-column label="加工方" prop="supplier_name" width="160" />
                        <el-table-column label="地区" width="100" align="center">
                           <template #default="scope">
                              <el-tag v-if="scope.row.province === '山东' && scope.row.city === '青岛'" type="success" size="small">同城</el-tag>
                              <el-tag v-else-if="scope.row.province === '山东'" size="small">同省</el-tag>
                              <el-tag v-else type="info" size="small">外地</el-tag>
                           </template>
                        </el-table-column>
                        <el-table-column label="参考单价" width="100" align="center">
                           <template #default="scope">
                              <span v-if="scope.row.has_price" style="color:#67C23A;font-weight:bold">¥{{ scope.row.base_price }}</span>
                              <el-tag v-else type="info" size="small">待询价</el-tag>
                           </template>
                        </el-table-column>
                        <el-table-column label="覆盖率" width="80" align="center">
                           <template #default="scope">{{ (scope.row.coverage_ratio * 100).toFixed(0) }}%</template>
                        </el-table-column>
                        <el-table-column label="联系人" prop="contact_name" width="100" />
                        <el-table-column label="电话" prop="contact_phone" width="130" />
                        <el-table-column label="匹配工艺">
                           <template #default="scope">
                              <el-tag v-for="m in scope.row.matched_processes" :key="m.id" size="small" type="success" class="mr4">{{ m.name }}</el-tag>
                           </template>
                        </el-table-column>
                        <el-table-column label="操作" width="80" align="center">
                           <template #default="scope">
                              <router-link :to="{ path: '/entrust/chat', query: { supplier_id: scope.row.supplier_id } }">
                                 <el-button link type="success" size="small">对话</el-button>
                              </router-link>
                           </template>
                        </el-table-column>
                     </el-table>
                  </div>

                  <!-- B组 -->
                  <div v-if="matchResult.groups && matchResult.groups.B && matchResult.groups.B.length">
                     <h4 style="color:#E6A23C">可完成部分工艺</h4>
                     <el-table :data="matchResult.groups.B" border size="small" class="mb8">
                        <el-table-column label="加工方" prop="supplier_name" width="160" />
                        <el-table-column label="地区" width="100" align="center">
                           <template #default="scope">
                              <el-tag v-if="scope.row.province === '山东' && scope.row.city === '青岛'" type="success" size="small">同城</el-tag>
                              <el-tag v-else-if="scope.row.province === '山东'" size="small">同省</el-tag>
                              <el-tag v-else type="info" size="small">外地</el-tag>
                           </template>
                        </el-table-column>
                        <el-table-column label="参考单价" width="100" align="center">
                           <template #default="scope">
                              <span v-if="scope.row.has_price" style="color:#67C23A;font-weight:bold">¥{{ scope.row.base_price }}</span>
                              <el-tag v-else type="info" size="small">待询价</el-tag>
                           </template>
                        </el-table-column>
                        <el-table-column label="覆盖率" width="80" align="center">
                           <template #default="scope">{{ (scope.row.coverage_ratio * 100).toFixed(0) }}%</template>
                        </el-table-column>
                        <el-table-column label="联系人" prop="contact_name" width="100" />
                        <el-table-column label="电话" prop="contact_phone" width="130" />
                        <el-table-column label="匹配工艺">
                           <template #default="scope">
                              <el-tag v-for="m in scope.row.matched_processes" :key="m.id" size="small" type="success" class="mr4">{{ m.name }}</el-tag>
                           </template>
                        </el-table-column>
                        <el-table-column label="缺失工艺">
                           <template #default="scope">
                              <el-tag v-for="m in scope.row.missing_processes" :key="m.id" size="small" type="danger" class="mr4">{{ m.name }}</el-tag>
                           </template>
                        </el-table-column>
                        <el-table-column label="操作" width="80" align="center">
                           <template #default="scope">
                              <router-link :to="{ path: '/entrust/chat', query: { supplier_id: scope.row.supplier_id } }">
                                 <el-button link type="success" size="small">对话</el-button>
                              </router-link>
                           </template>
                        </el-table-column>
                     </el-table>
                  </div>

                  <!-- C组 -->
                  <div v-if="matchResult.groups && matchResult.groups.C && matchResult.groups.C.length">
                     <h4 style="color:#F56C6C">可完成单个工艺</h4>
                     <el-table :data="matchResult.groups.C" border size="small" class="mb8">
                        <el-table-column label="加工方" prop="supplier_name" width="160" />
                        <el-table-column label="地区" width="100" align="center">
                           <template #default="scope">
                              <el-tag v-if="scope.row.province === '山东' && scope.row.city === '青岛'" type="success" size="small">同城</el-tag>
                              <el-tag v-else-if="scope.row.province === '山东'" size="small">同省</el-tag>
                              <el-tag v-else type="info" size="small">外地</el-tag>
                           </template>
                        </el-table-column>
                        <el-table-column label="参考单价" width="100" align="center">
                           <template #default="scope">
                              <span v-if="scope.row.has_price" style="color:#67C23A;font-weight:bold">¥{{ scope.row.base_price }}</span>
                              <el-tag v-else type="info" size="small">待询价</el-tag>
                           </template>
                        </el-table-column>
                        <el-table-column label="覆盖率" width="80" align="center">
                           <template #default="scope">{{ (scope.row.coverage_ratio * 100).toFixed(0) }}%</template>
                        </el-table-column>
                        <el-table-column label="匹配工艺">
                           <template #default="scope">
                              <el-tag v-for="m in scope.row.matched_processes" :key="m.id" size="small" type="success" class="mr4">{{ m.name }}</el-tag>
                           </template>
                        </el-table-column>
                        <el-table-column label="缺失工艺">
                           <template #default="scope">
                              <el-tag v-for="m in scope.row.missing_processes" :key="m.id" size="small" type="danger" class="mr4">{{ m.name }}</el-tag>
                           </template>
                        </el-table-column>
                        <el-table-column label="操作" width="80" align="center">
                           <template #default="scope">
                              <router-link :to="{ path: '/entrust/chat', query: { supplier_id: scope.row.supplier_id } }">
                                 <el-button link type="success" size="small">对话</el-button>
                              </router-link>
                           </template>
                        </el-table-column>
                     </el-table>
                  </div>

                  <div v-if="!matchResult.groups || (!matchResult.groups.A?.length && !matchResult.groups.B?.length && !matchResult.groups.C?.length)" style="text-align:center;padding:40px;color:#999">
                     未找到匹配的加工方，请检查是否已添加加工方并设置能力标签
                  </div>
               </div>
            </el-tab-pane>
         </el-tabs>
      </div>

      <!-- 批量询价入口对话框（只有两个按钮） -->
      <el-dialog title="批量询价" v-model="batchInquiryOpen" width="400px" append-to-body>
         <div style="text-align:center;padding:20px 0">
            <p style="margin-bottom:20px;font-size:15px">将向选中的加工方发送询价单</p>
         </div>
         <template #footer>
            <el-button type="primary" @click="openInquiryForm">去生成询价单</el-button>
            <el-button @click="batchInquiryOpen = false">取消</el-button>
         </template>
      </el-dialog>

      <!-- 询价单填写表单 -->
      <el-dialog title="询价单" v-model="inquiryFormOpen" width="900px" append-to-body top="5vh">
         <el-form ref="inquiryFormRef" :model="inquiryForm" :rules="inquiryRules" label-width="110px">
            <el-row :gutter="20">
               <el-col :span="12">
                  <el-form-item label="客户" prop="customer_name">
                     <el-input v-model="inquiryForm.customer_name" placeholder="我方公司名称" />
                  </el-form-item>
               </el-col>
               <el-col :span="12">
                  <el-form-item label="订单号" prop="order_no">
                     <el-input v-model="inquiryForm.order_no" placeholder="请输入订单号" />
                  </el-form-item>
               </el-col>
            </el-row>
            <el-row :gutter="20">
               <el-col :span="8">
                  <el-form-item label="联系人">
                     <el-input v-model="inquiryForm.customer_contact" placeholder="联系人" />
                  </el-form-item>
               </el-col>
               <el-col :span="8">
                  <el-form-item label="电话">
                     <el-input v-model="inquiryForm.customer_phone" placeholder="电话" />
                  </el-form-item>
               </el-col>
               <el-col :span="8">
                  <el-form-item label="询价日期">
                     <el-date-picker v-model="inquiryForm.inquiry_date" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" style="width:100%" />
                  </el-form-item>
               </el-col>
            </el-row>
            <el-row :gutter="20">
               <el-col :span="8">
                  <el-form-item label="截止报价日期" prop="deadline">
                     <el-date-picker v-model="inquiryForm.deadline" type="date" value-format="YYYY-MM-DD" placeholder="截止日期" style="width:100%" />
                  </el-form-item>
               </el-col>
               <el-col :span="8">
                  <el-form-item label="交付日期" prop="delivery_date">
                     <el-date-picker v-model="inquiryForm.delivery_date" type="date" value-format="YYYY-MM-DD" placeholder="交付日期" style="width:100%" />
                  </el-form-item>
               </el-col>
            </el-row>

            <!-- 询价范围（从项目零件自动导入） -->
            <el-divider content-position="left">询价范围（自动导入零件信息）</el-divider>
            <div class="inquiry-parts-table">
               <div class="inquiry-table-header">
                  <span class="col-part-no">零件编号</span>
                  <span class="col-part-name">零件名称</span>
                  <span class="col-material">材料</span>
                  <span class="col-qty">数量</span>
                  <span class="col-spec">规格</span>
                  <span class="col-process">所需工艺</span>
               </div>
               <div v-for="(item, idx) in inquiryForm.scope_json" :key="idx" class="inquiry-table-row">
                  <span class="col-part-no">{{ item.part_no }}</span>
                  <span class="col-part-name">{{ item.part_name }}</span>
                  <span class="col-material">{{ item.material }}</span>
                  <span class="col-qty">{{ item.qty }}</span>
                  <span class="col-spec">{{ item.spec }}</span>
                  <span class="col-process">
                     <el-tag v-for="p in (item.processes || [])" :key="p" size="small" class="mr4">{{ p }}</el-tag>
                  </span>
               </div>
            </div>
            <div class="inquiry-note">
               <p>说明：1. 以上零件信息由项目自动导入，如需调整请返回项目零件管理修改</p>
            </div>

            <!-- 选择加工方 -->
            <el-divider content-position="left">选择加工方</el-divider>
            <el-table :data="allMatchedSuppliers" border size="small" @selection-change="handleSupplierSelect" ref="supplierTableRef">
               <el-table-column type="selection" width="50" />
               <el-table-column label="加工方" prop="supplier_name" width="160" />
               <el-table-column label="地区" width="100" align="center">
                  <template #default="scope">
                     <span>{{ scope.row.province }} {{ scope.row.city }}</span>
                  </template>
               </el-table-column>
               <el-table-column label="联系人" prop="contact_name" width="100" />
               <el-table-column label="电话" prop="contact_phone" width="130" />
               <el-table-column label="覆盖率" width="80" align="center">
                  <template #default="scope">{{ (scope.row.coverage_ratio * 100).toFixed(0) }}%</template>
               </el-table-column>
            </el-table>
         </el-form>
         <template #footer>
            <el-button type="primary" @click="submitInquiryForm" :disabled="selectedSuppliers.length === 0">发送询价</el-button>
            <el-button @click="inquiryFormOpen = false">取消</el-button>
         </template>
      </el-dialog>
   </div>
</template>

<script setup name="Project">
import { listProject, getProject, addProject, updateProject, delProject,
         listMold, addMold, delMold,
         listPart, addPart, updatePart, delPart,
         listProcessMethods, listAttachments,
         submitProject, approveProject, rejectProject, getMatchResult } from "@/api/entrust/project";
import { addInquiry, sendInquiry } from "@/api/entrust/inquiry";
import { getToken } from '@/utils/auth'
import useUserStore from '@/store/modules/user'
import * as XLSX from 'xlsx'

const { proxy } = getCurrentInstance();
const router = useRouter();
const userStore = useUserStore();
const canApprove = computed(() => {
   const roles = userStore.roles || [];
   return roles.includes('admin') || roles.includes('manager');
});
const isAdmin = computed(() => {
   const roles = userStore.roles || [];
   return roles.includes('admin');
});

// ---- 列表 ----
const projectList = ref([]);
const open = ref(false);
const loading = ref(true);
const showSearch = ref(true);
const total = ref(0);
const title = ref("");

const data = reactive({
   form: {},
   queryParams: { page_num: 1, page_size: 10, name: undefined, customer: undefined, status: undefined },
   rules: {
      name: [{ required: true, message: "项目名称不能为空", trigger: "blur" }],
      customer: [{ required: true, message: "客户名称不能为空", trigger: "blur" }],
   },
});
const { queryParams, form, rules } = toRefs(data);

function getList() {
   loading.value = true;
   listProject(queryParams.value).then(response => {
      projectList.value = response.rows;
      total.value = response.total;
      loading.value = false;
   });
}

function cancel() { open.value = false; reset(); }
function reset() {
   form.value = { name: undefined, customer: undefined, deadline: undefined, quantity: 1, description: undefined };
   proxy.resetForm("projectRef");
}
function handleQuery() { queryParams.value.page_num = 1; getList(); }
function resetQuery() { proxy.resetForm("queryRef"); handleQuery(); }

function handleAdd() { reset(); open.value = true; title.value = "新增项目"; }
function handleUpdate(row) {
   reset();
   getProject(row.id).then(response => {
      form.value = response.data;
      open.value = true;
      title.value = "修改项目";
   });
}

function submitForm() {
   proxy.$refs["projectRef"].validate(valid => {
      if (valid) {
         if (form.value.id != undefined) {
            updateProject(form.value.id, form.value).then(() => {
               proxy.$modal.msgSuccess("修改成功");
               open.value = false;
               getList();
            });
         } else {
            addProject(form.value).then(() => {
               proxy.$modal.msgSuccess("新增成功");
               open.value = false;
               getList();
            });
         }
      }
   });
}

function handleDelete(row) {
   proxy.$modal.confirm('是否确认删除项目"' + row.name + '"？').then(() => delProject(row.id)).then(() => {
      getList(); proxy.$modal.msgSuccess("删除成功");
   }).catch(() => {});
}

function handleSubmit(row) {
   proxy.$modal.confirm('确认提交项目"' + row.name + '"？提交后将等待经理审批。').then(() => {
      return submitProject(row.id);
   }).then(res => {
      proxy.$modal.msgSuccess("提交成功，等待审批");
      getList();
      if (detailVisible.value && currentProject.value && currentProject.value.id === row.id) {
         currentProject.value.status = 'pending_approval';
      }
   }).catch(() => {});
}

function handleApprove(row) {
   proxy.$modal.confirm('确认审批通过项目"' + row.name + '"？通过后将触发加工方匹配。').then(() => {
      return approveProject(row.id);
   }).then(res => {
      proxy.$modal.msgSuccess("审批通过");
      getList();
      if (detailVisible.value && currentProject.value && currentProject.value.id === row.id) {
         currentProject.value.status = 'confirmed';
         loadMatchResult();
      }
   }).catch(() => {});
}

function handleReject(row) {
   proxy.$modal.confirm('确认驳回项目"' + row.name + '"？驳回后可重新编辑提交。').then(() => {
      return rejectProject(row.id);
   }).then(res => {
      proxy.$modal.msgSuccess("已驳回");
      getList();
      if (detailVisible.value && currentProject.value && currentProject.value.id === row.id) {
         currentProject.value.status = 'drafted';
      }
   }).catch(() => {});
}

// ---- 详情视图 ----
const detailVisible = ref(false);
const currentProject = ref(null);
const activeTab = ref('molds');

// 模具
const moldList = ref([]);
const moldLoading = ref(false);
const moldDialogVisible = ref(false);
const moldForm = ref({ name: '', sort_no: 0, remark: '' });

function loadMolds() {
   moldLoading.value = true;
   listMold(currentProject.value.id).then(res => {
      moldList.value = res.data || [];
      moldLoading.value = false;
   });
}

function submitMold() {
   addMold(currentProject.value.id, moldForm.value).then(() => {
      proxy.$modal.msgSuccess("添加成功");
      moldDialogVisible.value = false;
      moldForm.value = { name: '', sort_no: 0, remark: '' };
      loadMolds();
   });
}

function handleDeleteMold(row) {
   proxy.$modal.confirm('确认删除模具套"' + row.name + '"？').then(() => delMold(row.id)).then(() => {
      loadMolds(); proxy.$modal.msgSuccess("删除成功");
   }).catch(() => {});
}

// 零件
const partList = ref([]);
const partLoading = ref(false);
const partDialogVisible = ref(false);
const partDialogTitle = ref("添加零件");
const editingPartId = ref(null);
const partForm = ref({ part_no: '', part_name: '', material: '', qty: 1, spec: '', mold_id: undefined, process_method_ids: [] });
const partRules = {
   part_no: [{ required: true, message: "零件编号不能为空", trigger: "blur" }],
   part_name: [{ required: true, message: "零件名称不能为空", trigger: "blur" }],
};

// 工艺方法
const processMethodOptions = ref([]);

function loadProcessMethods() {
   listProcessMethods().then(res => { processMethodOptions.value = res.data || []; });
}

function getProcessName(id) {
   const pm = processMethodOptions.value.find(p => p.id === id);
   return pm ? pm.name : id;
}

function loadParts() {
   partLoading.value = true;
   listPart(currentProject.value.id).then(res => {
      partList.value = res.data || [];
      partLoading.value = false;
   });
}

function openPartDialog(row) {
   if (row) {
      partDialogTitle.value = "编辑零件";
      editingPartId.value = row.id;
      partForm.value = { ...row };
   } else {
      partDialogTitle.value = "添加零件";
      editingPartId.value = null;
      partForm.value = { part_no: '', part_name: '', material: '', qty: 1, spec: '', mold_id: undefined, process_method_ids: [] };
   }
   partDialogVisible.value = true;
}

function submitPart() {
   proxy.$refs["partFormRef"].validate(valid => {
      if (valid) {
         const pid = currentProject.value.id;
         if (editingPartId.value) {
            updatePart(editingPartId.value, partForm.value).then(() => {
               proxy.$modal.msgSuccess("修改成功");
               partDialogVisible.value = false;
               loadParts();
            });
         } else {
            addPart(pid, partForm.value).then(() => {
               proxy.$modal.msgSuccess("添加成功");
               partDialogVisible.value = false;
               loadParts();
            });
         }
      }
   });
}

function handleDeletePart(row) {
   proxy.$modal.confirm('确认删除零件"' + row.part_name + '"？').then(() => delPart(row.id)).then(() => {
      loadParts(); proxy.$modal.msgSuccess("删除成功");
   }).catch(() => {});
}

// 附件
const attachmentList = ref([]);
const attachmentLoading = ref(false);
const uploadUrl = ref('');
const uploadHeaders = ref({});

function loadAttachments() {
   attachmentLoading.value = true;
   listAttachments(currentProject.value.id, 'project', currentProject.value.id).then(res => {
      attachmentList.value = res.data || [];
      attachmentLoading.value = false;
   });
}

function handleUploadSuccess() {
   proxy.$modal.msgSuccess("上传成功");
   loadAttachments();
}

function handleUploadError() {
   proxy.$modal.msgError("上传失败");
}

function formatFileSize(bytes) {
   if (!bytes) return '-';
   if (bytes < 1024) return bytes + ' B';
   if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
   return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

// 匹配结果
const matchResult = ref({ required_processes: [], groups: { A: [], B: [], C: [] } });

// 无价格加工方列表（用于批量询价）
const noPriceSuppliers = computed(() => {
   const all = [];
   for (const group of ['A', 'B', 'C']) {
      const items = matchResult.value.groups?.[group] || [];
      for (const s of items) {
         if (!s.has_price) {
            all.push(s);
         }
      }
   }
   return all;
});

// 所有匹配加工方（用于询价选择）
const allMatchedSuppliers = computed(() => {
   const all = [];
   for (const group of ['A', 'B', 'C']) {
      const items = matchResult.value.groups?.[group] || [];
      for (const s of items) {
         all.push(s);
      }
   }
   return all;
});

// 批量询价入口
const batchInquiryOpen = ref(false);
const inquiryFormOpen = ref(false);
const selectedSuppliers = ref([]);
const supplierTableRef = ref(null);

const inquiryForm = ref({
   title: '',
   customer_name: '',
   customer_contact: '',
   customer_phone: '',
   order_no: '',
   inquiry_date: '',
   deadline: '',
   delivery_date: '',
   scope_json: [],
});
const inquiryRules = {
   customer_name: [{ required: true, message: '请填写客户名称', trigger: 'blur' }],
   deadline: [{ required: true, message: '请选择截止报价日期', trigger: 'change' }],
   delivery_date: [{ required: true, message: '请选择交付日期', trigger: 'change' }],
};

function openBatchInquiry() {
   batchInquiryOpen.value = true;
}

function openInquiryForm() {
   batchInquiryOpen.value = false;
   // 自动导入零件信息作为询价范围
   const scope = partList.value.map(p => ({
      part_no: p.part_no || '',
      part_name: p.part_name || '',
      material: p.material || '',
      qty: p.qty || 1,
      spec: p.spec || '',
      processes: (p.process_method_ids || []).map(id => getProcessName(id)),
   }));
   // 截止日期默认为询价日期后3天
   const today = new Date();
   const deadlineDate = new Date(today);
   deadlineDate.setDate(deadlineDate.getDate() + 3);
   inquiryForm.value = {
      title: currentProject.value.name + ' - 加工询价',
      customer_name: '青岛瑞利杰金属有限公司',
      customer_contact: '',
      customer_phone: '',
      order_no: '',
      inquiry_date: today.toISOString().slice(0, 10),
      deadline: deadlineDate.toISOString().slice(0, 10),
      delivery_date: '',
      scope_json: scope,
   };
   selectedSuppliers.value = [];
   inquiryFormOpen.value = true;
}

function handleSupplierSelect(selection) {
   selectedSuppliers.value = selection;
}

function submitInquiryForm() {
   proxy.$refs['inquiryFormRef'].validate(valid => {
      if (!valid) return;
      if (selectedSuppliers.value.length === 0) {
         proxy.$modal.msgWarning('请至少选择一个加工方');
         return;
      }
      const supplierIds = selectedSuppliers.value.map(s => s.supplier_id);
      const data = { ...inquiryForm.value, project_id: currentProject.value.id };
      addInquiry(data).then(res => {
         const inquiryId = res.data.id;
         return sendInquiry(inquiryId, supplierIds);
      }).then(() => {
         proxy.$modal.msgSuccess('询价单已创建并发送给 ' + supplierIds.length + ' 个加工方');
         inquiryFormOpen.value = false;
      });
   });
}

function exportInquiryXlsx() {
   const wb = XLSX.utils.book_new();
   // 表头信息
   const headerData = [
      ['询价单'],
      ['客户', inquiryForm.value.customer_name, '', '订单号', inquiryForm.value.order_no],
      ['联系人', inquiryForm.value.customer_contact, '', '电话', inquiryForm.value.customer_phone],
      ['询价日期', inquiryForm.value.inquiry_date, '', '截止日期', inquiryForm.value.deadline],
      ['交付日期', inquiryForm.value.delivery_date],
      [],
      ['零件编号', '零件名称', '材料', '数量', '规格', '所需工艺'],
   ];
   // 零件明细
   for (const item of (inquiryForm.value.scope_json || [])) {
      headerData.push([
         item.part_no, item.part_name, item.material, item.qty, item.spec,
         (item.processes || []).join('、'),
      ]);
   }
   const ws = XLSX.utils.aoa_to_sheet(headerData);
   ws['!cols'] = [{ wch: 12 }, { wch: 16 }, { wch: 10 }, { wch: 8 }, { wch: 18 }, { wch: 30 }];
   ws['!merges'] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 5 } }];
   XLSX.utils.book_append_sheet(wb, ws, '询价单');
   XLSX.writeFile(wb, '询价单_' + (inquiryForm.value.order_no || inquiryForm.value.title) + '.xlsx');
}

function loadMatchResult() {
   getMatchResult(currentProject.value.id).then(res => {
      matchResult.value = res.data || { required_processes: [], groups: { A: [], B: [], C: [] } };
   });
}

// 打开详情
function openDetail(row) {
   currentProject.value = row;
   detailVisible.value = true;
   activeTab.value = 'molds';
   loadMolds();
   loadParts();
   loadAttachments();
   loadProcessMethods();
   if (row.status === 'confirmed') {
      loadMatchResult();
   }
   uploadUrl.value = import.meta.env.VITE_APP_BASE_API + '/entrust/project/' + row.id + '/attachments';
   uploadHeaders.value = { Authorization: 'Bearer ' + getToken() };
}

function closeDetail() {
   detailVisible.value = false;
   currentProject.value = null;
}

getList();
</script>

<style scoped>
.mr4 { margin-right: 4px; }
.mb8 { margin-bottom: 8px; }
.inquiry-parts-table { border: 1px solid #dcdfe6; border-radius: 4px; overflow: hidden; margin-bottom: 8px; }
.inquiry-table-header {
   display: flex; background: #409EFF; color: #fff; font-weight: bold; font-size: 13px; padding: 8px 0;
}
.inquiry-table-row {
   display: flex; border-top: 1px solid #ebeef5; font-size: 13px; padding: 8px 0;
}
.inquiry-table-row:nth-child(even) { background: #fafafa; }
.col-part-no { width: 120px; text-align: center; }
.col-part-name { flex: 1; text-align: center; }
.col-material { width: 100px; text-align: center; }
.col-qty { width: 70px; text-align: center; }
.col-spec { width: 140px; text-align: center; }
.col-process { min-width: 200px; text-align: center; }
.inquiry-note { font-size: 12px; color: #909399; line-height: 1.8; padding: 4px 0 8px; }
</style>
