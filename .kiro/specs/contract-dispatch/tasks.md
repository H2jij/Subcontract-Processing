# Implementation Plan: Contract Dispatch (合同分发)

## Overview

将合同分发功能集成到 `module_entrust` 模块，包括模板管理 CRUD、基于订单的合同填充与发送、发送历史查询。实现语言为 Python，框架为 FastAPI + SQLAlchemy。

## Tasks

- [ ] 1. Database schema and migrations
  - [x] 1.1 Create `entrust_contract_templates` table model
    - 在 `module_entrust/entity/do/entrust_do.py` 中新增 `EntrustContractTemplate` SQLAlchemy 模型
    - 字段：`id`, `name`, `file_path`, `category`, `is_active`, `created_at`
    - _Requirements: 2.1_
  - [ ] 1.2 Add `order_id` and `template_id` columns to `EntrustContractRecord`
    - 在现有 `EntrustContractRecord` 模型中新增 `order_id: Integer` 和 `template_id: Integer` 字段
    - _Requirements: 5.1_
  - [ ] 1.3 Create Alembic migration for schema changes
    - 生成 migration 脚本：创建 `entrust_contract_templates` 表，修改 `entrust_contract_records` 表
    - 包含初始模板 seed 数据（钢料、全工序加工、五金加工三个模板记录）
    - _Requirements: 2.1, 2.6_

- [ ] 2. Contract template management service and controller
  - [ ] 2.1 Implement `ContractTemplateService`
    - 创建 `module_entrust/service/contract_template_service.py`
    - 实现 `upload_template()`：校验 DOCX 合法性（`DocxFiller.is_valid_docx`），保存文件到 `vf_admin/upload_path/contracts/`，创建数据库记录
    - 实现 `list_active_templates()`：查询 `is_active=True` 的模板
    - 实现 `soft_delete_template()`：设置 `is_active=False`
    - 实现 `get_template_by_id()` 和 `get_default_template()`
    - _Requirements: 2.2, 2.3, 2.4, 2.5_
  - [ ]* 2.2 Write property test: Invalid DOCX rejection
    - **Property 2: Invalid DOCX rejection**
    - **Validates: Requirements 2.3**
  - [ ]* 2.3 Write property test: Active templates filter
    - **Property 3: Active templates filter**
    - **Validates: Requirements 2.4**
  - [ ] 2.4 Implement `ContractTemplateController`
    - 创建 `module_entrust/controller/contract_template_controller.py`
    - `POST /entrust/contract/templates`：接收 multipart/form-data（file + name + category），调用 service
    - `GET /entrust/contract/templates`：返回启用模板列表
    - `DELETE /entrust/contract/templates/{template_id}`：软删除
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

- [ ] 3. Party A config reader and field mapping
  - [ ] 3.1 Refactor `get_party_a_config` to return missing fields list
    - 修改 `contract_service.py` 中的 `_get_party_a_config()` 函数
    - 返回 `tuple[dict[str, str], list[str]]`：(placeholder_values, missing_field_names)
    - 缺失字段值设为 `"【待填写】"`，并将字段名加入 missing 列表
    - _Requirements: 1.1, 1.2_
  - [ ]* 3.2 Write property test: Party A config reading with fallback
    - **Property 1: Party A config reading with fallback**
    - **Validates: Requirements 1.1, 1.2**
  - [ ] 3.3 Implement `build_field_values` as a pure function
    - 提取现有 `_build_field_values()` 为可独立测试的纯函数
    - 接收 `EntrustOutsourceOrder`, `EntrustSupplier`, `party_a_config` 参数
    - 按映射表组装占位符字典，金额格式化为 `￥X,XXX.XX`
    - `plan_delivery_date` 为空时填入 `"【待确认】"` 并标注 missing_fields
    - _Requirements: 3.1, 3.2_
  - [ ]* 3.4 Write property test: Field mapping correctness
    - **Property 4: Field mapping correctness**
    - **Validates: Requirements 3.1**
  - [ ]* 3.5 Write property test: Placeholder fill completeness (round-trip)
    - **Property 5: Placeholder fill completeness**
    - **Validates: Requirements 3.4**

