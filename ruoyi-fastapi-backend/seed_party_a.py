"""
初始化甲方信息到 sys_config
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config.env import GetConfig
GetConfig()

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from config.env import DataBaseConfig as c


def url():
    return f"postgresql+asyncpg://{c.db_username}:{c.db_password}@{c.db_host}:{c.db_port}/{c.db_database}"


# ── 甲方已知信息（直接写死的填进来，空字段留 '' 待界面维护）─────────────
PARTY_A_CONFIGS = [
    # (config_key,                      config_value,              显示名称)
    ("contract:party_a:name",           "青岛瑞利杰金属有限公司",  "甲方公司名称"),
    ("contract:party_a:address",        "青岛市城阳区春城路606号", "甲方地址"),
    ("contract:party_a:legal_rep",      "",                        "甲方法定代表人/授权负责人"),
    ("contract:party_a:contact",        "",                        "甲方联系方式"),
    ("contract:party_a:credit_code",    "",                        "甲方统一社会信用代码"),
    ("contract:party_a:pkg_guide_no",   "",                        "包装指导书编号"),
]


async def main():
    engine = create_async_engine(url(), echo=False)
    async with engine.begin() as conn:
        for key, value, name in PARTY_A_CONFIGS:
            # 先查是否存在
            result = await conn.execute(
                text("SELECT config_id, config_value FROM sys_config WHERE config_key = :key"),
                {"key": key}
            )
            row = result.fetchone()
            if row:
                # 已存在且有值 → 不覆盖；为空 → 用新值填入
                existing_value = row[1] or ""
                if existing_value == "" and value:
                    await conn.execute(
                        text("UPDATE sys_config SET config_value=:v, config_name=:n WHERE config_key=:k"),
                        {"v": value, "n": name, "k": key}
                    )
                    print(f"  UPDATE: {key:<40} = '{value}'")
                else:
                    print(f"  SKIP:   {key:<40} (现有值: '{existing_value}')")
            else:
                # 不存在 → 插入
                await conn.execute(
                    text("""
                        INSERT INTO sys_config
                            (config_name, config_key, config_value, config_type, create_by, create_time, remark)
                        VALUES (:name, :key, :value, 'N', 'admin', NOW(), :name)
                    """),
                    {"name": name, "key": key, "value": value}
                )
                print(f"  INSERT: {key:<40} = '{value}'")
    await engine.dispose()
    print("\n甲方信息已写入 sys_config")
    print("留空字段请在系统 [参数设置] 中搜索 'contract:party_a:' 补填。")


if __name__ == "__main__":
    asyncio.run(main())
