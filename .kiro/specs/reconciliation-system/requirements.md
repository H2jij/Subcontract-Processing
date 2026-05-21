# Requirements Document

## Introduction

对账系统用于委外加工业务中，**以真实的委外订购单为对账基准**，按月度、按供应商维度，对比"下单花费的金额"与"实际收到产品的价值"，找出每笔因异常问题导致的"货不对板"差异及其原因。

对账的核心公式：

```
对账差异 = 订购金额 -（实际交付价值 + 虚拟入库价值 - 异常扣除金额 + 物流费用）
```

- **订购金额**：我下的委外订购单上约定的总金额（单价 × 数量）
- **实际交付价值**：供应商实际交付且质检合格的产品价值
- **虚拟入库价值**：因异常补发的材料/零件，虽未走正式入库流程但需计入已收价值
- **异常扣除金额**：因问题决定不补发，直接从订单中扣除的款项
- **物流费用**：该订单产生的运输/物流费用

当差异不为零时，系统需追溯到具体的异常记录，说明是什么原因导致了"花的钱"和"收到的东西"对不上。

本文档覆盖：对账单生成与差异计算（需求1）、供应商确认（需求2）、异常识别与比对（需求3）、调整审批（需求4）、付款管理（需求5）、报表统计（需求6）、导出打印（需求7）、安全审计（需求8）、生产异常与责任判定（需求9）、订单结算明细（需求10）、PDF导出（需求11）、支付凭证（需求12）、虚拟入库（需求13）。

## Glossary

- **Reconciliation_System（对账系统）**: 以委外订购单为基准，对比订购金额与实际收到价值，识别差异并追溯原因的子系统
- **Reconciliation_Statement（对账单）**: 按供应商、按月度生成的对账清单，逐单对比订购金额与实际交付价值，标注差异及原因
- **Entrust_Order（委外订购单）**: 对账的基准数据源，记录了我方向供应商下单的零件、数量、单价、总金额
- **Eligible_Order（合格工单）**: status=delivered 且 quality_status=pass 的委外工单，具备进入对账流程的资格
- **Actual_Delivery（实际交付）**: 供应商实际交付且质检合格的产品，数量和金额可能与订购单不一致
- **Virtual_Inbound（虚拟入库）**: 因异常补发的材料/零件在系统中的登记记录，标注异常原因和责任方，计入已收价值
- **Anomaly_Deduction（异常扣除）**: 因问题决定不补发而直接从订单金额中扣除的款项，备注不补发原因
- **Order_Variance（订单差异）**: 订购金额与实际收到价值之间的差额，差异不为零即为"货不对板"
- **Variance_Reason（差异原因）**: 导致货不对板的具体原因，关联到 Production_Anomaly 记录
- **Supplier_Claim（供应商账单）**: 供应商提交的应收款项明细，用于与系统对账单进行核对
- **Anomaly（对账异常）**: 对账过程中发现的数据不一致，包括金额差异、数量差异、漏报、质量争议等
- **Adjustment（调整）**: 对对账金额的修正操作，需经审批流程确认后生效
- **Reconciliation_Period（对账周期）**: 对账的时间范围，默认为自然月
- **Confirmation_Status（确认状态）**: pending（待确认）、confirmed（已确认）、disputed（有争议）
- **Payment_Request（付款申请）**: 对账确认后生成的付款请求单
- **Payment_Record（付款记录）**: 实际付款操作的记录
- **Production_Anomaly（生产异常）**: 生产过程中的材料损坏或加工失误，是导致"货不对板"的根本原因
- **Liability_Type（责任类型）**: material_supplier_fault（材料方责任）或 processor_fault（加工方责任）
- **Re_Shipment（补发）**: 因异常导致的重新发货，补发后需做虚拟入库
- **Settlement_Detail（结算明细）**: 订单完整的收支对比明细，展示订购基准 vs 实际收到 vs 差异原因
- **Payment_Evidence（支付凭证）**: 付款证明文件

## Requirements

### Requirement 1: 对账单生成与差异计算

**User Story:** 作为财务人员，我希望系统以委外订购单为基准，按月度自动生成对账单，对比每笔订单"下单花的钱"与"实际收到的产品价值"，自动找出差异并关联异常原因，以便快速定位"货不对板"的问题。

#### Acceptance Criteria

