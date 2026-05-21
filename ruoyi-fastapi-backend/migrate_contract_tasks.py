"""建合同任务表 + 注册菜单"""
import asyncio, sys
sys.path.insert(0, '.')
from config.env import GetConfig; GetConfig()
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from config.env import DataBaseConfig as c

url = f"postgresql+asyncpg://{c.db_username}:{c.db_password}@{c.db_host}:{c.db_port}/{c.db_database}"

SQLS = [
    # 合同任务表
    """CREATE TABLE IF NOT EXISTS entrust_contract_tasks (
        id SERIAL PRIMARY KEY,
        supplier_id INTEGER NOT NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'pending',
        last_sent_at TIMESTAMP,
        send_count INTEGER NOT NULL DEFAULT 0,
        deferred_until TIMESTAMP,
        note TEXT,
        created_by BIGINT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    "COMMENT ON TABLE entrust_contract_tasks IS '框架合同发送任务'",
    "CREATE INDEX IF NOT EXISTS idx_contract_tasks_supplier ON entrust_contract_tasks(supplier_id)",
    "CREATE INDEX IF NOT EXISTS idx_contract_tasks_status ON entrust_contract_tasks(status)",

    # 菜单：合同分发管理
    """INSERT INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, remark)
       VALUES (9480, '合同分发', 9400, 5, 'contract', 'entrust/contract/index', '', 1, 0, 'C', '0', '0', 'entrust:contract:list', 'email', 'admin', NOW(), '框架合同发送管理')
       ON CONFLICT DO NOTHING""",

    # 角色菜单分配（admin + our_admin + manager + buyer）
    "INSERT INTO sys_role_menu (role_id, menu_id) VALUES (1, 9480) ON CONFLICT DO NOTHING",
    "INSERT INTO sys_role_menu (role_id, menu_id) VALUES (100, 9480) ON CONFLICT DO NOTHING",
    "INSERT INTO sys_role_menu (role_id, menu_id) VALUES (101, 9480) ON CONFLICT DO NOTHING",
    "INSERT INTO sys_role_menu (role_id, menu_id) VALUES (102, 9480) ON CONFLICT DO NOTHING",
]

async def run():
    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        for sql in SQLS:
            await conn.execute(text(sql))
            print(f"OK: {sql[:60].strip()}")
    await engine.dispose()
    print("\n迁移完成")

asyncio.run(run())
