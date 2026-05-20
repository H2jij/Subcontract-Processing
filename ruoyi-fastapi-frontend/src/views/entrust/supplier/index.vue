<template>
   <div class="app-container">
      <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
         <el-form-item label="名称" prop="name">
            <el-input v-model="queryParams.name" placeholder="请输入名称" clearable style="width: 200px" @keyup.enter="handleQuery" />
         </el-form-item>
         <el-form-item label="类型" prop="supplier_type">
            <el-select v-model="queryParams.supplier_type" placeholder="全部类型" clearable style="width: 120px">
               <el-option label="加工方" value="processor" />
               <el-option label="材料方" value="material" />
               <el-option label="其他" value="other" />
            </el-select>
         </el-form-item>
         <el-form-item label="分类" prop="category">
            <el-input v-model="queryParams.category" placeholder="请输入分类" clearable style="width: 150px" @keyup.enter="handleQuery" />
         </el-form-item>
         <el-form-item label="状态" prop="status">
            <el-select v-model="queryParams.status" placeholder="状态" clearable style="width: 100px">
               <el-option label="启用" value="active" />
               <el-option label="停用" value="disabled" />
            </el-select>
         </el-form-item>
         <el-form-item>
            <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
            <el-button icon="Refresh" @click="resetQuery">重置</el-button>
         </el-form-item>
      </el-form>

      <el-row :gutter="10" class="mb8">
         <el-col :span="1.5">
            <el-button type="primary" plain icon="Plus" @click="handleAdd">新增</el-button>
         </el-col>
         <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
      </el-row>

      <el-table v-loading="loading" :data="supplierList" class="wrap-table">
         <el-table-column label="编号" align="center" prop="id" width="60" />
         <el-table-column label="名称" prop="name" min-width="180" />
         <el-table-column label="类型" align="center" width="80">
            <template #default="scope">
               <el-tag v-if="scope.row.supplier_type === 'processor'" type="primary" size="small">加工方</el-tag>
               <el-tag v-else-if="scope.row.supplier_type === 'material'" type="warning" size="small">材料方</el-tag>
               <el-tag v-else type="info" size="small">其他</el-tag>
            </template>
         </el-table-column>
         <el-table-column label="分类" align="center" prop="category" width="90" />
         <el-table-column label="法定代表人" align="center" prop="legal_rep" width="90" />
         <el-table-column label="联系人" align="center" prop="contact_name" width="80" />
         <el-table-column label="电话" align="center" prop="contact_phone" width="120" />
         <el-table-column label="邮箱" prop="contact_email" min-width="160" show-overflow-tooltip />
         <el-table-column label="信用代码" prop="credit_code" min-width="160" show-overflow-tooltip />
         <el-table-column label="状态" align="center" prop="status" width="70">
            <template #default="scope">
               <el-tag v-if="scope.row.status === 'active'" type="success">启用</el-tag>
               <el-tag v-else type="info">停用</el-tag>
            </template>
         </el-table-column>
         <el-table-column v-if="isAdmin" label="关联账号" align="center" width="120">
            <template #default="scope">
               <el-tag v-if="scope.row.link_username" type="success" size="small">{{ scope.row.link_username }}</el-tag>
               <span v-else style="color:#999">未关联</span>
            </template>
         </el-table-column>
         <el-table-column label="操作" align="center" width="250" class-name="small-padding fixed-width">
            <template #default="scope">
               <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)">修改</el-button>
               <el-button link type="primary" icon="Delete" @click="handleDelete(scope.row)">删除</el-button>
               <el-button link type="primary" icon="Setting" @click="handleCapability(scope.row)">能力</el-button>
               <el-button v-if="!isProcessor" link type="success" icon="ChatDotRound" @click="handleChat(scope.row)">对话</el-button>
            </template>
         </el-table-column>
      </el-table>

      <pagination v-show="total > 0" :total="total" v-model:page="queryParams.page_num" v-model:limit="queryParams.page_size" @pagination="getList" />

      <!-- 添加或修改对话框 -->
      <el-dialog :title="title" v-model="open" width="700px" append-to-body>
         <el-form ref="supplierRef" :model="form" :rules="rules" label-width="110px">
            <el-divider content-position="left">基本信息</el-divider>
            <el-row :gutter="20">
               <el-col :span="12">
                  <el-form-item label="名称" prop="name">
                     <el-input v-model="form.name" placeholder="请输入名称" />
                  </el-form-item>
               </el-col>
               <el-col :span="12">
                  <el-form-item label="供应商类型" prop="supplier_type">
                     <el-select v-model="form.supplier_type" placeholder="请选择类型" style="width:100%">
                        <el-option label="加工方" value="processor" />
                        <el-option label="材料方" value="material" />
                        <el-option label="其他" value="other" />
                     </el-select>
                  </el-form-item>
               </el-col>
            </el-row>
            <el-row :gutter="20">
               <el-col :span="12">
                  <el-form-item label="分类" prop="category">
                     <el-input v-model="form.category" placeholder="如：钢料、全工序、五金等" />
                  </el-form-item>
               </el-col>
               <el-col :span="12">
                  <el-form-item label="状态" prop="status">
                     <el-select v-model="form.status" placeholder="请选择状态" style="width:100%">
                        <el-option label="启用" value="active" />
                        <el-option label="停用" value="disabled" />
                     </el-select>
                  </el-form-item>
               </el-col>
            </el-row>

            <el-divider content-position="left">联系信息（合同自动填充）</el-divider>
            <el-row :gutter="20">
               <el-col :span="12">
                  <el-form-item label="法定代表人" prop="legal_rep">
                     <el-input v-model="form.legal_rep" placeholder="合同乙方法定代表人" />
                  </el-form-item>
               </el-col>
               <el-col :span="12">
                  <el-form-item label="联系人" prop="contact_name">
                     <el-input v-model="form.contact_name" placeholder="日常联系人" />
                  </el-form-item>
               </el-col>
            </el-row>
            <el-row :gutter="20">
               <el-col :span="12">
                  <el-form-item label="联系电话" prop="contact_phone">
                     <el-input v-model="form.contact_phone" placeholder="联系电话" />
                  </el-form-item>
               </el-col>
               <el-col :span="12">
                  <el-form-item label="联系邮箱" prop="contact_email">
                     <el-input v-model="form.contact_email" placeholder="合同发送收件邮箱" />
                  </el-form-item>
               </el-col>
            </el-row>
            <el-row :gutter="20">
               <el-col :span="24">
                  <el-form-item label="统一社会信用代码" prop="credit_code">
                     <el-input v-model="form.credit_code" placeholder="18位统一社会信用代码" maxlength="18" show-word-limit />
                  </el-form-item>
               </el-col>
            </el-row>

            <el-divider content-position="left">地址信息</el-divider>
            <el-row :gutter="20">
               <el-col :span="12">
                  <el-form-item label="省" prop="province">
                     <el-input v-model="form.province" placeholder="如：广东" />
                  </el-form-item>
               </el-col>
               <el-col :span="12">
                  <el-form-item label="市" prop="city">
                     <el-input v-model="form.city" placeholder="如：深圳" />
                  </el-form-item>
               </el-col>
            </el-row>
            <el-form-item label="详细地址" prop="address">
               <el-input v-model="form.address" placeholder="请输入详细地址" />
            </el-form-item>

            <el-divider content-position="left">合同信息</el-divider>
            <el-row :gutter="20">
               <el-col :span="12">
                  <el-form-item label="框架合同额度" prop="contract_amount">
                     <el-input-number v-model="form.contract_amount" :min="0" :precision="2" placeholder="元" style="width:100%" />
                  </el-form-item>
               </el-col>
               <el-col :span="12">
                  <el-form-item label="参考单价" prop="base_price">
                     <el-input-number v-model="form.base_price" :min="0" :precision="2" placeholder="元" style="width:100%" />
                  </el-form-item>
               </el-col>
            </el-row>
            <el-row :gutter="20">
               <el-col :span="12">
                  <el-form-item label="合同起始日期" prop="contract_start">
                     <el-date-picker v-model="form.contract_start" type="date" value-format="YYYY-MM-DD" placeholder="合同起始日期" style="width:100%" />
                  </el-form-item>
               </el-col>
               <el-col :span="12">
                  <el-form-item label="合同终止日期" prop="contract_end">
                     <el-date-picker v-model="form.contract_end" type="date" value-format="YYYY-MM-DD" placeholder="合同终止日期" style="width:100%" />
                  </el-form-item>
               </el-col>
            </el-row>

            <el-divider v-if="isAdmin" content-position="left">登录账号（选填）</el-divider>
            <el-row v-if="isAdmin" :gutter="20">
               <el-col :span="12">
                  <el-form-item label="登录账号" prop="link_username">
                     <el-input v-if="!form.link_username" v-model="form.link_username" placeholder="如：qd_hexing（留空不创建）" />
                     <el-input v-else :model-value="form.link_username" disabled>
                        <template #suffix>
                           <el-tag type="success" size="small">已创建</el-tag>
                        </template>
                     </el-input>
                  </el-form-item>
               </el-col>
               <el-col :span="12">
                  <el-form-item label="登录密码" prop="link_password">
                     <el-input v-if="!form.link_username" v-model="form.link_password" placeholder="默认 admin123" />
                     <el-input v-else model-value="******" disabled />
                  </el-form-item>
               </el-col>
            </el-row>

            <el-form-item label="备注" prop="remark">
               <el-input v-model="form.remark" type="textarea" placeholder="请输入备注" />
            </el-form-item>
         </el-form>
         <template #footer>
            <div class="dialog-footer">
               <el-button type="primary" @click="submitForm">确 定</el-button>
               <el-button @click="cancel">取 消</el-button>
            </div>
         </template>
      </el-dialog>

      <!-- 能力标签对话框 -->
      <el-dialog title="设置能力标签" v-model="capabilityOpen" width="500px" append-to-body>
         <el-form label-width="100px">
            <el-form-item label="能力标签">
               <el-select v-model="capabilityTags" multiple filterable allow-create default-first-option placeholder="输入工艺名称并回车添加" style="width: 100%">
                  <el-option v-for="tag in commonTags" :key="tag" :label="tag" :value="tag" />
               </el-select>
            </el-form-item>
         </el-form>
         <template #footer>
            <div class="dialog-footer">
               <el-button type="primary" @click="submitCapability">确 定</el-button>
               <el-button @click="capabilityOpen = false">取 消</el-button>
            </div>
         </template>
      </el-dialog>
   </div>