1. WHEN 对账周期结束（自然月末）且存在 Eligible_Order, THE Reconciliation_System SHALL 按 supplier_id 分组，以委外订购单为基准生成该周期的 Reconciliation_Statement
2. THE Reconciliation_Statement 每个行项 SHALL 对应一笔真实的委外订购单，包含：order_no（委外单号）、part_no（零件编号）、part_name（零件名称）、ordered_quantity（订购数量）、ordered_unit_price（订购单价）、order_amount（订购金额 = 订购数量 × 订购单价）
3. THE Reconciliation_System SHALL 对每个行项计算实际收到价值：actual_received_value = 实际交付数量 × 单价 + 虚拟入库数量 × 单价（补发部分）- 异常扣除金额（不补发部分）
4. THE Reconciliation_System SHALL 对每个行项计算物流费用分摊：logistics_cost = 该订单关联的物流费用
5. THE Reconciliation_System SHALL 对每个行项计算差异金额：variance = order_amount -（actual_received_value + logistics_cost），variance 不为零即标记为"货不对板"
6. WHEN 行项 variance 不为零时, THE Reconciliation_System SHALL 自动关联导致差异的 Production_Anomaly 记录和 Virtual_Inbound 记录，逐条列出差异原因（材料损坏/加工失误/零件不可用/部分交付/补发入库/异常扣除等）
7. THE Reconciliation_System SHALL 计算对账单汇总：订购总金额、实际收到总价值、物流总费用、差异总金额、异常笔数、货不对板行项数
8. WHEN 财务人员手动触发对账单生成时, THE Reconciliation_System SHALL 支持自定义 Reconciliation_Period 的起止日期
9. THE Reconciliation_System SHALL 为每份 Reconciliation_Statement 生成唯一编号，格式为 REC-{YYYYMM}-{supplier_id}-{序号}
10. WHILE Reconciliation_Statement 处于 pending 状态, THE Reconciliation_System SHALL 允许财务人员对行项进行增删改操作
11. IF 指定 Reconciliation_Period 内某供应商无 Eligible_Order, THEN THE Reconciliation_System SHALL 不生成该供应商的 Reconciliation_Statement

### Requirement 2: 供应商对账确认

**User Story:** 作为供应商，我希望能在线查看对账单中每笔订单的差异明细和原因，确认或提出异议，以便及时完成对账。

#### Acceptance Criteria

1. WHEN Reconciliation_Statement 生成完成, THE Reconciliation_System SHALL 向对应供应商发送对账通知
2. THE Reconciliation_System SHALL 提供供应商查看 Reconciliation_Statement 明细的界面，展示每笔订单的订购金额、实际收到价值、差异金额及差异原因
3. WHEN 供应商通过系统界面主动点击"确认"操作时, THE Reconciliation_System SHALL 将 Confirmation_Status 更新为 confirmed，并记录确认时间和确认人；系统不得通过超时或自动规则将状态设为 confirmed
4. WHEN 供应商对对账单存在异议时, THE Reconciliation_System SHALL 将 Confirmation_Status 更新为 disputed，并要求供应商填写争议说明（可针对具体行项的差异原因提出异议）
5. WHILE Confirmation_Status 为 pending 且超过 7 个自然日, THE Reconciliation_System SHALL 向供应商发送催办提醒
6. IF 供应商在 Reconciliation_Statement 发出后 15 个自然日内未响应, THEN THE Reconciliation_System SHALL 将该对账单标记为超时未确认，并通知财务人员
7. THE Reconciliation_System SHALL 记录每份 Reconciliation_Statement 的完整确认历史

### Requirement 3: 异常数据识别与差异比对

**User Story:** 作为财务人员，我希望系统在供应商提交账单时，自动与我方订购单进行比对，找出每笔"货不对板"的差异并归类原因。

#### Acceptance Criteria

