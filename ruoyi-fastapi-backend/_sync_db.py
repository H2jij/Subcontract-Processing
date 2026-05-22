"""
一次性同步所有 ORM 模型中定义但数据库中缺失的列。
扫描所有 entrust 相关表，对比 ORM 定义和实际数据库结构，自动 ADD COLUMN。
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text, inspect
from config.env import DataBaseConfig
from config.database import Base

# 导入所有 ORM 模型确保它们注册到 Base.metadata
import module_entrust.entity.do.entrust_do  # noqa
import module_entrust.entity.do.reconciliation_do  # noqa


# SQLAlchemy 类型 → PostgreSQL DDL 类型映射
TYPE_MAP = {
    'INTEGER': 'INTEGER',
    'BIGINT': 'BIGINT',
    'SMALLINT': 'SMALLINT',
    'VARCHAR': 'VARCHAR(255)',
    'STRING': 'VARCHAR(255)',
    'TEXT': 'TEXT',
    'BOOLEAN': 'BOOLEAN',
    'FLOAT': 'FLOAT',
    'NUMERIC': 'NUMERIC(14,2)',
    'DECIMAL': 'NUMERIC(14,2)',
    'DATE': 'DATE',
    'DATETIME': 'TIMESTAMP',
    'JSON': 'JSONB',
    'JSONB': 'JSONB',
}


def get_pg_type(col):
    """从 SQLAlchemy Column 对象获取 PostgreSQL DDL 类型"""
    type_name = type(col.type).__name__.upper()
    
    if type_name == 'VARCHAR' or type_name == 'STRING':
        length = getattr(col.type, 'length', None)
        return f'VARCHAR({length})' if length else 'VARCHAR(255)'
    elif type_name == 'NUMERIC':
        precision = getattr(col.type, 'precision', 14)
        scale = getattr(col.type, 'scale', 2)
        return f'NUMERIC({precision},{scale})'
    elif type_name in TYPE_MAP:
        return TYPE_MAP[type_name]
    else:
        return 'TEXT'  # fallback


async def sync_all():
    url = (
        f'postgresql+asyncpg://{DataBaseConfig.db_username}:{DataBaseConfig.db_password}'
        f'@{DataBaseConfig.db_host}:{DataBaseConfig.db_port}/{DataBaseConfig.db_database}'
    )
    engine = create_async_engine(url)
    
    total_added = 0
    
    async with engine.begin() as conn:
        # 获取数据库中所有表的列信息
        for table_name, table in Base.metadata.tables.items():
            # 检查表是否存在
            exists = await conn.scalar(text(
                f"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = '{table_name}')"
            ))
            if not exists:
                print(f"  ⚠ 表 {table_name} 不存在，跳过")
                continue
            
            # 获取数据库中该表的现有列
            result = await conn.execute(text(
                f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}'"
            ))
            existing_cols = {row[0] for row in result.fetchall()}
            
            # 对比 ORM 定义的列
            for col in table.columns:
                if col.name not in existing_cols:
                    pg_type = get_pg_type(col)
                    # 添加默认值
                    default_clause = ''
                    if col.default is not None and hasattr(col.default, 'arg'):
                        arg = col.default.arg
                        if isinstance(arg, (int, float)):
                            default_clause = f' DEFAULT {arg}'
                        elif isinstance(arg, bool):
                            default_clause = f' DEFAULT {"true" if arg else "false"}'
                    elif pg_type.startswith('NUMERIC') or pg_type == 'INTEGER' or pg_type == 'BIGINT':
                        if not col.nullable:
                            default_clause = ' DEFAULT 0'
                    
                    sql = f'ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {col.name} {pg_type}{default_clause}'
                    await conn.execute(text(sql))
                    print(f"  + {table_name}.{col.name} ({pg_type})")
                    total_added += 1
    
    await engine.dispose()
    
    if total_added == 0:
        print("\n✅ 所有表结构已同步，无缺失列")
    else:
        print(f"\n✅ 共添加 {total_added} 个缺失列")


if __name__ == '__main__':
    print("正在同步数据库结构...")
    asyncio.run(sync_all())
