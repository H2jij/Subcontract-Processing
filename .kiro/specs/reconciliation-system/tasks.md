# Implementation Plan: Reconciliation System (对账系统)

## Overview

以委外订购单为基准的对账系统重构实现计划。核心变更：引入订单级差异计算引擎（VarianceCalculationService），新增虚拟入库实体（VirtualInbound），重构对账单生成逻辑以支持逐单差异追溯。采用增量修改策略，在现有 module_entrust 代码基础上进行扩展和重构。

## Tasks

- [x] 1. 数据库迁移与实体层更新
  - [x] 1.1 创建 Alembic 迁移脚本：新增表和修改列
    - 新增 `reconciliation_virtual_inbounds` 表（VirtualInbound 实体）
    - 新增 `reconciliation_line_item_variance_reasons` 表（LineItemVarianceReason 实体）
    - 修改 `reconciliation_line_items` 表：ADD ordered_quantity, ordered_unit_price, order_amount, actual_delivered_qty, actual_delivered_value, virtual_inbound_value, anomaly_deduction_amount, logistics_cost, variance, has_mismatch, variance_reasons
    - 修改 `reconciliation_statements` 表：ADD total_ordered_amount, total_received_value, total_logistics_cost, total_variance, anomaly_count
    - 修改 `reconciliation_settlement_details` 表：ADD ordered_quantity, ordered_unit_price, ordered_amount, actual_delivered_qty, actual_delivered_amount, virtual_inbound_amount, anomaly_deduction_amount, logistics_cost, variance, variance_reasons
    - 包含数据回填逻辑（旧数据兼容：order_amount=unit_price×quantity, actual_delivered_value=total_amount, variance=0）
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 10.2, 10.3, 13.1, 13.2_

  - [x] 1.2 修改 `module_entrust/entity/do/reconciliation_do.py`：更新 ORM 模型
    - 更新 ReconciliationStatement 模型：添加 total_ordered_amount, total_received_value, total_logistics_cost, total_variance, anomaly_count 字段
    - 更新 ReconciliationLineItem 模型：添加 ordered_quantity, ordered_unit_price, order_amount, actual_delivered_qty, actual_delivered_value, virtual_inbound_value, anomaly_deduction_amount, logistics_cost, variance, has_mismatch, variance_reasons 字段
    - 新增 VirtualInbound 模型（含索引定义）
    - 新增 LineItemVarianceReason 模型（含索引定义）
    - 更新 SettlementDetail 模型：添加 ordered_quantity, ordered_unit_price, ordered_amount, actual_delivered_qty, actual_delivered_amount, virtual_inbound_amount, anomaly_deduction_amount, logistics_cost, variance, variance_reasons 字段
    - _Requirements: 1.2, 1.3, 1.5, 10.2, 10.3, 13.1, 13.2_

  - [x] 1.3 修改 `module_entrust/entity/vo/reconciliation_vo.py`：更新 Pydantic schemas
    - 新增 VirtualInboundCreate, VirtualInboundUpdate, VirtualInboundResponse schemas
    - 新增 LineItemVarianceReasonResponse schema
    - 更新 ReconciliationLineItemResponse：添加差异相关字段
    - 更新 ReconciliationStatementResponse：添加汇总字段
    - 更新 SettlementDetailResponse：添加订购vs实际对比字段
    - 新增 VarianceSummaryResponse schema
    - _Requirements: 1.2, 1.5, 1.7, 10.2, 13.2_

