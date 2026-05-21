# Requirements Document

## Introduction

本文档定义对账系统**前端**的功能需求。后端 API 已完成开发（参见 reconciliation-system spec），本 spec 仅覆盖基于 uni-app (Vue 3) + Pinia + TailwindCSS + TypeScript 技术栈的移动端前端实现。

目标平台：微信小程序（主要）+ H5。

前端需实现以下核心模块：
- 对账管理（财务人员视角）
- 供应商确认（供应商视角）
- 异常管理与审批
- 付款管理
- 结算明细
- 虚拟入库管理
- 生产异常管理
- 仪表盘与报表

所有页面遵循移动端优先设计，中文界面，金额以 ¥ 格式显示并保留 2 位小数。

## Glossary

- **Frontend（前端应用）**: 基于 uni-app (Vue 3) + Pinia + TailwindCSS + TypeScript 构建的移动端应用
- **Page（页面）**: uni-app 中的一个独立视图，对应 src/pages/ 下的 .vue 文件
- **Store（状态仓库）**: Pinia store，管理页面间共享的业务状态和 API 调用
- **API_Service（API 服务层）**: 封装后端 RESTful API 调用的 TypeScript 模块
- **List_View（列表视图）**: 支持下拉刷新和上拉加载更多的分页列表组件
- **Filter_Panel（筛选面板）**: 提供多条件筛选的弹出面板组件
- **Form_View（表单视图）**: 带验证的数据录入表单组件
- **Detail_View（详情视图）**: 展示单条记录完整信息的页面
- **Variance_Indicator（差异标识）**: 用颜色标注差异方向的视觉元素（红色=正差异=供应商欠我们，绿色=负差异）
- **Mismatch_Badge（货不对板标识）**: 醒目标识货不对板行项的视觉元素
- **Pull_Refresh（下拉刷新）**: 用户下拉列表触发数据重新加载的交互
- **Load_More（上拉加载）**: 用户滚动到底部触发加载下一页数据的交互
- **Financial_User（财务人员）**: 具有对账管理、付款、结算等操作权限的用户角色
- **Supplier_User（供应商用户）**: 具有查看和确认对账单权限的供应商角色
- **Business_User（业务人员）**: 具有生产异常和虚拟入库操作权限的用户角色

## Requirements

### Requirement 1: 对账管理页面（财务人员视角）

**User Story:** 作为财务人员，我希望在移动端查看、筛选对账单列表，查看对账单详情（含差异明细和原因），手动生成对账单，以便随时随地管理对账工作。

#### Acceptance Criteria

1. THE Frontend SHALL 提供对账单列表页面，以 List_View 形式展示对账单，每条记录显示：对账单编号、供应商名称、对账周期、状态、订购总金额、差异总金额
2. THE List_View SHALL 支持 Pull_Refresh 和 Load_More，每页加载 20 条记录
3. THE Frontend SHALL 提供 Filter_Panel，支持按供应商、状态（pending/confirmed/disputed/timeout/paid）、对账周期进行筛选
4. WHEN 用户点击对账单列表项时, THE Frontend SHALL 导航至对账单详情页面，展示完整行项列表，每个行项显示：委外单号、零件名称、订购金额、实际收到价值、差异金额、差异原因摘要
5. THE Detail_View SHALL 对差异金额使用 Variance_Indicator 标注：正差异（供应商欠我们）显示红色，负差异显示绿色，零差异不标注颜色
6. THE Detail_View SHALL 对 has_mismatch 为 true 的行项显示 Mismatch_Badge（醒目的"货不对板"标识）
7. WHEN 用户点击行项的差异原因时, THE Frontend SHALL 展开显示完整的差异原因列表，包含：原因类型、描述、影响金额、责任方
8. THE Frontend SHALL 提供"生成对账单"入口，允许用户选择对账周期（起止日期）和供应商，调用后端 POST /entrust/reconciliation/generate 接口
9. WHEN 对账单生成请求提交后, THE Frontend SHALL 显示加载状态，生成完成后自动刷新列表并提示成功
10. THE Frontend SHALL 提供差异汇总视图，展示当前对账单的：订购总金额、实际收到总价值、物流总费用、差异总金额、异常笔数、货不对板行项数
11. THE Frontend SHALL 提供"重新计算差异"按钮，调用后端 POST /entrust/reconciliation/{id}/recalculate 接口，完成后刷新详情页数据
12. THE Frontend SHALL 所有金额字段以 ¥ 格式显示，保留 2 位小数

### Requirement 2: 供应商确认页面（供应商视角）

