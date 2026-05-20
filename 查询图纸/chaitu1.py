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

# 使用项目的 logger 配置（如果可用），否则使用默认的 loguru
try:
    from app.utils.logger import logger
except ImportError:
    from loguru import logger
    import sys
    # 配置日志：同时输出到控制台和文件
    logger.remove()  # 移除默认配置
    # 添加控制台输出（彩色，带时间戳）- 只显示 INFO 及以上级别
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",  # 只显示 INFO、WARNING、ERROR
        colorize=True
    )
    # 添加文件输出（详细日志，包含 DEBUG）
    logger.add(
        "logs/chaitu_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",  # 文件中保留所有级别
        rotation="00:00",
        retention="30 days",  # 保留30天
        encoding="utf-8"
    )

# ---------------- Configuration ----------------

class Config:
    def __init__(self):
        # 优先从原项目配置读取（相对导入），失败则读环境变量，最后才用硬编码默认值
        try:
            from ..config.settings import settings
            self.oda_file_converter_path = settings.ODA_FILE_CONVERTER_PATH
            self.z_root = Path(settings.CAD_SEARCH_ROOT)
        except ImportError:
            import os
            self.oda_file_converter_path = os.getenv(
                "ODA_FILE_CONVERTER_PATH", r"D:\AI\ODA\ODAFileConverter.exe"
            )
            self.z_root = Path(os.getenv("CAD_SEARCH_ROOT", r"E:\\"))
        self.temp_dir = tempfile.gettempdir()

# ---------------- DWG 本地查找（参考 nacad.py 逻辑） ----------------

def extract_model_base(keyword: str) -> str:
    m = re.search(r"(M\d{6})", keyword.upper())
    if not m:
        raise ValueError(f"关键字里找不到 M######：{keyword}")
    return m.group(1)


def pick_year_dir(z_root: Path, model_base: str) -> Path:
    from loguru import logger
    
    if model_base.startswith("M24"):
        year_prefix = "2024"
    elif model_base.startswith("M25"):
        year_prefix = "2025"
    elif model_base.startswith("M26"):
        year_prefix = "2026"
    else:
        raise ValueError(f"不支持的前缀：{model_base[:3]}（只支持 M24/M25/M26）")

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
        raise FileNotFoundError(f"在 {z_root} 下找不到年份目录：{year_prefix}---{model_base[:3]}*")
    
    # 按修改时间排序，取最新的
    hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    logger.debug(f"[CAD查找] 选择年份目录: {hits[0]}")
    return hits[0]


def seq_of(model_base: str) -> int:
    return int(model_base[3:])


def parse_month_range(folder_name: str, year2: str):
    # 解析类似 “10月新模具M250221~239”
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
        raise FileNotFoundError(f"在 {year_dir} 下找不到包含序号 {target} 的月份目录")

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

    raise FileNotFoundError(f"在 {month_dir} 下找不到型号目录：{model_base}*")


def locate_2d_dir(model_dir: Path) -> Path:
    direct = model_dir / "4.模具图" / "2D"
    if direct.exists():
        return direct

    # 兜底：找包含“模具图”的目录，再找其下的 2D
    mold_candidates = [p for p in model_dir.rglob("*模具图") if p.is_dir()]
    if not mold_candidates:
        raise FileNotFoundError(f"在 {model_dir} 下找不到“模具图”目录")
    mold_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    mold_dir = mold_candidates[0]

    two_d = mold_dir / "2D"
    if two_d.exists():
        return two_d

    hits = [p for p in mold_dir.rglob("2D") if p.is_dir()]
    if hits:
        hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return hits[0]

    raise FileNotFoundError(f"在 {mold_dir} 下找不到 2D 目录")


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
        raise FileNotFoundError(f"在 {two_d_dir} 下没找到 *{keyword}*.dwg")

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
            from ..config.settings import settings
            z_root = settings.CAD_SEARCH_ROOT
        except ImportError:
            z_root = r"E:\\"
    z_root_path = Path(z_root)
    model_base = extract_model_base(keyword)

    year_dir = pick_year_dir(z_root_path, model_base)
    month_dir = pick_month_dir(year_dir, model_base)
    model_dir = pick_model_dir(month_dir, model_base)
    two_d_dir = locate_2d_dir(model_dir)

    # 规范化 keyword：将 M250247.P6 转为 M250247-P6
    normalized_keyword = re.sub(r'(M\d{6})[.]([Pp]\d+)', r'\1-\2', keyword)
    
    latest = pick_latest_dwg(two_d_dir, normalized_keyword)
    return str(latest)

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

# ---------------- IntegralMoudleSplitting 集成（完整复制） ----------------
# (下面是从 IntegralMoudleSplitting.py 复制过来的实现，包含多个辅助类与导出逻辑)
# 为避免重复注释，该段直接放入完整类实现

