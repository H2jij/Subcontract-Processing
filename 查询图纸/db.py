# -*- coding: utf-8 -*-
"""
数据库连接管理
使用 psycopg2 直连 PostgreSQL，无需 ORM
"""
import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

PG_DSN = os.getenv("PG_DSN")

if not PG_DSN:
    raise RuntimeError("❌ 缺少 PG_DSN，请在 .env 中配置")


def get_conn():
    """
    获取一个新的数据库连接。
    调用方用 with get_conn() as conn: 使用，离开 with 块自动关闭。
    """
    return psycopg2.connect(PG_DSN)


def get_dict_cursor(conn):
    """
    获取返回字典格式结果的游标（列名作 key）。
    """
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