1. WHEN 供应商提交 Supplier_Claim 时, THE Reconciliation_System SHALL 将 Supplier_Claim 各行项与对应的委外订购单进行逐项比对
2. WHEN Supplier_Claim 行项金额与订购单金额存在差异时, THE Reconciliation_System SHALL 生成类型为"金额差异"的 Anomaly 记录，并记录差异金额
3. WHEN Supplier_Claim 行项数量与订购单数量不一致时, THE Reconciliation_System SHALL 生成类型为"数量差异"的 Anomaly 记录，并关联可能的 Production_Anomaly（如部分交付、损坏等）
4. WHEN 订购单中存在行项但 Supplier_Claim 中缺失对应条目时, THE Reconciliation_System SHALL 生成类型为"供应商漏报"的 Anomaly 记录
5. WHEN Supplier_Claim 中同一 order_no 出现多次时, THE Reconciliation_System SHALL 生成类型为"重复申报"的 Anomaly 记录
6. WHEN Supplier_Claim 包含 quality_status 为 fail 的工单时, THE Reconciliation_System SHALL 生成类型为"质量争议"的 Anomaly 记录
7. THE Reconciliation_System SHALL 为每条 Anomaly 记录分配严重程度：critical（差异金额超过行项金额 10% 或涉及质量争议）、warning（差异 5%-10%）、info（差异 5% 以内）
8. THE Reconciliation_System SHALL 为每条 Anomaly 记录维护处理状态：open → investigating → resolved → closed
9. WHEN Anomaly 被创建时, THE Reconciliation_System SHALL 通知相关财务人员处理

### Requirement 4: 异常调整与审批

**User Story:** 作为财务主管，我希望对账异常的调整操作需经过审批流程，确保金额变更有据可查、合规可控。

#### Acceptance Criteria

1. WHEN 财务人员针对 Anomaly 提出金额调整时, THE Reconciliation_System SHALL 创建 Adjustment 记录，包含原金额、调整后金额、调整原因
2. THE Reconciliation_System SHALL 根据调整金额设定审批层级：≤1000元由财务主管审批，>1000元由财务总监审批
3. WHILE Adjustment 处于待审批状态, THE Reconciliation_System SHALL 冻结对应行项金额，禁止重复调整
4. WHEN 审批人批准 Adjustment 时, THE Reconciliation_System SHALL 更新对应行项金额，并重新计算差异和汇总
5. WHEN 审批人驳回 Adjustment 时, THE Reconciliation_System SHALL 将 Adjustment 状态标记为 rejected，并通知发起人
6. THE Reconciliation_System SHALL 记录完整的 Adjustment 审批历史
7. IF 审批人在 3 个工作日内未处理, THEN THE Reconciliation_System SHALL 发送催办通知并自动升级至上级审批人

### Requirement 5: 付款申请与记录

**User Story:** 作为财务人员，我希望对账确认后能自动生成付款申请并跟踪付款状态。

#### Acceptance Criteria

1. WHEN Reconciliation_Statement 的 Confirmation_Status 变为 confirmed 时, THE Reconciliation_System SHALL 自动生成 Payment_Request，应付金额 = 实际收到总价值 + 物流总费用（即扣除差异后的实际应付金额）
2. THE Reconciliation_System SHALL 为 Payment_Request 维护付款状态：pending_payment / partially_paid / paid
3. WHEN 财务人员录入实际付款信息时, THE Reconciliation_System SHALL 记录 Payment_Record，包含付款日期、付款金额、银行流水号
4. THE Reconciliation_System SHALL 支持针对同一对账单录入多笔 Payment_Record（部分付款场景），并自动计算已付金额与剩余应付金额
5. WHEN 累计付款金额等于应付金额时, THE Reconciliation_System SHALL 将付款状态更新为 paid
6. WHEN 累计付款金额小于应付金额时, THE Reconciliation_System SHALL 将付款状态更新为 partially_paid
7. THE Reconciliation_System SHALL 在 Payment_Record 中关联对应的 Reconciliation_Statement 编号

### Requirement 6: 对账报表与统计

**User Story:** 作为财务主管，我希望通过仪表盘了解对账整体情况，特别是"货不对板"的比例和趋势。

#### Acceptance Criteria

1. THE Reconciliation_System SHALL 提供对账概览仪表盘：对账单总数、已确认数量、有争议数量、待确认数量、货不对板订单数、差异总金额
2. THE Reconciliation_System SHALL 提供按供应商维度的对账汇总：每个供应商的订购总金额、实际收到总价值、差异总金额、异常笔数
3. THE Reconciliation_System SHALL 提供月度趋势：对账单数量趋势、货不对板比例趋势、差异金额趋势、平均确认耗时
4. THE Reconciliation_System SHALL 提供账龄分析：将未付款项按 0-30天、31-60天、61-90天、90天以上分组
5. WHEN 财务人员查看报表时, THE Reconciliation_System SHALL 支持按时间范围、供应商、差异状态进行筛选
6. THE Reconciliation_System SHALL 每日自动更新仪表盘统计数据

