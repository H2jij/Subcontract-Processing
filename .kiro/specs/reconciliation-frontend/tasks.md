# Implementation Plan: Reconciliation Frontend (对账系统前端)

## Overview

基于 uni-app (Vue 3 Composition API) + Pinia + TailwindCSS + TypeScript 构建对账系统移动端前端。实现对账管理、供应商确认、异常管理、付款管理、结算明细、虚拟入库、生产异常、仪表盘与报表共 8 个业务模块，包含 26 个页面、11 个通用组件、8 个 API 服务模块和 8 个 Pinia Store。

## Tasks

- [x] 1. Foundation: Types + Utils + Constants
  - [x] 1.1 Create TypeScript type definitions
    - Create `src/types/reconciliation.ts` with all interfaces: PageResult, PageParams, all enum types (StatementStatus, ConfirmationStatus, SettlementStatus, PaymentStatus, AnomalyStatus, Severity, AnomalyType, ProductionAnomalyType, InboundType, VirtualInboundStatus, ResponsibleParty, ApprovalStatus, VarianceReasonType), all VO interfaces (ReconciliationStatementVO, ReconciliationLineItemVO, VarianceReasonVO, VarianceSummaryVO, AnomalyVO, AdjustmentVO, PaymentRequestVO, PaymentRecordVO, PaymentEvidenceVO, SettlementDetailVO, VirtualInboundVO, ProductionAnomalyVO, ReShipmentVO, DeductionVO, NegotiationRecordVO, DashboardVO, SupplierSummaryVO, MonthlyTrendVO, AgingAnalysisVO, AgingBucketVO), and all request param interfaces
    - _Requirements: 10.1_

  - [x] 1.2 Create formatters utility
    - Create `src/utils/reconciliation/formatters.ts` with: `formatAmount(value)` → ¥X,XXX.XX format, `formatDate(dateStr)` → YYYY-MM-DD, `formatPeriod(start, end)` → date range display
    - _Requirements: 1.12, 4.10, 5.11, 6.11, 7.12, 8.10_

  - [x] 1.3 Create validators utility
    - Create `src/utils/reconciliation/validators.ts` with: `validateRequired(value)`, `validateAmount(value)`, `validateQuantity(value)`, `validatePaymentAmount(value, remaining)`, `validateFileUpload(fileName, fileSize)`
    - _Requirements: 11.1, 11.2, 11.3, 4.5, 4.7_

  - [x] 1.4 Create constants utility
    - Create `src/utils/reconciliation/constants.ts` with: `getVarianceColorClass(variance)`, `getSeverityConfig(severity)`, `getStatusConfig(status, type)`, `ROLE_MODULE_MAP`, `INBOUND_TYPE_LABELS`, `RESPONSIBLE_PARTY_LABELS`, `PRODUCTION_ANOMALY_TYPE_LABELS`, `getAgingBucket(days)`, `ERROR_CODE_MESSAGES`
    - _Requirements: 12.2, 12.4, 12.5, 9.3, 8.4_

  - [ ]* 1.5 Write property tests for formatters (Property 1)
    - **Property 1: Amount formatting produces valid ¥ format**
    - Test that `formatAmount` always produces ¥X.XX with exactly 2 decimal places for any numeric input
    - **Validates: Requirements 1.12, 4.10, 5.11, 6.11, 7.12, 8.10**

  - [ ]* 1.6 Write property tests for constants (Properties 2, 3, 4, 11, 12)
    - **Property 2: Variance indicator color mapping** — verify red/green/gray for positive/negative/zero
    - **Property 3: Severity color mapping** — verify correct colors for critical/warning/info
    - **Property 4: Status tag color mapping** — verify correct colors for all statement statuses
    - **Property 11: Aging bucket assignment** — verify correct bucket for any day count
    - **Property 12: Role-based module visibility** — verify correct modules per role
    - **Validates: Requirements 1.5, 2.4, 3.12, 12.2, 12.4, 12.5, 8.4, 9.3**

  - [ ]* 1.7 Write property tests for validators (Properties 7, 8, 9)
    - **Property 7: File upload validation** — verify extension and size checks
    - **Property 8: Form field validation rules** — verify required/amount/quantity validators
    - **Property 9: Payment amount constraint** — verify amount ≤ remaining balance
    - **Validates: Requirements 11.1, 11.2, 11.3, 4.5, 4.7**

