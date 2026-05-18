-- =============================================================================
-- 修改 entrust_supplier_capabilities 表结构
-- 将 process_name 改为 process_code_id（外键关联到 entrust_process_codes）
-- =============================================================================

-- 1. 添加 process_code_id 字段
ALTER TABLE entrust_supplier_capabilities
ADD COLUMN process_code_id INTEGER;

COMMENT ON COLUMN entrust_supplier_capabilities.process_code_id IS '工艺代码ID（关联 entrust_process_codes.id）';

-- 2. 先更新 entrust_process_codes 表，添加缺失的工序
INSERT INTO entrust_process_codes (code, name, parent_id, sort_no) VALUES
('DRILL', 'CNC钻孔', NULL, 32),
('SHEET', '钣金', NULL, 33),
('FORGE', '锻造', NULL, 34),
('WELD', '焊接', NULL, 35),
('MOLD', '模架', NULL, 36),
('GRIND_OUT', '外圆磨', NULL, 37),
('LAP', '研磨', NULL, 38),
('INJECT', '注塑', NULL, 39),
('CAST', '铸造', NULL, 40)
ON CONFLICT (code) DO NOTHING;

-- 3. 迁移现有数据：使用 CASE WHEN 做名称映射
UPDATE entrust_supplier_capabilities cap
SET process_code_id = (
    SELECT id FROM entrust_process_codes pc
    WHERE
        pc.name = cap.process_name  -- 完全匹配
        OR (cap.process_name = '快走丝' AND pc.code = 'WC')  -- 别名匹配
        OR (cap.process_name = '慢走丝' AND pc.code = 'WE')
        OR (cap.process_name = '中走丝' AND pc.code = 'WZ')
        OR (cap.process_name = '电火花' AND pc.code = 'EDM')
        OR (cap.process_name = '车削' AND pc.code = '车床')
        OR (cap.process_name = '铣削' AND pc.code = 'X')
        OR (cap.process_name = '平面磨' AND pc.code = 'JM')
        OR (cap.process_name = '研磨' AND pc.code = 'JM')
    LIMIT 1
);

-- 对于大类（热处理、表面处理、焊接），暂时映射到第一个子项，后续手动调整
UPDATE entrust_supplier_capabilities cap
SET process_code_id = (
    SELECT id FROM entrust_process_codes WHERE code = 'PTR'  -- 普通热处理
)
WHERE process_name = '热处理' AND process_code_id IS NULL;

UPDATE entrust_supplier_capabilities cap
SET process_code_id = (
    SELECT id FROM entrust_process_codes WHERE code = '氮化'  -- 氮化
)
WHERE process_name = '表面处理' AND process_code_id IS NULL;

UPDATE entrust_supplier_capabilities cap
SET process_code_id = (
    SELECT id FROM entrust_process_codes WHERE code = 'WELD'  -- 焊接
)
WHERE process_name = '焊接' AND process_code_id IS NULL;

-- 4. 创建外键约束
ALTER TABLE entrust_supplier_capabilities
ADD CONSTRAINT fk_capability_code
FOREIGN KEY (process_code_id) REFERENCES entrust_process_codes(id);

-- 5. 删除旧的唯一约束（supplier_id + process_name）
ALTER TABLE entrust_supplier_capabilities
DROP CONSTRAINT IF EXISTS uk_entrust_sup_cap;

-- 6. 创建新的唯一约束（supplier_id + process_code_id）
ALTER TABLE entrust_supplier_capabilities
ADD CONSTRAINT uk_entrust_sup_cap_code UNIQUE (supplier_id, process_code_id);

-- 7. 创建索引
CREATE INDEX IF NOT EXISTS idx_ent_cap_code_id ON entrust_supplier_capabilities (process_code_id);

-- 8. 检查迁移结果（显示未匹配的记录）
SELECT cap.id, cap.process_name, s.name as supplier_name
FROM entrust_supplier_capabilities cap
LEFT JOIN entrust_suppliers s ON cap.supplier_id = s.id
WHERE cap.process_code_id IS NULL;
