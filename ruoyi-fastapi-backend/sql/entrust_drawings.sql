-- 委外加工系统 - 图纸表
-- 存储拆分后的零件子图信息，支持多版本管理

CREATE TABLE IF NOT EXISTS entrust_drawings (
    id              SERIAL PRIMARY KEY,
    mold_code       VARCHAR(64) NOT NULL,            -- 模具编号 如 M250247-P6
    part_code       VARCHAR(64) NOT NULL,            -- 零件编号 如 DIE-10, B03, PH-02
    -- 子图文件信息
    file_name       VARCHAR(255) NOT NULL,           -- 文件名 如 DIE-10_v2.dwg
    file_path       VARCHAR(512) NOT NULL,           -- 项目内相对路径 如 uploads/part_drawings/M250247-P6/DIE-10_v2.dwg
    file_size_kb    INTEGER,                         -- 文件大小(KB)
    -- 版本管理
    version         INTEGER NOT NULL DEFAULT 1,      -- 版本号，每次拆图+1
    is_latest       BOOLEAN NOT NULL DEFAULT TRUE,   -- 是否最新版
    -- 来源信息
    source_type     VARCHAR(32) DEFAULT 'auto_split', -- auto_split自动拆分 / manual手动上传
    split_at        TIMESTAMP,                       -- 拆分/上传时间
    -- 状态
    status          VARCHAR(32) DEFAULT 'available',  -- available/unavailable
    remark          TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_drawing_mold_part ON entrust_drawings (mold_code, part_code);
CREATE INDEX IF NOT EXISTS idx_drawing_latest ON entrust_drawings (mold_code, part_code, is_latest);