**User Story:** 作为供应商用户，我希望在移动端查看我的对账单列表和明细（含差异原因），并进行确认或提出争议操作。

#### Acceptance Criteria

1. THE Frontend SHALL 提供供应商对账单列表页面，仅展示当前登录供应商的对账单，每条记录显示：对账单编号、对账周期、状态、应付金额、差异总金额
2. THE List_View SHALL 支持 Pull_Refresh 和 Load_More
3. WHEN 供应商用户点击对账单列表项时, THE Frontend SHALL 导航至对账单明细页面，展示行项列表，每个行项显示：委外单号、零件名称、订购金额、实际收到价值、差异金额、差异原因
4. THE Detail_View SHALL 使用 Variance_Indicator 和 Mismatch_Badge 标注差异行项
5. THE Frontend SHALL 在对账单明细页面底部提供"确认"和"有异议"两个操作按钮
6. WHEN 供应商用户点击"确认"按钮时, THE Frontend SHALL 弹出二次确认对话框，确认后调用 POST /entrust/supplier-claim/statements/{id}/confirm 接口
7. WHEN 供应商用户点击"有异议"按钮时, THE Frontend SHALL 展示争议表单，要求填写争议说明（支持针对具体行项），提交后调用 POST /entrust/supplier-claim/statements/{id}/dispute 接口
8. WHEN 确认或争议操作成功后, THE Frontend SHALL 更新页面状态显示并返回列表页
9. WHILE 对账单状态为 confirmed 或 paid 时, THE Frontend SHALL 隐藏操作按钮，仅展示只读明细

### Requirement 3: 异常管理页面

**User Story:** 作为财务人员，我希望在移动端查看异常记录列表、异常详情，提出金额调整，并处理待审批的调整请求。

#### Acceptance Criteria

1. THE Frontend SHALL 提供异常记录列表页面，以 List_View 形式展示，每条记录显示：异常类型、严重程度标识（critical/warning/info 用不同颜色）、关联对账单编号、状态、差异金额
2. THE Frontend SHALL 提供 Filter_Panel，支持按异常类型、严重程度、状态（open/investigating/resolved/closed）进行筛选
3. THE List_View SHALL 支持 Pull_Refresh 和 Load_More
4. WHEN 用户点击异常记录时, THE Frontend SHALL 导航至异常详情页面，展示：异常类型、严重程度、关联订单信息、差异金额、原金额、处理状态、创建时间
5. THE Frontend SHALL 在异常详情页面提供"提出调整"按钮，点击后展示调整表单，包含：原金额（只读）、调整后金额（必填）、调整原因（必填）
6. WHEN 用户提交调整表单时, THE Frontend SHALL 验证调整后金额为有效数字且与原金额不同，验证通过后调用 POST /entrust/anomaly/{id}/adjustment 接口
7. THE Frontend SHALL 提供待审批列表页面，展示当前用户需要审批的 Adjustment 记录
8. WHEN 审批人查看待审批记录时, THE Frontend SHALL 展示调整详情：原金额、调整后金额、调整原因、申请人、申请时间
9. THE Frontend SHALL 提供"通过"和"驳回"操作按钮
10. WHEN 审批人点击"驳回"时, THE Frontend SHALL 要求填写驳回原因（必填），提交后调用 POST /entrust/anomaly/adjustments/{id}/reject 接口
11. WHEN 审批人点击"通过"时, THE Frontend SHALL 弹出确认对话框，确认后调用 POST /entrust/anomaly/adjustments/{id}/approve 接口
12. THE Frontend SHALL 对 critical 级别异常使用红色背景标识，warning 使用橙色，info 使用蓝色

### Requirement 4: 付款管理页面

**User Story:** 作为财务人员，我希望在移动端查看付款申请列表和详情，录入付款记录，上传支付凭证。

#### Acceptance Criteria

