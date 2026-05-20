"""
委外加工 — 图纸服务
查找图纸 → 数据库有直接取 → 没有则找原图 → 全量拆图 → 所有子图存库 → 返回匹配结果
"""
import os
import re
import shutil
import subprocess
import tempfile
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_entrust.entity.do.entrust_do import EntrustDrawing

logger = logging.getLogger(__name__)

# 子图保存根目录（绝对路径，指向 RuoYi-Vue3-FastAPI/uploads/part_drawings）
PART_DRAWINGS_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / 'uploads' / 'part_drawings')
# 数据库中存储的相对路径前缀
PART_DRAWINGS_REL = 'uploads/part_drawings'


# ==================== 拆图引擎导入 ====================

try:
    from module_entrust.utils.chaitu_engine import find_latest_dwg_path, DWGConverter, Config
    from module_entrust.utils.dxf_split import split_dxf_file_with_output, EZDXF_AVAILABLE
    CAD_AVAILABLE = EZDXF_AVAILABLE
    logger.info('[图纸模块] 拆图引擎加载成功')
except Exception as e:
    CAD_AVAILABLE = False
    find_latest_dwg_path = None
    DWGConverter = None
    Config = None
    split_dxf_file_with_output = None
    logger.warning(f'[图纸模块] 拆图引擎加载失败，拆图功能不可用: {e}')


def _get_cad_config():
    """从系统配置获取 CAD 路径"""
    try:
        from config.env import AppSettings
        settings = AppSettings()
        return settings.cad_search_root, settings.oda_file_converter_path
    except Exception:
        return 'D:\\', 'D:\\ODAFileConverter_title 21.5.0\\ODAFileConverter.exe'


# ==================== 参数规范化 ====================

def normalize_mold_code(raw: str) -> str:
    """规范化模具编号: M250247.P6-WUJIN → M250247-P6"""
    mc = raw.strip()
    m = re.match(r'(M\d{6})[.\-]?(P\d+)', mc, re.IGNORECASE)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.match(r'(M\d{6})', mc, re.IGNORECASE)
    return m.group(1) if m else mc


def normalize_part_code(mold_code: str, raw: str) -> str:
    """去掉零件编号中的模具号前缀"""
    parts = [s.strip() for s in re.split(r'[,，]+', raw) if s.strip()]
    cleaned = []
    for p in parts:
        result = re.sub(rf'^{re.escape(mold_code)}-', '', p, flags=re.IGNORECASE)
        if result == p:
            result = re.sub(r'^M\d{6}[.\-]?P\d+[.\-]', '', p, flags=re.IGNORECASE)
        cleaned.append(result)
    return ','.join(cleaned)


# ==================== 核心业务 ====================

async def lookup_drawings(
    db: AsyncSession,
    mold_code: str,
    part_codes_str: str,
) -> List[dict]:
    """
    批量查找图纸（询价时调用）
    1. 查数据库有没有
    2. 没有 → 找原图拆图
    3. 返回每个零件的查找结果
    """
    mold_code = normalize_mold_code(mold_code)
    part_codes = [p.strip() for p in part_codes_str.split(',') if p.strip()]

    results = []
    for pc in part_codes:
        pc = normalize_part_code(mold_code, pc)
        result = await _lookup_single(db, mold_code, pc)
        results.append(result)

    return results