- [x] 2. 核心差异计算引擎（新建）
  - [x] 2.1 创建 `module_entrust/service/variance_calculation_service.py`
    - 实现 `calculate_order_variance()` 纯函数：variance = order_amount - (actual + virtual - deduction + logistics)
    - 实现 `compute_actual_delivered_value()` 异步方法：从工单获取实际交付数据
    - 实现 `get_virtual_inbound_value()` 异步方法：聚合 re_shipment_in 类型记录金额
    - 实现 `get_anomaly_deduction_amount()` 异步方法：聚合 applied 状态的 Deduction 金额
    - 实现 `compute_line_item_variance()` 异步方法：组合以上方法计算完整差异数据
    - 实现 `link_variance_reasons()` 异步方法：关联 ProductionAnomaly + VirtualInbound + Deduction 记录
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 13.5_

  - [ ]* 2.2 Write property test for variance calculation formula
    - **Property 3: Variance calculation formula**
    - **Validates: Requirements 1.3, 1.4, 1.5, 10.3, 13.5**
    - 使用 Hypothesis 生成随机 Decimal 值（order_amount, actual_value, virtual_value, deduction, logistics）
    - 验证 variance = order_amount - (actual + virtual - deduction + logistics)
    - 验证 has_mismatch = (variance != 0)

  - [ ]* 2.3 Write property test for virtual inbound inclusion
    - **Property 20: Virtual inbound inclusion in variance calculation**
    - **Validates: Requirements 13.5**
    - 生成随机 VirtualInbound 记录列表（含 cancelled 状态），验证仅 re_shipment_in 且非 cancelled 的记录被计入

- [x] 3. 虚拟入库服务与控制器（新建）
  - [x] 3.1 创建 `module_entrust/service/virtual_inbound_service.py`
    - 实现 `create_virtual_inbound()`：创建虚拟入库记录，强制要求 anomaly_reason
    - 实现 `get_inbound_value_for_order()`：计算指定工单的虚拟入库总价值
    - 实现 `list_by_order()`：按工单查询虚拟入库记录
    - 实现 `list_virtual_inbounds()`：列表查询（支持按工单号、零件、入库类型、责任方、时间范围筛选）
    - 实现 `update_virtual_inbound()`：修改记录（检查关联 SettlementDetail 非 finalized）
    - 实现 `delete_virtual_inbound()`：删除记录（检查关联 SettlementDetail 非 finalized）
    - 实现 `auto_create_from_reshipment()`：补发确认发货时自动创建虚拟入库
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8_

  - [x] 3.2 创建 `module_entrust/controller/virtual_inbound_controller.py`
    - GET `/entrust/virtual-inbound/list` — 虚拟入库记录列表（支持筛选）
    - GET `/entrust/virtual-inbound/{id}` — 虚拟入库详情
    - POST `/entrust/virtual-inbound/` — 手动创建虚拟入库记录
    - PUT `/entrust/virtual-inbound/{id}` — 修改虚拟入库记录
    - DELETE `/entrust/virtual-inbound/{id}` — 删除虚拟入库记录
    - GET `/entrust/virtual-inbound/by-order/{order_id}` — 按工单查询
    - 注册路由到 FastAPI app
    - _Requirements: 13.1, 13.2, 13.6_

  - [ ]* 3.3 Write property test for settlement state-based mutability
    - **Property 17: Settlement state-based mutability**
    - **Validates: Requirements 10.7, 10.8, 12.6, 13.8**
    - 生成随机状态（draft/finalized）+ 随机操作（update/delete），验证 finalized 状态拒绝修改

