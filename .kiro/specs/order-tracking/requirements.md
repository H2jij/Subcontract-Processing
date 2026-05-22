# Requirements Document

## Introduction

订单全生命周期资金追踪系统是对现有对账系统的前置扩展。现有对账系统仅在交付后进行"事后对账"（post-delivery reconciliation），计算订购金额与实际收到价值的差异。本功能将追踪范围前移至**订单下达时刻**，记录从下单到最终付款的每一笔资金事件，形成完整的订单资金流水。

核心价值：
- **实时可见性**：任何时刻都能查看某订单已发生的累计成本
- **事件驱动**：订单状态变更、生产异常、补发、扣款、收货、付款等事件自动产生流水记录
- **收货确认**：引入实际收货数量确认环节，替代现有"默认全量交付"的假设
- **物流费用关联**：将物流费用精确关联到具体订单，替代现有 logistics_cost=0 的硬编码
- **无缝衔接**：收货确认后自动触发对账差异重算，流水数据为对账提供完整的成本依据

本文档覆盖：订单资金流水表（需求1）、收货确认环节（需求2）、物流费用关联（需求3）、自动触发机制（需求4）。

## Glossary

- **Order_Tracking_System（订单追踪系统）**: 记录订单从下达到付款全生命周期资金事件的子系统
- **Order_Financial_Ledger（订单资金流水表）**: 记录某订单所有资金事件的流水账，每条记录对应一笔资金变动
- **Financial_Event（资金事件）**: 订单生命周期中产生的一笔资金变动记录，包含事件类型、金额、累计余额
- **Running_Balance（累计余额）**: 某订单截至当前事件的累计成本总额，每新增一条流水自动更新
- **Event_Type（事件类型）**: 资金事件的分类，包括 order_placed（下单）、material_sent（材料发出）、logistics_paid（物流付款）、production_anomaly（生产异常）、re_shipment（补发）、deduction（扣款）、delivery_received（收货）、payment_made（付款）
- **Delivery_Receipt（收货确认）**: 货物到达后由用户录入的实际收货信息，包含实际数量、质量状态等
- **Logistics_Record（物流记录）**: 某订单的一次物流运输记录，包含物流公司、运单号、费用等
- **EntrustOutsourceOrder（委外工单）**: 现有系统中的委外订购单实体，是订单追踪的主体
- **ReconciliationStatement（对账单）**: 现有对账系统中按供应商按月生成的对账清单
- **VirtualInbound（虚拟入库）**: 现有系统中因异常补发的材料/零件登记记录
- **ProductionAnomaly（生产异常）**: 现有系统中的生产过程异常记录
- **ReShipment（补发记录）**: 现有系统中因异常导致的重新发货记录
- **Deduction（扣款记录）**: 现有系统中因问题不补发而直接扣除的款项记录
- **Variance_Recalculation（差异重算）**: 收货确认后触发的对账差异重新计算过程

## Requirements

### Requirement 1: 订单资金流水表

**User Story:** 作为财务人员，我希望系统能记录每个委外订单从下单到付款的所有资金事件，形成完整的资金流水账，以便随时查看某订单的累计成本和资金变动历史。

#### Acceptance Criteria

1. THE Order_Tracking_System SHALL 为每条 Financial_Event 记录以下字段：order_id（关联委外工单ID）、event_type（事件类型）、amount（金额，正数=成本支出，负数=资金回收）、running_balance（累计余额）、description（事件描述）、related_entity_id（关联实体ID）、related_entity_type（关联实体类型）、created_at（创建时间）、created_by（创建人）
2. THE Order_Tracking_System SHALL 支持以下 Event_Type 分类：order_placed（下单）、material_sent（材料发出）、logistics_paid（物流付款）、production_anomaly（生产异常）、re_shipment（补发）、deduction（扣款，金额为负数表示回收）、delivery_received（收货）、payment_made（付款）
3. WHEN 新的 Financial_Event 创建时, THE Order_Tracking_System SHALL 自动计算 Running_Balance = 该订单上一条流水的 Running_Balance + 当前事件的 amount
4. IF 该订单无历史流水记录, THEN THE Order_Tracking_System SHALL 将首条流水的 Running_Balance 设为该条流水的 amount
5. THE Order_Tracking_System SHALL 提供按 order_id 查询该订单全部资金流水的接口，返回结果按 created_at 升序排列
6. THE Order_Tracking_System SHALL 提供按时间范围、事件类型、供应商筛选资金流水的列表查询接口
7. THE Order_Tracking_System SHALL 确保同一订单的流水记录按时间顺序保持 Running_Balance 的连续性和一致性
8. IF 流水记录创建后发现金额错误, THEN THE Order_Tracking_System SHALL 通过创建一条冲正流水（reversal）进行修正，禁止直接修改已有流水记录

### Requirement 2: 收货确认环节

**User Story:** 作为仓库/质检人员，我希望在货物到达时能录入实际收货数量和质量状态，以便系统用真实数据替代"默认全量交付"的假设来计算对账差异。

#### Acceptance Criteria

