"""测试 supplier update 接口是否正确保存 legal_rep"""
import asyncio, sys
sys.path.insert(0, '.')
from config.env import GetConfig; GetConfig()
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from config.env import DataBaseConfig as c
from module_entrust.entity.do.entrust_do import EntrustSupplier
from module_entrust.entity.vo.entrust_vo import SupplierUpdate
from module_entrust.service.supplier_service import SupplierService

url = f"postgresql+asyncpg://{c.db_username}:{c.db_password}@{c.db_host}:{c.db_port}/{c.db_database}"

async def run():
    engine = create_async_engine(url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        # 直接更新 id=1 的供应商
        data = SupplierUpdate(
            legal_rep="测试法定代表人_已更新",
            credit_code="91310000UPDATE00001",
            contact_email="updated@test.com",
        )
        result = await SupplierService.update_supplier(session, 1, data)
        if result:
            print(f"更新成功: legal_rep={result.legal_rep}, credit_code={result.credit_code}, contact_email={result.contact_email}")
        else:
            print("更新失败: 找不到供应商")
    await engine.dispose()

asyncio.run(run())
