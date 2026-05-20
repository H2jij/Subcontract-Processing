# Requirements Document

## Introduction

本功能将合同分发能力集成进现有的委外加工系统（ruoyi-fastapi-backend）。
具体包括：选标后基于 DOCX 模板自动生成框架合同、从系统数据填写合同字段、通过 SMTP 邮件将合同发送给供应商，以及记录每次发送历史。

甲方（我方）信息存储在系统配置中，乙方（供应商）信息从 `EntrustSupplier` 取得，合同金额与期限从 `EntrustOutsourceOrder` / `EntrustOutsourceRequest` 推导。
整个流程复用项目中已有的 `contract_toolkit`（`DocxFiller` + `EmailSender`）工具包。

---

## Glossary

- **Contract_Dispatch_System**：本功能所描述的合同分发系统，集成于 `module_entrust` 后端模块
- **DocxFiller**：`contract_toolkit.DocxFiller`，负责将字段值填入 DOCX 模板并返回字节流
- **EmailSender**：`contract_toolkit.EmailSender`，负责通过 SMTP 发送带附件邮件
- **ContractTemplate**：存储于数据库的合同模板记录，关联服务端磁盘上的 `.docx` 文件
- **ContractRecord**：合同发送历史记录，存储于 `entrust_contract_records` 表
- **Party_A_Config**：甲方（我方公司）信息，存储在系统参数表（`sys_config`）中
- **Party_B**：乙方，即 `EntrustSupplier` 供应商
- **Order**：`EntrustOutsourceOrder`，委外工单，选标后生成
- **Inquiry**：`EntrustOutsourceRequest`，委外询价单
- **SMTP_Config**：SMTP 邮件服务配置，存储于 `.env.dev` / `.env.prod` 等环境变量文件

---

## Requirements

### Requirement 1

**User Story:** 作为系统管理员，我希望在系统参数中维护甲方公司信息，以便合同模板自动填充时无需人工输入。

#### Acceptance Criteria

1. THE Contract_Dispatch_System SHALL 从系统参数表（`sys_config`）读取以下甲方字段：`甲方法定代表人`、`甲方联系方式`、`甲方信用代码`、`甲方签字`。
2. WHEN 甲方参数在 `sys_config` 中不存在时，THE Contract_Dispatch_System SHALL 将对应占位符保留为字符串 `【待填写】`，并在 API 响应中返回缺失字段名称列表。
3. THE Contract_Dispatch_System SHALL 支持通过现有 `/system/config` 接口对甲方参数进行增删改查，无需开发额外接口。

---

### Requirement 2

**User Story:** 作为合同管理员，我希望在系统中维护多个 DOCX 合同模板，以便根据加工类型选用不同模板。

#### Acceptance Criteria

1. THE Contract_Dispatch_System SHALL 在数据库中维护 `entrust_contract_templates` 表，每条记录包含：模板名称（`name`）、关联文件路径（`file_path`）、适用分类（`category`，可选）、是否启用（`is_active`）、创建时间（`created_at`）。
2. WHEN 管理员通过 `POST /entrust/contract/templates` 上传新模板时，THE Contract_Dispatch_System SHALL 将 DOCX 文件保存至服务端 `vf_admin/upload_path/contracts/` 目录，并在 `entrust_contract_templates` 表中创建对应记录。
3. IF 上传的文件不是合法 DOCX 格式（DocxFiller.is_valid_docx 校验失败），THEN THE Contract_Dispatch_System SHALL 返回 HTTP 400 及错误描述，不保存文件。
4. THE Contract_Dispatch_System SHALL 通过 `GET /entrust/contract/templates` 返回所有 `is_active=true` 的模板列表，每条包含 `id`、`name`、`category`、`file_path`。
5. WHEN 管理员通过 `DELETE /entrust/contract/templates/{template_id}` 删除模板时，THE Contract_Dispatch_System SHALL 将 `is_active` 设为 `false`（软删除），不删除磁盘文件。
6. WHEN 系统初始化时，THE Contract_Dispatch_System SHALL 将 `律师修订版框架合同` 目录下的三个 DOCX 文件（钢料、全工序加工、五金加工）作为初始模板记录写入 `entrust_contract_templates` 表（通过 Alembic migration 数据填充）。

---

### Requirement 3

**User Story:** 作为业务人员，我希望系统从数据库自动填写合同字段，以减少手动录入并降低出错概率。

#### Acceptance Criteria

1. WHEN Contract_Dispatch_System 执行合同填充时，THE DocxFiller SHALL 按以下规则将字段映射到模板占位符：
   - `甲方法定代表人`、`甲方联系方式`、`甲方信用代码`、`甲方签字` ← 来自 `sys_config` 甲方参数
   - `乙方名称` ← `EntrustSupplier.name`
   - `乙方地址` ← `EntrustSupplier.address`
   - `乙方法定代表人` ← `EntrustSupplier.contact_name`
   - `乙方联系电话` ← `EntrustSupplier.contact_phone`
   - `统一社会信用代码` ← `EntrustSupplier.credit_code`（新增字段，见需求 6）
   - `合同额度` ← `EntrustOutsourceOrder.total_amount`（格式化为人民币字符串，如 `￥12,000.00`）
   - `合同期限_起_年/月/日` ← `EntrustOutsourceOrder.created_at` 的年、月、日
   - `合同期限_止_年/月/日` ← `EntrustOutsourceOrder.plan_delivery_date` 的年、月、日
   - `签订日期_年/月/日` ← 触发填充时的当前日期的年、月、日
   - `包装指导书编号` ← `EntrustOutsourceRequest.order_no`