- [ ] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Contract send and preview service (order-based)
  - [ ] 5.1 Implement `send_contract_by_order` in ContractService
    - 基于 `order_id` 查询 `EntrustOutsourceOrder` → 获取 `supplier_id` → 查询 `EntrustSupplier`
    - 校验 `contact_email` 非空，否则返回 HTTP 422
    - 根据 `template_id` 参数选择模板（未传入时使用默认模板）
    - 调用 `build_field_values()` 组装字段
    - 调用 `DocxFiller.fill()` 生成 DOCX 字节流
    - 构建邮件 HTML（包含订单号、供应商名称、合同金额、交付日期）
    - 调用 `EmailSender.send()` 发送
    - 写入 `entrust_contract_records` 记录（含 `order_id`, `template_id`）
    - 失败时记录 `status=failed` + `error_message`
    - _Requirements: 4.1, 4.4, 4.5, 5.1, 5.2, 6.3_
  - [ ]* 5.2 Write property test: Missing email validation
    - **Property 10: Missing email validation**
    - **Validates: Requirements 6.3**
  - [ ]* 5.3 Write property test: Attachment filename format
    - **Property 6: Attachment filename format**
    - **Validates: Requirements 4.2**
  - [ ]* 5.4 Write property test: Email body contains required info
    - **Property 7: Email body contains required info**
    - **Validates: Requirements 4.3**
  - [ ] 5.5 Implement `preview_contract_by_order`
    - 与发送逻辑共享字段组装，但不发邮件不写记录
    - 返回 `(docx_bytes, filename)` 元组
    - _Requirements: 4.6_

- [ ] 6. Contract records query service
  - [ ] 6.1 Implement `get_records_by_order` in ContractService
    - 查询 `entrust_contract_records` WHERE `order_id=?`
    - 按 `sent_at` 降序排列
    - 返回包含 `id`, `status`, `recipient_email`, `sent_at`, `error_message` 的列表
    - _Requirements: 5.3_
  - [ ]* 6.2 Write property test: Re-send creates independent records
    - **Property 8: Re-send creates independent records**
    - **Validates: Requirements 5.2**
  - [ ]* 6.3 Write property test: Records sorted descending
    - **Property 9: Records sorted descending**
    - **Validates: Requirements 5.3**

- [ ] 7. Contract controller (API endpoints)
  - [ ] 7.1 Create `ContractController` with order-based endpoints
    - 创建 `module_entrust/controller/contract_controller.py`
    - `POST /entrust/contract/orders/{order_id}/send`：接收可选 `template_id`，调用 `send_contract_by_order`
    - `GET /entrust/contract/orders/{order_id}/preview`：接收可选 `template_id` query param，返回 StreamingResponse
    - `GET /entrust/contract/records?order_id={id}`：返回发送历史
    - _Requirements: 4.1, 4.6, 5.3_
  - [ ] 7.2 Register new controllers in module router
    - 在 `module_entrust/controller/__init__.py` 中注册 `contract_template_controller` 和 `contract_controller`
    - _Requirements: 4.1_

- [ ] 8. SMTP configuration and debug mode
  - [ ] 8.1 Update `.env.dev` with SMTP placeholder variables
    - 添加 `SMTP_HOST=`, `SMTP_PORT=465`, `SMTP_USER=`, `SMTP_PASSWORD=`, `EMAIL_FROM=`, `EMAIL_SENDER_NAME=`, `EMAIL_DEBUG=true`
    - 所有敏感值为空字符串，附注释说明
    - _Requirements: 7.1, 7.2_
  - [ ] 8.2 Add SMTP completeness check at startup
    - 在 `_build_sender()` 或应用启动时检查 `SMTP_HOST` 和 `SMTP_USER`
    - 为空时记录警告日志 `"SMTP 配置不完整，合同邮件功能不可用"`
    - 不阻止应用启动
    - _Requirements: 7.4_
  - [ ]* 8.3 Write property test: Debug mode skips SMTP
    - **Property 11: Debug mode skips SMTP**
    - **Validates: Requirements 7.3**

- [ ] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Task Dependency Graph

```json
{
  "waves": [
    { "tasks": ["1"] },
    { "tasks": ["2", "3"] },
    { "tasks": ["4"] },
    { "tasks": ["5", "6"] },
    { "tasks": ["7"] },
    { "tasks": ["8"] },
    { "tasks": ["9"] }
  ]
}
```

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use the **Hypothesis** library with minimum 100 iterations
- The existing `contract_service.py` and `contract_task_controller.py` provide working patterns to follow
- `contact_email` and `credit_code` fields already exist on `EntrustSupplier` — no migration needed for Requirement 6.1
