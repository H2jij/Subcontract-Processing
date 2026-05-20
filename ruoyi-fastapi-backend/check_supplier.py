import asyncio, sys
sys.path.insert(0, '.')
from config.env import GetConfig; GetConfig()
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from config.env import DataBaseConfig as c

url = f"postgresql+asyncpg://{c.db_username}:{c.db_password}@{c.db_host}:{c.db_port}/{c.db_database}"

async def run():
    engine = create_async_engine(url, echo=False)
    async with engine.connect() as conn:
        # 1. 表结构
        rows = await conn.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name='entrust_suppliers' ORDER BY ordinal_position"
        ))
        print("=== entrust_suppliers 字段 ===")
        cols = []
        for r in rows:
            cols.append(r[0])
            print(f"  {r[0]:<30} {r[1]}")

        # 2. 现有数据
        rows2 = await conn.execute(text("SELECT * FROM entrust_suppliers ORDER BY id"))
        print("\n=== 现有供应商数据 ===")
        for r in rows2:
            d = dict(zip(cols, r))
            for k, v in d.items():
                if v is not None:
                    print(f"  {k}: {v}")
            print("  ---")

    await engine.dispose()

asyncio.run(run())