class ProfessionalDrawingNumberExtractor:
    """专业图纸编号提取器 + 子图文件名提取"""

    def __init__(self):
        # 子图名称识别优先级：
        # 1) 优先匹配“编号”后面的编号
        # 2) 没有编号的话匹配“加工说明”后面的编号
        # 3) 再兜底：子图左上角可能存在编号（如 PS-01）
        self.number_inline_res = [
            re.compile(r'^\s*编号\s*[：:]\s*(\S+)\s*$', re.IGNORECASE),
            re.compile(r'编号\s*[：:]\s*(\S+)', re.IGNORECASE),
            re.compile(r'编号\s*:\([^)]+\)_(\S+)', re.IGNORECASE),
        ]
        self.processing_inline_res = [
            # 兼容：加工说明：外限位 B02 / 加工说明:小母位 _B07 / 加工说明(侧限位)B08 / 加工说明:(下垫脚)_B2-02
            re.compile(
                r'加工说明[^\r\n]*?[_\-\s]*([A-Za-z]{1,4}\d{1,3}(?:[-_][A-Za-z0-9]+)*)',
                re.IGNORECASE,
            ),
            # 兼容：加工说明:(下垫脚) B2-03 / 加工说明(下垫脚):B2-03 / 加工说明 B2-03
            re.compile(
                r'加工说明\s*(?:[：:]\s*)?(?:\([^)]*\)\s*)?([A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*)',
                re.IGNORECASE,
            ),
            re.compile(r'加工说明\s*(?:\([^)]*\)\s*)?[：:]\s*(\S+)', re.IGNORECASE),
        ]
        self.number_label_only_res = re.compile(r'^\s*编号\s*[:：]?\s*$', re.IGNORECASE)
        self.processing_label_only_res = re.compile(r'^\s*加工说明\s*[:：]?\s*$', re.IGNORECASE)
        # 兼容“加工说明xxx”这一整段文字作为锚点（编号可能在旁边另一个文字实体里，如 B07/B08）
        self.processing_label_anchor_res = re.compile(r'^\s*加工说明.*$', re.IGNORECASE)

        # 受控编号字符集：命中该字符集则认为是有效编号（用于“就近匹配”避免误抓普通文字）
        self.confirm_code_res = [
            re.compile(
                r'('
                r'U[12](?:-\s*[A-Z0-9]+)?|'
                r'(?:UP|UB|PH|PU|PS|GU|LB|LP|EB|EJ|FB|CV|CJ|CB|PM)(?:-\s*[A-Z0-9]+)?|'
                r'(?:PPS|DIE|BOL|BOI)(?:-\s*[A-Z0-9]+)?|'
                r'B\d{2}(?:-\s*[A-Z0-9]+)?|'
                r'(?:DIE2|PPS2|PS2|PH2|LB2)(?:-\s*[A-Z0-9]+)?|'
                r'(?:UB_P|PH_P|PU_P|PPS_P|PS_P|GU_P|LB_P|DIE_P)(?:-\s*[A-Z0-9]+)?|'
                r'(?:DIE2_P|PPS2_P|PS2_P|PH2_P|LB2_P)(?:-\s*[A-Z0-9]+)?|'
                r'(?:UP_JIAT|PS_JIAT|LOW_JIAT)(?:-\s*[A-Z0-9]+)?|'
                r'(?:UP_ITEM|PSITEM|LOW_ITEM)(?:-\s*[A-Z0-9]+)?|'
                r'(?:STRIP|CAM)(?:-\s*[A-Z0-9]+)?|'
                r'ST[23](?:-\s*[A-Z0-9]+)?|'
                r'TEMP[12](?:-\s*[A-Z0-9]+)?|'
                r'[A-Z]-\d{1,3}(?:-\s*[A-Z0-9]+)?'
                r')(?=\s|$|[^\w-])',
                re.IGNORECASE,
            ),
            re.compile(
                r'(?:[\(_])'
                r'('
                r'U[12](?:-\s*[A-Z0-9]+)?|'
                r'(?:UP|UB|PH|PU|PS|GU|LB|LP|EB|EJ|FB|CV|CJ|CB|PM)(?:-\s*[A-Z0-9]+)?|'
                r'(?:PPS|DIE|BOL|BOI)(?:-\s*[A-Z0-9]+)?|'
                r'B\d{2}(?:-\s*[A-Z0-9]+)?|'
                r'(?:DIE2|PPS2|PS2|PH2|LB2)(?:-\s*[A-Z0-9]+)?|'
                r'(?:UB_P|PH_P|PU_P|PPS_P|PS_P|GU_P|LB_P|DIE_P)(?:-\s*[A-Z0-9]+)?|'
                r'(?:DIE2_P|PPS2_P|PS2_P|PH2_P|LB2_P)(?:-\s*[A-Z0-9]+)?|'
                r'(?:UP_JIAT|PS_JIAT|LOW_JIAT)(?:-\s*[A-Z0-9]+)?|'
                r'(?:UP_ITEM|PSITEM|LOW_ITEM)(?:-\s*[A-Z0-9]+)?|'
                r'(?:STRIP|CAM)(?:-\s*[A-Z0-9]+)?|'
                r'ST[23](?:-\s*[A-Z0-9]+)?|'
                r'TEMP[12](?:-\s*[A-Z0-9]+)?|'
                r'[A-Z]-\d{1,3}(?:-\s*[A-Z0-9]+)?'
                r')(?=\s|$|[^\w-])',
                re.IGNORECASE,
            ),
        ]

        # 高优先级编号模式
        self.primary_patterns = [
            r'PH-[A-Z0-9]+',
            r'DIE-[A-Z0-9]+',
            r'[A-Z]{1,2}[0-9]{1,3}-[A-Z]{1,2}',
            r'[A-Z]{1,2}[0-9]{2,3}',
            r'[A-Z]{2,4}-[0-9]{1,3}',
        ]

        # 排除词汇库   , '加工说明'
        self.excluded_terms = {
            '图纸', '设计', '审核', '标准', '规格', '材料', '备注', '品名', '编号',
                '数量', '热处理', '修改', '尺寸', '所有', '全周', '已订购',
                'TITLE', 'DRAWING', 'DESIGN', 'SCALE', 'DATE', '制图', '日期',
                '单位', '比例', '共页', '第页', '版本', 'PCS', '深', '攻', '钻',
                '割', '铰', '倒角', '沉头', '背', '穿', '让位', '合销', '导套',
                '螺丝', '基准', '弹簧', '定位', '精铣', '慢丝', '线割', '垂直度',
                '位置度', '加工', '夹板', '入子', '连接块', '外形', '绿色', '虚线',
                '直身', '拼装', '零件', '模板', '精磨'
        }

        # CAD标注符号库
        self.cad_annotations = {'M', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9', 'M10',
                'G', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7', 'G8', 'G9',
                'L', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8', 'L9',
                'U', 'U1', 'U2', 'U3', 'U4', 'U5', 'X', 'X1', 'X2', 'X3', 'X4', 'X5', 'X6', 'X7', 'X8', 'X9',
                'K', 'K1', 'K2', 'K3', 'K4', 'K5', 'A', 'A1', 'A2', 'A3', 'A4', 'A5',
                'Q', 'Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9'}

    def _text_pos(self, t: Dict, fallback: Tuple[float, float]) -> Tuple[float, float]:
        p = t.get('position')
        if isinstance(p, (tuple, list)) and len(p) >= 2:
            try:
                return float(p[0]), float(p[1])
            except Exception:
                return fallback
        return fallback

    def _extract_inline(self, texts: List[Dict], regexes: List[re.Pattern]) -> Optional[str]:
        for t in texts:
            c = (t.get('content') or '').strip()
            if not c:
                continue
            for rx in regexes:
                m = rx.search(c)
                if m and m.group(1):
                    cand = self._clean_candidate_after_label(m.group(1))
                    if self._validate_drawing_number(cand):
                        return cand
        return None

    def _extract_near_label(self, bounds: Dict, texts: List[Dict], label_only_re: re.Pattern) -> Optional[str]:
        if not texts:
            return None
        min_x, max_x = bounds.get('min_x', 0.0), bounds.get('max_x', 0.0)
        min_y, max_y = bounds.get('min_y', 0.0), bounds.get('max_y', 0.0)
        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        fallback = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

        label_texts = []
        for t in texts:
            c = (t.get('content') or '').strip()
            if c and label_only_re.match(c):
                label_texts.append(t)
        if not label_texts:
            return None

        candidates = []
        for t in texts:
            c = (t.get('content') or '').strip()
            if not c:
                continue
            cand = self._clean_candidate_after_label(c)
            if not self._validate_drawing_number(cand):
                continue
            x, y = self._text_pos(t, fallback)
            candidates.append((cand, x, y))
        if not candidates:
            return None

        best = None
        best_score = None
        for label_t in label_texts:
            lx, ly = self._text_pos(label_t, fallback)
            for cand, x, y in candidates:
                dx = abs(x - lx)
                dy = abs(y - ly)
                same_line = dy <= height * 0.06
                right_side = x >= lx - width * 0.02
                below = y <= ly + height * 0.02

                score = (dy * 2.0 + dx)
                if same_line and right_side:
                    score *= 0.25
                elif below and right_side:
                    score *= 0.45
                if dx > width * 0.5 or dy > height * 0.5:
                    score *= 3.0

                if best_score is None or score < best_score:
                    best_score = score
                    best = cand
        return best

    def _normalize_confirmed_code(self, code: str) -> str:
        c = (code or "").strip().upper()
        if not c:
            return ""
        c = re.sub(r"\s*-\s*", "-", c)
        c = re.sub(r"\s+", "", c)
        return c

    def _extract_confirmed_codes_from_text(self, text: str) -> List[str]:
        s = (text or "").strip()
        if not s:
            return []
        found: List[str] = []
        for rx in getattr(self, "confirm_code_res", []):
            for m in rx.finditer(s):
                try:
                    g = m.group(1)
                except Exception:
                    g = None
                if not g:
                    continue
                code = self._normalize_confirmed_code(g)
                if code:
                    found.append(code)
        # 去重保持顺序
        uniq: List[str] = []
        seen = set()
        for c in found:
            if c not in seen:
                uniq.append(c)
                seen.add(c)
        return uniq

    def _extract_near_label_confirmed(self, bounds: Dict, texts: List[Dict], label_re: re.Pattern) -> Optional[str]:
        if not texts:
            return None
        min_x, max_x = bounds.get("min_x", 0.0), bounds.get("max_x", 0.0)
        min_y, max_y = bounds.get("min_y", 0.0), bounds.get("max_y", 0.0)
        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        fallback = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

        label_texts = []
        for t in texts:
            c = (t.get("content") or "").strip()
            if c and label_re.match(c):
                label_texts.append(t)
        if not label_texts:
            return None

        candidates: List[Tuple[str, float, float]] = []
        for t in texts:
            c = (t.get("content") or "").strip()
            if not c:
                continue
            codes = self._extract_confirmed_codes_from_text(c)
            if not codes:
                continue
            x, y = self._text_pos(t, fallback)
            for code in codes:
                candidates.append((code, x, y))
        if not candidates:
            return None

        best = None
        best_score = None
        for label_t in label_texts:
            lx, ly = self._text_pos(label_t, fallback)
            for code, x, y in candidates:
                dx = abs(x - lx)
                dy = abs(y - ly)
                same_line = dy <= height * 0.06
                right_side = x >= lx - width * 0.02
                below = y <= ly + height * 0.02

                score = (dy * 2.0 + dx)
                if same_line and right_side:
                    score *= 0.25
                elif below and right_side:
                    score *= 0.45
                if dx > width * 0.6 or dy > height * 0.6:
                    score *= 3.0

                if best_score is None or score < best_score:
                    best_score = score
                    best = code
        return best

    def _extract_from_top_left(self, bounds: Dict, texts: List[Dict]) -> Optional[str]:
        if not texts:
            return None
        min_x, max_x = bounds.get('min_x', 0.0), bounds.get('max_x', 0.0)
        min_y, max_y = bounds.get('min_y', 0.0), bounds.get('max_y', 0.0)
        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        fallback = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

        x_cut = min_x + width * 0.35
        y_cut = max_y - height * 0.35
        corner_x, corner_y = min_x, max_y

        best = None
        best_dist = None
        for t in texts:
            c = (t.get('content') or '').strip()
            if not c:
                continue
            cand = self._clean_candidate_after_label(c)
            if not self._validate_drawing_number(cand):
                continue
            x, y = self._text_pos(t, fallback)
            if x > x_cut or y < y_cut:
                continue
            d = ((x - corner_x) ** 2 + (y - corner_y) ** 2) ** 0.5
            if best_dist is None or d < best_dist:
                best_dist = d
                best = cand
        return best

    # 按“编号”>“加工说明”>“左上角编号”优先级提取子图文件名
    def extract_region_filename_by_patterns(self, subdrawing_data: Dict) -> Optional[str]:
        texts = subdrawing_data.get('texts', []) or []
        bounds = subdrawing_data.get('bounds') or {}

        cand = self._extract_inline(texts, self.number_inline_res)
        if cand:
            return self.generate_safe_filename(cand)

        cand = self._extract_near_label(bounds, texts, self.number_label_only_res)
        if cand:
            return self.generate_safe_filename(cand)

        cand = self._extract_inline(texts, self.processing_inline_res)
        if cand:
            return self.generate_safe_filename(cand)

        cand = self._extract_near_label(bounds, texts, self.processing_label_only_res)
        if cand:
            return self.generate_safe_filename(cand)

        # 加工说明锚点（如“加工说明小母位”），编号可能在旁边另一个文字实体：B07/B08
        cand = self._extract_near_label_confirmed(bounds, texts, self.processing_label_anchor_res)
        if cand:
            return self.generate_safe_filename(cand)

        cand = self._extract_from_top_left(bounds, texts)
        if cand:
            return self.generate_safe_filename(cand)

        return None

    # 备用：图纸编号提取逻辑
    def extract_drawing_number_from_region(self, subdrawing_data: Dict) -> Optional[str]:
        bounds = subdrawing_data['bounds']
        texts = subdrawing_data['texts']

        filtered_texts = self._preprocess_texts(texts)
        if not filtered_texts:
            return None

        extraction_methods = [
            self._extract_from_explicit_labels,   # 编号 > 加工说明
            self._extract_from_key_positions,     # 左上角兜底
            self._extract_from_pattern_matching,  # 全局正则兜底
        ]
        for method in extraction_methods:
            result = method(bounds, filtered_texts)
            if result and self._validate_drawing_number(result):
                return result
        return None

    # 文本预处理（过滤无效文本）
    def _preprocess_texts(self, texts: List) -> List:
        content_frequency = Counter([text['content'].strip() for text in texts])
        processed = []
        for text in texts:
            content = text['content'].strip()
            layer = (text.get('layer') or '').lower()
            if not content or len(content) > 30:
                continue
            if layer not in {'0', 'dim', 'dimension'}:
                if any(term in content for term in self.excluded_terms):
                    continue
                if content in self.cad_annotations:
                    continue
                if len(content) <= 2 and content_frequency[content] > 5:
                    continue
                if self._is_dimension_or_value(content):
                    continue
            processed.append(text)
        return processed

    # 判断是否为尺寸/数值文本（过滤用）
    def _is_dimension_or_value(self, content: str) -> bool:
        dimension_patterns = [
            r'^\d+\.?\d*$', r'^\d+\.?\d*[LWTHDRC]$', r'^Φ\d+\.?\d*$',
            r'^R\d+\.?\d*$', r'^\d+\.?\d*°$', r'^\d+\.?\d*mm$',
            r'^M\d+x\d+\.?\d*$', r'^\d+\.?\d*深$', r'^C\d+\.?\d*$'
        ]
        return any(re.match(pattern, content) for pattern in dimension_patterns)

    # 从显式标签提取（优先：编号，其次：加工说明）
    def _extract_from_explicit_labels(self, bounds: Dict, texts: List) -> Optional[str]:
        cand = self._extract_inline(texts, self.number_inline_res)
        if cand:
            return cand
        cand = self._extract_near_label(bounds, texts, self.number_label_only_res)
        if cand:
            return cand

        cand = self._extract_inline(texts, self.processing_inline_res)
        if cand:
            return cand
        cand = self._extract_near_label(bounds, texts, self.processing_label_only_res)
        if cand:
            return cand

        cand = self._extract_near_label_confirmed(bounds, texts, self.processing_label_anchor_res)
        if cand:
            return cand

        return None

    # 从关键位置提取（第三优先级：子图左上角可能存在编号）
    def _extract_from_key_positions(self, bounds: Dict, texts: List) -> Optional[str]:
        return self._extract_from_top_left(bounds, texts)

    # 从正则模式提取
    def _extract_from_pattern_matching(self, bounds: Dict, texts: List) -> Optional[str]:
        """使用正则表达式匹配编号"""
        if not texts:
            return None
        
        for t in texts:
            content = t.get('content', '').strip()
            
            # 按优先级尝试各个正则模式
            for pattern in self.primary_patterns:
                match = re.search(pattern, content)
                if match:
                    cand = match.group(0)
                    if self._validate_drawing_number(cand):
                        return cand
        
        return None

    # 清洗提取到的候选文件名
    def _clean_candidate_after_label(self, s: str) -> str:
        cleaned = (s or '').strip()
        if not cleaned:
            return cleaned
        
        # 先提取括号前的主编号（如果有括号的话）
        # 例如：A07(GH-SHES8-70-P6.40-W4.80) -> A07
        match = re.match(r'^([A-Z0-9\-_]+)(?:\(|（)', cleaned)
        if match:
            cleaned = match.group(1)
        else:
            # 没有括号，按原逻辑处理
            cleaned = cleaned.split()[0]
            cleaned = cleaned.strip('，,。.;；:：)]】）\'"').strip('([【（\'"')
        
        cleaned = re.sub(r'^[\s\-_]+|[\s\-_]+$', '', cleaned)
        return cleaned[:64] if len(cleaned) > 64 else cleaned

    # 验证编号有效性
    def _validate_drawing_number(self, content: str) -> bool:
        if not content or len(content) > 50:  # 增加长度限制以支持带括号的编号
            return False
        # 命中受控字符集则直接认可
        try:
            normalized = self._normalize_confirmed_code(content)
            if normalized and normalized in self._extract_confirmed_codes_from_text(normalized):
                return True
        except Exception:
            pass
        invalid_patterns = [
            r'^[:：].*', r'.*[:：]\s*$', r'^\d+\.\d+$', r'^[0-9]{4,}$',
            r'.*说明.*', r'.*加工.*'
        ]
        if any(re.match(p, content) for p in invalid_patterns):
            return False
        valid_patterns = [
            r'^[A-Z]{1,4}[0-9]*$',                    # A01, SPB10, PS
            r'^[A-Z]+[0-9]*(-[A-Z0-9]+)+$',           # 支持多段横杠：SPB10-40, R-BZ-112-PH-10
            r'^[A-Z]{2,4}$',                          # UP, DIE
            r'^[A-Z0-9]+\([^)]+\)$',                  # 支持括号：A07(CH-SHESS-70-PG.40-W4.80)
        ]
        return any(re.match(p, content) for p in valid_patterns)

    # 生成安全文件名（过滤非法字符）
    def generate_safe_filename(self, name: str) -> str:
        if not name:
            return "未知编号"
        # 先去除括号内容（保留主编号），然后再处理非法字符
        # 例如：A07(CH-SHESS-70-PG.40-W4.80) -> A07
        s = name.strip()
        # 提取括号前的主编号
        match = re.match(r'^([^(]+)', s)
        if match:
            s = match.group(1).strip()
        # 如果没有主编号（整个都是括号），则保留原样
        if not s:
            s = name.strip()
        # 过滤非法字符
        s = re.sub(r'[<>:"/\\|?*]', '_', s).replace(' ', '_')
        s = s.rstrip(' .')
        return s if len(s) <= 80 else s[:80]