### Requirement 7: 对账单导出与打印

**User Story:** 作为财务人员，我希望能将对账单（含差异明细和原因）导出为 Excel 和 PDF 格式。

#### Acceptance Criteria

1. WHEN 财务人员选择导出 Excel 时, THE Reconciliation_System SHALL 生成 .xlsx 文件，包含：订购金额、实际收到价值、差异金额、差异原因、物流费用等完整对账信息
2. WHEN 财务人员选择导出 PDF 时, THE Reconciliation_System SHALL 生成正式格式 PDF，包含公司印章/签名区域
3. THE Reconciliation_System SHALL 支持批量导出
4. THE Reconciliation_System SHALL 在 PDF 中包含甲方和乙方签章位置
5. WHEN 财务人员选择导出异常报告时, THE Reconciliation_System SHALL 单独生成异常报告，包含所有"货不对板"行项的详细差异原因
6. IF 导出失败, THEN THE Reconciliation_System SHALL 通知操作人员并记录失败原因

### Requirement 8: 对账数据安全与审计

**User Story:** 作为系统管理员，我希望对账系统具备完善的数据安全和审计追踪能力。

#### Acceptance Criteria

1. THE Reconciliation_System SHALL 记录所有对账操作的审计日志
2. THE Reconciliation_System SHALL 基于角色权限控制数据访问
3. WHILE Reconciliation_Statement 处于 confirmed 或 paid 状态, THE Reconciliation_System SHALL 禁止修改
4. WHEN 管理员发起数据回滚请求时, THE Reconciliation_System SHALL 仅允许对 24 小时内的误操作进行回滚，且需管理员审批
5. THE Reconciliation_System SHALL 保留所有历史数据至少 3 年
6. IF 未授权用户尝试访问对账数据, THEN THE Reconciliation_System SHALL 拒绝访问并记录安全事件
7. THE Reconciliation_System SHALL 对审计日志本身实施保护，禁止删除或篡改

### Requirement 9: 生产异常与责任判定

**User Story:** 作为业务人员，我希望系统能记录生产异常并判定责任方，这些异常记录是对账时追溯"货不对板"原因的依据。

#### Acceptance Criteria

1. WHEN 生产过程中发生材料损坏、加工失误或零件不可使用事件时, THE Reconciliation_System SHALL 创建 Production_Anomaly 记录，包含异常类型、发生时间、涉及零件、损失描述
2. THE Reconciliation_System SHALL 支持将 Liability_Type 分类为 material_supplier_fault 或 processor_fault
3. WHEN Liability_Type 为 material_supplier_fault 时, THE Reconciliation_System SHALL 自动创建材料 Re_Shipment 请求
4. WHEN Liability_Type 为 processor_fault 时, THE Reconciliation_System SHALL 创建零件 Re_Shipment 请求或生成扣款记录（由业务人员选择）
5. THE Reconciliation_System SHALL 记录 Production_Anomaly 的协商过程
6. THE Reconciliation_System SHALL 将每条 Production_Anomaly 关联至具体的委外工单和零件
7. WHEN Production_Anomaly 确认责任方后, THE Reconciliation_System SHALL 计算损失金额 = 材料成本 + 返工成本 + 误工费
8. THE Reconciliation_System SHALL 确保每条 Production_Anomaly 在对账时能被自动关联到对应行项的差异原因中

### Requirement 10: 订单结算明细

**User Story:** 作为财务人员，我希望每个订单完成后，系统能以订购单为基准生成完整的结算明细，清晰展示"下单花的钱"vs"实际收到的东西"，并逐项追溯每笔差异的原因。

#### Acceptance Criteria

1. WHEN 委外工单状态变为 delivered 且 quality_status 为 pass 时, THE Reconciliation_System SHALL 生成该订单的 Settlement_Detail
2. THE Settlement_Detail SHALL 以委外订购单为基准，包含以下对比：
   - 订购基准：订购数量、订购单价、订购总金额（下单花的钱）
   - 实际交付：实际交付数量、实际交付金额（质检合格的产品价值）
   - 虚拟入库：因异常补发的数量和金额（补发材料/零件的价值）
   - 物流费用：该订单产生的物流费用
   - 异常扣除：因不补发而从订单扣除的金额
