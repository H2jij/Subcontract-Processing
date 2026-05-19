# -*- coding: utf-8 -*-
"""
查询图纸 - 独立服务启动入口
只需要 PostgreSQL 数据库即可运行，无其他依赖。
"""
import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ==================== 创建 FastAPI 应用 ====================

app = FastAPI(
    title="查询图纸 & 拆图 API",
    description="""
## 图纸查询 + 拆图服务

从采购系统独立拆离的图纸模块，包含两大功能：

### 📐 查询图纸
查询已生成的拆图文件，支持按订单号、模具编号、子订单ID等多种方式检索。

### ✂️ 拆图
从完整的大模具图纸中，按零件编号拆出指定部分，生成独立的 DWG 文件。

**拆图依赖：**
- `ODAFileConverter.exe`（DWG ↔ DXF 格式转换，需本地安装）
- `ezdxf`（Python 解析 DXF）
- 网络共享盘图纸源文件（`CAD_SEARCH_ROOT`）

---

### 涉及数据库表

| 表名 | 说明 |
|------|------|
| `supplier_shortlist_chaidan_wujin` | 存储拆图结果文件路径 |
| `wujin_items_v4` | 存储五金物料明细，提供关联信息 |
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# 跨域配置（按需修改允许的域名）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 注册路由 ====================

from router import router as query_router
from split_router import router as split_router

app.include_router(query_router)
app.include_router(split_router)


# ==================== 健康检查 ====================

@app.get("/health", tags=["系统"])
def health():
    """服务健康检查"""
    import os
    from db import get_conn

    # 数据库连通性
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        db_ok = True
        db_msg = "connected"
    except Exception as e:
        db_ok = False
        db_msg = str(e)

    # 拆图模块可用性
    try:
        from split_router import CAD_AVAILABLE, ODA_PATH, CAD_SEARCH_ROOT
        oda_exists = os.path.exists(ODA_PATH)
        cad_root_exists = os.path.exists(CAD_SEARCH_ROOT)
    except Exception:
        CAD_AVAILABLE = False
        oda_exists = False
        cad_root_exists = False
        ODA_PATH = ""
        CAD_SEARCH_ROOT = ""

    return {
        "status": "ok" if db_ok else "degraded",
        "database": {"ok": db_ok, "message": db_msg},
        "static_base_url": os.getenv("STATIC_BASE_URL", "http://localhost:8000"),
        "split": {
            "available": CAD_AVAILABLE,
            "oda_converter": ODA_PATH,
            "oda_exists": oda_exists,
            "cad_search_root": CAD_SEARCH_ROOT,
            "cad_root_exists": cad_root_exists,
        },
    }


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "7000"))

    logger.info("=" * 50)
    logger.info("📐 查询图纸服务启动")
    logger.info(f"   地址：http://{host}:{port}")
    logger.info(f"   文档：http://{host}:{port}/docs")
    logger.info("=" * 50)

    uvicorn.run(app, host=host, port=port)