async def _lookup_single(db: AsyncSession, mold_code: str, part_code: str) -> dict:
    """查找单个零件的图纸"""

    # Step1: 查数据库（取最新版）
    # 用前缀匹配：part_code 以 part_no 开头即匹配（如 part_no='A08' 匹配 'A08-M250082-P2'）
    stmt = select(EntrustDrawing).where(
        EntrustDrawing.mold_code == mold_code,
        EntrustDrawing.part_code.like(f'{part_code}%'),
        EntrustDrawing.is_latest == True,
        EntrustDrawing.status == 'available',
    ).limit(1)
    row = (await db.execute(stmt)).scalar_one_or_none()

    if row:
        return {
            'part_code': part_code,
            'found': True,
            'source': 'database',
            'download_url': f'/entrust/drawing/download/{row.id}',
            'file_path': row.file_path,
            'drawing_id': row.id,
        }

    # Step2: 检查该模具是否已做过全量拆图（避免重复拆）
    split_count = (await db.execute(
        select(func.count()).select_from(EntrustDrawing).where(
            EntrustDrawing.mold_code == mold_code,
            EntrustDrawing.source_type == 'auto_split',
            EntrustDrawing.status == 'available',
        )
    )).scalar()

    if split_count > 0:
        # 已经拆过了，说明原图中确实没有这个零件
        return {
            'part_code': part_code,
            'found': False,
            'message': f'原图中未找到零件: {part_code}',
        }

    # Step3: 没拆过，执行全量拆图
    if not CAD_AVAILABLE:
        return {
            'part_code': part_code,
            'found': False,
            'message': '拆图引擎不可用',
        }

    try:
        cad_root, oda_path = _get_cad_config()
        source_dwg = find_latest_dwg_path(mold_code, z_root=cad_root)
        if not source_dwg or not os.path.exists(source_dwg):
            return {
                'part_code': part_code,
                'found': False,
                'message': f'原图未找到: {mold_code}',
            }

        # 全量拆图，保存所有子图
        drawing = await _do_full_split(db, mold_code, part_code, source_dwg)
        if drawing:
            return {
                'part_code': part_code,
                'found': True,
                'source': 'auto_split',
                'download_url': f'/entrust/drawing/download/{drawing.id}',
                'file_path': drawing.file_path,
                'drawing_id': drawing.id,
            }
        else:
            return {
                'part_code': part_code,
                'found': False,
                'message': f'拆图完成但未找到零件: {part_code}',
            }
    except Exception as e:
        logger.error(f'[图纸查找] 拆图异常: {e}', exc_info=True)
        return {
            'part_code': part_code,
            'found': False,
            'message': f'拆图异常: {str(e)}',
        }