</template>

<script setup name="Supplier">
import { listSupplier, getSupplier, addSupplier, updateSupplier, delSupplier, getCapabilities, setCapabilities } from "@/api/entrust/supplier";
import { listProcessMethods } from "@/api/entrust/project";
import useUserStore from '@/store/modules/user'
import { useRouter } from 'vue-router'

const router = useRouter();
const { proxy } = getCurrentInstance();
const userStore = useUserStore();
const isAdmin = computed(() => userStore.roles.includes('admin'));
const isProcessor = computed(() => (userStore.roles || []).includes('processor'));

const supplierList = ref([]);
const open = ref(false);
const loading = ref(true);
const showSearch = ref(true);
const total = ref(0);
const title = ref("");
const capabilityOpen = ref(false);
const currentSupplierId = ref(null);
const capabilityTags = ref([]);

const commonTags = ref([]);

function loadProcessMethodNames() {
   listProcessMethods().then(res => {
      commonTags.value = (res.data || []).map(p => p.name);
   });
}
loadProcessMethodNames();

const data = reactive({
   form: {},
   queryParams: {
      page_num: 1,
      page_size: 10,
      name: undefined,
      supplier_type: undefined,
      category: undefined,
      status: undefined,
   },
   rules: {
      name: [{ required: true, message: "加工方名称不能为空", trigger: "blur" }],
   },
});