- [x] 2. API Service Layer
  - [x] 2.1 Create reconciliation API service
    - Create `src/api/reconciliation/reconciliation.ts` with: `getStatementList`, `getStatementDetail`, `getVarianceSummary`, `generateStatement`, `recalculateVariance`, `notifySupplier`
    - _Requirements: 1.1, 1.4, 1.8, 1.10, 1.11_

  - [x] 2.2 Create supplier claim API service
    - Create `src/api/reconciliation/supplierClaim.ts` with: `getSupplierStatements`, `getSupplierStatementDetail`, `confirmStatement`, `disputeStatement`
    - _Requirements: 2.1, 2.3, 2.6, 2.7_

  - [x] 2.3 Create anomaly API service
    - Create `src/api/reconciliation/anomaly.ts` with: `getAnomalyList`, `getAnomalyDetail`, `createAdjustment`, `getPendingApprovals`, `approveAdjustment`, `rejectAdjustment`
    - _Requirements: 3.1, 3.4, 3.5, 3.7, 3.10, 3.11_

  - [x] 2.4 Create payment API service
    - Create `src/api/reconciliation/payment.ts` with: `getPaymentRequests`, `getPaymentRequestDetail`, `createPaymentRecord`, `uploadEvidence`, `deleteEvidence`
    - _Requirements: 4.1, 4.3, 4.4, 4.6, 4.7_

  - [x] 2.5 Create settlement API service
    - Create `src/api/reconciliation/settlement.ts` with: `getSettlementList`, `getSettlementDetail`, `updateSettlementLineItems`, `finalizeSettlement`, `getSettlementPdf`, `getVarianceDetail`
    - _Requirements: 5.1, 5.3, 5.6, 5.8, 5.9_

  - [x] 2.6 Create virtual inbound API service
    - Create `src/api/reconciliation/virtualInbound.ts` with: `getVirtualInboundList`, `getVirtualInboundDetail`, `createVirtualInbound`, `updateVirtualInbound`, `deleteVirtualInbound`, `getVirtualInboundByOrder`
    - _Requirements: 6.1, 6.4, 6.6, 6.8, 6.9, 6.10_

  - [x] 2.7 Create production anomaly API service
    - Create `src/api/reconciliation/productionAnomaly.ts` with: `getProductionAnomalyList`, `getProductionAnomalyDetail`, `createProductionAnomaly`, `setLiability`, `createReShipment`, `createDeduction`, `addNegotiation`
    - _Requirements: 7.1, 7.3, 7.5, 7.6, 7.8, 7.9, 7.11_

  - [x] 2.8 Create report API service
    - Create `src/api/reconciliation/report.ts` with: `getDashboard`, `getSupplierSummary`, `getMonthlyTrend`, `getAgingAnalysis`, `exportExcel`, `exportPdf`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.6, 8.7_

- [x] 3. Pinia Stores
  - [x] 3.1 Create reconciliation store
    - Create `src/store/modules/reconciliation/reconciliation.ts` with: list/total/loading/loadingMore state, filters, currentDetail, varianceSummary, fetchList/loadMore/fetchDetail/generate/recalculate actions
    - _Requirements: 1.1, 1.2, 1.4, 1.8, 1.10, 1.11, 10.3, 10.6_

  - [x] 3.2 Create supplier claim store
    - Create `src/store/modules/reconciliation/supplierClaim.ts` with: list state, currentDetail, confirm/dispute actions
    - _Requirements: 2.1, 2.2, 2.3, 2.6, 2.7, 10.3_

  - [x] 3.3 Create anomaly store
    - Create `src/store/modules/reconciliation/anomaly.ts` with: list state, filters, currentDetail, pendingApprovals, createAdjustment/approve/reject actions
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 10.3_

  - [x] 3.4 Create payment store
    - Create `src/store/modules/reconciliation/payment.ts` with: list state, currentDetail, paymentRecords, evidences, createRecord/uploadEvidence actions
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 10.3_

  - [x] 3.5 Create settlement store
    - Create `src/store/modules/reconciliation/settlement.ts` with: list state, currentDetail, editMode, updateLineItems/finalize/downloadPdf actions
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.8, 5.9, 10.3_

  - [x] 3.6 Create virtual inbound store
    - Create `src/store/modules/reconciliation/virtualInbound.ts` with: list state, filters, currentDetail, orderInbounds, create/update/delete/fetchByOrder actions
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6, 6.8, 6.9, 6.10, 10.3_

  - [x] 3.7 Create production anomaly store
    - Create `src/store/modules/reconciliation/productionAnomaly.ts` with: list state, currentDetail, negotiations, create/setLiability/createReShipment/createDeduction/addNegotiation actions
    - _Requirements: 7.1, 7.2, 7.3, 7.5, 7.6, 7.8, 7.9, 7.11, 10.3_

  - [x] 3.8 Create report store
    - Create `src/store/modules/reconciliation/report.ts` with: dashboard/trend/aging state, fetch actions, exportExcel/exportPdf actions
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.6, 8.7, 10.3_

  - [x] 3.9 Create store index file
    - Create `src/store/modules/reconciliation/index.ts` that re-exports all 8 stores
    - _Requirements: 10.3_