async def _do_full_split(
    db: AsyncSession,
    mold_code: str,
    part_code: str,
    source_dwg: str,
) -> Optional[EntrustDrawing]:
    """
    全量拆图：从原图拆出所有子图，全部保存到磁盘 + 写入数据库。
    返回目标零件的 EntrustDrawing（未匹配到则返回 None）。
    """

    temp_dir = tempfile.mkdtemp(prefix='fullsplit_')

    try:
        # Step 1: DWG → DXF
        config = Config()
        _, oda_path = _get_cad_config()
        config.oda_file_converter_path = oda_path
        converter = DWGConverter(config)

        dxf_path = os.path.join(temp_dir, 'source.dxf')
        logger.info(f'[全量拆图] DWG → DXF: {source_dwg}')
        if not converter.convert_dwg_to_dxf(source_dwg, dxf_path):
            logger.error('[全量拆图] DWG → DXF 失败')
            return None

        # Step 2: 全量拆图（DXF → 所有子图 DXF）
        splits_dir = os.path.join(temp_dir, 'splits')
        logger.info(f'[全量拆图] 开始拆图，输出目录: {splits_dir}')
        exported_dir = split_dxf_file_with_output(dxf_path, splits_dir)

        if not exported_dir or not os.path.isdir(exported_dir):
            logger.warning(f'[全量拆图] 拆图输出为空: {mold_code}')
            return None

        dxf_files = [f for f in os.listdir(exported_dir) if f.lower().endswith('.dxf')]
        if not dxf_files:
            logger.warning(f'[全量拆图] 未拆出任何子图: {mold_code}')
            return None

        logger.info(f'[全量拆图] {mold_code} 拆出 {len(dxf_files)} 个子图')

        # Step 3: 批量 DXF → DWG（ODA 一次转换整个目录）
        dwg_output_dir = os.path.join(temp_dir, 'dwg_output')
        os.makedirs(dwg_output_dir, exist_ok=True)

        if os.path.exists(oda_path):
            try:
                logger.info('[全量拆图] 批量 DXF → DWG 转换...')
                subprocess.run(
                    [oda_path, exported_dir, dwg_output_dir, 'ACAD2004', 'DWG', '0', '1'],
                    check=True, capture_output=True, timeout=300,
                )
                logger.info('[全量拆图] DXF → DWG 转换完成')
            except Exception as e:
                logger.warning(f'[全量拆图] DXF → DWG 批量转换失败: {e}')

        # Step 4: 保存所有子图到持久目录 + 写入数据库
        save_dir = Path(PART_DRAWINGS_DIR) / mold_code
        save_dir.mkdir(parents=True, exist_ok=True)

        matched_drawing = None

        for dxf_file in dxf_files:
            part_name = os.path.splitext(dxf_file)[0]
            dxf_full = os.path.join(exported_dir, dxf_file)

            # 优先用 DWG，没有则用 DXF
            dwg_full = os.path.join(dwg_output_dir, f'{part_name}.dwg')
            if os.path.exists(dwg_full):
                src_file = dwg_full
                final_ext = '.dwg'
            else:
                src_file = dxf_full
                final_ext = '.dxf'

            file_name = f'{part_name}{final_ext}'
            save_path = save_dir / file_name

            # 跳过磁盘上已有的（避免覆盖）
            if not save_path.exists():
                shutil.copyfile(src_file, save_path)

            file_size_kb = int(os.path.getsize(save_path) / 1024) if save_path.exists() else 0

            # 检查数据库是否已存在该零件
            existing = (await db.execute(
                select(EntrustDrawing).where(
                    EntrustDrawing.mold_code == mold_code,
                    EntrustDrawing.part_code == part_name,
                    EntrustDrawing.is_latest == True,
                    EntrustDrawing.status == 'available',
                )
            )).scalar_one_or_none()

            if existing:
                # 前缀匹配：拆图名以目标零件编号开头即为匹配
                if part_name.upper().startswith(part_code.upper()):
                    matched_drawing = existing
                continue

            # 写入数据库
            drawing = EntrustDrawing(
                mold_code=mold_code,
                part_code=part_name,
                file_name=file_name,
                file_path=f'{PART_DRAWINGS_REL}/{mold_code}/{file_name}',
                file_size_kb=file_size_kb,
                version=1,
                is_latest=True,
                source_type='auto_split',
                split_at=datetime.now(),
                status='available',
            )
            db.add(drawing)
            await db.flush()

            logger.info(f'[全量拆图] 保存: {mold_code}/{part_name} ({file_size_kb}KB)')

            # 前缀匹配：拆图名以目标零件编号开头即为匹配
            if part_name.upper().startswith(part_code.upper()):
                matched_drawing = drawing

        logger.info(f'[全量拆图] 完成: {mold_code}, 共 {len(dxf_files)} 个子图, '
                     f'目标 {part_code} → {"找到" if matched_drawing else "未找到"}')
        return matched_drawing

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ==================== 图纸管理 ====================