1. THE Frontend SHALL 提供付款申请列表页面，以 List_View 形式展示，每条记录显示：关联对账单编号、供应商名称、应付金额、已付金额、付款状态
2. THE List_View SHALL 支持 Pull_Refresh 和 Load_More
3. WHEN 用户点击付款申请列表项时, THE Frontend SHALL 导航至付款申请详情页面，展示：对账单信息、应付金额、已付金额、剩余应付、付款记录列表
4. THE Frontend SHALL 在付款详情页面提供"录入付款"按钮，点击后展示付款表单，包含：付款金额（必填）、付款日期（必填）、银行流水号（必填）
5. WHEN 用户提交付款表单时, THE Frontend SHALL 验证付款金额为正数且不超过剩余应付金额，验证通过后调用 POST /entrust/payment/requests/{id}/records 接口
6. THE Frontend SHALL 提供"上传凭证"功能，支持从相册选择或拍照上传图片（jpg/png/jpeg），以及选择 PDF 文件
7. WHEN 用户选择文件后, THE Frontend SHALL 验证文件类型（jpg/png/jpeg/pdf）和文件大小（不超过 10MB），验证通过后调用 POST /entrust/payment/evidences/upload 接口
8. THE Frontend SHALL 在付款详情页面展示已上传的凭证缩略图列表，点击可预览大图
9. WHEN 付款记录录入成功后, THE Frontend SHALL 自动刷新付款详情页面，更新已付金额和付款状态
10. THE Frontend SHALL 所有金额字段以 ¥ 格式显示，保留 2 位小数

### Requirement 5: 结算明细页面

**User Story:** 作为财务人员，我希望在移动端查看订单结算明细，了解订购 vs 实际收到的对比，编辑 draft 状态的行项，确认结算，并下载 PDF 结算单。

#### Acceptance Criteria

1. THE Frontend SHALL 提供结算明细列表页面，以 List_View 形式展示，每条记录显示：委外单号、供应商名称、订购金额、实际交付金额、差异金额、状态（draft/finalized）
2. THE List_View SHALL 支持 Pull_Refresh 和 Load_More
3. WHEN 用户点击结算明细列表项时, THE Frontend SHALL 导航至结算详情页面，分区展示：
   - 订购基准区：订购数量、订购单价、订购总金额
   - 实际交付区：实际交付数量、实际交付金额
   - 虚拟入库区：虚拟入库总金额、关联记录列表
   - 异常扣除区：异常扣除总金额
   - 物流费用区：物流费用
   - 差异区：差异金额、差异原因列表
   - 净利润区：客户付款金额、净利润
4. THE Detail_View SHALL 对差异金额使用 Variance_Indicator 标注
5. WHILE Settlement_Detail 处于 draft 状态, THE Frontend SHALL 在详情页面提供"编辑"按钮，允许用户修改行项数据
6. WHEN 用户点击"编辑"按钮时, THE Frontend SHALL 将详情页面切换为编辑模式，允许修改可编辑字段，提交后调用 PUT /entrust/settlement/{id}/line-items 接口
7. THE Frontend SHALL 在 draft 状态的详情页面提供"确认结算"按钮
8. WHEN 用户点击"确认结算"时, THE Frontend SHALL 弹出二次确认对话框（提示确认后不可修改），确认后调用 POST /entrust/settlement/{id}/finalize 接口
9. THE Frontend SHALL 提供"下载 PDF"按钮，点击后调用 GET /entrust/settlement/{id}/pdf 接口并触发文件下载/预览
10. WHILE Settlement_Detail 处于 finalized 状态, THE Frontend SHALL 隐藏编辑和确认按钮，仅展示只读详情和下载 PDF 按钮
11. THE Frontend SHALL 所有金额字段以 ¥ 格式显示，保留 2 位小数

### Requirement 6: 虚拟入库页面

**User Story:** 作为业务人员，我希望在移动端管理虚拟入库记录，包括查看列表、创建新记录、修改和删除记录，以便跟踪因异常补发的货物。

#### Acceptance Criteria

1. THE Frontend SHALL 提供虚拟入库记录列表页面，以 List_View 形式展示，每条记录显示：关联工单号、零件名称、入库类型、数量、金额、责任方、状态
2. THE Frontend SHALL 提供 Filter_Panel，支持按工单号、零件、入库类型（re_shipment_in/anomaly_deduction）、责任方（material_supplier/processor）进行筛选
3. THE List_View SHALL 支持 Pull_Refresh 和 Load_More
4. THE Frontend SHALL 提供"创建虚拟入库"入口，展示创建表单，包含：关联工单（必填，支持搜索选择）、零件（必填，支持搜索选择）、入库类型（必填，下拉选择）、数量（必填，正整数）、单价（必填，正数保留2位小数）、异常原因说明（必填，文本）、责任方（必填，下拉选择）
5. WHEN 用户提交创建表单时, THE Frontend SHALL 验证所有必填项已填写且格式正确，金额自动计算为数量×单价，验证通过后调用 POST /entrust/virtual-inbound/ 接口
6. WHEN 用户点击虚拟入库记录时, THE Frontend SHALL 导航至详情页面，展示完整信息
7. WHILE Virtual_Inbound 记录状态非 linked_to_settlement, THE Frontend SHALL 在详情页面提供"修改"和"删除"按钮
8. WHEN 用户点击"修改"按钮时, THE Frontend SHALL 展示编辑表单（预填当前值），提交后调用 PUT /entrust/virtual-inbound/{id} 接口
9. WHEN 用户点击"删除"按钮时, THE Frontend SHALL 弹出确认对话框，确认后调用 DELETE /entrust/virtual-inbound/{id} 接口
10. THE Frontend SHALL 提供"按工单查看"入口，输入或选择工单号后展示该工单下所有虚拟入库记录
11. THE Frontend SHALL 所有金额字段以 ¥ 格式显示，保留 2 位小数

