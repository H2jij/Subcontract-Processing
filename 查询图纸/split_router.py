# -*- coding: utf-8 -*-
"""
拆图 API 路由

功能：把一张完整的大模具图纸按零件编号拆分，
      输出只包含指定零件的小 DWG 文件。

依赖：
  - ODAFileConverter.exe（DWG <-> DXF 格式转换，需本地安装）
  - ezdxf（Python 解析 DXF 文件）
  - 网络共享盘上的图纸源文件（由 CAD_SEARCH_ROOT 指定）
"""
import os
import re
import shutil
import tempfile
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ==================== 读取配置 ====================

CAD_SEARCH_ROOT     = os.getenv("CAD_SEARCH_ROOT", r"E:\\")
ODA_PATH            = os.getenv("ODA_FILE_CONVERTER_PATH", r"D:\AI\ODA\ODAFileConverter.exe")
CHAITU_OUTPUT_DIR   = os.getenv("CHAITU_OUTPUT_DIR", "static/dwg/chaidan")
STATIC_BASE_URL     = os.getenv("STATIC_BASE_URL", "http://localhost:8000")
CHAITU_SAVE_TO_DB   = os.getenv("CHAITU_SAVE_TO_DB", "true").lower() == "true"

# 确保输出目录存在
Path(CHAITU_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

# ==================== 导入拆图核心 ====================

try:
    # chaitu1.py 与本文件在同一目录
    import sys, os as _os
    _here = _os.path.dirname(_os.path.abspath(__file__))
    if _here not in sys.path:
        sys.path.insert(0, _here)

    from chaitu1 import CADProcessor, find_latest_dwg_path
    CAD_AVAILABLE = True
    logger.info("✅ 拆图模块加载成功")
except Exception as _e:
    CAD_AVAILABLE = False
    CADProcessor = None
    find_latest_dwg_path = None
    logger.warning(f"⚠️ 拆图模块加载失败，拆图接口不可用: {_e}")

router = APIRouter(prefix="/split", tags=["拆图"])


# ==================== 请求 / 响应模型 ====================

class SplitRequest(BaseModel):
    model_code: str = Field(
        ...,
        description="模具编号，用于在图纸库中找到源 DWG 文件。"
                    "支持格式：M250247-P6 / M250247.P6 / M250247.P6-WUJIN",
        example="M250247-P6",
    )
    sub_codes: str = Field(
        ...,
        description="要拆出的子图编号，多个用英文逗号分隔。"
                    "支持带模具号前缀（自动去掉）或纯编号。",
        example="DIE-10,A-10",
    )
    save_to_db: Optional[bool] = Field(
        None,
        description="是否将结果写入数据库 supplier_shortlist_chaidan_wujin.dwg 字段。"
                    "不传则使用 .env 中 CHAITU_SAVE_TO_DB 的设置。",
    )
    group_uid: Optional[str] = Field(
        None,
        description="子订单ID（UUID）。当 save_to_db=true 时，用于定位要更新的数据库记录。",
        example="550e8400-e29b-41d4-a716-446655440000",
    )
    no: Optional[str] = Field(
        None,
        description="请购单编号。当 save_to_db=true 时配合 group_uid 定位记录。",
        example="WJJQG202512080005",
    )


class SplitResponse(BaseModel):
    success: bool
    message: Optional[str] = None

    # 成功时返回
    dwg_path: Optional[str] = Field(None, description="生成文件的相对路径")
    dwg_url: Optional[str] = Field(None, description="生成文件的完整访问 URL")
    filename: Optional[str] = Field(None, description="生成的文件名")

    # 输入信息回显
    model_code: Optional[str] = Field(None, description="规范化后的模具编号")
    sub_codes: Optional[str] = Field(None, description="规范化后的子图编号列表")

    # 数据库写入结果
    db_updated: Optional[bool] = Field(None, description="是否成功写入数据库")


class PreviewResponse(BaseModel):
    """预览：列出图纸中所有可识别的子图编号"""
    success: bool
    message: Optional[str] = None
    model_code: Optional[str] = None
    source_dwg: Optional[str] = Field(None, description="源 DWG 文件路径")
    sub_drawings: Optional[List[str]] = Field(None, description="可识别到的所有子图编号列表")
    total: Optional[int] = None


# ==================== 工具函数 ====================

def _normalize_model_code(raw: str) -> str:
    """
    规范化模具编号：
      M250247.P6-WUJIN  →  M250247-P6
      M250247.P6        →  M250247-P6
      M250247-P6        →  M250247-P6（不变）
    """
    mc = raw.strip()
    m = re.match(r'(M\d{6})[.\-]?(P\d+)', mc, re.IGNORECASE)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.match(r'(M\d{6})', mc, re.IGNORECASE)
    return m.group(1) if m else mc


def _normalize_sub_codes(model_code: str, raw: str) -> str:
    """
    规范化子图编号，去掉模具号前缀：
      M250247-P6-DIE-10,M250247-P6-A-10  →  DIE-10,A-10
      DIE-10,A-10                         →  DIE-10,A-10（不变）
    支持中英文逗号。
    """
    parts = [s.strip() for s in re.split(r'[,，]+', raw) if s.strip()]
    cleaned = []
    for p in parts:
        # 先尝试去掉 M######-P#- 前缀
        result = re.sub(rf'^{re.escape(model_code)}-', '', p, flags=re.IGNORECASE)
        if result == p:
            # 兜底：去掉任意 M######[.-]P##- 前缀
            result = re.sub(r'^M\d{6}[.\-]?P\d+[.\-]', '', p, flags=re.IGNORECASE)
        cleaned.append(result)
    return ','.join(cleaned)


def _build_url(path: str) -> str:
    base = STATIC_BASE_URL.rstrip("/")
    return f"{base}/{path.lstrip('/')}"


def _save_dwg_to_db(group_uid: str, no: str, dwg_relative_path: str):
    """
    将拆图结果路径写入数据库 supplier_shortlist_chaidan_wujin.dwg 字段。
    写入格式：{"dwg": "static/dwg/chaidan/xxx.dwg"}
    """
    try:
        from db import get_conn, get_dict_cursor
        dwg_json = json.dumps({"dwg": dwg_relative_path}, ensure_ascii=False)

        sql = """
            UPDATE supplier_shortlist_chaidan_wujin
            SET dwg = %(dwg)s
            WHERE group_uid::text = %(group_uid)s
              AND no = %(no)s
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {
                    "dwg": dwg_json,
                    "group_uid": str(group_uid),
                    "no": no,
                })
                affected = cur.rowcount
            conn.commit()

        if affected > 0:
            logger.info(f"[拆图-写库] 成功更新 {affected} 条记录: group_uid={group_uid}")
            return True
        else:
            logger.warning(f"[拆图-写库] 未匹配到记录: group_uid={group_uid}, no={no}")
            return False
    except Exception as e:
        logger.error(f"[拆图-写库] 写入失败: {e}", exc_info=True)
        return False


# ==================== 接口1：执行拆图 ====================

@router.post(
    "/chaitu",
    response_model=SplitResponse,
    summary="拆分图纸",
    description="""
从大模具图纸中拆出指定零件的子图，生成独立的 DWG 文件。

### 拆图流程
1. 根据 `model_code` 在图纸库（CAD_SEARCH_ROOT）中找到最新版源 DWG 文件
2. 用 ODAFileConverter 将 DWG 转换为 DXF
3. 用 ezdxf 解析 DXF，识别每个子图的编号
4. 匹配 `sub_codes` 中指定的编号，提取对应的图形实体
5. 合并匹配的子图，纵向排版，导出为新 DXF
6. 再用 ODAFileConverter 将 DXF 转回 DWG
7. 保存到输出目录，返回文件路径

### 编号格式说明
子图编号会自动去掉模具号前缀，以下三种写法等效：
- `DIE-10`
- `M250247-P6-DIE-10`
- `M250247.P6-DIE-10`

多个编号用英文逗号分隔：`DIE-10,A-10,B03`
    """,
)
async def chaitu(request: SplitRequest):
    if not CAD_AVAILABLE:
        return SplitResponse(
            success=False,
            message="CAD 拆图模块不可用，请检查 ODA 转换器和 ezdxf 是否正确安装",
        )

    # 1. 规范化参数
    model_code = _normalize_model_code(request.model_code)
    sub_codes  = _normalize_sub_codes(model_code, request.sub_codes)
    logger.info(f"[拆图] 请求: model_code={model_code}, sub_codes={sub_codes}")

    # 2. 查找源 DWG 文件
    try:
        source_dwg = find_latest_dwg_path(model_code, z_root=CAD_SEARCH_ROOT)
        if not source_dwg or not os.path.exists(source_dwg):
            return SplitResponse(
                success=False,
                message=f"在图纸库中未找到源文件: {model_code}，请确认模具编号是否正确",
                model_code=model_code,
            )
        logger.info(f"[拆图] 源文件: {source_dwg}")
    except Exception as e:
        return SplitResponse(
            success=False,
            message=f"查找源文件失败: {e}",
            model_code=model_code,
        )

    # 3. 读取源文件内容
    with open(source_dwg, 'rb') as f:
        input_data = f.read()

    # 4. 执行拆图（在临时目录里处理）
    temp_dir = tempfile.mkdtemp(prefix="chaitu_split_")
    temp_output = os.path.join(temp_dir, "output.dwg")

    try:
        processor = CADProcessor()
        success, result_path, _ = processor.process_workflow(
            input_data,
            temp_output,
            target_name=sub_codes,
        )

        if not success or not result_path or not os.path.exists(result_path):
            return SplitResponse(
                success=False,
                message=f"拆图处理失败：在源文件中未找到匹配编号 [{sub_codes}]，请确认子图编号是否正确",
                model_code=model_code,
                sub_codes=sub_codes,
            )

        # 5. 保存到输出目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_sub = sub_codes.replace(',', '_')[:30]
        filename = f"{model_code}_{safe_sub}_{timestamp}.dwg"
        save_dir = Path(CHAITU_OUTPUT_DIR)
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / filename
        shutil.copyfile(result_path, save_path)

        # 6. 构建返回路径
        dwg_relative = f"{CHAITU_OUTPUT_DIR.rstrip('/')}/{filename}"
        dwg_url = _build_url(dwg_relative)
        logger.info(f"[拆图] ✅ 成功: {save_path}")

        # 7. 可选：写入数据库
        db_updated = None
        should_save = request.save_to_db if request.save_to_db is not None else CHAITU_SAVE_TO_DB
        if should_save and request.group_uid and request.no:
            db_updated = _save_dwg_to_db(request.group_uid, request.no, dwg_relative)

        return SplitResponse(
            success=True,
            message="拆图成功",
            dwg_path=dwg_relative,
            dwg_url=dwg_url,
            filename=filename,
            model_code=model_code,
            sub_codes=sub_codes,
            db_updated=db_updated,
        )

    finally:
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


# ==================== 接口2：预览子图列表 ====================

@router.get(
    "/preview",
    response_model=PreviewResponse,
    summary="预览图纸中所有子图编号",
    description="""
在真正拆图之前，先列出源图纸中所有可识别到的子图编号。

适合用于：
- 不确定子图叫什么编号时先查一下
- 验证某个编号是否存在于源图纸中

**注意**：解析过程需要 ODA 转换和 ezdxf 解析，耗时较长（10-60 秒），请耐心等待。
    """,
)
async def preview(
    model_code: str,
):
    """
    列出源 DWG 图纸中所有可识别的子图编号。

    - **model_code**: 模具编号，如 M250247-P6
    """
    if not CAD_AVAILABLE:
        return PreviewResponse(
            success=False,
            message="CAD 拆图模块不可用，请检查依赖是否安装",
        )

    model_code = _normalize_model_code(model_code)

    # 1. 查找源文件
    try:
        source_dwg = find_latest_dwg_path(model_code, z_root=CAD_SEARCH_ROOT)
        if not source_dwg or not os.path.exists(source_dwg):
            return PreviewResponse(
                success=False,
                message=f"未找到源文件: {model_code}",
                model_code=model_code,
            )
    except Exception as e:
        return PreviewResponse(
            success=False,
            message=f"查找源文件失败: {e}",
            model_code=model_code,
        )

    # 2. DWG → DXF
    try:
        from chaitu1 import DWGConverter, Config, OptimizedCADBlockAnalyzer
        config = Config()
        config.oda_file_converter_path = ODA_PATH

        temp_dir = tempfile.mkdtemp(prefix="chaitu_preview_")
        dxf_path = os.path.join(temp_dir, "preview.dxf")

        try:
            converter = DWGConverter(config)
            result = converter.convert_dwg_to_dxf(source_dwg, dxf_path)
            if not result or not os.path.exists(dxf_path):
                return PreviewResponse(
                    success=False,
                    message="DWG 转 DXF 失败，请检查 ODA 转换器配置",
                    model_code=model_code,
                    source_dwg=source_dwg,
                )

            # 3. 解析子图
            analyzer = OptimizedCADBlockAnalyzer()
            sub_drawings = analyzer.analyze_cad_file(dxf_path)

            names = []
            for region_id, region in sub_drawings.items():
                fname = analyzer.resolve_region_name(region_id, region)
                if fname and fname != region_id:
                    names.append(fname)

            names = sorted(set(names))

            return PreviewResponse(
                success=True,
                model_code=model_code,
                source_dwg=source_dwg,
                sub_drawings=names,
                total=len(names),
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f"[预览] 异常: {e}", exc_info=True)
        return PreviewResponse(
            success=False,
            message=f"解析图纸失败: {e}",
            model_code=model_code,
        )


# ==================== 接口3：查找源文件路径 ====================

@router.get(
    "/locate",
    summary="定位源 DWG 文件路径",
    description="""
只做一件事：根据模具编号在图纸库中找到源 DWG 文件路径，不做任何转换。

用于验证图纸库中是否存在这套模具的图纸，以及文件的具体位置。
    """,
)
def locate(
    model_code: str,
):
    """
    - **model_code**: 模具编号，如 M250247-P6
    """
    if not CAD_AVAILABLE:
        return {"success": False, "message": "CAD 模块不可用"}

    model_code = _normalize_model_code(model_code)
    try:
        path = find_latest_dwg_path(model_code, z_root=CAD_SEARCH_ROOT)
        if path and os.path.exists(path):
            stat = os.stat(path)
            return {
                "success": True,
                "model_code": model_code,
                "source_dwg": path,
                "file_size_mb": round(stat.st_size / 1024 / 1024, 2),
                "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        return {
            "success": False,
            "model_code": model_code,
            "message": f"未找到图纸文件: {model_code}",
        }
    except Exception as e:
        return {
            "success": False,
            "model_code": model_code,
            "message": str(e),
        }
