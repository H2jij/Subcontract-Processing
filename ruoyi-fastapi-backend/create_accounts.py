"""
创建加工方账号和材料方账号
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.env import GetConfig
GetConfig()

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text
from config.env import DataBaseConfig
from utils.pwd_util import PwdUtil


def build_db_url():
    c = DataBaseConfig
    return f"postgresql+asyncpg://{c.db_username}:{c.db_password}@{c.db_host}:{c.db_port}/{c.db_database}"


# ── 要创建的账号配置 ──────────────────────────────────────────────────────────
ACCOUNTS = [
    {
        "user_name":  "processor01",
        "nick_name":  "加工方01",
        "password":   "admin123",
        "role_key":   "processor",   # role_id=103
        "desc":       "加工方账号",
    },
    {
        "user_name":  "processor02",
        "nick_name":  "加工方02",
        "password":   "admin123",
        "role_key":   "processor",
        "desc":       "加工方账号",
    },
    {
        "user_name":  "material01",
        "nick_name":  "材料方01",
        "password":   "admin123",
        "role_key":   "material",    # 需要先创建角色
        "desc":       "材料方账号",
    },
    {
        "user_name":  "material02",
        "nick_name":  "材料方02",
        "password":   "admin123",
        "role_key":   "material",
        "desc":       "材料方账号",
    },
]
# ─────────────────────────────────────────────────────────────────────────────


async def ensure_material_role(session: AsyncSession) -> int:
    """确保材料方角色存在，返回 role_id。"""
    from module_admin.entity.do.role_do import SysRole
    stmt = select(SysRole).where(SysRole.role_key == "material")
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        print(f"  ✓ 材料方角色已存在 role_id={existing.role_id}")
        return existing.role_id

    role = SysRole(
        role_id=104,
        role_name="材料方",
        role_key="material",
        role_sort=5,
        data_scope="5",
        menu_check_strictly=True,
        dept_check_strictly=True,
        status="0",
        del_flag="0",
        create_by="admin",
        remark="材料供应方，查看与自己相关的询价和工单",
    )
    session.add(role)
    await session.flush()

    # 分配和加工方相同的菜单权限（加工方工作台）
    await session.execute(text(
        "INSERT INTO sys_role_menu (role_id, menu_id) "
        "SELECT 104, menu_id FROM sys_role_menu WHERE role_id=103 "
        "ON CONFLICT DO NOTHING"
    ))
    print(f"  ✓ 创建材料方角色 role_id=104")
    return 104


async def get_role_id(session: AsyncSession, role_key: str) -> int:
    from module_admin.entity.do.role_do import SysRole
    stmt = select(SysRole).where(SysRole.role_key == role_key)
    role = (await session.execute(stmt)).scalar_one_or_none()
    if not role:
        raise ValueError(f"角色 {role_key} 不存在")
    return role.role_id


async def create_account(session: AsyncSession, cfg: dict, role_id: int):
    from module_admin.entity.do.user_do import SysUser, SysUserRole

    # 检查用户名是否已存在
    stmt = select(SysUser).where(SysUser.user_name == cfg["user_name"], SysUser.del_flag == "0")
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        print(f"  ~ {cfg['user_name']} 已存在，跳过")
        return

    user = SysUser(
        user_name=cfg["user_name"],
        nick_name=cfg["nick_name"],
        password=PwdUtil.get_password_hash(cfg["password"]),
        status="0",
        del_flag="0",
        create_by="admin",
    )
    session.add(user)
    await session.flush()

    user_role = SysUserRole(user_id=user.user_id, role_id=role_id)
    session.add(user_role)
    await session.flush()

    print(f"  ✓ 创建 {cfg['desc']}: {cfg['user_name']} / {cfg['password']}  (user_id={user.user_id})")


async def main():
    engine = create_async_engine(build_db_url(), echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("\n=== 创建系统账号 ===\n")

    async with AsyncSessionLocal() as session:
        # 确保材料方角色存在
        print("[1/2] 检查/创建角色...")
        await ensure_material_role(session)
        await session.commit()

        print("\n[2/2] 创建用户账号...")
        for cfg in ACCOUNTS:
            role_id = await get_role_id(session, cfg["role_key"])
            await create_account(session, cfg, role_id)
        await session.commit()

    await engine.dispose()

    print("\n=== 完成 ===")
    print("\n账号汇总：")
    print(f"{'用户名':<16} {'昵称':<12} {'密码':<12} {'角色'}")
    print("-" * 56)
    for a in ACCOUNTS:
        print(f"{a['user_name']:<16} {a['nick_name']:<12} {a['password']:<12} {a['desc']}")


if __name__ == "__main__":
    asyncio.run(main())