- [x] 4. Checkpoint - 确保数据库迁移和新实体正常工作
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. 重构 ReconciliationService（对账单生成核心逻辑）
  - [x] 5.1 修改 `module_entrust/service/reconciliation_service.py`：重构 generate_statements 方法
    - 修改 `generate_statements()`：以订购单为基准，调用 VarianceCalculationService 逐单计算差异
    - 每个行项填充：ordered_quantity, ordered_unit_price, order_amount, actual_delivered_qty, actual_delivered_value, virtual_inbound_value, anomaly_deduction_amount, logistics_cost, variance, has_mismatch
    - variance != 0 时调用 link_variance_reasons() 关联差异原因，创建 LineItemVarianceReason 记录
    - 生成对账单编号：REC-{YYYYMM}-{supplier_id}-{NNN}
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.9, 1.11_

  - [x] 5.2 修改 `module_entrust/service/reconciliation_service.py`：重构 calculate_summary 方法
    - 实现扩展版汇总计算：total_ordered_amount, total_received_value, total_logistics_cost, total_variance, anomaly_count, total_amount(应付)
    - 汇总计算在行项变更后自动触发
    - _Requirements: 1.7_

  - [x] 5.3 修改 `module_entrust/service/reconciliation_service.py`：行项编辑与重算
    - 修改行项增删改方法：仅 pending 状态允许操作
    - 行项变更后自动重新计算差异和汇总
    - 新增 `recalculate_variance()` 方法：手动触发差异重算
    - _Requirements: 1.10, 8.3_

  - [ ]* 5.4 Write property test for statement generation grouping
    - **Property 1: Statement generation groups orders by supplier**
    - **Validates: Requirements 1.1, 1.11**
    - 生成随机订单列表（随机 supplier_id, 日期, 金额），验证每个 supplier 恰好一份对账单

  - [ ]* 5.5 Write property test for line item order data mapping
    - **Property 2: Line item order data mapping**
    - **Validates: Requirements 1.2**
    - 生成随机订单字段，验证行项映射正确性

  - [ ]* 5.6 Write property test for statement summary invariant
    - **Property 4: Statement summary invariant**
    - **Validates: Requirements 1.7**
    - 生成随机行项列表，验证汇总等于各项之和

  - [ ]* 5.7 Write property test for statement number format
    - **Property 5: Statement number format**
    - **Validates: Requirements 1.9**
    - 生成随机日期 + supplier_id，验证编号格式

  - [ ]* 5.8 Write property test for state-based mutability control
    - **Property 6: State-based mutability control**
    - **Validates: Requirements 1.10, 8.3**
    - 生成随机状态 + 随机操作，验证仅 pending 状态允许修改

- [x] 6. 重构 SettlementService（订单结算明细）
  - [x] 6.1 修改 `module_entrust/service/settlement_service.py`：重构 generate_settlement_detail 方法
    - 以订购单为基准生成结算明细：填充 ordered_quantity, ordered_unit_price, ordered_amount
    - 填充 actual_delivered_qty, actual_delivered_amount
    - 填充 virtual_inbound_amount, anomaly_deduction_amount, logistics_cost
    - 计算 variance 和 variance_reasons
    - 计算净利润：customer_payment - (actual_delivered_amount + logistics_cost + virtual_inbound_amount - anomaly_deduction_amount)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 6.2 修改 `module_entrust/service/settlement_service.py`：状态控制与编辑
    - draft 状态允许编辑行项
    - finalize 操作：标记为 finalized，记录时间和操作人
    - finalized 状态禁止修改和删除关联附件/虚拟入库记录
    - _Requirements: 10.7, 10.8_

  - [ ]* 6.3 Write property test for settlement net profit calculation
    - **Property 16: Settlement net profit calculation**
    - **Validates: Requirements 10.6**
    - 生成随机结算数据，验证净利润公式

- [x] 7. 修改异常服务与供应商比对
  - [x] 7.1 修改 `module_entrust/service/anomaly_service.py`：更新异常检测逻辑
    - 更新 `compare_supplier_claim()` 方法：与订购单逐项比对
    - 金额差异检测：claim 金额 vs order_amount
    - 数量差异检测：claim 数量 vs ordered_quantity，关联 ProductionAnomaly
    - 供应商漏报检测：订购单有但 claim 无
    - 重复申报检测：同一 order_no 出现多次
    - 质量争议检测：引用 quality_status=fail 的工单
    - 严重程度分类：critical(>10% 或质量争议) / warning(5-10%) / info(<5%)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [ ]* 7.2 Write property test for anomaly detection completeness
    - **Property 8: Anomaly detection completeness**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**
    - 生成随机订购单 + 随机供应商账单（含各种差异），验证每种条件恰好生成一条 Anomaly

  - [ ]* 7.3 Write property test for anomaly severity classification
    - **Property 9: Anomaly severity classification**
    - **Validates: Requirements 3.7**
    - 生成随机 diff_amount + order_amount，验证分类正确

