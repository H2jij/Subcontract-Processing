# Requirements Document

## Introduction

本功能在委外加工系统（ruoyi-fastapi-backend）的现有基础上，完善**合同邮件分发**与**框架合同自动生成**两个核心能力。

现状：已有 `ContractService`（合同填充 + 发送）和 `DocxFiller` / `EmailSender` 工具包，以及 `POST /entrust/inquiry/{id}/send-contract`、批量发送、预览下载三个接口。但存在以下缺口：

1. 甲方信息（法定代表人、信用代码等）仅由 `.env` 读取，无界面维护入口，也无回落策略；
2. 发送后没有持久化的状态记录（成功/失败/时间/Message-ID）；
3. `EntrustSupplier` 缺少 `contact_email` 和 `credit_code` 字段，收件邮箱只能手动传入；
4. `_build_field_values` 中部分占位符（统一社会信用代码、合同额度）留空；
5. 没有发送历史查询接口，无法追踪已发送合同。

本需求文档覆盖上述所有缺口，以及支撑这些能力的数据库变更和配置管理。

---

## Glossary

- **Contract_Distribution_System**：本功能描述的合同分发子系统，集成于 `module_entrust`
- **DocxFiller**：`contract_toolkit.DocxFiller`，负责将字段值填入 DOCX 模板并返回字节流
- **EmailSender**：`contract_toolkit.EmailSender`，负责通过 SMTP 发送带附件邮件
- **ContractRecord**：合同发送历史记录，持久化于 `entrust_contract_records` 表
- **Party_A_Config**：甲方（我方公司）固定信息，存储于系统参数表 `sys_config`
- **Supplier**：`EntrustSupplier`，乙方（加工方/供应商）
- **Inquiry**：`EntrustOutsourceRequest`，委外询价单
- **Invitation**：`EntrustInvitation`，询价邀请记录，关联 Inquiry 与 Supplier
- **SMTP_Config**：SMTP 邮件服务配置，由 `SmtpSettings`（`config/env.py`）从环境变量读取
- **ContractService**：现有后端服务类 `module_entrust/service/contract_service.py`

---

## Requirements

### Requirement 1: 供应商扩展字段

**User Story:** 作为系统管理员，我希望为每个供应商维护联系邮箱和统一社会信用代码，以便合同发送时自动获取收件地址并填充合同模板，无需每次手动输入。

#### Acceptance Criteria

1. THE Contract_Distribution_System SHALL 在 `entrust_suppliers` 表新增 `contact_email VARCHAR(255)` 和 `credit_code VARCHAR(64)` 两个可空字段，通过 Alembic migration 完成数据库变更。
2. THE Contract_Distribution_System SHALL 在 `SupplierCreate`、`SupplierUpdate` Pydantic 模型中加入 `contact_email: Optional[str]` 和 `credit_code: Optional[str]`，并在 `SupplierResponse` 中返回这两个字段。
3. WHEN 用户通过现有 `PUT /entrust/suppliers/{id}` 接口更新供应商时，THE Contract_Distribution_System SHALL 支持同步写入 `contact_email` 和 `credit_code`。
4. IF 调用合同发送接口时 `Supplier.contact_email` 为空且请求体未显式提供 `recipient_email`，THEN THE Contract_Distribution_System SHALL 返回 HTTP 422 及错误描述 `"供应商邮箱未配置，无法发送合同"`，不执行填充或发送。

---

### Requirement 2: 甲方信息系统参数维护

**User Story:** 作为系统管理员，我希望通过系统参数界面维护甲方公司信息，以便合同自动填充时不依赖 `.env` 配置文件，支持运行时修改而无需重启服务。

#### Acceptance Criteria

1. THE Contract_Distribution_System SHALL 从系统参数表（`sys_config`）读取甲方字段，参数键名约定为：`contract:party_a:legal_rep`、`contract:party_a:contact`、`contract:party_a:credit_code`、`contract:party_a:pkg_guide_no`。
2. WHEN `sys_config` 中对应参数不存在或值为空时，THE Contract_Distribution_System SHALL 回落到 `CompanyConfig`（`.env` 读取）的对应字段；若 `.env` 字段也为空，THEN THE Contract_Distribution_System SHALL 将占位符保留为 `【待填写】`，并在 API 响应的 `missing_fields` 列表中列出缺失字段名称。
3. THE Contract_Distribution_System SHALL 复用现有 `/system/config`（`sys_config` CRUD）接口管理甲方参数，无需开发专用接口。
4. WHEN Party_A_Config 被读取时，THE Contract_Distribution_System SHALL 优先使用 `sys_config` 中的值，以确保运行时更新立即生效，不需重启应用。

