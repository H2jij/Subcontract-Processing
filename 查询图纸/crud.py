# -*- coding: utf-8 -*-
"""
图纸查询的所有数据库操作。

涉及两张表：
  supplier_shortlist_chaidan_wujin  —— 存储拆图结果（dwg 字段为 JSON）
  wujin_items_v4                    —— 存储物料明细，通过 group_uid 关联上表

dwg 字段格式示例：
  {"dwg": "static/dwg/chaidan/M250247-P6_DIE-10_20250516.dwg"}
  {"message": "找不到拆图文件", "error": "未找到源文件: M250247-P6"}
"""
import json
import os
import logging
from typing import Optional, List, Dict, Any

from db import get_conn, get_dict_cursor

logger = logging.getLogger(__name__)

STATIC_BASE_URL = os.getenv("STATIC_BASE_URL", "http://localhost:8000")


# ==================== 内部工具函数 ====================

def _parse_dwg_field(raw: Any) -> tuple[Optional[str], Optional[str]]:
    """
    解析 dwg 字段，返回 (相对路径, 原始值字符串)。

    dwg 字段可能是：
    - JSON 字符串：'{"dwg": "static/dwg/..."}'
    - dict（已反序列化）
    - None / 空字符串

    返回 (dwg_path, raw_str)
    """
    if not raw:
        return None, None

    raw_str = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)

    try:
        data = json.loads(raw_str) if isinstance(raw, str) else raw
        path = data.get("dwg", "")
        if path:
            # 统一为正斜杠
            path = path.replace("\\", "/")
            return path, raw_str
    except (json.JSONDecodeError, AttributeError):
        logger.warning(f"解析 dwg 字段失败: {raw_str}")

    return None, raw_str


def _build_url(path: Optional[str]) -> Optional[str]:
    """将相对路径拼接为完整 URL"""
    if not path:
        return None
    base = STATIC_BASE_URL.rstrip("/")
    path = path.lstrip("/")
    return f"{base}/{path}"


def _row_to_dict(row: Dict) -> Dict:
    """将数据库行转换为标准字典，处理时间格式"""
    d = dict(row)
    # 将 datetime 转为 ISO 字符串
    for key in ("created_at", "updated_at", "eta_date"):
        val = d.get(key)
        if val is not None and hasattr(val, "isoformat"):
            d[key] = val.isoformat()
    return d


# ==================== 查询函数 ====================

def query_by_group_uid(group_uid: str) -> Optional[Dict]:
    """
    根据子订单 ID（group_uid）查询对应图纸。

    Args:
        group_uid: UUID 格式的子订单ID

    Returns:
        包含图纸信息的字典，或 None
    """
    sql = """
        SELECT
            s.group_uid::text   AS group_uid,
            s.group_name,
            s.no,
            s.supplier_code,
            s.status,
            s.dwg,
            s.created_at,
            s.updated_at,
            s.eta_date,
            -- 从 wujin_items_v4 关联取 req_code
            wi.req_code
        FROM supplier_shortlist_chaidan_wujin s
        LEFT JOIN wujin_items_v4 wi
            ON wi.group_uid::text = s.group_uid::text
           AND wi.no = s.no
        WHERE s.group_uid::text = %(group_uid)s
        LIMIT 1
    """
    with get_conn() as conn:
        with get_dict_cursor(conn) as cur:
            cur.execute(sql, {"group_uid": str(group_uid)})
            row = cur.fetchone()

    if not row:
        return None

    d = _row_to_dict(row)
    dwg_path, dwg_raw = _parse_dwg_field(d.pop("dwg", None))
    d["dwg_path"] = dwg_path
    d["dwg_url"] = _build_url(dwg_path)
    d["dwg_raw"] = dwg_raw
    return d


