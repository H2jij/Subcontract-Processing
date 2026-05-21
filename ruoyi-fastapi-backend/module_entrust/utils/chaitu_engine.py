#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CAD 拆图处理工具模块

功能：
- DWG <-> DXF 文件格式转换（ODAFileConverter 支持）
- 集成 IntegralMoudleSplitting.py 的拆图实现（子图识别、导出）
- 集成 GraphicMerge.py 的合并实现（按子文件夹合并并纵向紧凑排版）
- 本地 DWG 文件查找（基于订单代码）

使用方式：
1. 作为工具模块导入（推荐）：
   from app.utils.chaitu1 import CADProcessor, find_dwg_by_keyword
   processor = CADProcessor()
   result = processor.process_workflow(...)

2. 作为独立 Flask 服务运行（可选）：
   取消文件末尾 if __name__ == '__main__' 的注释
   python chaitu1.py

注意：
- 当前默认作为工具模块使用，不会启动 Flask 服务
- Flask 相关代码保留是为了保持兼容性和未来扩展
"""

# Flask 相关导入设为可选（主要使用 FastAPI）
try:
    from flask import Flask, request, send_file, jsonify
    from flask_cors import CORS
    from werkzeug.utils import secure_filename
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    Flask = None

import tempfile
import os
import subprocess
import shutil
import ezdxf
import math
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Optional
from collections import defaultdict, Counter
import re

# 使用 Python 标准 logging
import logging
logger = logging.getLogger(__name__)

# ---------------- Configuration ----------------

class Config:
    def __init__(self):
        # 从 RuoYi 项目配置读取 CAD 路径
        try:
            from config.env import AppSettings
            settings = AppSettings()
            self.oda_file_converter_path = settings.oda_file_converter_path
            self.z_root = Path(settings.cad_search_root)
        except Exception:
            # 如果无法导入配置，使用默认值
            self.oda_file_converter_path = r"D:\ODAFileConverter_title 21.5.0\ODAFileConverter.exe"
            self.z_root = Path(r"D:\\")
        self.temp_dir = tempfile.gettempdir()

# ---------------- DWG 本地查找（参考 nacad.py 逻辑） ----------------

def extract_model_base(keyword: str) -> str:
    m = re.search(r"(M\d{6})", keyword.upper())
    if not m:
        raise ValueError(f'关键字里找不到 M######：{keyword}')
    return m.group(1)


def pick_year_dir(z_root: Path, model_base: str) -> Path:

    if model_base.startswith("M24"):
        year_prefix = "2024"
    elif model_base.startswith("M25"):
        year_prefix = "2025"
    elif model_base.startswith("M26"):
        year_prefix = "2026"
    else:
        raise ValueError(f'不支持的前缀：{model_base[:3]}（只支持 M24/M25/M26）')

    logger.debug(f"[CAD查找] 搜索年份目录: z_root={z_root}, year_prefix={year_prefix}")
    
    # 先列出根目录下的所有目录（用于调试）
    try:
        all_dirs = [p.name for p in z_root.iterdir() if p.is_dir()]
        logger.debug(f"[CAD查找] 根目录下的所有目录（前10个）: {all_dirs[:10]}")
    except Exception as e:
        logger.error(f"[CAD查找] 无法列出根目录内容: {e}")
        raise
    
    # 匹配格式：2025---M250001 ~ 或 2024---M240001 ~341
    # 必须以 "年份---M年份前缀" 开头
    pattern_prefix = f"{year_prefix}---{model_base[:3]}"
    
    hits = []
    for p in z_root.iterdir():
        if p.is_dir() and p.name.startswith(pattern_prefix):
            hits.append(p)
            logger.debug(f"[CAD查找] 找到匹配目录: {p.name}")
    
    logger.debug(f"[CAD查找] 匹配到 {len(hits)} 个年份目录")
    
    if not hits:
        raise FileNotFoundError(f'在 {z_root} 下找不到年份目录：{year_prefix}---{model_base[:3]}*')
    
    # 按修改时间排序，取最新的
    hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    logger.debug(f"[CAD查找] 选择年份目录: {hits[0]}")
    return hits[0]


def seq_of(model_base: str) -> int:
    return int(model_base[3:])


def parse_month_range(folder_name: str, year2: str):
    # 解析类似 "10月新模具M250221~239"
    m_start = re.search(rf"(M{year2}\d{{4}})", folder_name, re.IGNORECASE)
    if not m_start:
        return None
    start_seq = int(m_start.group(1)[3:])
    m_end = re.search(r"~\s*(\d+)", folder_name)
    end_seq = int(m_end.group(1)) if m_end else math.inf
    return start_seq, end_seq


def pick_month_dir(year_dir: Path, model_base: str) -> Path:
    year2 = model_base[1:3]
    target = seq_of(model_base)

    candidates = []
    for p in year_dir.iterdir():
        if not p.is_dir():
            continue
        r = parse_month_range(p.name, year2)
        if not r:
            continue
        s, e = r
        if s <= target <= e:
            span = (e - s) if e != math.inf else math.inf
            candidates.append((span, s, p))

    if not candidates:
        raise FileNotFoundError(f'在 {year_dir} 下找不到包含序号 {target} 的月份目录')

    candidates.sort(key=lambda x: (x[0], -x[1]))
    return candidates[0][2]


def pick_model_dir(month_dir: Path, model_base: str) -> Path:
    starts = [p for p in month_dir.iterdir() if p.is_dir() and p.name.upper().startswith(model_base)]
    if starts:
        starts.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return starts[0]

    contains = [p for p in month_dir.iterdir() if p.is_dir() and model_base in p.name.upper()]
    if contains:
        contains.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return contains[0]

    raise FileNotFoundError(f'在 {month_dir} 下找不到型号目录：{model_base}*')


def locate_2d_dir(model_dir: Path) -> Path:
    direct = model_dir / "4.模具图" / "2D"
    if direct.exists():
        return direct

    # 兜底：找包含"模具图"的目录，再找其下的 2D
    mold_candidates = [p for p in model_dir.rglob("*模具图") if p.is_dir()]
    if not mold_candidates:
        raise FileNotFoundError(f'在 {model_dir} 下找不到"模具图"目录')
    mold_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    mold_dir = mold_candidates[0]

    two_d = mold_dir / "2D"
    if two_d.exists():
        return two_d

    hits = [p for p in mold_dir.rglob("2D") if p.is_dir()]
    if hits:
        hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return hits[0]

    raise FileNotFoundError(f'在 {mold_dir} 下找不到 2D 目录')


def extract_date_from_name(filename: str):
    """
    支持：
      M250230-P1.2025.11.21.dwg -> 2025-11-21
      M250230-P1_20251121.dwg   -> 2025-11-21
      M250230-P1 2025-11-21.dwg -> 2025-11-21
    """
    s = filename
    m = re.search(r"(20\d{2})[.\-_](\d{1,2})[.\-_](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return (y, mo, d)

    m = re.search(r"(20\d{2})(\d{2})(\d{2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return (y, mo, d)

    return None


def pick_latest_dwg(two_d_dir: Path, keyword: str) -> Path:
    files = [p for p in two_d_dir.glob(f"*{keyword}*.dwg") if p.is_file()]
    if not files:
        raise FileNotFoundError(f'在 {two_d_dir} 下没找到 *{keyword}*.dwg')

    scored = []
    for p in files:
        d = extract_date_from_name(p.name)
        mtime = p.stat().st_mtime
        scored.append((d is not None, d or (0, 0, 0), mtime, p))

    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    return scored[0][3]


def find_latest_dwg_path(keyword: str, z_root: str = None) -> str:
    # 如果没有传入 z_root，从配置读取
    if z_root is None:
        try:
            from config.env import AppSettings
            z_root = AppSettings().cad_search_root
        except Exception:
            z_root = r"D:\\"
    z_root_path = Path(z_root)
    model_base = extract_model_base(keyword)

    year_dir = pick_year_dir(z_root_path, model_base)
    month_dir = pick_month_dir(year_dir, model_base)
    model_dir = pick_model_dir(month_dir, model_base)
    two_d_dir = locate_2d_dir(model_dir)

    # 规范化 keyword：将 M250247.P6 转为 M250247-P6
    normalized_keyword = re.sub(r'(M\d{6})[.]([Pp]\d+)', r'\1-\2', keyword)

    # 优先用完整关键词（含P号）搜索，搜不到则回退到纯模具号
    try:
        latest = pick_latest_dwg(two_d_dir, normalized_keyword)
        return str(latest)
    except FileNotFoundError:
        if normalized_keyword != model_base:
            logger.debug(f"[CAD查找] 用 '{normalized_keyword}' 未找到，回退用 '{model_base}' 搜索")
            latest = pick_latest_dwg(two_d_dir, model_base)
            return str(latest)
        raise

# ---------------- DWG <-> DXF Converter ----------------

class DWGConverter:
    def __init__(self, config: Config):
        self.config = config

    def _convert(self, input_file, output_file, output_format, output_version='ACAD2004'):
        """
        统一转换入口，使用 ODAFileConverter.exe 将文件转换为指定格式（DXF 或 DWG）
        output_format: 'DXF' 或 'DWG'
        """
        if not os.path.exists(input_file):
            logger.debug(f"错误：找不到输入文件 {input_file}")
            return None

        temp_output_dir = tempfile.mkdtemp(prefix="oda_output_")
        input_dir = os.path.dirname(input_file)

        command = [
            self.config.oda_file_converter_path,
            input_dir,
            temp_output_dir,
            output_version,
            output_format,
            '0',
            '1',
        ]

        try:
            logger.debug(f"开始使用 ODA 将 {os.path.basename(input_file)} 转换为 {output_format} (版本: {output_version})...")
            result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=300)
            base_name = os.path.splitext(os.path.basename(input_file))[0]
            generated_file = os.path.join(temp_output_dir, f"{base_name}.{output_format.lower()}")
            if os.path.exists(generated_file):
                shutil.move(generated_file, output_file)
                logger.debug(f"转换成功！文件已保存到 {output_file}")
                return output_file
            else:
                logger.debug(f"转换后的文件未找到。ODA输出目录：{os.listdir(temp_output_dir)}")
                return None
        except Exception as e:
            logger.debug(f"转换失败: {e}")
            if hasattr(e, 'stdout') and e.stdout:
                logger.debug("stdout:", e.stdout)
            if hasattr(e, 'stderr') and e.stderr:
                logger.debug("stderr:", e.stderr)
            return None
        finally:
            try:
                shutil.rmtree(temp_output_dir)
            except Exception:
                pass

    def convert_dwg_to_dxf(self, input_dwg_file, output_dxf_file):
        return self._convert(input_dwg_file, output_dxf_file, 'DXF')

    def convert_dxf_to_dwg(self, input_dxf_file, output_dwg_file, output_version='ACAD2004'):
        return self._convert(input_dxf_file, output_dwg_file, 'DWG', output_version)

# ---------------- 拆图引擎：调用 dxf_split.py ----------------
from module_entrust.utils.dxf_split import (
    EZDXF_AVAILABLE,
    split_dxf_file_with_output,
)

if EZDXF_AVAILABLE:
    from module_entrust.utils.dxf_split import OptimizedCADBlockAnalyzer as _NewAnalyzer


class CADProcessor:
    """
    CAD 处理入口：DWG→DXF 转换 + 调用 dxf_split 拆图 + DXF→DWG 回转
    """
    def __init__(self):
        self.config = Config()
        self.dwg_converter = DWGConverter(self.config)

    def process_workflow(self, input_dwg_data: bytes, output_dwg_path: str,
                        target_name: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        完整拆图流程：
        1. DWG → DXF（ODAFileConverter）
        2. 全量拆图（dxf_split.py），输出到临时目录
        3. 如果指定了 target_name，在输出中匹配该零件文件
        4. 匹配到的 DXF → DWG 回转
        """
        if not EZDXF_AVAILABLE:
            logger.error('ezdxf 不可用，无法拆图')
            return False, None, None

        main_work_dir = tempfile.mkdtemp(prefix="cad_workflow_")

        try:
            input_dwg_path = os.path.join(main_work_dir, "input.dwg")
            temp_dxf_path = os.path.join(main_work_dir, "input.dxf")

            # 保存输入 DWG
            with open(input_dwg_path, 'wb') as f:
                f.write(input_dwg_data)
            logger.info(f"[拆图] 输入文件已创建: {input_dwg_path}")

            # Step 1: DWG → DXF
            logger.info("[拆图] Step 1: DWG → DXF 转换...")
            oda_success = False
            try:
                oda_out = self.dwg_converter.convert_dwg_to_dxf(input_dwg_path, temp_dxf_path)
                if oda_out:
                    oda_success = True
            except Exception as e:
                logger.warning(f"[拆图] ODA 转换异常: {e}")

            if not oda_success or not os.path.exists(temp_dxf_path):
                logger.error("[拆图] DWG → DXF 转换失败")
                return False, None, None

            logger.info("[拆图] DXF 转换成功")

            # Step 2: 全量拆图（dxf_split.py）
            splits_dir = os.path.join(main_work_dir, "splits")
            logger.info(f"[拆图] Step 2: 全量拆图，输出目录: {splits_dir}")
            exported_dir = split_dxf_file_with_output(temp_dxf_path, splits_dir)

            if not exported_dir or not os.path.isdir(exported_dir):
                logger.warning("[拆图] 拆图输出目录为空")
                return False, None, None

            # 列出所有拆出的文件
            split_files = [f for f in os.listdir(exported_dir) if f.lower().endswith('.dxf')]
            logger.info(f"[拆图] 拆出 {len(split_files)} 个子图文件: {split_files}")

            # Step 3: 如果指定了 target_name，匹配对应子图
            if target_name:
                names = [n.strip() for n in re.split(r'[,，]+', target_name) if n.strip()]
                matched_file = None
                for name in names:
                    # 按文件名匹配（dxf_split 导出的文件名就是零件编号）
                    for f in split_files:
                        basename = os.path.splitext(f)[0]
                        if name.upper() == basename.upper() or name.upper() in basename.upper():
                            matched_file = os.path.join(exported_dir, f)
                            break
                    if matched_file:
                        break

                if not matched_file:
                    logger.warning(f"[拆图] 未匹配到零件: {target_name}，可用文件: {split_files}")
                    return False, None, None

                logger.info(f"[拆图] Step 3: 匹配到 {os.path.basename(matched_file)}")

                # Step 4: DXF → DWG
                logger.info("[拆图] Step 4: DXF → DWG 回转...")
                final_path = output_dwg_path
                if not self.dwg_converter.convert_dxf_to_dwg(matched_file, final_path, 'ACAD2004'):
                    # 回转失败就直接返回 DXF
                    shutil.copyfile(matched_file, final_path.replace('.dwg', '.dxf'))
                    logger.warning("[拆图] DXF→DWG 回转失败，返回 DXF 文件")
                    return True, final_path.replace('.dwg', '.dxf'), f"{names[0]}.dxf"

                return True, final_path, f"{names[0]}.dwg"

            # 未指定 target_name，返回全部拆图目录
            logger.info("[拆图] 未指定目标零件，返回全部拆图结果")
            return True, exported_dir, None

        except Exception as e:
            logger.error(f"[拆图] 处理异常: {e}")
            import traceback
            traceback.print_exc()
            return False, None, None
        finally:
            # 注意：不立即清理，因为返回的文件路径在 main_work_dir 中
            # 调用方负责在使用完后清理
            pass


def preview_sub_drawings(dxf_path: str) -> List[str]:
    """
    预览 DXF 文件中所有可拆的零件编号（供 drawing_service.preview_assembly 调用）
    """
    if not EZDXF_AVAILABLE:
        return []

    analyzer = _NewAnalyzer()
    sub_drawings = analyzer.analyze_cad_file(dxf_path)

    names = []
    for region_id, region in sub_drawings.items():
        # 尝试从区域数据中提取文件名
        extractor = analyzer.number_extractor
        fname = extractor.extract_region_filename_by_patterns(region)
        if fname:
            if isinstance(fname, list):
                names.extend(fname)
            else:
                names.append(fname)
        elif region.get('factory_model_number'):
            names.append(region['factory_model_number'])

    return sorted(set(names))


def resolve_region_name(region_id: str, region: dict) -> Optional[str]:
    """
    兼容旧接口：从区域数据中提取零件名
    """
    if not EZDXF_AVAILABLE:
        return region_id

    extractor = _NewAnalyzer().number_extractor
    fname = extractor.extract_region_filename_by_patterns(region)
    if fname:
        if isinstance(fname, list):
            return fname[0]
        return fname
    return region_id