- [~] 8. Checkpoint - 确保核心差异计算和对账单生成逻辑正确
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. 修改付款与调整审批服务
  - [x] 9.1 修改 `module_entrust/service/payment_service.py`：更新付款申请生成逻辑
    - 修改 `create_payment_request()`：payable_amount = total_received_value + total_logistics_cost
    - 确认状态变为 confirmed 时自动生成 PaymentRequest
    - _Requirements: 5.1_

  - [x] 9.2 修改 `module_entrust/service/anomaly_service.py`：调整审批相关
    - 确保审批层级判定：≤1000元 manager, >1000元 director
    - 确保行项冻结逻辑：pending 调整时拒绝新调整
    - 审批通过后重新计算差异和汇总
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 9.3 Write property test for confirmed statement generates payment request
    - **Property 12: Confirmed statement generates payment request**
    - **Validates: Requirements 5.1**
    - 生成随机对账单（含差异数据），验证确认后生成正确金额的付款申请

  - [ ]* 9.4 Write property test for payment status calculation
    - **Property 13: Payment status calculation**
    - **Validates: Requirements 5.4, 5.5, 5.6**
    - 生成随机付款记录列表 + 应付金额，验证状态计算

  - [ ]* 9.5 Write property test for approval level determination
    - **Property 10: Approval level determination**
    - **Validates: Requirements 4.2**
    - 生成随机调整金额，验证审批层级

  - [ ]* 9.6 Write property test for frozen line items reject concurrent adjustments
    - **Property 11: Frozen line items reject concurrent adjustments**
    - **Validates: Requirements 4.3**
    - 生成随机行项 + 多个调整请求，验证冻结行项拒绝新调整

- [x] 10. 修改生产异常服务
  - [x] 10.1 修改 `module_entrust/service/production_anomaly_service.py`：确保与差异计算集成
    - 确保 Production_Anomaly 创建后可被 link_variance_reasons() 关联
    - 确保责任判定后触发补发请求或扣款记录创建
    - 确保损失金额计算：total_loss = material_cost + rework_cost + delay_penalty
    - 补发确认发货时调用 VirtualInboundService.auto_create_from_reshipment()
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.6, 9.7, 9.8, 13.1_

  - [ ]* 10.2 Write property test for production anomaly loss calculation
    - **Property 15: Production anomaly loss calculation**
    - **Validates: Requirements 9.7**
    - 生成随机成本组件（material_cost, rework_cost, delay_penalty），验证 total_loss 计算

- [x] 11. 供应商确认与通知流程
  - [x] 11.1 修改供应商确认逻辑：确保确认/争议操作正确
    - 确认操作：原子性更新 confirmation_status, confirmed_at, confirmed_by + 创建 ConfirmationHistory
    - 争议操作：更新 confirmation_status=disputed，要求填写争议说明（可针对具体行项）
    - 禁止自动/超时设为 confirmed（仅超时标记为 timeout）
    - 7天催办提醒 + 15天超时标记
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ]* 11.2 Write property test for confirmation action correctness
    - **Property 7: Confirmation action correctness**
    - **Validates: Requirements 2.3, 2.4, 2.7**
    - 生成随机对账单 + 确认/争议操作，验证原子性更新

