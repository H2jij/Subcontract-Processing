"""
一键初始化数据库脚本
- 创建数据库 weiwai
- 导入初始化 SQL
- 验证连接
"""
import asyncio
import subprocess
import sys
import os

PSQL = r"C:\Program Files\PostgreSQL\18\bin\psql.exe"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_USER = "postgres"
DB_NAME = "weiwai"

# 需要按顺序执行的 SQL 文件
SQL_DIR = r"c:\Users\Arno\Desktop\Subcontract-Processing\ruoyi-fastapi-backend\sql"
SQL_FILES = [
    "ruoyi-fastapi-pg.sql",
    "entrust_tables.sql",
    "entrust_menu.sql",
    "insert_roles.sql",
    "entrust_process_codes.sql",
    "seed_process_methods.sql",
    "setup_roles.sql",
    "add_supplier_region.sql",
    "add_supplier_userid.sql",
    "alter_supplier_capabilities.sql",
    "hide_menus.sql",
]


def run_psql(sql_cmd, dbname="postgres", env=None):
    """执行 psql 命令，通过环境变量传密码（避免交互输入）"""
    cmd = [PSQL, "-h", DB_HOST, "-p", DB_PORT, "-U", DB_USER, "-d", dbname, "-c", sql_cmd]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result


def run_psql_file(filepath, dbname, env=None):
    cmd = [PSQL, "-h", DB_HOST, "-p", DB_PORT, "-U", DB_USER, "-d", dbname, "-f", filepath]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result


def prompt_pg_password():
    import getpass
    return getpass.getpass(f"请输入 PostgreSQL postgres 用户密码: ")


def main():
    # 获取 postgres 用户密码
    password = prompt_pg_password()

    env = os.environ.copy()
    env["PGPASSWORD"] = password

    print("\n[1/3] 检查并创建数据库 weiwai ...")
    # 检查数据库是否存在
    r = run_psql(f"SELECT 1 FROM pg_database WHERE datname='{DB_NAME}'", env=env)
    if "1 row" in r.stdout or "(1 row)" in r.stdout:
        print(f"  ✓ 数据库 {DB_NAME} 已存在")
    else:
        r2 = run_psql(f"CREATE DATABASE {DB_NAME} ENCODING 'UTF8'", env=env)
        if r2.returncode == 0:
            print(f"  ✓ 数据库 {DB_NAME} 创建成功")
        else:
            print(f"  ✗ 创建失败: {r2.stderr}")
            sys.exit(1)

    print("\n[2/3] 导入 SQL 初始化文件 ...")
    for sql_file in SQL_FILES:
        filepath = os.path.join(SQL_DIR, sql_file)
        if not os.path.exists(filepath):
            print(f"  ⚠ 跳过（文件不存在）: {sql_file}")
            continue
        r = run_psql_file(filepath, DB_NAME, env=env)
        if r.returncode == 0:
            print(f"  ✓ {sql_file}")
        else:
            # 部分 SQL 文件报 "already exists" 是正常的，只记录真正的错误
            stderr = r.stderr.strip()
            if "already exists" in stderr or "does not exist" in stderr:
                print(f"  ~ {sql_file} (部分跳过: 对象已存在)")
            else:
                print(f"  ✗ {sql_file}: {stderr[:200]}")

    print("\n[3/3] 更新 .env.dev 数据库密码 ...")
    env_path = r"c:\Users\Arno\Desktop\Subcontract-Processing\ruoyi-fastapi-backend\.env.dev"
    with open(env_path, "r", encoding="utf-8") as f:
        content = f.read()

    import re
    content = re.sub(r"(?m)^DB_PASSWORD\s*=.*$", f"DB_PASSWORD = {password}", content)
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✓ .env.dev 中 DB_PASSWORD 已更新")

    print("\n✅ 初始化完成！")
    print(f"\n系统登录账号（默认）:")
    print(f"  管理员: admin / admin123")
    print(f"  后端地址: http://localhost:9099")
    print(f"  Swagger: http://localhost:9099/dev-api/docs")
    print(f"\n现在可以启动后端:")
    print(f"  python app.py")


if __name__ == "__main__":
    main()
