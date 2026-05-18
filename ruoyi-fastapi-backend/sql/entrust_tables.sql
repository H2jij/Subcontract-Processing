-- =============================================================================
-- 委外加工模块 — 业务建表脚本（weiwai 库 / PostgreSQL）
-- 在执行完 ruoyi-fastapi-pg.sql（若依系统表）之后再执行本文件
-- =============================================================================

-- 1. 加工方/供应商表
CREATE TABLE IF NOT EXISTS entrust_suppliers (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(255) NOT NULL UNIQUE,
    category      VARCHAR(128),
    address       VARCHAR(512),
    contact_name  VARCHAR(64),
    contact_phone VARCHAR(32),
    rating        DECIMAL(4,2),
    status        VARCHAR(32) DEFAULT 'active',
    remark        TEXT,
    created_by    BIGINT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. 委外项目表
CREATE TABLE IF NOT EXISTS entrust_projects (
    id            SERIAL PRIMARY KEY,
    project_no    VARCHAR(64) NOT NULL UNIQUE,
    name          VARCHAR(255) NOT NULL,
    customer      VARCHAR(255) NOT NULL,
    deadline      DATE,
    unit_price    DECIMAL(14,2),
    quantity      INTEGER,
    description   TEXT,
    status        VARCHAR(32) NOT NULL DEFAULT 'drafted',
    created_by    BIGINT,
    confirmed_at  TIMESTAMP,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. 模具套表
CREATE TABLE IF NOT EXISTS entrust_molds (
    id            SERIAL PRIMARY KEY,
    project_id    INTEGER NOT NULL,
    name          VARCHAR(255),
    sort_no       INTEGER DEFAULT 0,
    remark        TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. 零件表
CREATE TABLE IF NOT EXISTS entrust_parts (
    id                  SERIAL PRIMARY KEY,
    project_id          INTEGER NOT NULL,
    mold_id             INTEGER,
    part_no             VARCHAR(64),
    part_name           VARCHAR(255),
    material            VARCHAR(64),
    material_id         INTEGER,
    qty                 INTEGER NOT NULL DEFAULT 1,
    spec                VARCHAR(255),
    part_type           VARCHAR(32),
    processes_json      JSONB,
    process_method_ids  JSONB,
    status              VARCHAR(32) DEFAULT 'pending',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. 工艺方法基础表
CREATE TABLE IF NOT EXISTS entrust_process_methods (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(64) NOT NULL UNIQUE,
    category      VARCHAR(64),
    remark        TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. 材料基础表
CREATE TABLE IF NOT EXISTS entrust_materials (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(128) NOT NULL,
    spec          VARCHAR(128),
    category      VARCHAR(64),
    unit          VARCHAR(32),
    remark        TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. 加工方能力表
CREATE TABLE IF NOT EXISTS entrust_supplier_capabilities (
    id            SERIAL PRIMARY KEY,
    supplier_id   INTEGER NOT NULL,
    process_name  VARCHAR(64) NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_entrust_sup_cap UNIQUE (supplier_id, process_name)
);

-- 8. 委外询价单
CREATE TABLE IF NOT EXISTS entrust_outsource_requests (
    id                SERIAL PRIMARY KEY,
    project_id        INTEGER NOT NULL,
    title             VARCHAR(255) NOT NULL,
    scope_json        JSONB,
    deadline          DATE,
    status            VARCHAR(32) NOT NULL DEFAULT 'draft',
    closed_at         TIMESTAMP,
    winning_quote_id  INTEGER,
    created_by        BIGINT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 9. 询价邀请
CREATE TABLE IF NOT EXISTS entrust_invitations (
    id                SERIAL PRIMARY KEY,
    request_id        INTEGER NOT NULL,
    supplier_id       INTEGER NOT NULL,
    status            VARCHAR(32) NOT NULL DEFAULT 'sent',
    sent_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    quoted_at         TIMESTAMP,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_entrust_inv_req_sup UNIQUE (request_id, supplier_id)
);

-- 10. 报价单
CREATE TABLE IF NOT EXISTS entrust_quotations (
    id                SERIAL PRIMARY KEY,
    invitation_id     INTEGER NOT NULL UNIQUE,
    unit_price        DECIMAL(14,2),
    lead_time_days    INTEGER,
    note              TEXT,
    lines_json        JSONB,
    submitted_by      BIGINT,
    submitted_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 11. 委外工单
CREATE TABLE IF NOT EXISTS entrust_outsource_orders (
    id                  SERIAL PRIMARY KEY,
    request_id          INTEGER,
    quotation_id        INTEGER,
    supplier_id         INTEGER NOT NULL,
    project_id          INTEGER,
    part_id             INTEGER,
    order_no            VARCHAR(64) NOT NULL UNIQUE,
    process_name        VARCHAR(200),
    unit_price          DECIMAL(14,2),
    quantity            INTEGER NOT NULL DEFAULT 1,
    total_amount        DECIMAL(14,2),
    lead_time_days      INTEGER,
    plan_delivery_date  TIMESTAMP,
    actual_delivery_date TIMESTAMP,
    status              VARCHAR(32) NOT NULL DEFAULT 'awarded',
    quality_status      VARCHAR(32),
    remark              TEXT,
    created_by          BIGINT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 12. 附件/图纸表
CREATE TABLE IF NOT EXISTS entrust_attachments (
    id            SERIAL PRIMARY KEY,
    related_type  VARCHAR(32) NOT NULL,
    related_id    INTEGER NOT NULL,
    file_name     VARCHAR(255) NOT NULL,
    file_path     VARCHAR(512) NOT NULL,
    file_size     INTEGER,
    mime_type     VARCHAR(128),
    category      VARCHAR(64),
    uploaded_by   BIGINT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_ent_parts_project ON entrust_parts (project_id);
CREATE INDEX IF NOT EXISTS idx_ent_molds_project ON entrust_molds (project_id);
CREATE INDEX IF NOT EXISTS idx_ent_req_project    ON entrust_outsource_requests (project_id);
CREATE INDEX IF NOT EXISTS idx_ent_req_status     ON entrust_outsource_requests (status);
CREATE INDEX IF NOT EXISTS idx_ent_inv_request    ON entrust_invitations (request_id);
CREATE INDEX IF NOT EXISTS idx_ent_order_supplier ON entrust_outsource_orders (supplier_id, status);
CREATE INDEX IF NOT EXISTS idx_ent_att_related    ON entrust_attachments (related_type, related_id);