### Requirement 7: 生产异常页面

**User Story:** 作为业务人员，我希望在移动端创建生产异常记录、进行责任判定、选择补发或扣款处理方式，并确认补发发货以触发虚拟入库。

#### Acceptance Criteria

1. THE Frontend SHALL 提供生产异常列表页面，以 List_View 形式展示，每条记录显示：异常类型、关联工单号、零件名称、责任方、损失金额、处理状态
2. THE List_View SHALL 支持 Pull_Refresh 和 Load_More
3. THE Frontend SHALL 提供"创建生产异常"入口，展示创建表单，包含：关联工单（必填，支持搜索选择）、零件（必填）、异常类型（必填，下拉：material_damage/process_error/unusable）、损失描述（必填，文本）、发生时间（必填，日期选择器）
4. WHEN 用户提交创建表单时, THE Frontend SHALL 验证所有必填项，验证通过后调用 POST /entrust/production-anomaly/ 接口
5. WHEN 用户查看生产异常详情时, THE Frontend SHALL 展示完整信息并提供"责任判定"操作区域
6. THE Frontend SHALL 提供责任判定表单，包含：责任方选择（material_supplier/processor）、判定说明（必填），提交后调用 PUT /entrust/production-anomaly/{id}/liability 接口
7. WHEN 责任判定完成后, THE Frontend SHALL 展示处理方式选择：补发（Re_Shipment）或 扣款（Deduction）
8. WHEN 用户选择"补发"时, THE Frontend SHALL 展示补发表单（补发零件、数量、预计发货日期），提交后调用 POST /entrust/production-anomaly/{id}/re-shipment 接口
9. WHEN 用户选择"扣款"时, THE Frontend SHALL 展示扣款表单（扣款金额、不补发原因），提交后调用 POST /entrust/production-anomaly/{id}/deduction 接口
10. THE Frontend SHALL 在补发记录中提供"确认发货"按钮，点击后触发虚拟入库记录的自动创建
11. THE Frontend SHALL 提供协商记录区域，支持添加协商备注，调用 POST /entrust/production-anomaly/{id}/negotiation 接口
12. THE Frontend SHALL 所有金额字段以 ¥ 格式显示，保留 2 位小数

### Requirement 8: 仪表盘与报表页面

**User Story:** 作为财务主管，我希望在移动端查看对账概览仪表盘、供应商汇总、月度趋势和账龄分析，并支持导出报表。

#### Acceptance Criteria

1. THE Frontend SHALL 提供对账概览仪表盘页面，展示核心指标卡片：对账单总数、已确认数量、有争议数量、待确认数量、货不对板订单数、差异总金额
2. THE Frontend SHALL 在仪表盘页面展示供应商汇总区域，以列表形式展示每个供应商的：订购总金额、实际收到总价值、差异总金额、异常笔数
3. THE Frontend SHALL 提供月度趋势图页面，以折线图/柱状图展示：对账单数量趋势、货不对板比例趋势、差异金额趋势
4. THE Frontend SHALL 提供账龄分析页面，以分组展示未付款项：0-30天、31-60天、61-90天、90天以上，每组显示笔数和金额
5. THE Frontend SHALL 在仪表盘和报表页面提供时间范围筛选（默认当月）
6. THE Frontend SHALL 提供"导出 Excel"按钮，点击后调用 GET /entrust/reconciliation-report/export/excel 接口并触发文件下载
7. THE Frontend SHALL 提供"导出 PDF"按钮，点击后调用 GET /entrust/reconciliation-report/export/pdf 接口并触发文件下载
8. WHEN 导出操作触发后, THE Frontend SHALL 显示加载提示，导出完成后提示用户保存文件
9. IF 导出失败, THEN THE Frontend SHALL 显示错误提示信息，告知用户导出失败原因
10. THE Frontend SHALL 所有金额字段以 ¥ 格式显示，保留 2 位小数

### Requirement 9: 页面导航与路由