---

### Requirement 3: 合同字段完整映射

**User Story:** 作为业务人员，我希望系统从数据库自动填写所有合同占位符，包括统一社会信用代码和合同额度，减少人工录入并降低出错率。

#### Acceptance Criteria

1. WHEN Contract_Distribution_System 执行合同填充时，THE DocxFiller SHALL 按下表将字段映射到模板占位符：

   | 占位符 | 数据来源 |
   |---|---|
   | `甲方法定代表人` | `sys_config` / `CompanyConfig.company_legal_rep` |
   | `甲方联系方式` | `sys_config` / `CompanyConfig.company_contact` |
   | `甲方信用代码` | `sys_config` / `CompanyConfig.company_credit_code` |
   | `甲方签字` | `sys_config` / `CompanyConfig.company_legal_rep` |
   | `乙方名称` | `Supplier.name` |
   | `乙方地址` | `Supplier.province + city + address` 拼接 |
   | `乙方法定代表人` | `Supplier.contact_name` |
   | `乙方联系电话` | `Supplier.contact_phone` |
   | `统一社会信用代码` | `Supplier.credit_code`（需求1新增字段） |
   | `合同额度` | 由调用方通过 `extra_values` 传入，或留空 `【待填写】` |
   | `合同期限_起_年/月/日` | `Inquiry.inquiry_date`，缺失则用当天 |
   | `合同期限_止_年/月/日` | `Inquiry.delivery_date`，缺失则填 `【待确认】` |
   | `签订日期_年/月/日` | 触发时当前日期 |
   | `包装指导书编号` | `sys_config` / `CompanyConfig.company_pkg_guide_no` |
   | `乙方印章` | 固定为 `【待盖章】` |
   | `乙方签字` | 固定为 `【待签字】` |

2. IF `Inquiry.delivery_date` 为空，THEN THE Contract_Distribution_System SHALL 将 `合同期限_止_年`、`合同期限_止_月`、`合同期限_止_日` 三个占位符均填入 `【待确认】`，并在 API 响应的 `missing_fields` 中列出这三个字段名。
3. THE DocxFiller SHALL 返回填充后的 DOCX 字节流，不写入磁盘临时文件。
4. FOR ALL 合法的字段值字典，DocxFiller 填充后再次解析占位符 SHALL 返回空列表（所有 `{{...}}` 均已被替换或以 fallback 填写）。

---

### Requirement 4: 合同发送与历史记录

**User Story:** 作为业务人员，我希望发送合同后系统自动记录发送结果，以便后续追踪每份合同的发送状态，并在失败时了解原因。

#### Acceptance Criteria

1. THE Contract_Distribution_System SHALL 在 `entrust_contract_records` 表中为每次发送操作持久化以下字段：`id`、`inquiry_id`、`supplier_id`、`recipient_email`、`status`（枚举：`sent` / `failed`）、`smtp_message_id`（可空）、`error_message`（可空）、`sent_at`、`created_by`、`created_at`。
2. WHEN `POST /entrust/inquiry/{id}/send-contract` 执行成功时，THE Contract_Distribution_System SHALL 在 `entrust_contract_records` 中写入 `status='sent'` 的记录，并在响应中返回 `record_id`。
3. IF EmailSender 发送失败（返回 `success: false`），THEN THE Contract_Distribution_System SHALL 在 `entrust_contract_records` 中写入 `status='failed'` 及 `error_message`，并返回 HTTP 500 及错误描述，不影响其他并行发送操作。
4. WHEN 同一 `inquiry_id` + `supplier_id` 组合已存在 `status='sent'` 的记录时，THE Contract_Distribution_System SHALL 允许重发，并新建独立记录，不修改原有记录。
5. THE Contract_Distribution_System SHALL 通过 `GET /entrust/inquiry/{id}/contract/records` 返回该询价单的所有历史发送记录，按 `sent_at` 降序排列，每条包含 `id`、`supplier_id`、`supplier_name`、`recipient_email`、`status`、`sent_at`、`error_message`。
6. THE Contract_Distribution_System SHALL 通过 `GET /entrust/contract/records/{record_id}` 返回单条发送记录详情，包含 `smtp_message_id`。