class RelaxedCuttingDetector:
    """放宽的切割轮廓检测器"""

    def __init__(self):
        self.cutting_colors = set(range(1, 256))
        self.BYLAYER_COLOR = 256  # ByLayer
        self.geometric_entities = {'LINE', 'CIRCLE', 'ARC', 'LWPOLYLINE', 'POLYLINE', 'SPLINE', 'ELLIPSE'}
        self.exclude_layer_patterns = [
            r'^text$', r'^dimension$', r'^dim$', r'^annotation$',
            r'^center$', r'^construction$', r'^hidden$', r'^dashed$'
        ]

    # 检测区域内切割轮廓
    def detect_cutting_contours_in_region(self, bounds: Dict, entities: List, layer_colors: Dict) -> Dict:
        region_entities = self._get_entities_in_bounds(entities, bounds)
        red = []
        for e in region_entities:
            if self._should_exclude_entity(e):
                continue
            color = e.get('entity_color', self.BYLAYER_COLOR)
            if color == self.BYLAYER_COLOR:
                color = layer_colors.get(e.get('layer', ''), self.BYLAYER_COLOR)
            e['final_color'] = color

            if self._is_geometric_entity_relaxed(e):
                red.append(e)

        analysis = self._generate_cutting_analysis(red)
        ref_idx = self._identify_reference_points(red)
        analysis['reference_points'] = ref_idx
        analysis['reference_count'] = len(ref_idx)

        return analysis

    # 获取区域内实体
    def _get_entities_in_bounds(self, entities: List[Dict], bounds: Dict) -> List[Dict]:
        res = []
        min_x, max_x = bounds['min_x'], bounds['max_x']
        min_y, max_y = bounds['min_y'], bounds['max_y']
        for info in entities:
            center = info.get('center')
            if center is None:
                continue
            cx, cy = center
            if (min_x <= cx <= max_x) and (min_y <= cy <= max_y):
                res.append(info)
        return res

    # 排除不需要的实体
    def _should_exclude_entity(self, entity_info: Dict) -> bool:
        layer = (entity_info.get('layer') or '').lower()
        for pat in self.exclude_layer_patterns:
            if re.match(pat, layer, re.IGNORECASE):
                return True
        return False

    # 放宽的几何实体判断
    def _is_geometric_entity_relaxed(self, entity_info: Dict) -> bool:
        if entity_info.get('type', '') not in self.geometric_entities:
            return False

        color = entity_info.get('final_color', self.BYLAYER_COLOR)
        if color not in self.cutting_colors and color != self.BYLAYER_COLOR:
            return False

        lt = (entity_info.get('linetype', 'ByLayer') or '').lower()
        excluded_linetypes = {'hidden', 'dashed', 'center'}
        return lt not in excluded_linetypes

    # 轮廓类型统计
    def _get_contour_types(self, contours: List[Dict]) -> Dict[str, int]:
        d = defaultdict(int)
        for c in contours:
            d[c.get('type', 'UNKNOWN')] += 1
        return dict(d)

    # 生成切割分析结果
    def _generate_cutting_analysis(self, contours: List[Dict]) -> Dict:
        analysis = {
            'summary': '未检测到切割轮廓',
            'contour_count': 0,
            'total_cutting_length': 0.0,
            'avg_length': 0.0,
            'min_length': 0.0,
            'max_length': 0.0,
            'type_distribution': {}
        }
        if not contours:
            return analysis
        peris = [c.get('perimeter', 0.0) for c in contours if c.get('perimeter', 0.0) > 0.0]
        total_len = sum(peris)
        analysis['contour_count'] = len(contours)
        analysis['total_cutting_length'] = total_len
        analysis['type_distribution'] = self._get_contour_types(contours)
        if peris:
            analysis['avg_length'] = total_len / len(peris)
            analysis['min_length'] = min(peris)
            analysis['max_length'] = max(peris)
            analysis['summary'] = f"检测到{analysis['contour_count']}个切割轮廓，总长度{total_len:.2f}mm"
        else:
            analysis['summary'] = f"检测到{analysis['contour_count']}个切割轮廓，但未获取到有效长度数据"
        return analysis

    # 识别基准点
    def _identify_reference_points(self, red_entities: List[Dict]) -> List[int]:
        circles = [i for i, e in enumerate(red_entities) if e.get('type') == 'CIRCLE']
        if len(circles) < 3:
            return []
        for i in range(len(circles)):
            for j in range(i + 1, len(circles)):
                for k in range(j + 1, len(circles)):
                    idxs = [circles[i], circles[j], circles[k]]
                    ents = [red_entities[t] for t in idxs]
                    peris = [e.get('perimeter', 0.0) for e in ents]
                    if not peris or any(p <= 0 for p in peris):
                        continue
                    if not all(abs(peris[0] - p) < 0.5 for p in peris[1:]):
                        continue
                    centers = [e.get('center', (0.0, 0.0)) for e in ents]
                    if self._is_equal_right_triangle(centers):
                        return idxs
        return []

    # 判断是否为等腰直角三角形（基准点验证）
    def _is_equal_right_triangle(self, centers: List[Tuple[float, float]]) -> bool:
        if len(centers) != 3:
            return False
        d = []
        for a in range(3):
            for b in range(a + 1, 3):
                x1, y1 = centers[a]
                x2, y2 = centers[b]
                d.append(math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2))
        d.sort()
        if len(d) != 3:
            return False
        tol = 0.5
        equal_sides = abs(d[0] - d[1]) < tol
        hyp = d[2]
        return equal_sides and abs(hyp - d[0] * 1.414) < tol


class IntelligentTextProcessor:
    """智能文字处理器（过滤无效文本）"""

    def __init__(self):
        self.noise_patterns = [
            r'^\d+\.?\d*$', r'^[\d\.\-\+\s]+$', r'^\d+\.?\d*[LWTHDRC]$',
            r'^Φ\d+\.?\d*', r'^R\d+\.?\d*', r'^M\d+x',
            r'^\d+\.?\d*°$', r'^\d+\.?\d*mm$', r'^\d+\.?\d*[×xX]\d+\.?\d*',
            r'.*深$', r'.*攻$', r'.*钻$',
        ]
        self.meaningful_keywords = [
            '品名', '编号', '材料', '热处理', '数量',
            '加工说明', '尺寸', '修改', '备注', '规格', '型号'
        ]

    # 处理文本列表（过滤噪音）
    def process_text_list(self, texts: List[Dict]) -> List[Dict]:
        if not texts:
            return []
        counter = Counter([t['content'].strip() for t in texts])
        processed = []
        for t in texts:
            c = t['content'].strip()
            if self._should_keep_text(c, counter):
                processed.append(t)
        return processed

    # 判断是否保留文本
    def _should_keep_text(self, content: str, counter: Counter) -> bool:
        if not content:
            return False
        if len(content) > 50:
            return False
        if any(k in content for k in self.meaningful_keywords):
            return True
        if any(re.match(p, content) for p in self.noise_patterns):
            return False
        if len(content) <= 3 and counter[content] > 8:
            return False
        if len(content) <= 1 and counter[content] > 3:
            return False
        return True


