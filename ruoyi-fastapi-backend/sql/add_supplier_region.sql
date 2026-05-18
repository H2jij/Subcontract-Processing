-- 给加工方表添加省/市字段
ALTER TABLE entrust_suppliers ADD COLUMN IF NOT EXISTS province VARCHAR(64);
ALTER TABLE entrust_suppliers ADD COLUMN IF NOT EXISTS city VARCHAR(64);
COMMENT ON COLUMN entrust_suppliers.province IS '省';
COMMENT ON COLUMN entrust_suppliers.city IS '市';