---

### Requirement 5: 批量发送优化

**User Story:** 作为业务人员，我希望批量发送合同时能够从供应商档案自动获取邮箱，并在发送完成后得到每个供应商的发送结果汇总。

#### Acceptance Criteria

1. WHEN 调用 `POST /entrust/inquiry/{id}/send-contract/batch` 时，THE Contract_Distribution_System SHALL 优先从 `Supplier.contact_email` 自动获取收件地址，不要求请求体中强制传入 `email_map`；若请求体中 `email_map` 中有指定地址，SHALL 以请求体中的地址为准（覆盖数据库中的值）。
2. THE Contract_Distribution_System SHALL 对每个受邀供应商独立执行发送，单个供应商的失败 SHALL NOT 阻止其余供应商的发送继续执行。
3. THE Contract_Distribution_System SHALL 在批量发送响应中返回每个供应商的 `supplier_id`、`supplier_name`、`success`、`recipient_email`、`record_id`（成功时）、`error`（失败时）。
4. THE Contract_Distribution_System SHALL 在批量发送完成后汇总结果，在响应顶层包含 `success_count` 和 `total` 字段。
5. IF `email_map` 未传入且某供应商 `contact_email` 为空，THEN THE Contract_Distribution_System SHALL 对该供应商标记 `success: false`，`error: "供应商邮箱未配置"`，并继续处理其他供应商。

---

### Requirement 6: 邮件内容与模板

**User Story:** 作为供应商联系人，我希望收到的邮件格式清晰、内容完整，包含关键合同信息，以便快速了解合同内容并作出回应。

#### Acceptance Criteria

1. THE Contract_Distribution_System SHALL 使用 `EmailSender.wrap_html()` 生成邮件正文，正文中 SHALL 包含：询价单号（`order_no`）、询价标题（`title`）、供应商名称、联系人、计划交付日期。
2. THE Contract_Distribution_System SHALL 将填充后的 DOCX 作为附件，附件文件名格式为 `年度采购框架合同_{供应商名称}_{order_no 或 inquiry_id}.docx`。
3. THE Contract_Distribution_System SHALL 在邮件正文中包含提示文本，告知收件方在收到邮件后 72 小时内确认，以及如有异议的联系方式说明。
4. WHEN `SmtpConfig.smtp_debug` 为 `true` 时，THE EmailSender SHALL 跳过实际 SMTP 连接，仅将邮件元数据写入应用日志，并向 `entrust_contract_records` 写入 `status='sent'`（调试模式标记）。

---

### Requirement 7: SMTP 配置与启动检查

**User Story:** 作为运维人员，我希望系统在 SMTP 配置不完整时给出明确警告，并在 debug 模式下可以不依赖真实邮件服务进行本地开发。

#### Acceptance Criteria

1. THE Contract_Distribution_System SHALL 从环境变量读取以下 SMTP 配置：`SMTP_HOST`、`SMTP_PORT`（整数，默认 465）、`SMTP_USER`、`SMTP_PASSWORD`、`SMTP_SENDER_NAME`（可选）、`SMTP_DEBUG`（`true`/`false`，默认 `false`）。
2. IF `SMTP_HOST` 或 `SMTP_USER` 或 `SMTP_PASSWORD` 在应用启动时为空字符串，THEN THE Contract_Distribution_System SHALL 在应用日志中记录 WARNING 级别消息 `"SMTP 配置不完整，合同邮件功能不可用"`，但 SHALL NOT 阻止应用正常启动。
3. WHILE `SMTP_DEBUG=true`，THE EmailSender SHALL 不建立真实 SMTP 连接，将邮件元数据（收件人、主题、附件名）以 INFO 级别写入应用日志，并返回 `{"success": true, "smtp_message_id": "<debug-xxx@debug>"}`。
4. THE Contract_Distribution_System SHALL 在 `.env.dev` 文件中为所有 SMTP 配置项提供注释说明和空占位符，不在版本库中存储真实凭证。
