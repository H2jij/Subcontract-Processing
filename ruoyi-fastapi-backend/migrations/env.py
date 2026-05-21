"""Alembic 环境配置.

通过 ``config.env.DataBaseConfig`` 注入数据库 URL；显式导入项目内的 ORM 模块，
将所有表注册到 ``Base.metadata``，以便 ``alembic revision --autogenerate``
能识别新增/修改的表。
"""
from __future__ import annotations

import importlib
import sys
from logging.config import fileConfig
from pathlib import Path

# 确保后端根目录加入 sys.path，便于导入项目模块
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from alembic import context  # noqa: E402
from sqlalchemy import engine_from_config, pool  # noqa: E402

from config.database import Base, SYNC_SQLALCHEMY_DATABASE_URL  # noqa: E402

# Alembic 配置对象
config = context.config

# 读取 alembic.ini 中的日志配置（可选）
if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception:
        # 在某些环境下日志配置缺省字段时不阻塞迁移
        pass

# 注入数据库 URL（如 alembic.ini 未填写则使用项目配置）
if not config.get_main_option('sqlalchemy.url'):
    config.set_main_option('sqlalchemy.url', SYNC_SQLALCHEMY_DATABASE_URL)


# ---------------------------------------------------------------------------
# 显式导入所有 ORM 模块，将其表注册到 Base.metadata。
# 注意：避免使用 ``ImportUtil.find_models``，因为它会扫描整个后端目录并真正
# 导入脚本文件（其中部分会在 import 时执行副作用，如建表、连接 DB）。
# ---------------------------------------------------------------------------
_MODEL_MODULES: tuple[str, ...] = (
    'module_entrust.entity.do.entrust_do',
    'module_entrust.entity.do.reconciliation_do',
)

for _mod in _MODEL_MODULES:
    try:
        importlib.import_module(_mod)
    except ImportError:
        # 某些模型模块在特定分支可能尚未存在，忽略错误避免阻塞迁移
        pass

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """以离线模式运行迁移（仅生成 SQL 脚本）。"""
    url = config.get_main_option('sqlalchemy.url')
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """以在线模式运行迁移（实际连接数据库执行）。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