def query_by_no(no: str) -> List[Dict]:
    """
    根据请购单编号（no）查询该订单下所有图纸。

    一个请购单下可能有多个分组（多个供应商各一份图纸）。

    Args:
        no: 请购单编号，如 WJJQG202512080005

    Returns:
        图纸记录列表
    """
    sql = """
        SELECT
            s.group_uid::text   AS group_uid,
            s.group_name,
            s.no,
            s.supplier_code,
            s.status,
            s.dwg,
            s.created_at,
            s.updated_at,
            s.eta_date,
            wi.req_code
        FROM supplier_shortlist_chaidan_wujin s
        LEFT JOIN (
            SELECT DISTINCT ON (group_uid) group_uid, req_code, no
            FROM wujin_items_v4
            WHERE no = %(no)s
            ORDER BY group_uid, created_at DESC
        ) wi ON wi.group_uid::text = s.group_uid::text AND wi.no = s.no
        WHERE s.no = %(no)s
        ORDER BY s.created_at DESC
    """
    with get_conn() as conn:
        with get_dict_cursor(conn) as cur:
            cur.execute(sql, {"no": no})
            rows = cur.fetchall()

    result = []
    for row in rows:
        d = _row_to_dict(row)
        dwg_path, dwg_raw = _parse_dwg_field(d.pop("dwg", None))
        d["dwg_path"] = dwg_path
        d["dwg_url"] = _build_url(dwg_path)
        d["dwg_raw"] = dwg_raw
        result.append(d)

    return result


def query_by_order_code(order_code: str) -> List[Dict]:
    """
    根据模具订单编号（order_code，如 M250247-P6）查询图纸。

    通过 wujin_items_v4.req_code 字段关联（req_code = order_code + '-WUJIN'）。

    Args:
        order_code: 模具编号，如 M250247-P6 或 M250247.P6

    Returns:
        图纸记录列表
    """
    # 兼容两种格式：M250247.P6 和 M250247-P6
    normalized = order_code.replace(".", "-")
    req_code_pattern = f"{normalized}-%"

    sql = """
        SELECT
            s.group_uid::text   AS group_uid,
            s.group_name,
            s.no,
            s.supplier_code,
            s.status,
            s.dwg,
            s.created_at,
            s.updated_at,
            s.eta_date,
            wi.req_code
        FROM supplier_shortlist_chaidan_wujin s
        JOIN (
            SELECT DISTINCT ON (group_uid) group_uid, req_code, no
            FROM wujin_items_v4
            WHERE req_code LIKE %(pattern)s
            ORDER BY group_uid, created_at DESC
        ) wi ON wi.group_uid::text = s.group_uid::text AND wi.no = s.no
        ORDER BY s.created_at DESC
    """
    with get_conn() as conn:
        with get_dict_cursor(conn) as cur:
            cur.execute(sql, {"pattern": req_code_pattern})
            rows = cur.fetchall()

    result = []
    for row in rows:
        d = _row_to_dict(row)
        dwg_path, dwg_raw = _parse_dwg_field(d.pop("dwg", None))
        d["dwg_path"] = dwg_path
        d["dwg_url"] = _build_url(dwg_path)
        d["dwg_raw"] = dwg_raw
        result.append(d)

    return result


def query_list(
    page: int = 1,
    page_size: int = 20,
    only_with_dwg: bool = False,
    status: Optional[str] = None,
) -> tuple[List[Dict], int]:
    """
    分页查询全部图纸记录。

    Args:
        page:          页码，从 1 开始
        page_size:     每页条数，最大 100
        only_with_dwg: True 时只返回已有图纸文件的记录
        status:        按状态筛选，如 "待接单" / "跟单" / "加工完成"

    Returns:
        (记录列表, 总数)
    """
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size

    conditions = []
    params: Dict[str, Any] = {"limit": page_size, "offset": offset}

    if only_with_dwg:
        # dwg 字段不为空且包含 "dwg" key
        conditions.append("s.dwg IS NOT NULL AND s.dwg::text LIKE '%\"dwg\"%'")

    if status:
        conditions.append("s.status = %(status)s")
        params["status"] = status

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    count_sql = f"""
        SELECT COUNT(*) AS total
        FROM supplier_shortlist_chaidan_wujin s
        {where_clause}
    """
    data_sql = f"""
        SELECT
            s.group_uid::text   AS group_uid,
            s.group_name,
            s.no,
            s.supplier_code,
            s.status,
            s.dwg,
            s.created_at,
            s.updated_at,
            s.eta_date
        FROM supplier_shortlist_chaidan_wujin s
        {where_clause}
        ORDER BY s.created_at DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """

    with get_conn() as conn:
        with get_dict_cursor(conn) as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()["total"]

            cur.execute(data_sql, params)
            rows = cur.fetchall()

    result = []
    for row in rows:
        d = _row_to_dict(row)
        dwg_path, dwg_raw = _parse_dwg_field(d.pop("dwg", None))
        d["dwg_path"] = dwg_path
        d["dwg_url"] = _build_url(dwg_path)
        d["dwg_raw"] = dwg_raw
        result.append(d)

    return result, total


