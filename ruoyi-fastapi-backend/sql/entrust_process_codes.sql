-- =============================================================================
-- 工艺代码对照表（带父子层级字段）
-- 创建时间: 2026-05-16
-- 说明: 用于存储工序代码与工序名称的对照关系，支持父子层级分类
-- =============================================================================

-- 创建表
CREATE TABLE IF NOT EXISTS entrust_process_codes (
    id            SERIAL PRIMARY KEY,
    code          VARCHAR(32) NOT NULL UNIQUE,
    name          VARCHAR(64) NOT NULL,
    parent_id     INTEGER,
    sort_no       INTEGER DEFAULT 0,
    is_active     SMALLINT DEFAULT 1,
    remark        TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_parent_code FOREIGN KEY (parent_id) REFERENCES entrust_process_codes(id)
);

COMMENT ON TABLE entrust_process_codes IS '工艺代码对照表（父子层级）';
COMMENT ON COLUMN entrust_process_codes.id IS '主键';
COMMENT ON COLUMN entrust_process_codes.code IS '工序代码：Z-钻床 X-铣床 WC-快丝等';
COMMENT ON COLUMN entrust_process_codes.name IS '工序名称：钻床、铣床、快丝等';
COMMENT ON COLUMN entrust_process_codes.parent_id IS '父级ID（NULL表示顶级分类，后续维护）';
COMMENT ON COLUMN entrust_process_codes.sort_no IS '排序号';
COMMENT ON COLUMN entrust_process_codes.is_active IS '是否启用：0-禁用 1-启用';
COMMENT ON COLUMN entrust_process_codes.remark IS '备注';

-- 索引
CREATE INDEX IF NOT EXISTS idx_ent_proc_code_parent ON entrust_process_codes (parent_id);
CREATE INDEX IF NOT EXISTS idx_ent_proc_code_active ON entrust_process_codes (is_active);
CREATE INDEX IF NOT EXISTS idx_ent_proc_code_code ON entrust_process_codes (code);


-- =============================================================================
-- 工艺代码初始化数据（全部平级，parent_id暂为NULL，后续维护层级）
-- =============================================================================

INSERT INTO entrust_process_codes (code, name, parent_id, sort_no) VALUES
-- 机加工类
('Z', '钻床', NULL, 1),
('X', '铣床', NULL, 2),
('S', 'CNC开粗', NULL, 3),
('SS', 'CNC精铣', NULL, 4),
('SS拼铣', 'CNC精铣-拼料', NULL, 5),
('CM', '粗磨', NULL, 6),
('JM', '精磨', NULL, 7),
('M', '大水磨', NULL, 8),
('PM', '拼磨', NULL, 9),
('YM', '小磨床', NULL, 10),
('MZ', '磨直角', NULL, 11),
-- 热处理类
('PTR', '普通热处理', NULL, 12),
('ZKR', '真空热处理', NULL, 13),
('深冷', '深冷热处理', NULL, 14),
('超深冷', '超深冷热处理', NULL, 15),
-- 线切割类
('WZ', '中丝', NULL, 16),
('WC', '快丝', NULL, 17),
('WE', '慢丝', NULL, 18),
-- 其他工序
('车床', '车床', NULL, 19),
('DK', '雕刻', NULL, 20),
('EDM', '放电加工', NULL, 21),
('QC', '质检', NULL, 22),
('补焊', '补焊', NULL, 23),
('点焊', '点焊', NULL, 24),
('抛光', '抛光', NULL, 25),
('氮化', '氮化', NULL, 26),
('超级氮化', '超级氮化', NULL, 27),
('PVD', 'PVD', NULL, 28),
('镀硬铬', '镀硬铬', NULL, 29),
('DLC', 'DLC', NULL, 30),
('氮化铬铝', '氮化铬铝', NULL, 31)
ON CONFLICT (code) DO NOTHING;