- [~] 12. Checkpoint - 确保付款、调整、异常、确认流程正确
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. 更新报表与导出服务
  - [~] 13.1 修改 `module_entrust/service/reconciliation_report_service.py`：更新仪表盘统计
    - 更新仪表盘数据：新增货不对板订单数、差异总金额统计
    - 更新供应商汇总：订购总金额、实收总价值、差异总金额、异常笔数
    - 更新月度趋势：货不对板比例趋势
    - 账龄分析：按 0-30/31-60/61-90/90+ 天分桶
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 13.2 Write property test for aging analysis bucket assignment
    - **Property 14: Aging analysis bucket assignment**
    - **Validates: Requirements 6.4**
    - 生成随机创建日期，验证分桶正确

  - [~] 13.3 修改 `module_entrust/service/reconciliation_export_service.py`：更新 Excel 导出
    - Excel 导出包含：订购金额、实际收到价值、差异金额、差异原因、物流费用
    - 支持批量导出
    - 新增异常报告导出：所有货不对板行项的详细差异原因
    - _Requirements: 7.1, 7.3, 7.5, 7.6_

  - [~] 13.4 修改 `module_entrust/service/reconciliation_pdf_service.py`：更新 PDF 生成
    - PDF 包含订购vs实际对比信息、差异金额及原因列表
    - 结算 PDF 包含虚拟入库信息、支付凭证区域
    - 包含公司信息和签章位置
    - _Requirements: 7.2, 7.4, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [ ]* 13.5 Write property test for file upload validation
    - **Property 18: File upload validation**
    - **Validates: Requirements 12.1, 12.5**
    - 生成随机文件名 + 大小，验证仅 jpg/png/pdf/jpeg 且不超限的文件被接受

- [ ] 14. 更新控制器层
  - [~] 14.1 修改 `module_entrust/controller/reconciliation_controller.py`
    - 新增 `/{id}/variance-summary` 端点：返回差异汇总
    - 新增 `/recalculate` 端点：手动触发差异重算
    - 更新 `/{id}` 详情端点：返回含差异原因的完整行项数据
    - _Requirements: 1.5, 1.6, 1.7_

  - [~] 14.2 修改 `module_entrust/controller/settlement_controller.py`
    - 新增 `/{id}/variance-detail` 端点：查看差异原因明细
    - 更新详情端点：返回订购vs实际对比数据
    - _Requirements: 10.2, 10.3, 10.4_

  - [~] 14.3 修改 `module_entrust/controller/supplier_claim_controller.py`
    - 更新供应商查看明细端点：展示每笔订单的差异金额及差异原因
    - _Requirements: 2.2_

  - [~] 14.4 修改 `module_entrust/controller/reconciliation_report_controller.py`
    - 更新仪表盘端点：返回货不对板统计
    - 新增异常报告导出端点
    - _Requirements: 6.1, 7.5_

- [ ] 15. 审计日志与安全（验证现有实现）
  - [~] 15.1 验证并补充 `module_entrust/service/reconciliation_audit_service.py`
    - 确保新增操作（虚拟入库 CRUD、差异重算、行项差异原因创建）都有审计日志
    - 确保审计日志不可删除/修改
    - _Requirements: 8.1, 8.7_

  - [ ]* 15.2 Write property test for audit log immutability and completeness
    - **Property 19: Audit log immutability and completeness**
    - **Validates: Requirements 8.1, 8.7**
    - 生成随机审计记录 + 删改操作，验证不可变性

- [~] 16. Final checkpoint - 确保所有功能集成正确
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (20 properties)
- Unit tests validate specific examples and edge cases
- 现有文件采用修改策略而非重写，保持向后兼容
- 数据库迁移包含回填逻辑，确保旧数据在新字段中有合理默认值
- VarianceCalculationService 的 `calculate_order_variance()` 是纯函数，便于测试
- 虚拟入库服务是全新模块，无需考虑旧代码兼容

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "2.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "3.1"] },
    { "id": 4, "tasks": ["3.2", "3.3", "5.1"] },
    { "id": 5, "tasks": ["5.2", "5.3", "5.4", "5.5", "6.1"] },
    { "id": 6, "tasks": ["5.6", "5.7", "5.8", "6.2", "6.3"] },
    { "id": 7, "tasks": ["7.1", "9.1", "9.2", "10.1"] },
    { "id": 8, "tasks": ["7.2", "7.3", "9.3", "9.4", "9.5", "9.6", "10.2", "11.1"] },
    { "id": 9, "tasks": ["11.2", "13.1", "13.3", "13.4"] },
    { "id": 10, "tasks": ["13.2", "13.5", "14.1", "14.2", "14.3", "14.4"] },
    { "id": 11, "tasks": ["15.1"] },
    { "id": 12, "tasks": ["15.2"] }
  ]
}
```