1. WHEN 货物到达时, THE Order_Tracking_System SHALL 支持用户创建 Delivery_Receipt 记录，包含以下字段：order_id（关联委外工单ID）、received_quantity（实际收货数量）、received_date（收货日期）、quality_status（质量状态：pass/partial_pass/fail）、inspector（验收人）、remarks（备注）
2. THE Order_Tracking_System SHALL 支持同一订单创建多条 Delivery_Receipt 记录（分批到货场景）
3. WHEN received_quantity 与 EntrustOutsourceOrder 的 ordered_quantity 不一致时, THE Order_Tracking_System SHALL 自动将该订单标记为存在数量差异
4. THE Order_Tracking_System SHALL 计算同一订单所有 Delivery_Receipt 的累计收货数量，并与订购数量进行对比
5. WHEN Delivery_Receipt 创建成功后, THE Order_Tracking_System SHALL 自动创建一条 event_type 为 delivery_received 的 Financial_Event 流水记录
6. WHEN Delivery_Receipt 的 quality_status 为 fail 时, THE Order_Tracking_System SHALL 将该批次收货数量排除在有效收货数量之外
7. THE Order_Tracking_System SHALL 提供按 order_id 查询所有收货记录的接口
8. WHEN 所有批次的有效收货数量（quality_status 为 pass 或 partial_pass）累计完成后, THE Order_Tracking_System SHALL 触发对账系统的 Variance_Recalculation，使用实际收货数量替代默认的订购数量进行差异计算

### Requirement 3: 物流费用关联

**User Story:** 作为财务人员，我希望能将每笔物流运输费用精确关联到具体的委外订单，以便对账时使用真实物流费用替代当前硬编码的 logistics_cost=0。

#### Acceptance Criteria

1. THE Order_Tracking_System SHALL 支持为每个订单创建 Logistics_Record，包含以下字段：order_id（关联委外工单ID）、logistics_company（物流公司名称）、tracking_no（运单号）、shipping_date（发货日期）、delivery_date（到货日期）、cost（物流费用金额）、payment_status（付款状态：unpaid/paid）、receipt_image（物流回单图片路径）
2. THE Order_Tracking_System SHALL 支持同一订单关联多条 Logistics_Record（分批发货场景）
3. THE Order_Tracking_System SHALL 自动计算同一订单所有 Logistics_Record 的费用合计（total_logistics_cost）
4. WHEN Logistics_Record 创建成功后, THE Order_Tracking_System SHALL 自动创建一条 event_type 为 logistics_paid 的 Financial_Event 流水记录
5. WHEN 对账系统计算订单物流费用时, THE Order_Tracking_System SHALL 提供该订单的 total_logistics_cost 作为 ReconciliationLineItem 的 logistics_cost 字段值，替代现有的硬编码值 0
6. THE Order_Tracking_System SHALL 提供按 order_id 查询所有物流记录的接口
7. THE Order_Tracking_System SHALL 支持上传物流回单图片（jpg/png/pdf 格式）作为费用凭证
8. WHEN Logistics_Record 的 payment_status 变更为 paid 时, THE Order_Tracking_System SHALL 更新对应 Financial_Event 的描述信息标注已付款

### Requirement 4: 自动触发机制

**User Story:** 作为系统管理员，我希望订单状态变更和关键业务事件能自动产生资金流水记录，无需人工干预，以确保流水数据的完整性和实时性。

#### Acceptance Criteria

1. WHEN EntrustOutsourceOrder 的 status 从 awarded 变更为 accepted 时, THE Order_Tracking_System SHALL 自动创建一条 event_type 为 order_placed 的 Financial_Event，amount 为该订单的 total_amount（订购总金额）
2. WHEN EntrustOutsourceOrder 的 status 变更为 producing 时, THE Order_Tracking_System SHALL 自动创建一条 event_type 为 material_sent 的 Financial_Event，amount 为该订单关联的材料成本（如有）
3. WHEN ProductionAnomaly 创建且关联到某订单时, THE Order_Tracking_System SHALL 自动创建一条 event_type 为 production_anomaly 的 Financial_Event，amount 为该异常的 total_loss
4. WHEN ReShipment 的 status 变更为 shipped 时, THE Order_Tracking_System SHALL 自动创建一条 event_type 为 re_shipment 的 Financial_Event，amount 为补发物品的估算成本
5. WHEN ReShipment 确认发货时, THE Order_Tracking_System SHALL 同时触发现有系统的 VirtualInbound 创建流程
6. WHEN Deduction 的 status 变更为 applied 时, THE Order_Tracking_System SHALL 自动创建一条 event_type 为 deduction 的 Financial_Event，amount 为负数（表示资金回收）
7. WHEN Delivery_Receipt 创建成功时, THE Order_Tracking_System SHALL 自动触发对账系统的 Variance_Recalculation，将 actual_delivered_qty 更新为实际累计有效收货数量
8. WHEN PaymentRecord 创建且关联到某订单时, THE Order_Tracking_System SHALL 自动创建一条 event_type 为 payment_made 的 Financial_Event，amount 为付款金额
9. IF 自动触发过程中发生异常（数据库错误、关联实体不存在等）, THEN THE Order_Tracking_System SHALL 记录错误日志并发送告警通知，流水创建失败不得影响原业务操作的正常执行
10. THE Order_Tracking_System SHALL 确保每个自动触发的 Financial_Event 记录 related_entity_id 和 related_entity_type，以便追溯触发来源