**User Story:** 作为用户，我希望对账系统的各功能页面有清晰的导航结构，能从工作台快速进入各模块。

#### Acceptance Criteria

1. THE Frontend SHALL 在工作台页面（pages/work/index）提供对账系统功能入口，以功能卡片/图标网格形式展示各模块入口
2. THE Frontend SHALL 将对账相关页面注册到 pages.json 中，路径格式为 pages/reconciliation/{module}/{page}
3. THE Frontend SHALL 根据用户角色动态显示可访问的功能入口：Financial_User 可见全部模块，Supplier_User 仅可见供应商确认模块，Business_User 可见生产异常和虚拟入库模块
4. WHEN 用户未登录或 token 过期时, THE Frontend SHALL 自动跳转至登录页面
5. THE Frontend SHALL 在所有子页面提供返回导航，支持返回上一页或返回工作台
6. THE Frontend SHALL 页面间传参使用 URL query 参数或 Pinia store 共享状态

### Requirement 10: 数据交互与状态管理

**User Story:** 作为开发者，我希望前端有统一的 API 调用层和状态管理方案，确保数据一致性和良好的用户体验。

#### Acceptance Criteria

1. THE Frontend SHALL 使用 TypeScript 定义所有 API 请求和响应的类型接口
2. THE Frontend SHALL 基于现有 src/utils/request.js 封装对账模块的 API_Service，统一处理请求头（token）、错误码、超时
3. THE Frontend SHALL 使用 Pinia store 管理对账模块的共享状态，包括：当前筛选条件、列表缓存、用户角色信息
4. WHEN API 请求发生网络错误时, THE Frontend SHALL 显示统一的错误提示（toast），并提供重试选项
5. WHEN API 请求返回业务错误码时, THE Frontend SHALL 根据错误码显示对应的中文错误信息
6. THE Frontend SHALL 在列表页面实现数据缓存，返回列表时恢复之前的滚动位置和数据
7. THE Frontend SHALL 在表单提交时显示 loading 状态，防止重复提交
8. WHEN 表单提交成功后, THE Frontend SHALL 显示成功提示并自动返回上一页或刷新列表

### Requirement 11: 表单验证与交互规范

**User Story:** 作为用户，我希望表单有清晰的验证提示和流畅的交互体验。

#### Acceptance Criteria

1. THE Frontend SHALL 对所有必填字段进行非空验证，未填写时显示红色提示文字
2. THE Frontend SHALL 对金额字段验证：必须为正数，最多保留 2 位小数
3. THE Frontend SHALL 对数量字段验证：必须为正整数
4. THE Frontend SHALL 对日期字段提供日期选择器组件，禁止手动输入非法日期
5. WHEN 用户提交表单且验证未通过时, THE Frontend SHALL 滚动至第一个错误字段并聚焦
6. THE Frontend SHALL 对破坏性操作（删除、确认结算、确认对账）提供二次确认对话框
7. THE Frontend SHALL 对长文本输入（争议说明、异常原因等）提供字数统计和最大长度限制
8. THE Frontend SHALL 在网络请求期间禁用提交按钮，防止重复提交

### Requirement 12: 视觉规范与响应式设计

**User Story:** 作为用户，我希望应用界面美观、信息层次清晰、在不同设备上都有良好的显示效果。

#### Acceptance Criteria

1. THE Frontend SHALL 使用 TailwindCSS 实现响应式布局，适配微信小程序和 H5 两种平台
2. THE Frontend SHALL 对差异金额使用颜色编码：正差异（variance > 0，供应商欠我们）使用红色文字，负差异（variance < 0）使用绿色文字，零差异使用默认颜色
3. THE Frontend SHALL 对货不对板行项（has_mismatch = true）使用醒目的视觉标识：左侧红色竖条 + "货不对板"标签
4. THE Frontend SHALL 对异常严重程度使用颜色编码：critical 使用红色背景/标签，warning 使用橙色，info 使用蓝色
5. THE Frontend SHALL 对状态字段使用标签样式展示：pending（灰色）、confirmed（绿色）、disputed（橙色）、timeout（红色）、paid（蓝色）
6. THE Frontend SHALL 列表项使用卡片式布局，信息分层展示（主要信息 + 次要信息 + 状态标签）
7. THE Frontend SHALL 金额数字使用等宽字体或加粗显示，确保对齐和可读性
8. THE Frontend SHALL 在数据加载时显示骨架屏（skeleton），避免页面闪烁
9. THE Frontend SHALL 空列表状态显示友好的空状态插图和提示文字