- [~] 4. Checkpoint - Foundation layers complete
  - Ensure all types compile correctly, utils have no TypeScript errors, API services reference correct types, and stores wire to API services. Ask the user if questions arise.

- [x] 5. Reusable Components
  - [x] 5.1 Create VarianceIndicator component
    - Create `src/components/reconciliation/VarianceIndicator.vue` — displays variance amount with color coding (red positive, green negative, gray zero)
    - _Requirements: 1.5, 2.4, 5.4, 12.2_

  - [x] 5.2 Create MismatchBadge component
    - Create `src/components/reconciliation/MismatchBadge.vue` — red vertical bar + "货不对板" label when show=true
    - _Requirements: 1.6, 2.4, 12.3_

  - [x] 5.3 Create StatusTag component
    - Create `src/components/reconciliation/StatusTag.vue` — colored pill label for statement/settlement/payment statuses
    - _Requirements: 12.5_

  - [x] 5.4 Create SeverityBadge component
    - Create `src/components/reconciliation/SeverityBadge.vue` — colored badge for critical/warning/info severity levels
    - _Requirements: 3.12, 12.4_

  - [x] 5.5 Create AmountDisplay component
    - Create `src/components/reconciliation/AmountDisplay.vue` — formatted ¥ amount with size variants (sm/md/lg), monospace font
    - _Requirements: 1.12, 12.7_

  - [x] 5.6 Create FilterPanel component
    - Create `src/components/reconciliation/FilterPanel.vue` — popup panel with slot for filter fields, reset/confirm buttons
    - _Requirements: 1.3, 3.2, 6.2_

  - [x] 5.7 Create ListContainer component
    - Create `src/components/reconciliation/ListContainer.vue` — scroll-view with pull-refresh, load-more, skeleton loading, empty state
    - _Requirements: 1.2, 2.2, 3.3, 4.2, 5.2, 6.3, 7.2, 12.8, 12.9_

  - [x] 5.8 Create EmptyState component
    - Create `src/components/reconciliation/EmptyState.vue` — friendly empty state with icon and message
    - _Requirements: 12.9_

  - [x] 5.9 Create SkeletonLoader component
    - Create `src/components/reconciliation/SkeletonLoader.vue` — skeleton placeholder cards during loading
    - _Requirements: 12.8_

  - [x] 5.10 Create ConfirmDialog component
    - Create `src/components/reconciliation/ConfirmDialog.vue` — secondary confirmation popup for destructive actions
    - _Requirements: 2.6, 5.8, 6.9, 11.6_

  - [x] 5.11 Create SearchSelect component
    - Create `src/components/reconciliation/SearchSelect.vue` — searchable selector for work orders and parts
    - _Requirements: 6.4, 7.3_

  - [ ]* 5.12 Write unit tests for components
    - Test VarianceIndicator renders correct colors for positive/negative/zero values
    - Test MismatchBadge shows/hides based on prop
    - Test StatusTag renders correct label and color per status
    - Test SeverityBadge renders correct styling per severity level
    - _Requirements: 1.5, 1.6, 3.12, 12.2, 12.3, 12.4, 12.5_

- [ ] 6. 对账管理 Pages (Statement Module)
  - [~] 6.1 Create reconciliation module entry page
    - Create `src/pages/reconciliation/index.vue` — module entry with feature cards/icon grid showing available sub-modules based on user role
    - _Requirements: 9.1, 9.3_

  - [~] 6.2 Create statement list page
    - Create `src/pages/reconciliation/statement/list.vue` — paginated list with filter panel (supplier, status, period), card layout showing statement_no, supplier, period, status, amounts
    - _Requirements: 1.1, 1.2, 1.3, 12.6_

  - [~] 6.3 Create statement detail page
    - Create `src/pages/reconciliation/statement/detail.vue` — variance summary section + line items list with VarianceIndicator, MismatchBadge, expandable variance reasons, recalculate button
    - _Requirements: 1.4, 1.5, 1.6, 1.7, 1.10, 1.11_

  - [~] 6.4 Create generate statement page
    - Create `src/pages/reconciliation/statement/generate.vue` — form with period date pickers and optional supplier selector, loading state on submit, auto-refresh list on success
    - _Requirements: 1.8, 1.9_