2. IF `EntrustOutsourceOrder.plan_delivery_date` 为空，THEN THE Contract_Dispatch_System SHALL 将合同期限止日期对应的三个占位符填入 `【待确认】`，并在 API 响应中标注 `missing_fields: ["合同期限_止_年", "合同期限_止_月", "合同期限_止_日"]`。
3. THE DocxFiller SHALL 返回填充后的 DOCX 字节流，不写入磁盘临时文件。
4. FOR ALL 合法的字段值字典，THE DocxFiller 填充后再次解析占位符时 SHALL 返回空列表（所有 `{{...}}` 占位符均已被替换）。

---

### Requirement 4

**User Story:** 作为业务人员，我希望在确认后通过邮件将合同发送给供应商，以便对方及时收到并签署。

#### Acceptance Criteria

1. WHEN 用户调用 `POST /entrust/contract/orders/{order_id}/send` 时，THE Contract_Dispatch_System SHALL 依次执行：（a）填充 DOCX 合同，（b）通过 EmailSender 发送邮件至 `EntrustSupplier.contact_email`，（c）在 `entrust_contract_records` 中写入发送记录，（d）返回 `{"success": true, "record_id": <id>}`。
2. THE Contract_Dispatch_System SHALL 在发送邮件时将填充后的 DOCX 文件作为附件，附件文件名格式为 `合同_{供应商名称}_{order_no}.docx`。
3. THE Contract_Dispatch_System SHALL 使用 `EmailSender.wrap_html()` 生成邮件正文，正文中包含：订单号、供应商名称、合同金额、计划交付日期。
4. IF EmailSender 发送失败（返回 `success: false`），THEN THE Contract_Dispatch_System SHALL 将 `entrust_contract_records` 记录的 `status` 设为 `failed`，在 `error_message` 字段记录错误原因，并在 API 响应中返回 HTTP 500 及错误描述。
5. WHERE 调用方传入 `template_id` 参数，THE Contract_Dispatch_System SHALL 使用指定模板；WHEN 未传入 `template_id` 时，THE Contract_Dispatch_System SHALL 使用第一条 `is_active=true` 的默认模板。
6. THE Contract_Dispatch_System SHALL 支持合同预览，通过 `GET /entrust/contract/orders/{order_id}/preview?template_id={id}` 返回填充后的 DOCX 字节流（`Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`）。

---

### Requirement 5

**User Story:** 作为业务人员，我希望查看每份合同的发送历史，以便追踪合同状态和排查问题。

#### Acceptance Criteria

1. THE Contract_Dispatch_System SHALL 在 `entrust_contract_records` 表中为每次发送操作保存以下字段：`order_id`、`supplier_id`、`template_id`、`recipient_email`、`status`（`sent` / `failed`）、`smtp_message_id`、`error_message`、`sent_at`、`created_by`。
2. WHEN 同一订单已存在 `status=sent` 的记录，且用户再次调用发送接口时，THE Contract_Dispatch_System SHALL 允许重发，并在 `entrust_contract_records` 中新建独立记录，不覆盖或修改原记录。
3. THE Contract_Dispatch_System SHALL 通过 `GET /entrust/contract/records?order_id={id}` 返回指定订单的所有历史发送记录，按 `sent_at` 降序排列，每条包含 `id`、`status`、`recipient_email`、`sent_at`、`error_message`。

---

### Requirement 6

**User Story:** 作为系统管理员，我希望为供应商添加邮箱和统一社会信用代码字段，以便支持合同发送和模板填充。

#### Acceptance Criteria

1. THE Contract_Dispatch_System SHALL 在 `entrust_suppliers` 表中新增 `contact_email`（VARCHAR 255）和 `credit_code`（VARCHAR 64）两个可空字段，并通过 Alembic migration 完成数据库变更。
2. THE Contract_Dispatch_System SHALL 在 `SupplierCreate` 和 `SupplierUpdate` Pydantic 模型中加入 `contact_email: Optional[str]` 和 `credit_code: Optional[str]` 字段，并在 `SupplierResponse` 中返回这两个字段。
3. IF 调用 `POST /entrust/contract/orders/{order_id}/send` 时 `EntrustSupplier.contact_email` 为空，THEN THE Contract_Dispatch_System SHALL 返回 HTTP 422 及错误描述 `"供应商邮箱未配置，无法发送合同"`，不执行填充或发送操作。

---

### Requirement 7

**User Story:** 作为运维人员，我希望通过环境变量文件统一管理 SMTP 配置，以便在不同部署环境中切换邮件服务。

#### Acceptance Criteria

1. THE Contract_Dispatch_System SHALL 从以下环境变量读取 SMTP 配置：`SMTP_HOST`、`SMTP_PORT`（整数）、`SMTP_USER`、`SMTP_PASSWORD`、`EMAIL_FROM`（可选，默认同 `SMTP_USER`）、`EMAIL_SENDER_NAME`（可选显示名）、`EMAIL_DEBUG`（`true`/`false`，默认 `false`）。
2. THE Contract_Dispatch_System SHALL 在 `.env.dev` 文件中提供上述所有变量的占位符示例（值为空字符串或注释说明），不写入真实凭证。
3. WHILE `EMAIL_DEBUG=true`，THE EmailSender SHALL 跳过实际 SMTP 连接，仅将邮件元数据记录到应用日志，并返回 `success: true`，以便本地开发调试。
4. IF `SMTP_HOST` 或 `SMTP_USER` 环境变量为空字符串，THEN THE Contract_Dispatch_System SHALL 在应用启动时记录警告日志 `"SMTP 配置不完整，合同邮件功能不可用"`，但不阻止应用启动。
