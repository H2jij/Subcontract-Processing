"""为现有所有供应商补建合同发送任务"""
import asyncio, sys
sys.path.insert(0, '.')
from config.env import GetConfig; GetConfig()
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text
from config.env import DataBaseConfig as c
from module_entrust.entity.do.entrust_do import EntrustSupplier
from module_entrust.service.contract_task_service import ContractTaskService

url = f"postgresql+asyncpg://{c.db_username}:{c.db_password}@{c.db_host}:{c.db_port}/{c.db_database}"

async def run():
    engine = create_async_engine(url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        suppliers = (await db.execute(select(EntrustSupplier))).scalars().all()
        print(f"共 {len(suppliers)} 个供应商")
        for s in suppliers:
            task = await ContractTaskService.ensure_task(db, s.id, 1)
            print(f"  ✓ {s.name} ({s.supplier_type}) → task_id={task.id} status={task.status}")
        await db.commit()
    await engine.dispose()
    print("\n完成")

asyncio.run(run())