- [ ] 7. 供应商确认 Pages (Supplier Claim Module)
  - [~] 7.1 Create supplier claim list page
    - Create `src/pages/reconciliation/supplier-claim/list.vue` — paginated list showing current supplier's statements with statement_no, period, status, payable amount, variance
    - _Requirements: 2.1, 2.2_

  - [~] 7.2 Create supplier claim detail page
    - Create `src/pages/reconciliation/supplier-claim/detail.vue` — line items with VarianceIndicator/MismatchBadge, bottom action bar with "确认"/"有异议" buttons (hidden when confirmed/paid), confirm dialog
    - _Requirements: 2.3, 2.4, 2.5, 2.6, 2.8, 2.9_

  - [~] 7.3 Create dispute form page
    - Create `src/pages/reconciliation/supplier-claim/dispute.vue` — dispute reason textarea with character count, optional line item selection, submit validation
    - _Requirements: 2.7, 2.8, 11.7_

- [ ] 8. 异常管理 Pages (Anomaly Module)
  - [~] 8.1 Create anomaly list page
    - Create `src/pages/reconciliation/anomaly/list.vue` — paginated list with SeverityBadge, filter panel (type, severity, status), card layout
    - _Requirements: 3.1, 3.2, 3.3, 3.12_

  - [~] 8.2 Create anomaly detail page
    - Create `src/pages/reconciliation/anomaly/detail.vue` — full anomaly info display with severity badge, amounts, status, "提出调整" button
    - _Requirements: 3.4, 3.5_

  - [~] 8.3 Create adjustment form page
    - Create `src/pages/reconciliation/anomaly/adjustment.vue` — form with original amount (readonly), adjusted amount (validated), adjustment reason (required), submit logic
    - _Requirements: 3.5, 3.6, 11.2_

  - [~] 8.4 Create approval list page
    - Create `src/pages/reconciliation/anomaly/approval.vue` — pending approvals list with adjustment details, approve/reject buttons, reject reason dialog
    - _Requirements: 3.7, 3.8, 3.9, 3.10, 3.11_

- [ ] 9. 付款管理 Pages (Payment Module)
  - [~] 9.1 Create payment list page
    - Create `src/pages/reconciliation/payment/list.vue` — paginated list showing statement_no, supplier, payable/paid amounts, payment status
    - _Requirements: 4.1, 4.2_

  - [~] 9.2 Create payment detail page
    - Create `src/pages/reconciliation/payment/detail.vue` — payment request info, amount breakdown, payment records list, evidence thumbnails with preview, "录入付款" button
    - _Requirements: 4.3, 4.8, 4.9_

  - [~] 9.3 Create payment record form page
    - Create `src/pages/reconciliation/payment/record.vue` — form with payment amount (validated ≤ remaining), payment date picker, bank reference, file upload for evidence
    - _Requirements: 4.4, 4.5, 4.6, 4.7, 11.2_

- [ ] 10. 结算明细 Pages (Settlement Module)
  - [~] 10.1 Create settlement list page
    - Create `src/pages/reconciliation/settlement/list.vue` — paginated list showing order_no, supplier, ordered/delivered/variance amounts, status tag
    - _Requirements: 5.1, 5.2_

  - [~] 10.2 Create settlement detail page
    - Create `src/pages/reconciliation/settlement/detail.vue` — sectioned display (订购基准/实际交付/虚拟入库/异常扣除/物流/差异/净利润), edit mode toggle for draft, finalize button with confirm dialog, PDF download
    - _Requirements: 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11_

- [ ] 11. 虚拟入库 Pages (Virtual Inbound Module)
  - [~] 11.1 Create virtual inbound list page
    - Create `src/pages/reconciliation/virtual-inbound/list.vue` — paginated list with filter panel (order, part, type, responsible party), card layout
    - _Requirements: 6.1, 6.2, 6.3_

  - [~] 11.2 Create virtual inbound detail page
    - Create `src/pages/reconciliation/virtual-inbound/detail.vue` — full record display, edit/delete buttons (hidden when linked_to_settlement), confirm dialog for delete
    - _Requirements: 6.6, 6.7, 6.9_

  - [~] 11.3 Create virtual inbound create page
    - Create `src/pages/reconciliation/virtual-inbound/create.vue` — form with SearchSelect for order/part, type dropdown, quantity/unit_price inputs, auto-calculated amount, reason textarea, responsible party dropdown
    - _Requirements: 6.4, 6.5, 6.11, 11.1, 11.2, 11.3_

  - [~] 11.4 Create virtual inbound edit page
    - Create `src/pages/reconciliation/virtual-inbound/edit.vue` — pre-filled edit form (same fields as create), submit calls update API
    - _Requirements: 6.8_