async def list_drawings(
    db: AsyncSession,
    mold_code: Optional[str] = None,
    part_code: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    """图纸列表"""
    conditions = [EntrustDrawing.status == 'available']
    if mold_code:
        conditions.append(EntrustDrawing.mold_code.ilike(f'%{mold_code}%'))
    if part_code:
        conditions.append(EntrustDrawing.part_code.ilike(f'%{part_code}%'))

    from sqlalchemy import func
    count_stmt = select(func.count()).select_from(EntrustDrawing).where(*conditions)
    total = (await db.execute(count_stmt)).scalar()

    stmt = (
        select(EntrustDrawing)
        .where(*conditions)
        .order_by(EntrustDrawing.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return rows, total


async def get_drawing_by_id(db: AsyncSession, drawing_id: int) -> Optional[EntrustDrawing]:
    """根据ID获取图纸"""
    stmt = select(EntrustDrawing).where(EntrustDrawing.id == drawing_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def delete_drawing(db: AsyncSession, drawing_id: int) -> bool:
    """删除图纸（软删除）"""
    stmt = select(EntrustDrawing).where(EntrustDrawing.id == drawing_id)
    drawing = (await db.execute(stmt)).scalar_one_or_none()
    if not drawing:
        return False

    drawing.status = 'unavailable'
    await db.flush()
    return True


async def manual_split(
    db: AsyncSession,
    mold_code: str,
    part_codes_str: str,
) -> List[dict]:
    """手动触发全量拆图"""
    if not CAD_AVAILABLE:
        raise ValueError('拆图引擎不可用，请检查 ODA 和 ezdxf 是否安装')

    mold_code = normalize_mold_code(mold_code)
    part_codes = [normalize_part_code(mold_code, p) for p in part_codes_str.split(',') if p.strip()]

    cad_root, _ = _get_cad_config()
    source_dwg = find_latest_dwg_path(mold_code, z_root=cad_root)

    if not source_dwg or not os.path.exists(source_dwg):
        raise FileNotFoundError(f'原图未找到: {mold_code}')

    # 全量拆图一次（不指定目标，拆出所有）
    # 用第一个零件编号触发全量拆图
    trigger_part = part_codes[0] if part_codes else ''
    try:
        await _do_full_split(db, mold_code, trigger_part, source_dwg)
    except Exception as e:
        logger.error(f'[手动拆图] 全量拆图异常: {e}', exc_info=True)
        raise

    # 拆图完成后，从数据库查询每个零件的结果
    results = []
    for pc in part_codes:
        row = (await db.execute(
            select(EntrustDrawing).where(
                EntrustDrawing.mold_code == mold_code,
                EntrustDrawing.part_code == pc,
                EntrustDrawing.is_latest == True,
                EntrustDrawing.status == 'available',
            ).limit(1)
        )).scalar_one_or_none()
        results.append({
            'part_code': pc,
            'success': row is not None,
            'drawing_id': row.id if row else None,
        })

    return results


async def ensure_project_drawings(db: AsyncSession, project_id: int) -> dict:
    """
    决策时调用：为项目的所有模具号执行全量拆图（仅拆还没拆过的模具）。
    返回 {mold_code: {split_count, parts_found}} 汇总。
    """
    from module_entrust.entity.do.entrust_do import EntrustMold, EntrustPart

    # 查项目下所有零件（含有关联 mold_id 的和没有的）
    parts_stmt = select(EntrustPart).where(EntrustPart.project_id == project_id)
    all_parts = (await db.execute(parts_stmt)).scalars().all()

    if not all_parts:
        return {'message': '项目无零件', 'details': {}}

    # 查项目下所有模具
    molds_stmt = select(EntrustMold).where(EntrustMold.project_id == project_id)
    all_molds = (await db.execute(molds_stmt)).scalars().all()
    mold_map = {m.id: m for m in all_molds}  # mold_id → mold
    # 项目名本身也可能是模具号（如项目名 "M250191"）
    project_mold_codes = list({normalize_mold_code(m.name or '') for m in all_molds if m.name})

    # 按 mold_code 分组零件
    mold_parts = {}
    for part in all_parts:
        mc = None
        # 优先从 mold_id 获取模具号
        if part.mold_id and part.mold_id in mold_map:
            mc = normalize_mold_code(mold_map[part.mold_id].name or '')
        # 没有 mold_id，用项目下的模具号兜底
        if not mc and project_mold_codes:
            mc = project_mold_codes[0]
        if not mc:
            continue
        if mc not in mold_parts:
            mold_parts[mc] = []
        if part.part_no:
            mold_parts[mc].append(part.part_no)

    if not mold_parts:
        return {'message': '无有效模具号', 'details': {}}

    details = {}
    for mold_code, part_nos in mold_parts.items():
        # 检查该模具是否已拆过
        split_count = (await db.execute(
            select(func.count()).select_from(EntrustDrawing).where(
                EntrustDrawing.mold_code == mold_code,
                EntrustDrawing.source_type == 'auto_split',
                EntrustDrawing.status == 'available',
            )
        )).scalar()

        if split_count > 0:
            # 已拆过，统计能匹配到几个零件
            # 用前缀匹配：part_code 以 part_no 开头即匹配
            from sqlalchemy import or_
            like_conditions = [EntrustDrawing.part_code.like(f'{pn}%') for pn in part_nos]
            found = (await db.execute(
                select(func.count()).select_from(EntrustDrawing).where(
                    EntrustDrawing.mold_code == mold_code,
                    or_(*like_conditions),
                    EntrustDrawing.is_latest == True,
                    EntrustDrawing.status == 'available',
                )
            )).scalar()
            details[mold_code] = {'status': 'already_split', 'split_count': split_count, 'parts_found': found}
            logger.info(f'[决策拆图] {mold_code} 已拆过({split_count}个子图)，匹配 {found}/{len(part_nos)} 个零件')
            continue

        # 未拆过，执行全量拆图
        if not CAD_AVAILABLE:
            details[mold_code] = {'status': 'engine_unavailable'}
            continue

        try:
            cad_root, _ = _get_cad_config()
            source_dwg = find_latest_dwg_path(mold_code, z_root=cad_root)
            if not source_dwg or not os.path.exists(source_dwg):
                details[mold_code] = {'status': 'source_not_found'}
                logger.warning(f'[决策拆图] 原图未找到: {mold_code}')
                continue

            # 用第一个零件编号触发（实际会全量拆出所有子图）
            trigger_part = normalize_part_code(mold_code, part_nos[0]) if part_nos else ''
            await _do_full_split(db, mold_code, trigger_part, source_dwg)

            # 统计结果
            new_count = (await db.execute(
                select(func.count()).select_from(EntrustDrawing).where(
                    EntrustDrawing.mold_code == mold_code,
                    EntrustDrawing.source_type == 'auto_split',
                    EntrustDrawing.status == 'available',
                )
            )).scalar()
            from sqlalchemy import or_
            like_conditions = [EntrustDrawing.part_code.like(f'{pn}%') for pn in part_nos]
            found = (await db.execute(
                select(func.count()).select_from(EntrustDrawing).where(
                    EntrustDrawing.mold_code == mold_code,
                    or_(*like_conditions),
                    EntrustDrawing.is_latest == True,
                    EntrustDrawing.status == 'available',
                )
            )).scalar()
            details[mold_code] = {'status': 'split_done', 'split_count': new_count, 'parts_found': found}
            logger.info(f'[决策拆图] {mold_code} 拆图完成: {new_count}个子图，匹配 {found}/{len(part_nos)} 个零件')

        except Exception as e:
            details[mold_code] = {'status': 'error', 'message': str(e)}
            logger.error(f'[决策拆图] {mold_code} 异常: {e}', exc_info=True)

    return {'message': '拆图完成', 'details': details}


async def preview_assembly(mold_code: str) -> dict:
    """预览原图中有哪些可拆的零件编号"""
    if not CAD_AVAILABLE:
        return {'success': False, 'message': '拆图引擎不可用'}

    mold_code = normalize_mold_code(mold_code)

    try:
        cad_root, _ = _get_cad_config()
        source_dwg = find_latest_dwg_path(mold_code, z_root=cad_root)
        if not source_dwg or not os.path.exists(source_dwg):
            return {'success': False, 'message': f'原图未找到: {mold_code}'}

        # 使用拆图引擎预览
        from module_entrust.utils.chaitu_engine import DWGConverter, Config, preview_sub_drawings
        config = Config()
        _, oda_path = _get_cad_config()
        config.oda_file_converter_path = oda_path

        temp_dir = tempfile.mkdtemp(prefix='preview_')
        dxf_path = os.path.join(temp_dir, 'preview.dxf')

        try:
            converter = DWGConverter(config)
            result = converter.convert_dwg_to_dxf(source_dwg, dxf_path)
            if not result or not os.path.exists(dxf_path):
                return {'success': False, 'message': 'DWG转DXF失败'}

            names = preview_sub_drawings(dxf_path)

            return {
                'success': True,
                'mold_code': mold_code,
                'source_dwg': source_dwg,
                'sub_drawings': names,
                'total': len(names),
            }
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f'[预览] 异常: {e}', exc_info=True)
        return {'success': False, 'message': str(e)}