const { queryParams, form, rules } = toRefs(data);

/** 查询列表 */
function getList() {
   loading.value = true;
   listSupplier(queryParams.value).then(response => {
      supplierList.value = response.rows;
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
      name: undefined, supplier_type: 'processor', category: undefined,
      province: undefined, city: undefined, address: undefined,
      legal_rep: undefined, contact_name: undefined, contact_phone: undefined,
      contact_email: undefined, credit_code: undefined,
      rating: undefined, base_price: undefined,
      contract_amount: undefined, contract_start: undefined, contract_end: undefined,
      status: 'active', remark: undefined,
      link_username: undefined, link_password: undefined,
   };
   proxy.resetForm("supplierRef");
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
   title.value = "新增加工方";
}

function handleUpdate(row) {
   reset();
   getSupplier(row.id).then(response => {
      form.value = response.data;
      open.value = true;
      title.value = "修改加工方";
   });
}

function submitForm() {
   proxy.$refs["supplierRef"].validate(valid => {
      if (valid) {
         if (form.value.id != undefined) {
            updateSupplier(form.value.id, form.value).then(() => {
               proxy.$modal.msgSuccess("修改成功");
               open.value = false;
               getList();
            });
         } else {
            addSupplier(form.value).then(() => {
               proxy.$modal.msgSuccess("新增成功");
               open.value = false;
               getList();
            });
         }
      }
   });
}

function handleDelete(row) {
   proxy.$modal.confirm('是否确认删除加工方"' + row.name + '"？').then(() => {
      return delSupplier(row.id);
   }).then(() => {
      getList();
      proxy.$modal.msgSuccess("删除成功");
   }).catch(() => {});
}

function handleCapability(row) {
   currentSupplierId.value = row.id;
   getCapabilities(row.id).then(response => {
      capabilityTags.value = (response.data || []).map(c => c.process_name);
      capabilityOpen.value = true;
   });
}

function submitCapability() {
   setCapabilities(currentSupplierId.value, capabilityTags.value).then(() => {
      proxy.$modal.msgSuccess("更新成功");
      capabilityOpen.value = false;
   });
}

function handleChat(row) {
   router.push({ path: '/entrust/chat', query: { supplier_id: row.id } });
}

getList();
</script>

<style scoped>
.wrap-table :deep(.cell) {
   white-space: normal;
   word-break: break-all;
   line-height: 1.4;
}
</style>