class OptimizedCADBlockAnalyzer:
    """优化的CAD块分析器 + 按特定规则分类保存（修复图框丢失）"""

    def __init__(self):
        self.all_texts = []
        self.all_entities = []
        self.frame_blocks = []  # 存储图框块实体
        self.sub_drawings = {}
        self.layer_colors = {}
        self.text_processor = IntelligentTextProcessor()
        self.cutting_detector = RelaxedCuttingDetector()
        self.number_extractor = ProfessionalDrawingNumberExtractor()
        self.doc = None
        self.msp = None
        self.classify_map = None
        self.source_path: Optional[str] = None

    # 分析CAD文件（提取子图）
    def analyze_cad_file(self, file_path: str) -> Dict:
        logger.debug(f"开始分析CAD文件: {file_path}")
        try:
            doc = ezdxf.readfile(file_path)
            msp = doc.modelspace()
            self.doc = doc
            self.msp = msp
            self.source_path = file_path

            self._extract_layer_colors(doc)
            self._extract_all_texts(msp)
            self._extract_all_entities(msp)
            self._identify_frame_blocks(msp)  # 识别图框块
            self._create_subdrawing_regions()
            self._assign_texts_to_regions()
            self._analyze_cutting_contours_for_regions()

            logger.debug(f"分析完成，识别出 {len(self.sub_drawings)} 个子图区域")
            return self.sub_drawings
        except Exception as e:
            logger.debug(f"文件分析失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return {}

    # 安全获取SPLINE点
    def _safe_spline_points(self, entity):
        pts = []
        try:
            if hasattr(entity, 'control_points') and entity.control_points:
                for p in entity.control_points:
                    try:
                        pts.append((float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0))
                    except Exception:
                        pts.append((float(p.x), float(p.y), float(getattr(p, 'z', 0.0))))
            if not pts and hasattr(entity, 'fit_points') and entity.fit_points:
                for p in entity.fit_points:
                    pts.append((float(p.x), float(p.y), float(getattr(p, 'z', 0.0))))
        except Exception:
            pass
        return pts

    # 判断点是否在区域内
    def _point_in_bounds(self, pt, bounds: Dict) -> bool:
        if pt is None:
            return False
        x, y = pt
        return (bounds['min_x'] <= x <= bounds['max_x']) and (bounds['min_y'] <= y <= bounds['max_y'])

    # 获取椭圆起止点
    def _ellipse_start_end_points(self, entity) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
        try:
            tool = entity.construction_tool()
            sp = (float(tool.start_point.x), float(tool.start_point.y))
            ep = (float(tool.end_point.x), float(tool.end_point.y))
            return sp, ep
        except Exception:
            pass
        return None, None

    # 判断椭圆是否在区域内
    def _ellipse_hits_region_by_endpoints(self, entity, bounds: Dict) -> bool:
        sp, ep = self._ellipse_start_end_points(entity)
        return self._point_in_bounds(sp, bounds) or self._point_in_bounds(ep, bounds)

    # 计算实体边界框（用于筛选/删除）
    def _compute_entity_bounds(self, e, blocks_doc) -> Optional[Dict]:
        try:
            entity_type = e.dxftype()
            dim_pad = 150.0  # 尺寸/引线边界外扩，避免标注文字/箭头被裁掉
            dim_min_box = 200.0  # bbox 失败时给尺寸/引线一个兜底范围

            if entity_type == 'LINE':
                start, end = e.dxf.start, e.dxf.end
                return {
                    'min_x': min(start.x, end.x),
                    'max_x': max(start.x, end.x),
                    'min_y': min(start.y, end.y),
                    'max_y': max(start.y, end.y)
                }

            elif entity_type in ('CIRCLE', 'ARC'):
                center = e.dxf.center
                radius = float(e.dxf.radius)
                return {
                    'min_x': center.x - radius,
                    'max_x': center.x + radius,
                    'min_y': center.y - radius,
                    'max_y': center.y + radius
                }

            elif entity_type in ('LWPOLYLINE', 'POLYLINE'):
                try:
                    pts = e.get_points(format='xy')
                    if pts:
                        xs, ys = zip(*pts)
                        return {
                            'min_x': min(xs),
                            'max_x': max(xs),
                            'min_y': min(ys),
                            'max_y': max(ys)
                        }
                except Exception:
                    return None

            elif entity_type == 'ELLIPSE':
                center = e.dxf.center
                major_axis = e.dxf.major_axis
                ratio = float(getattr(e.dxf, 'ratio', 0.5) or 0.5)
                a = (major_axis.x ** 2 + major_axis.y ** 2) ** 0.5
                b = a * ratio
                return {
                    'min_x': center.x - a,
                    'max_x': center.x + a,
                    'min_y': center.y - b,
                    'max_y': center.y + b
                }

            elif entity_type in ('DIMENSION', 'HATCH', 'SOLID', 'MTEXT', 'LEADER', 'MLEADER'):
                try:
                    bb = e.bbox()
                    if bb and getattr(bb, 'has_data', False):
                        min_v, max_v = bb.extmin, bb.extmax
                        min_x = float(min_v.x)
                        max_x = float(max_v.x)
                        min_y = float(min_v.y)
                        max_y = float(max_v.y)
                        if entity_type in ('DIMENSION', 'LEADER', 'MLEADER'):
                            min_x -= dim_pad
                            max_x += dim_pad
                            min_y -= dim_pad
                            max_y += dim_pad
                        return {
                            'min_x': min_x,
                            'max_x': max_x,
                            'min_y': min_y,
                            'max_y': max_y
                        }
                except Exception:
                    pass
                if entity_type in ('DIMENSION', 'LEADER', 'MLEADER'):
                    c = self._calculate_entity_center(e)
                    if c:
                        cx, cy = c
                        return {
                            'min_x': cx - dim_min_box,
                            'max_x': cx + dim_min_box,
                            'min_y': cy - dim_min_box,
                            'max_y': cy + dim_min_box
                        }

            elif entity_type in ('TEXT', 'ATTRIB', 'ATTDEF'):
                pos = getattr(e.dxf, 'insert', None) or getattr(e.dxf, 'pos', None)
                if not pos:
                    return None
                height = float(getattr(e.dxf, 'height', 2.5) or 2.5)
                width = height * 5
                return {
                    'min_x': pos.x,
                    'max_x': pos.x + width,
                    'min_y': pos.y,
                    'max_y': pos.y + height
                }

            elif entity_type == 'INSERT':
                block_bounds = self._calculate_block_bounds(blocks_doc.get(e.dxf.name), e)
                if block_bounds:
                    return block_bounds
                ins = getattr(e.dxf, 'insert', None)
                if ins:
                    pad = 10.0
                    return {
                        'min_x': ins.x - pad, 'max_x': ins.x + pad,
                        'min_y': ins.y - pad, 'max_y': ins.y + pad
                    }

        except Exception:
            return None

    # 生成子图文件名（编号）
    def resolve_region_name(self, region_id: str, region: Dict) -> str:
        fname = self.number_extractor.extract_region_filename_by_patterns(region)
        if not fname:
            drawing_number = self.number_extractor.extract_drawing_number_from_region(region)
            if drawing_number:
                fname = self.number_extractor.generate_safe_filename(drawing_number)
        if not fname:
            # 识别失败，输出调试信息
            texts = region.get('texts', [])
            text_contents = [t.get('content', '') for t in texts[:20]]  # 增加到前20个文本
            logger.warning(f"[识别失败] {region_id} 未识别到编号")
            logger.warning(f"[识别失败] 文本内容（前20个）: {text_contents}")
            fname = region_id
        return fname

    # 提取品名（简单规则：识别“品名”标签及下一段文本）
    def extract_part_name(self, region: Dict) -> Optional[str]:
        texts = region.get('texts', []) or []
        label_re = re.compile(r'^\s*品\s*名\s*[:：]?\s*(.*)$', re.IGNORECASE)
        for i, t in enumerate(texts):
            c = (t.get('content') or '').strip()
            if not c:
                continue
            m = label_re.match(c)
            if m:
                inline_val = (m.group(1) or '').strip()
                if inline_val:
                    return inline_val
                # 下一条非空文本
                for j in range(i + 1, min(i + 6, len(texts))):
                    nxt = (texts[j].get('content') or '').strip()
                    if nxt and not label_re.match(nxt):
                        return nxt
        return None

    # 提取图层颜色
    def _extract_layer_colors(self, doc):
        logger.debug("正在提取图层颜色信息...")
        try:
            for layer in doc.layers:
                self.layer_colors[layer.dxf.name] = getattr(layer.dxf, 'color', 7)
            logger.debug(f"图层颜色信息提取完成: {len(self.layer_colors)} 个图层")
        except Exception as e:
            logger.debug(f"图层颜色提取失败: {e}")

    # 提取几何实体
    def _extract_all_entities(self, msp):
        logger.debug("正在提取几何实体...")
        geometric_types = ['LINE', 'CIRCLE', 'ARC', 'LWPOLYLINE', 'POLYLINE', 'ELLIPSE', 'SPLINE',
                           'DIMENSION', 'HATCH', 'SOLID', 'LEADER', 'MLEADER']
        for entity_type in geometric_types:
            try:
                for entity in msp.query(entity_type):
                    info = self._process_geometric_entity(entity)
                    if info:
                        self.all_entities.append(info)
            except Exception:
                continue
        logger.debug(f"几何实体提取完成: {len(self.all_entities)} 个实体")

    # 处理几何实体信息
    def _process_geometric_entity(self, entity) -> Optional[Dict]:
        try:
            t = entity.dxftype()
            layer = getattr(entity.dxf, 'layer', '0')
            color = getattr(entity.dxf, 'color', 256)
            handle = getattr(entity.dxf, 'handle', 'N/A')
            linetype = getattr(entity.dxf, 'linetype', 'ByLayer')
            center = self._calculate_entity_center(entity)
            if center is None:
                return None
            perimeter = self._calculate_entity_perimeter(entity)
            return {
                'type': t, 'layer': layer, 'entity_color': color, 'handle': handle,
                'linetype': linetype, 'center': center, 'perimeter': perimeter
            }
        except Exception:
            return None

    # 计算实体中心
    def _calculate_entity_center(self, entity):
        try:
            t = entity.dxftype()
            if t in ['CIRCLE', 'ARC']:
                c = entity.dxf.center
                return (round(c.x, 2), round(c.y, 2))
            elif t == 'LINE':
                s, e = entity.dxf.start, entity.dxf.end
                return (round((s.x + e.x) / 2, 2), round((s.y + e.y) / 2, 2))
            elif t in ['LWPOLYLINE', 'POLYLINE']:
                pts = entity.get_points(format='xy')
                if pts:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    return (round(sum(xs) / len(xs), 2), round(sum(ys) / len(ys), 2))
            elif t == 'ELLIPSE':
                c = entity.dxf.center
                return (round(c.x, 2), round(c.y, 2))
            elif t == 'SPLINE':
                pts = self._safe_spline_points(entity)
                if len(pts) >= 2:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    return (round(sum(xs) / len(xs), 2), round(sum(ys) / len(ys), 2))
            elif t in ['TEXT', 'ATTRIB', 'ATTDEF']:
                # 文字实体：使用 insert 或 position 点
                if hasattr(entity.dxf, 'insert'):
                    p = entity.dxf.insert
                    return (round(p.x, 2), round(p.y, 2))
                elif hasattr(entity.dxf, 'position'):
                    p = entity.dxf.position
                    return (round(p.x, 2), round(p.y, 2))
            elif t == 'MTEXT':
                # 多行文字：使用 insert 点
                p = entity.dxf.insert
                return (round(p.x, 2), round(p.y, 2))
            elif t in ['DIMENSION', 'LEADER', 'MLEADER']:
                # 先尝试 bbox
                bb = getattr(entity, "bbox", None)
                if callable(bb):
                    box = bb()
                    if box and getattr(box, "has_data", False):
                        min_v, max_v = box.extmin, box.extmax
                        return (round((min_v.x + max_v.x) / 2, 2), round((min_v.y + max_v.y) / 2, 2))
                # 再尝试关键点平均
                pts = []
                for attr in ['defpoint', 'defpoint2', 'defpoint3', 'dimline_point', 'text_midpoint', 'insert']:
                    p = getattr(entity.dxf, attr, None)
                    if p:
                        pts.append((p.x, p.y))
                if pts:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    return (round(sum(xs) / len(xs), 2), round(sum(ys) / len(ys), 2))
            # 兜底：使用包围盒中心（DIMENSION/LEADER/MLEADER 等）
            bb = getattr(entity, "bbox", None)
            if callable(bb):
                box = bb()
                if box and getattr(box, "has_data", False):
                    min_v, max_v = box.extmin, box.extmax
                    return (round((min_v.x + max_v.x) / 2, 2), round((min_v.y + max_v.y) / 2, 2))
        except Exception:
            pass
        return None

    # 计算实体周长
    def _calculate_entity_perimeter(self, entity):
        try:
            t = entity.dxftype()
            if t == 'CIRCLE':
                r = entity.dxf.radius
                return round(2 * math.pi * r, 2)
            elif t == 'ARC':
                r = entity.dxf.radius
                sa = math.radians(entity.dxf.start_angle)
                ea = math.radians(entity.dxf.end_angle)
                if ea < sa:
                    ea += 2 * math.pi
                return round(r * (ea - sa), 2)
            elif t == 'LINE':
                s, e = entity.dxf.start, entity.dxf.end
                return round(math.sqrt((e.x - s.x) ** 2 + (e.y - s.y) ** 2), 2)
            elif t in ['LWPOLYLINE', 'POLYLINE']:
                return round(self._calculate_polyline_length(entity), 2)
            # 兜底：使用包围盒估算周长（DIMENSION/LEADER/MLEADER 等）
            bb = getattr(entity, "bbox", None)
            if callable(bb):
                box = bb()
                if box and getattr(box, "has_data", False):
                    min_v, max_v = box.extmin, box.extmax
                    w = max_v.x - min_v.x
                    h = max_v.y - min_v.y
                    return round(2 * (w + h), 2)
        except Exception:
            pass
        return 0.0

    # 计算多段线长度
    def _calculate_polyline_length(self, polyline):
        try:
            pts = polyline.get_points(format='xy')
            if len(pts) < 2:
                return 0.0
            total = 0.0
            for i in range(len(pts) - 1):
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                total += math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            if getattr(polyline, 'closed', False) and len(pts) > 2:
                x1, y1 = pts[-1]
                x2, y2 = pts[0]
                total += math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            return total
        except Exception:
            return 0.0

    # 提取文本实体
    def _extract_all_texts(self, msp):
        logger.debug("正在提取文字实体...")
        for t in ['TEXT', 'MTEXT', 'ATTRIB', 'ATTDEF', 'DIMENSION']:
            try:
                for e in msp.query(t):
                    info = self._process_text_entity(e)
                    if info:
                        self.all_texts.append(info)
            except Exception:
                continue
        logger.debug(f"文字提取完成: {len(self.all_texts)} 个实体")

    # 处理文本实体信息
    def _process_text_entity(self, entity) -> Optional[Dict]:
        try:
            content = self._extract_text_content(entity)
            if not content:
                return None
            position = self._get_text_position(entity)
            if not position:
                return None
            return {
                'content': self._clean_text_content(content),
                'position': position,
                'entity_type': entity.dxftype(),
                'layer': getattr(entity.dxf, 'layer', '').strip()
            }
        except Exception:
            return None

    # 提取文本内容
    def _extract_text_content(self, entity) -> Optional[str]:
        t = entity.dxftype()
        try:
            if t == 'TEXT':
                return entity.dxf.text
            elif t == 'MTEXT':
                if hasattr(entity, 'get_text'):
                    return entity.get_text()
                elif hasattr(entity, 'plain_text'):
                    return entity.plain_text()
                return getattr(entity.dxf, 'text', None)
            elif t in ['ATTRIB', 'ATTDEF']:
                return entity.dxf.text
            elif t == 'DIMENSION':
                if hasattr(entity, 'get_measurement'):
                    return str(entity.get_measurement())
                return getattr(entity.dxf, 'text', None)
        except Exception:
            pass
        return None

    # 获取文本位置
    def _get_text_position(self, entity) -> Optional[Tuple[float, float]]:
        try:
            if hasattr(entity.dxf, 'insert'):
                p = entity.dxf.insert
                return (float(p.x), float(p.y))
            elif hasattr(entity.dxf, 'position'):
                p = entity.dxf.position
                return (float(p.x), float(p.y))
        except Exception:
            pass
        return None

    # 清洗文本内容
    def _clean_text_content(self, content: str) -> str:
        if not content:
            return ""
        content = re.sub(r'\{\\[^}]*\}', '', content)
        content = re.sub(r'\\[A-Za-z][^;]*;', '', content)
        repl = {'%%c': 'Φ', '%%C': 'Φ', '%%d': '°', '%%D': '°', '%%p': '±', '%%P': '±'}
        for k, v in repl.items():
            content = content.replace(k, v)
        return re.sub(r'\s+', ' ', content).strip()

    # 识别框架块（图框）
    def _identify_frame_blocks(self, msp):
        logger.debug("正在识别框架块...")
        for insert in msp.query('INSERT'):
            try:
                name = insert.dxf.name
                ins_pt = insert.dxf.insert
                # if name.startswith('*u'):
                #     continue
                block_def = insert.doc.blocks.get(name)
                if not block_def:
                    continue
                bounds = self._calculate_block_bounds(block_def, insert)
                if not bounds or not self._is_valid_frame_block(bounds):
                    continue
                self.frame_blocks.append({
                    'block_name': name,
                    'insert_point': (ins_pt.x, ins_pt.y),
                    'bounds': bounds,
                    'insert_entity': insert  # 保存图框块实体本身
                })
            except Exception:
                continue
        logger.debug(f"初步识别框架块: {len(self.frame_blocks)} 个")
        self._filter_frame_blocks_by_name_frequency()
        logger.debug(f"框架块识别完成: {len(self.frame_blocks)} 个")

    # 过滤框架块（保留主要类型）
    def _filter_frame_blocks_by_name_frequency(self):
        """改为只去重重叠的图框，不按名称过滤"""
        if len(self.frame_blocks) <= 1:
            return
        
        # 按面积从大到小排序
        self.frame_blocks.sort(key=lambda x: (x['bounds']['width'] * x['bounds']['height']), 
                            reverse=True)
        
        unique = [self.frame_blocks[0]]
        
        # 只去除空间重叠的图框，保留所有不同类型
        for candidate in self.frame_blocks[1:]:
            c_bounds = candidate['bounds']
            overlap = False
            
            for existing in unique:
                e_bounds = existing['bounds']
                # # 检查是否重叠
                # if (c_bounds['max_x'] > e_bounds['min_x'] and
                #     c_bounds['min_x'] < e_bounds['max_x'] and
                #     c_bounds['max_y'] > e_bounds['min_y'] and
                #     c_bounds['min_y'] < e_bounds['max_y']):
                #     overlap = True
                #     break

                # 检查是否有空间交集
                if (c_bounds['max_x'] > e_bounds['min_x'] and
                    c_bounds['min_x'] < e_bounds['max_x'] and
                    c_bounds['max_y'] > e_bounds['min_y'] and
                    c_bounds['min_y'] < e_bounds['max_y']):

                    # 计算重叠区域的边界
                    overlap_x_min = max(c_bounds['min_x'], e_bounds['min_x'])
                    overlap_x_max = min(c_bounds['max_x'], e_bounds['max_x'])
                    overlap_y_min = max(c_bounds['min_y'], e_bounds['min_y'])
                    overlap_y_max = min(c_bounds['max_y'], e_bounds['max_y'])

                    # 计算重叠面积
                    overlap_area = (overlap_x_max - overlap_x_min) * (overlap_y_max - overlap_y_min)

                    # 计算候选图框的面积
                    candidate_area = c_bounds['width'] * c_bounds['height']

                    # 计算重叠比例（重叠面积占候选图框面积的比例）
                    overlap_ratio = overlap_area / candidate_area if candidate_area > 0 else 0

                    # 只有重叠比例超过阈值才认为是真正的重叠
                    OVERLAP_THRESHOLD = 0.2  # 阈值：50%，可根据需要调整
                    if overlap_ratio > OVERLAP_THRESHOLD:
                        overlap = True
                        break
            
            if not overlap:
                unique.append(candidate)
        
        orig = len(self.frame_blocks)
        self.frame_blocks = unique
        logger.debug(f"去重后：原有 {orig} 个图框，保留 {len(self.frame_blocks)} 个不重叠的图框")


    # 计算块边界（用于图框检测）
    def _calculate_block_bounds(self, block_def, insert) -> Optional[Dict]:
        try:
            min_x = min_y = float('inf')
            max_x = max_y = float('-inf')
            has_entities = False
            for e in block_def:
                eb = self._get_entity_bounds(e)
                if eb:
                    has_entities = True
                    min_x = min(min_x, eb['min_x'])
                    max_x = max(max_x, eb['max_x'])
                    min_y = min(min_y, eb['min_y'])
                    max_y = max(max_y, eb['max_y'])
            if not has_entities:
                return None
            ip = insert.dxf.insert
            sx = getattr(insert.dxf, 'xscale', 1.0)
            sy = getattr(insert.dxf, 'yscale', 1.0)
            return {
                'min_x': ip.x + min_x * sx,
                'max_x': ip.x + max_x * sx,
                'min_y': ip.y + min_y * sy,
                'max_y': ip.y + max_y * sy,
                'width': (max_x - min_x) * abs(sx),
                'height': (max_y - min_y) * abs(sy)
            }
        except Exception:
            return None

    # 获取实体边界
    def _get_entity_bounds(self, entity) -> Optional[Dict]:
        try:
            t = entity.dxftype()
            if t == 'LINE':
                s, e = entity.dxf.start, entity.dxf.end
                return {'min_x': min(s.x, e.x), 'max_x': max(s.x, e.x),
                        'min_y': min(s.y, e.y), 'max_y': max(s.y, e.y)}
            elif t in ['CIRCLE', 'ARC']:
                c = entity.dxf.center
                r = entity.dxf.radius
                return {'min_x': c.x - r, 'max_x': c.x + r, 'min_y': c.y - r, 'max_y': c.y + r}
            elif t in ['LWPOLYLINE', 'POLYLINE']:
                pts = entity.get_points(format='xy')
                if pts:
                    xs, ys = zip(*pts)
                    return {'min_x': min(xs), 'max_x': max(xs), 'min_y': min(ys), 'max_y': max(ys)}
        except Exception:
            pass
        return None

    # 判断是否为有效框架块
    def _is_valid_frame_block(self, bounds: Dict) -> bool:
        min_size = 120
        return bounds['width'] > min_size or bounds['height'] > min_size

    # 创建子图区域
    def _create_subdrawing_regions(self):
        self.frame_blocks.sort(key=self._get_spatial_sort_key)
        for i, fb in enumerate(self.frame_blocks):
            rid = f"subdrawing_{i + 1:03d}"
            self.sub_drawings[rid] = {
                'frame_block': fb,
                'bounds': fb['bounds'],
                'texts': [],
                'cutting_analysis': {}
            }

    # 空间排序键（用于子图排序）
    def _get_spatial_sort_key(self, frame_block):
        b = frame_block['bounds']
        tol = 100
        return (-round(b['min_y'] / tol), round(b['min_x'] / tol))

    # 分配文本到子图区域
    def _assign_texts_to_regions(self):
        logger.debug("正在分配文字到区域...")
        for text in self.all_texts:
            x, y = text['position']
            assigned = False
            for rid, r in self.sub_drawings.items():
                b = r['bounds']
                if b['min_x'] <= x <= b['max_x'] and b['min_y'] <= y <= b['max_y']:
                    r['texts'].append(text)
                    assigned = True
                    break
            if not assigned:
                cr = self._find_closest_region((x, y))
                if cr:
                    self.sub_drawings[cr]['texts'].append(text)
        for rid, r in self.sub_drawings.items():
            before = len(r['texts'])
            r['texts'] = self.text_processor.process_text_list(r['texts'])
            after = len(r['texts'])
            logger.debug(f"区域 {rid}: 处理前 {before} 个文字，处理后 {after} 个文字")

    # 分析各区域切割轮廓
    def _analyze_cutting_contours_for_regions(self):
        logger.debug("正在分析各区域的切割轮廓...")
        for rid, r in self.sub_drawings.items():
            b = r['bounds']
            cutting = self.cutting_detector.detect_cutting_contours_in_region(b, self.all_entities, self.layer_colors)
            r['cutting_analysis'] = cutting
            logger.debug(
                f"区域 {rid}: 检测到 {cutting['contour_count']} 个切割轮廓，总长度 {cutting['total_cutting_length']:.2f}mm")

    # 找到最近的子图区域
    def _find_closest_region(self, pos: Tuple[float, float]) -> Optional[str]:
        x, y = pos
        md = float('inf')
        cid = None
        for rid, r in self.sub_drawings.items():
            b = r['bounds']
            cx = (b['min_x'] + b['max_x']) / 2
            cy = (b['min_y'] + b['max_y']) / 2
            d = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            if d < md:
                md = d
                cid = rid
        return cid


class CADAnalysisSystem:
    """CAD分析系统主类（按特定规则分类保存）"""

    def __init__(self):
        self.analyzer = OptimizedCADBlockAnalyzer()
        self.number_extractor = ProfessionalDrawingNumberExtractor()

    # 分析文件并导出子图DXF
    def analyze_file(self, input_file: str, output_dir: Optional[str] = None):
        if not os.path.exists(input_file):
            logger.debug(f"错误：文件不存在 - {input_file}")
            return
        if not input_file.lower().endswith('.dxf'):
            logger.debug("错误：仅支持DXF格式文件，请先转换DWG为DXF")
            return

        # 分析CAD文件提取子图
        results = self.analyzer.analyze_cad_file(input_file)
        if not results:
            logger.debug("未提取到任何子图信息")
            return

    # 计算两个边界框的重叠面积
    def _calculate_overlap_area(self, bounds1: Dict, bounds2: Dict) -> float:
        """计算两个边界框的重叠面积"""
        try:
            # 计算重叠区域
            overlap_min_x = max(bounds1['min_x'], bounds2['min_x'])
            overlap_max_x = min(bounds1['max_x'], bounds2['max_x'])
            overlap_min_y = max(bounds1['min_y'], bounds2['min_y'])
            overlap_max_y = min(bounds1['max_y'], bounds2['max_y'])
            
            # 如果没有重叠，返回 0
            if overlap_min_x >= overlap_max_x or overlap_min_y >= overlap_max_y:
                return 0.0
            
            # 计算重叠面积
            overlap_area = (overlap_max_x - overlap_min_x) * (overlap_max_y - overlap_min_y)
            return overlap_area
        except Exception:
            return 0.0

    # 平移单个实体
    def _translate_entity(self, entity, dx: float, dy: float):
        """平移单个CAD实体"""
        try:
            # 优先使用 ezdxf 的 transform 方法（最可靠）
            # 这个方法可以正确处理所有实体类型，包括复杂的标注
            try:
                from ezdxf.math import Matrix44
                # 创建平移矩阵
                m = Matrix44.translate(dx, dy, 0)
                entity.transform(m)
                return  # 成功则直接返回
            except Exception:
                # 如果 transform 不可用，使用手动平移
                pass
            
            # 手动平移（兜底方案）
            entity_type = entity.dxftype()
            
            if entity_type == 'LINE':
                start = entity.dxf.start
                end = entity.dxf.end
                entity.dxf.start = (start.x + dx, start.y + dy, start.z if hasattr(start, 'z') else 0)
                entity.dxf.end = (end.x + dx, end.y + dy, end.z if hasattr(end, 'z') else 0)
            
            elif entity_type in ['CIRCLE', 'ARC']:
                center = entity.dxf.center
                entity.dxf.center = (center.x + dx, center.y + dy, center.z if hasattr(center, 'z') else 0)
            
            elif entity_type == 'ELLIPSE':
                center = entity.dxf.center
                entity.dxf.center = (center.x + dx, center.y + dy, center.z if hasattr(center, 'z') else 0)
            
            elif entity_type in ['TEXT', 'ATTRIB', 'ATTDEF']:
                if hasattr(entity.dxf, 'insert'):
                    insert = entity.dxf.insert
                    entity.dxf.insert = (insert.x + dx, insert.y + dy, insert.z if hasattr(insert, 'z') else 0)
                elif hasattr(entity.dxf, 'position'):
                    pos = entity.dxf.position
                    entity.dxf.position = (pos.x + dx, pos.y + dy, pos.z if hasattr(pos, 'z') else 0)
            
            elif entity_type == 'MTEXT':
                insert = entity.dxf.insert
                entity.dxf.insert = (insert.x + dx, insert.y + dy, insert.z if hasattr(insert, 'z') else 0)
            
            elif entity_type in ['LWPOLYLINE', 'POLYLINE']:
                # 平移所有顶点
                points = list(entity.get_points())
                new_points = []
                for pt in points:
                    if len(pt) >= 2:
                        new_pt = (pt[0] + dx, pt[1] + dy) + pt[2:]
                        new_points.append(new_pt)
                if new_points:
                    entity.set_points(new_points)
            
            elif entity_type == 'SPLINE':
                # 平移控制点
                if hasattr(entity, 'control_points') and entity.control_points:
                    new_control_points = []
                    for pt in entity.control_points:
                        try:
                            if hasattr(pt, 'x'):
                                new_control_points.append((pt.x + dx, pt.y + dy, getattr(pt, 'z', 0)))
                            else:
                                new_control_points.append((pt[0] + dx, pt[1] + dy, pt[2] if len(pt) > 2 else 0))
                        except Exception:
                            new_control_points.append(pt)
                    entity.control_points = new_control_points
                
                # 平移拟合点
                if hasattr(entity, 'fit_points') and entity.fit_points:
                    new_fit_points = []
                    for pt in entity.fit_points:
                        new_fit_points.append((pt.x + dx, pt.y + dy, getattr(pt, 'z', 0)))
                    entity.fit_points = new_fit_points
            
            elif entity_type == 'INSERT':  # 块引用
                insert = entity.dxf.insert
                entity.dxf.insert = (insert.x + dx, insert.y + dy, insert.z if hasattr(insert, 'z') else 0)
            
            elif entity_type == 'DIMENSION':
                # 标注实体：平移所有定义点
                dimension_attrs = [
                    'defpoint', 'defpoint2', 'defpoint3', 'defpoint4',
                    'text_midpoint', 'dimline_point', 'insert'
                ]
                for attr in dimension_attrs:
                    if hasattr(entity.dxf, attr):
                        pt = getattr(entity.dxf, attr)
                        if pt is not None:
                            try:
                                setattr(entity.dxf, attr, (pt.x + dx, pt.y + dy, pt.z if hasattr(pt, 'z') else 0))
                            except Exception:
                                pass
            
            elif entity_type in ['LEADER', 'MLEADER']:
                # 平移引线的顶点
                if hasattr(entity, 'vertices'):
                    new_vertices = []
                    for pt in entity.vertices:
                        new_vertices.append((pt[0] + dx, pt[1] + dy, pt[2] if len(pt) > 2 else 0))
                    entity.vertices = new_vertices
            
            elif entity_type == 'HATCH':
                # 填充图案需要特殊处理
                # 使用 transform 方法更可靠
                pass
            
            elif entity_type == 'SOLID':
                # 平移实体填充的顶点
                for i in range(4):
                    attr = f'vtx{i}'
                    if hasattr(entity.dxf, attr):
                        pt = getattr(entity.dxf, attr)
                        if pt:
                            setattr(entity.dxf, attr, (pt.x + dx, pt.y + dy, pt.z if hasattr(pt, 'z') else 0))
            
        except Exception as e:
            logger.debug(f"平移实体失败 ({entity.dxftype() if hasattr(entity, 'dxftype') else 'unknown'}): {e}")

    # 仅导出匹配目标名称的子图（就地删除其他实体）
    def export_matching_regions(self, target_names: List[str], output_path: str, pad: float = 0.0, 
                               horizontal_spacing: float = 50.0, align_to_origin: bool = True) -> Tuple[bool, str]:
        if not self.analyzer.sub_drawings or not self.analyzer.source_path:
            return False, "未提取到子图或未加载源文件"

        names_raw = [n.strip() for n in target_names if n.strip()]
        if not names_raw:
            return False, "目标名称为空"
        names = [n.upper() for n in names_raw]

        def tokens(s: str):
            return [t for t in re.split(r'[^A-Za-z0-9]+', s.upper()) if t]

        def norm_text(s: str) -> str:
            s = (s or "").strip()
            if not s:
                return ""
            # 去除空白与常见分隔符，便于“品名”模糊匹配
            s = re.sub(r'\([^)]*\)', '', s)  # 去除括号及其内容
            s = re.sub(r'[\s\-_，,。.;；:：/\\|－–—‐]+', '', s)
            return s.upper()

        # 预先标准化所有用户输入（用于标准化匹配）
        names_normalized = [norm_text(n) for n in names_raw]
        
        logger.info(f"[匹配调试] 用户输入: {names_raw}")
        logger.info(f"[匹配调试] 标准化后: {names_normalized}")
        logger.info(f"[匹配调试] 图纸中共有 {len(self.analyzer.sub_drawings)} 个子图")

        exact_matches = []
        fuzzy_matches = []
        for region_id, region in self.analyzer.sub_drawings.items():
            fname = self.analyzer.resolve_region_name(region_id, region)
            region['resolved_name'] = fname
            fname_upper = fname.upper()
            fname_tokens = tokens(fname_upper)
            fname_normalized = norm_text(fname)  # 标准化子图名称
            
            # 只在调试模式下输出详细信息
            if fname_normalized in names_normalized:
                logger.debug(f"[匹配调试] 子图 {region_id}: 原名='{fname}', 标准化='{fname_normalized}' - 准备匹配")
            
            # 1. 完全精准匹配（原样比较）
            if fname_upper in names:
                logger.info(f"[匹配成功] 完全精准匹配: {fname}")
                exact_matches.append((region_id, region))
                continue
            
            # 2. 标准化精准匹配（去除空格、横杠等分隔符后比较）
            if fname_normalized in names_normalized:
                logger.info(f"[匹配成功] 标准化精准匹配: {fname} → {fname_normalized}")
                exact_matches.append((region_id, region))
                continue
            # 品名匹配兜底
            part_name = self.analyzer.extract_part_name(region)
            if part_name:
                pn_upper = part_name.upper()
                pn_norm = norm_text(part_name)
                if any(n == pn_upper for n in names) or any(n in pn_upper for n in names):
                    fuzzy_matches.append((region_id, region))
                    continue
                # 额外：标准化后再比一次（应对空格/下划线/冒号等差异）
                if pn_norm and any(norm_text(n) == pn_norm or norm_text(n) in pn_norm for n in names_raw):
                    fuzzy_matches.append((region_id, region))
                    continue
        matches = exact_matches if exact_matches else fuzzy_matches
        if not matches:
            logger.warning(f"[匹配失败] 未匹配到图纸信息")
            logger.warning(f"[匹配失败] 用户输入: {names_raw}, 标准化: {names_normalized}")
            
            # 显示图纸中所有子图的原始名称和标准化名称
            drawing_names = []
            for rid, r in self.analyzer.sub_drawings.items():
                original = self.analyzer.resolve_region_name(rid, r)
                normalized = norm_text(original)
                drawing_names.append(f"{original}→{normalized}")
            
            logger.warning(f"[匹配失败] 图纸中共有 {len(drawing_names)} 个子图")
            
            # 尝试找到相似的子图名称（包含用户输入的部分字符）
            similar_drawings = []
            for name_pair in drawing_names:
                original = name_pair.split('→')[0]
                normalized = name_pair.split('→')[1]
                # 检查是否包含用户输入的任何部分
                for user_input in names_raw:
                    user_upper = user_input.upper()
                    user_norm = norm_text(user_input)
                    # 分割用户输入，检查每个部分
                    user_parts = [p for p in re.split(r'[-_\s]+', user_upper) if len(p) > 1]
                    original_upper = original.upper()
                    
                    # 检查是否有任何部分匹配
                    matched = False
                    for part in user_parts:
                        if part in original_upper or part in normalized:
                            matched = True
                            break
                    
                    if matched and name_pair not in similar_drawings:
                        similar_drawings.append(name_pair)
                        break
            
            if similar_drawings:
                # 去重并限制数量
                unique_similar = []
                seen = set()
                for item in similar_drawings:
                    if item not in seen:
                        unique_similar.append(item)
                        seen.add(item)
                        if len(unique_similar) >= 30:  # 增加到30个
                            break
                
                logger.warning(f"[匹配失败] 可能相关的子图（前30个，已去重）: {unique_similar}")
                
                # 额外：专门搜索用户输入的完整标准化名称
                for user_norm in names_normalized:
                    exact_found = False
                    for name_pair in drawing_names:
                        if name_pair.endswith(f"→{user_norm}"):
                            logger.warning(f"[匹配失败] 找到完全匹配的标准化名称: {name_pair}")
                            exact_found = True
                    if not exact_found:
                        logger.warning(f"[匹配失败] 未找到标准化名称为 '{user_norm}' 的子图")
            else:
                logger.warning(f"[匹配失败] 未找到相似的子图名称")
                logger.warning(f"[匹配失败] 前20个子图: {drawing_names[:20]}")
            
            return False, "未匹配到图纸信息"

        # 按用户传入的 target_names 顺序排序匹配结果
        # 创建一个顺序映射
        name_order = {n.upper(): i for i, n in enumerate(names_raw)}
        
        def get_match_order(match_tuple):
            region_id, region = match_tuple
            fname = region.get('resolved_name', '').upper()
            # 尝试在 name_order 中找到匹配的顺序
            for name_key, order in name_order.items():
                if name_key in fname or fname in name_key:
                    return order
            return 999  # 未匹配到的放最后
        
        matches.sort(key=get_match_order)
        logger.debug(f"[匹配导出] 找到 {len(matches)} 个匹配子图，按用户顺序排列")

        # 允许多匹配，采用多个区域的并集
        def pad_bounds(bounds: Dict, pad_val: float) -> Dict:
            return {
                'min_x': bounds['min_x'] - pad_val,
                'max_x': bounds['max_x'] + pad_val,
                'min_y': bounds['min_y'] - pad_val,
                'max_y': bounds['max_y'] + pad_val
            }

        def fully_inside(b1: Dict, b2: Dict) -> bool:
            """判断 b1 是否完全在 b2 内部"""
            return (b1['min_x'] >= b2['min_x'] and b1['max_x'] <= b2['max_x'] and
                    b1['min_y'] >= b2['min_y'] and b1['max_y'] <= b2['max_y'])

        target_bounds = [pad_bounds(r['bounds'], pad) for _, r in matches]

        try:
            doc_copy = ezdxf.readfile(self.analyzer.source_path)
            msp_copy = doc_copy.modelspace()
        except Exception as e:
            return False, f"读取源文件失败: {e}"

        # ===== 步骤 1: 删除不匹配的实体 =====
        logger.debug("[步骤1] 删除不匹配的实体...")
        removed = 0
        total = 0
        for ent in list(msp_copy):
            total += 1
            try:
                b = self.analyzer._compute_entity_bounds(ent, doc_copy.blocks)
                
                # 判断是否保留该实体
                keep = False
                
                if b:
                    # 有边界：优先保留完全落在目标框内的实体
                    for tb in target_bounds:
                        if fully_inside(b, tb):
                            keep = True
                            break
                    
                    # 其次保留中心点落在目标框内的实体
                    if not keep:
                        c = self.analyzer._calculate_entity_center(ent)
                        if c and any(self.analyzer._point_in_bounds(c, tb) for tb in target_bounds):
                            keep = True
                else:
                    # 无边界：尝试用中心点判断（避免误删文字标注）
                    c = self.analyzer._calculate_entity_center(ent)
                    if c and any(self.analyzer._point_in_bounds(c, tb) for tb in target_bounds):
                        keep = True
                        logger.debug(f"[步骤1] 保留无边界实体（类型: {ent.dxftype() if hasattr(ent, 'dxftype') else 'unknown'}，中心点在目标区域内）")
                
                # 删除不需要保留的实体
                if not keep:
                    msp_copy.delete_entity(ent)
                    removed += 1
                    
            except Exception:
                continue
        
        logger.debug(f"[步骤1] 删除了 {removed}/{total} 个不相关实体，保留 {total - removed} 个实体")

        # ===== 步骤 2: 计算每个子图的平移量（如果启用对齐到原点）=====
        if align_to_origin:
            logger.debug("[步骤2] 计算子图平移量...")
            offsets = []
            current_x = 0.0
            
            for i, (region_id, region) in enumerate(matches):
                bounds = region['bounds']
                width = bounds['max_x'] - bounds['min_x']
                height = bounds['max_y'] - bounds['min_y']
                
                if i == 0:
                    # 第一个子图：左下角移到原点 (0, 0)
                    offset_x = -bounds['min_x']
                    offset_y = -bounds['min_y']
                    logger.debug(f"  子图 {i+1} ({region.get('resolved_name', region_id)}): "
                               f"原位置 ({bounds['min_x']:.1f}, {bounds['min_y']:.1f}), "
                               f"平移 ({offset_x:.1f}, {offset_y:.1f}) -> 新位置 (0, 0)")
                else:
                    # 后续子图：向右排列，下边界对齐 y=0
                    offset_x = current_x - bounds['min_x']
                    offset_y = -bounds['min_y']
                    logger.debug(f"  子图 {i+1} ({region.get('resolved_name', region_id)}): "
                               f"原位置 ({bounds['min_x']:.1f}, {bounds['min_y']:.1f}), "
                               f"平移 ({offset_x:.1f}, {offset_y:.1f}) -> 新位置 ({current_x:.1f}, 0)")
                
                offsets.append({
                    'region_id': region_id,
                    'bounds': bounds,
                    'offset': (offset_x, offset_y),
                    'index': i
                })
                
                # 更新下一个子图的起始 x 坐标
                current_x += width + horizontal_spacing
            
            # ===== 步骤 3: 平移保留的实体 =====
            logger.debug("[步骤3] 平移保留的实体到目标位置...")
            translated_count = 0
            unmatched_count = 0
            
            # 扩展边界用于判断实体归属（避免边缘实体被遗漏）
            expanded_bounds = []
            for offset_info in offsets:
                b = offset_info['bounds']
                # 向外扩展 20% 的边界，确保边缘的标注、尺寸线也能被识别
                width = b['max_x'] - b['min_x']
                height = b['max_y'] - b['min_y']
                expand_x = width * 0.2
                expand_y = height * 0.2
                expanded = {
                    'min_x': b['min_x'] - expand_x,
                    'max_x': b['max_x'] + expand_x,
                    'min_y': b['min_y'] - expand_y,
                    'max_y': b['max_y'] + expand_y
                }
                expanded_bounds.append({
                    'bounds': expanded,
                    'offset': offset_info['offset'],
                    'index': offset_info['index']
                })
            
            for ent in msp_copy:
                try:
                    # 判断实体属于哪个子图
                    # 策略1: 优先使用中心点判断
                    center = self.analyzer._calculate_entity_center(ent)
                    matched = False
                    
                    if center:
                        # 先尝试精确匹配（原始边界）
                        for i, offset_info in enumerate(offsets):
                            if self.analyzer._point_in_bounds(center, offset_info['bounds']):
                                dx, dy = offset_info['offset']
                                self._translate_entity(ent, dx, dy)
                                translated_count += 1
                                matched = True
                                break
                        
                        # 如果精确匹配失败，尝试扩展边界匹配
                        if not matched:
                            for expanded_info in expanded_bounds:
                                if self.analyzer._point_in_bounds(center, expanded_info['bounds']):
                                    dx, dy = expanded_info['offset']
                                    self._translate_entity(ent, dx, dy)
                                    translated_count += 1
                                    matched = True
                                    break
                    
                    # 策略2: 如果中心点判断失败，尝试使用边界框判断
                    if not matched:
                        entity_bounds = self.analyzer._compute_entity_bounds(ent, doc_copy.blocks)
                        if entity_bounds:
                            # 计算实体边界框与子图边界框的重叠面积
                            max_overlap = 0
                            best_match_idx = -1
                            
                            for i, expanded_info in enumerate(expanded_bounds):
                                overlap = self._calculate_overlap_area(entity_bounds, expanded_info['bounds'])
                                if overlap > max_overlap:
                                    max_overlap = overlap
                                    best_match_idx = i
                            
                            # 如果有重叠，使用重叠最大的子图
                            if best_match_idx >= 0 and max_overlap > 0:
                                dx, dy = expanded_bounds[best_match_idx]['offset']
                                self._translate_entity(ent, dx, dy)
                                translated_count += 1
                                matched = True
                    
                    if not matched:
                        unmatched_count += 1
                        
                except Exception as e:
                    logger.debug(f"平移实体时出错: {e}")
                    unmatched_count += 1
                    continue
            
            logger.debug(f"[步骤3] 成功平移 {translated_count} 个实体，未匹配 {unmatched_count} 个实体")
            logger.debug(f"[完成] 最终输出：{len(matches)} 个子图横向排列，第一个子图左下角在原点 (0,0)")
        else:
            logger.debug("[跳过平移] align_to_origin=False，保持原始位置")

        # ===== 步骤 4: 保存结果 =====
        try:
            doc_copy.saveas(output_path)
            if align_to_origin:
                logger.debug(f"[匹配导出] 目标 {names} -> {output_path} (删除 {removed}/{total} 个不相关实体，横向排列)")
            else:
                logger.debug(f"[匹配导出] 目标 {names} -> {output_path} (删除 {removed}/{total} 个不相关实体)")
            return True, ""
        except Exception as e:
            return False, f"保存失败: {e}"

class CADProcessor:
    def __init__(self):
        self.config = Config()
        self.dwg_converter = DWGConverter(self.config)
        self.analysis_system = CADAnalysisSystem()

    def process_workflow(self, input_dwg_data: bytes, output_dwg_path: str,
                        target_name: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        main_work_dir = tempfile.mkdtemp(prefix="cad_workflow_")

        try:
            input_dwg_path = os.path.join(main_work_dir, "input.dwg")
            temp_dxf_path = os.path.join(main_work_dir, "temp.dxf")

            # 保存输入 DWG
            with open(input_dwg_path, 'wb') as f:
                f.write(input_dwg_data)
            logger.debug(f"输入文件已创建: {input_dwg_path}")

            # 优先尝试使用 ODA 转换（如果可用），否则使用 AutoCAD 自动化脚本
            logger.debug("步骤1: 尝试 ODAFileConverter 转换 DWG -> DXF ...")
            oda_success = False
            try:
                oda_out = self.dwg_converter.convert_dwg_to_dxf(input_dwg_path, temp_dxf_path)
                if oda_out:
                    oda_success = True
            except Exception:
                oda_success = False

            if not oda_success:
                logger.debug("步骤1b: AutoCAD 兜底已禁用，未执行。")

            actual_dxf_path = temp_dxf_path
            logger.debug(f"DXF 文件已生成: {actual_dxf_path}")

            # 步骤2: 识别子图区域
            logger.debug("步骤2: 识别子图区域")
            splits_dir = os.path.join(main_work_dir, "splits")
            os.makedirs(splits_dir, exist_ok=True)
            try:
                # 调用解析并识别子图区域
                self.analysis_system.analyze_file(actual_dxf_path, splits_dir)
                logger.debug(f"识别区域完成")
            except Exception as e:
                logger.debug(f"识别区域发生错误: {e}")
                # 不强制失败，保留输出用于调试/手动处理

            # 步骤四：如果传入目标名称，仅返回匹配的子图文件（就地删除其他区域）
            logger.debug("步骤3: 保留匹配的子图，得到子图文件")
            if target_name:
                # 只按逗号分割，不按空格分割（因为子图名称中可能包含空格）
                names = [n.strip() for n in re.split(r'[,，]+', target_name) if n.strip()]
                target_dxf = os.path.join(main_work_dir, "target.dxf")
                # 调用导出函数，启用横向排列功能
                ok, msg = self.analysis_system.export_matching_regions(
                    names, 
                    target_dxf, 
                    pad=0.0,
                    horizontal_spacing=50.0,  # 子图之间的间距（单位：mm）
                    align_to_origin=True      # 启用对齐到原点功能
                )
                if not ok or not os.path.exists(target_dxf):
                    logger.debug(msg or "未匹配到图纸信息")
                    return False, None, None
                logger.debug(msg or "已匹配得到子图文件")

                final_path = output_dwg_path
                base_for_name = os.path.splitext(os.path.basename(names[0]))[0] if names else "target"
                logger.debug("步骤4: 将匹配子图 DXF 转为 DWG ...")
                if not self.dwg_converter.convert_dxf_to_dwg(target_dxf, final_path, 'ACAD2004'):
                    logger.debug("DXF -> DWG 版本转换失败")
                    return False, None, None
                download_name = f"{base_for_name}.dwg"
                logger.debug("处理完成，已返回匹配子图 DWG")
                return True, final_path, download_name

            # 若未指定目标名称，返回整体处理结果
            logger.debug("步骤3: 将处理后的 DXF 转回指定版本 DWG（ACAD2004）...")
            if not self.dwg_converter.convert_dxf_to_dwg(actual_dxf_path, output_dwg_path, 'ACAD2004'):
                logger.debug("DXF -> DWG 版本转换失败")
                return False, None, None

            logger.debug("所有处理步骤完成！")
            return True, output_dwg_path, None
        except Exception as e:
            logger.debug(f"处理工作流程时发生错误: {e}")
            import traceback
            traceback.print_exc()
            return False, None, None
        finally:
            # 自动清理临时工作目录
            try:
                if os.path.exists(main_work_dir):
                    shutil.rmtree(main_work_dir)
                    logger.debug(f"已清理临时工作目录: {main_work_dir}")
            except Exception as e:
                logger.debug(f"清理临时目录失败: {e}")

# ---------------- Flask API ----------------

if FLASK_AVAILABLE:
    app = Flask(__name__)
    CORS(app, origins="*")
    app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB 可按需调整

    @app.route('/health', methods=['GET'])
    def health_check():
        return jsonify({"status": "healthy", "service": "CAD处理服务（集成拆图与合并）"})

    @app.route('/process-cad', methods=['POST'])
    def process_cad_file():
        try:
            form_data = request.form or {}
            json_data = request.get_json(silent=True) or {}

            keyword = (form_data.get('keyword') or json_data.get('keyword') or '').strip()
            if not keyword:
                return jsonify({"error": "缺少关键字 keyword"}), 400

            target_name = (form_data.get('target_name') or json_data.get('target_name') or '').strip()

            cfg = Config()
            try:
                dwg_path = find_latest_dwg_path(keyword, str(cfg.z_root))
            except Exception as e:
                # 未找到匹配文件，返回空结果
                return jsonify({"dwg": ""})

            if not os.path.exists(dwg_path):
                return jsonify({"dwg": ""})

            with open(dwg_path, 'rb') as f:
                input_data = f.read()

            processor = CADProcessor()
            temp_dir = tempfile.mkdtemp()
            output_dwg_path = os.path.join(temp_dir, "output.dwg")

            try:
                success, result_path, download_name = processor.process_workflow(input_data, output_dwg_path,
                                                                                 target_name or None)

                # 若处理失败或无匹配子图，返回空结果
                if not success or not result_path or not os.path.exists(result_path):
                    return jsonify({"dwg": ""})

                if success:
                    # 将生成的 DWG 保存到固定目录（不再直接返回文件）
                    save_dir = Path("static") / "dwg" / "orders"
                    save_dir.mkdir(parents=True, exist_ok=True)
                    # 将生成的 DWG 保存到固定目录（不再直接返回文件）
                    # save_dir = Path(r"D:\AI\Pycharm\project\temp_procurement\app\api\v1\chaitu_result")
                    # save_dir.mkdir(parents=True, exist_ok=True)

                    def safe_name(name: str) -> str:
                        return re.sub(r'[^A-Za-z0-9._-]+', '_', name) or "file"

                    base_name = safe_name(keyword)
                    target_label = safe_name(target_name) if target_name else base_name
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"{base_name}_{target_label}_{ts}.dwg"
                    save_path = save_dir / filename

                    shutil.copyfile(result_path, save_path)
                    
                    # 构建访问路径（使用反斜杠格式）
                    image_path = f"static\\dwg\\orders\\{filename}"
                    result_json = {"image": image_path}
                    
                    logger.debug(f"✅ 文件已保存: {save_path}")
                    import json
                    logger.debug(f"📁 返回结果: {json.dumps(result_json, ensure_ascii=False)}")
                    
                    return jsonify(result_json)
                else:
                    return jsonify({"error": "文件处理失败"}), 500
            finally:
                # 清理临时目录
                try:
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                        logger.debug(f"已清理临时目录: {temp_dir}")
                except Exception as e:
                    logger.debug(f"清理临时目录失败: {e}")
        except Exception as e:
            return jsonify({"error": f"服务器错误: {str(e)}"}), 500

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({"error": "文件大小超过限制"}), 413
else:
    app = None

# 注意：此文件现在作为工具模块被导入使用
# 如果需要独立运行 Flask 服务，可以取消下面的注释
# if __name__ == '__main__':
#     logger.debug("CAD处理API服务器启动中...")
#     app.run(host='0.0.0.0', port=3000, debug=False)