def query_search(
    no: Optional[str] = None,
    order_code: Optional[str] = None,
    supplier_code: Optional[str] = None,
    status: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    only_with_dwg: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> tuple[List[Dict], int]:
    """
    多条件组合搜索图纸。

    Args:
        no:             请购单编号（模糊匹配）
        order_code:     模具编号（模糊匹配，如 M250247）
        supplier_code:  供应商编码（精确匹配）
        status:         状态（精确匹配）
        created_after:  创建时间起始，格式 YYYY-MM-DD
        created_before: 创建时间截止，格式 YYYY-MM-DD
        only_with_dwg:  只返回有图纸文件的记录
        page:           页码
        page_size:      每页条数

    Returns:
        (记录列表, 总数)
    """
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size

    conditions = []
    params: Dict[str, Any] = {"limit": page_size, "offset": offset}

    if no:
        conditions.append("s.no LIKE %(no)s")
        params["no"] = f"%{no}%"

    if supplier_code:
        conditions.append("s.supplier_code = %(supplier_code)s")
        params["supplier_code"] = supplier_code

    if status:
        conditions.append("s.status = %(status)s")
        params["status"] = status

    if created_after:
        conditions.append("s.created_at >= %(created_after)s")
        params["created_after"] = created_after

    if created_before:
        conditions.append("s.created_at <= %(created_before)s::date + interval '1 day'")
        params["created_before"] = created_before

    if only_with_dwg:
        conditions.append("s.dwg IS NOT NULL AND s.dwg::text LIKE '%\"dwg\"%'")

    # order_code 需要联查 wujin_items_v4
    join_clause = ""
    if order_code:
        normalized = order_code.replace(".", "-")
        join_clause = """
            JOIN (
                SELECT DISTINCT ON (group_uid) group_uid, req_code, no
                FROM wujin_items_v4
                WHERE req_code LIKE %(req_pattern)s
                ORDER BY group_uid, created_at DESC
            ) wi ON wi.group_uid::text = s.group_uid::text AND wi.no = s.no
        """
        params["req_pattern"] = f"{normalized}-%"

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    count_sql = f"""
        SELECT COUNT(*) AS total
        FROM supplier_shortlist_chaidan_wujin s
        {join_clause}
        {where_clause}
    """
    data_sql = f"""
        SELECT
            s.group_uid::text   AS group_uid,
            s.group_name,
            s.no,
            s.supplier_code,
            s.status,
            s.dwg,
            s.created_at,
            s.updated_at,
            s.eta_date
            {',' + 'wi.req_code' if order_code else ''}
        FROM supplier_shortlist_chaidan_wujin s
        {join_clause}
        {where_clause}
        ORDER BY s.created_at DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """

    with get_conn() as conn:
        with get_dict_cursor(conn) as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()["total"]

            cur.execute(data_sql, params)
            rows = cur.fetchall()

    result = []
    for row in rows:
        d = _row_to_dict(row)
        dwg_path, dwg_raw = _parse_dwg_field(d.pop("dwg", None))
        d["dwg_path"] = dwg_path
        d["dwg_url"] = _build_url(dwg_path)
        d["dwg_raw"] = dwg_raw
        result.append(d)

    return result, total
