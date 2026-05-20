-- 加工方/材料方数据库扩展
ALTER TABLE entrust_suppliers
  ADD COLUMN IF NOT EXISTS supplier_type VARCHAR(32) DEFAULT 'processor',
  ADD COLUMN IF NOT EXISTS legal_rep VARCHAR(64),
  ADD COLUMN IF NOT EXISTS bank_name VARCHAR(128),
  ADD COLUMN IF NOT EXISTS bank_account VARCHAR(64),
  ADD COLUMN IF NOT EXISTS bank_account_name VARCHAR(128),
  ADD COLUMN IF NOT EXISTS contract_amount NUMERIC(14,2),
  ADD COLUMN IF NOT EXISTS contract_start DATE,
  ADD COLUMN IF NOT EXISTS contract_end DATE,
  ADD COLUMN IF NOT EXISTS signed_at DATE;

COMMENT ON COLUMN entrust_suppliers.supplier_type IS '供应商类型：processor-加工方 material-材料方 other-其他';
COMMENT ON COLUMN entrust_suppliers.legal_rep IS '法定代表人（合同乙方法定代表人）';
COMMENT ON COLUMN entrust_suppliers.bank_name IS '开户银行';
COMMENT ON COLUMN entrust_suppliers.bank_account IS '银行账号';
COMMENT ON COLUMN entrust_suppliers.bank_account_name IS '银行开户名';
COMMENT ON COLUMN entrust_suppliers.contract_amount IS '框架合同额度';
COMMENT ON COLUMN entrust_suppliers.contract_start IS '合同起始日期';
COMMENT ON COLUMN entrust_suppliers.contract_end IS '合同终止日期';
COMMENT ON COLUMN entrust_suppliers.signed_at IS '合同签订日期';

-- 现有数据默认为加工方
UPDATE entrust_suppliers SET supplier_type='processor' WHERE supplier_type IS NULL;

-- 加约束
ALTER TABLE entrust_suppliers
  DROP CONSTRAINT IF EXISTS chk_supplier_type;
ALTER TABLE entrust_suppliers
  ADD CONSTRAINT chk_supplier_type CHECK (supplier_type IN ('processor','material','other'));

-- 视图
CREATE OR REPLACE VIEW v_processors AS
  SELECT * FROM entrust_suppliers WHERE supplier_type='processor' AND status='active';

CREATE OR REPLACE VIEW v_material_suppliers AS
  SELECT * FROM entrust_suppliers WHERE supplier_type='material' AND status='active';