3. THE Settlement_Detail SHALL 计算订单差异：差异金额 = 订购总金额 -（实际交付金额 + 虚拟入库金额 - 异常扣除金额 + 物流费用）
4. WHEN 订单存在差异时, THE Settlement_Detail SHALL 逐项列出导致差异的原因，每条原因关联具体的 Production_Anomaly，说明：异常类型、责任方、处理方式、影响金额
5. THE Settlement_Detail SHALL 包含客户付款信息，记录终端客户为该订单支付给我方的金额
6. THE Reconciliation_System SHALL 计算净利润 = 客户付款金额 -（实际支付给供应商的金额 + 物流费用 + 补发费用 - 扣款回收金额）
7. WHILE Settlement_Detail 处于 draft 状态, THE Reconciliation_System SHALL 允许财务人员手动编辑
8. WHEN 财务人员确认 Settlement_Detail 后, THE Reconciliation_System SHALL 将其标记为 finalized

### Requirement 11: PDF 结算单生成与导出

**User Story:** 作为财务人员，我希望结算明细能生成为 PDF 格式，清晰展示订购 vs 实际收到的对比和差异原因。

#### Acceptance Criteria

1. WHEN 财务人员请求生成结算 PDF 时, THE Reconciliation_System SHALL 生成包含完整对比信息的 PDF 文件
2. THE PDF 文件 SHALL 包含：订单信息头、订购基准信息、实际交付信息、虚拟入库信息、差异金额及原因列表、物流费用、客户付款金额
3. THE PDF 文件 SHALL 在结算内容之后包含支付凭证区域
4. THE Reconciliation_System SHALL 支持 PDF 文件的下载和导出
5. THE PDF 文件 SHALL 包含公司信息和格式化排版
6. IF PDF 生成失败, THEN THE Reconciliation_System SHALL 通知操作人员并记录原因

### Requirement 12: 支付凭证与附件管理

**User Story:** 作为财务人员，我希望能上传支付凭证并关联到对应的结算记录。

#### Acceptance Criteria

1. THE Reconciliation_System SHALL 支持上传 Payment_Evidence 附件（jpg/png/pdf/jpeg）
2. THE Reconciliation_System SHALL 将 Payment_Evidence 关联至 Payment_Record 或 Settlement_Detail
3. THE Reconciliation_System SHALL 支持每条记录关联多个附件
4. THE Reconciliation_System SHALL 在 PDF 结算单中展示已关联的凭证
5. WHEN 用户上传文件时, THE Reconciliation_System SHALL 验证文件类型和大小
6. WHILE Settlement_Detail 处于 finalized 状态, THE Reconciliation_System SHALL 禁止删除已关联的附件
7. THE Reconciliation_System SHALL 记录每个附件的上传时间、上传人、文件名、文件大小

### Requirement 13: 虚拟入库与异常库存管理

**User Story:** 作为业务人员，我希望当订单因加工方或材料方问题导致补发时，系统能将补发内容进行虚拟入库并备注异常原因；如果决定不补发，则记录从订单中扣除的款项及原因。虚拟入库记录是对账时计算"实际收到价值"的重要组成部分。

#### Acceptance Criteria

1. WHEN Production_Anomaly 触发 Re_Shipment 且补发确认发货时, THE Reconciliation_System SHALL 自动创建 Virtual_Inbound 记录，关联工单、零件和补发记录
2. THE Virtual_Inbound 记录 SHALL 包含：入库类型（re_shipment_in/anomaly_deduction）、关联工单号、零件编号、零件名称、数量、单价、金额、异常原因说明、责任方、操作时间、操作人
3. WHEN 决定不补发而直接扣款时, THE Reconciliation_System SHALL 创建入库类型为"anomaly_deduction"的记录，备注扣除原因
4. THE Reconciliation_System SHALL 强制要求填写异常原因说明：异常类型 + 责任方判定 + 处理方式
5. WHEN Virtual_Inbound 记录创建后, THE Reconciliation_System SHALL 自动将其纳入对应订单的对账计算（计入 actual_received_value）
6. THE Reconciliation_System SHALL 提供虚拟入库记录的列表查询，支持按工单号、零件、入库类型、责任方、时间范围筛选
7. THE Reconciliation_System SHALL 在 Settlement_Detail 中展示所有关联的 Virtual_Inbound 记录
8. WHILE 关联的 Settlement_Detail 处于 finalized 状态, THE Reconciliation_System SHALL 禁止修改或删除虚拟入库记录