- [ ] 12. 生产异常 Pages (Production Anomaly Module)
  - [~] 12.1 Create production anomaly list page
    - Create `src/pages/reconciliation/production-anomaly/list.vue` — paginated list showing anomaly type, order, part, responsible party, loss amount, status
    - _Requirements: 7.1, 7.2_

  - [~] 12.2 Create production anomaly detail page
    - Create `src/pages/reconciliation/production-anomaly/detail.vue` — full info display, liability judgment section, re-shipment/deduction action area, negotiation records with add form
    - _Requirements: 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11_

  - [~] 12.3 Create production anomaly create page
    - Create `src/pages/reconciliation/production-anomaly/create.vue` — form with SearchSelect for order/part, anomaly type dropdown, description textarea, date picker
    - _Requirements: 7.3, 7.4, 7.12_

- [ ] 13. 仪表盘与报表 Pages (Report Module)
  - [~] 13.1 Create dashboard page
    - Create `src/pages/reconciliation/report/dashboard.vue` — KPI cards (total/confirmed/disputed/pending/mismatch/variance), supplier summary list, time range filter, export buttons
    - _Requirements: 8.1, 8.2, 8.5, 8.6, 8.7, 8.8, 8.9_

  - [~] 13.2 Create monthly trend page
    - Create `src/pages/reconciliation/report/trend.vue` — line/bar chart showing statement count, mismatch ratio, variance amount trends
    - _Requirements: 8.3, 8.10_

  - [~] 13.3 Create aging analysis page
    - Create `src/pages/reconciliation/report/aging.vue` — grouped display of unpaid items by aging bucket (0-30, 31-60, 61-90, 90+) with count and amount per bucket
    - _Requirements: 8.4, 8.10_

- [~] 14. Checkpoint - All pages implemented
  - Ensure all 26 pages compile without TypeScript errors, components render correctly, stores connect to API services. Ask the user if questions arise.

- [ ] 15. Navigation & Routing
  - [~] 15.1 Register pages in pages.json
    - Update `src/pages.json` to add all 26 reconciliation pages with correct paths and navigationBarTitleText in Chinese
    - _Requirements: 9.2_

  - [~] 15.2 Add entry cards to work page
    - Update `src/pages/work/index.vue` to add reconciliation module entry cards/icons with role-based visibility (financial sees all, supplier sees supplier-claim, business sees virtual-inbound + production-anomaly)
    - _Requirements: 9.1, 9.3_

  - [ ]* 15.3 Write property test for role-based visibility (Property 5, 6)
    - **Property 5: State-based action visibility** — verify buttons show/hide based on entity status
    - **Property 6: Pagination logic** — verify hasMore computed correctly for any total/loaded combination
    - **Validates: Requirements 2.9, 5.5, 5.10, 6.7, 1.2, 2.2, 3.3**

- [~] 16. Final Checkpoint - Integration complete
  - Ensure all pages are registered in pages.json, navigation flows work (work page → module entry → sub-pages), role-based visibility is correct, all TypeScript compiles cleanly. Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All code uses TypeScript with Vue 3 Composition API (`<script setup lang="ts">`)
- Existing infrastructure (`request.js`, `auth.js`, `permission.js`) is reused without modification
- TailwindCSS classes are used for all styling (no custom CSS unless necessary)
- All pages target 微信小程序 + H5 compatibility

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "id": 1, "tasks": ["1.5", "1.6", "1.7", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "3.9"] },
    { "id": 3, "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7", "5.8", "5.9", "5.10", "5.11"] },
    { "id": 4, "tasks": ["5.12", "6.1", "6.2", "6.3", "6.4", "7.1", "7.2", "7.3"] },
    { "id": 5, "tasks": ["8.1", "8.2", "8.3", "8.4", "9.1", "9.2", "9.3", "10.1", "10.2"] },
    { "id": 6, "tasks": ["11.1", "11.2", "11.3", "11.4", "12.1", "12.2", "12.3", "13.1", "13.2", "13.3"] },
    { "id": 7, "tasks": ["15.1", "15.2"] },
    { "id": 8, "tasks": ["15.3"] }
  ]
}
```
