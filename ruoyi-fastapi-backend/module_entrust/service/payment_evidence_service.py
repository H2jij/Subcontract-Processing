"""
对账系统 — 支付凭证 Service
=========================================
覆盖需求 12.1 / 12.2 / 12.3 / 12.5 / 12.6 / 12.7 与 Property 16

职责：
  1. 上传支付凭证文件（jpg / png / pdf / jpeg），保存到本地并落库
       - 校验扩展名（大小写不敏感）
       - 校验文件大小（不超过 sys_config 配置上限，默认 10MB）
       - 生成 UUID 前缀文件名，避免冲突
       - 同步记录上传时间、上传人、文件名、文件大小、mime_type
  2. 删除凭证（仅非 finalized 状态允许）
       - 关联类型为 settlement_detail：父 SettlementDetail 状态须不为
         'finalized'
       - 关联类型为 payment_record：对应 ReconciliationStatement 状态
         须不为 'paid'
       - 删除成功后同步从磁盘移除文件
  3. 查询关联凭证列表（按 related_type + related_id）

设计要点：
  - 与现有 ``utils/upload_util.py`` 保持松耦合（独立校验逻辑，避免误用
    系统其它默认扩展名集合）
  - 文件保存路径：``<project_root>/uploads/payment_evidences/
    {related_type}/{related_id}/<uuid>{ext}``
  - mime_type 通过 file.content_type 优先，回落至 ``mimetypes`` 标准库
  - 全部操作 async，事务由本 Service 管理（commit / rollback）
"""
from __future__ import annotations

import mimetypes
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import UploadFile
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceException
from module_entrust.entity.do.reconciliation_do import (
    PaymentEvidence,
    PaymentRecord,
    ReconciliationStatement,
    SettlementDetail,
)
from module_entrust.service.reconciliation_audit_service import (
    ACTION_CREATE,
    ACTION_DELETE,
    ENTITY_TYPE_PAYMENT_EVIDENCE,
    ReconciliationAuditService,
)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# Requirements 12.1 / 12.5：仅允许 jpg / png / pdf / jpeg（大小写不敏感）
_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({'jpg', 'jpeg', 'png', 'pdf'})

# 关联类型
RELATED_TYPE_PAYMENT_RECORD = 'payment_record'
RELATED_TYPE_SETTLEMENT_DETAIL = 'settlement_detail'
_VALID_RELATED_TYPES: frozenset[str] = frozenset({
    RELATED_TYPE_PAYMENT_RECORD,
    RELATED_TYPE_SETTLEMENT_DETAIL,
})

# 默认文件大小上限：10MB；可通过 sys_config 'reconciliation.evidence.max_size'
# （单位：字节）覆盖。
_DEFAULT_MAX_SIZE_BYTES: int = 10 * 1024 * 1024
_MAX_SIZE_CONFIG_KEY = 'reconciliation.evidence.max_size'

# 上传根目录：<project_root>/uploads/payment_evidences/
# 当前文件路径：<project_root>/ruoyi-fastapi-backend/module_entrust/service/
#               payment_evidence_service.py
# parent x4 -> <project_root>
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_UPLOAD_BASE_DIR = _PROJECT_ROOT / 'uploads' / 'payment_evidences'
_UPLOAD_BASE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _extract_extension(filename: Optional[str]) -> str:
    """
    从原始文件名中提取扩展名（小写、不含点）。

    无后缀返回空串；文件名以点结尾返回空串。
    """
    if not filename:
        return ''
    if '.' not in filename:
        return ''
    ext = filename.rsplit('.', 1)[-1]
    return ext.lower()


def _is_allowed_extension(ext: str) -> bool:
    """扩展名（小写）是否在白名单内。"""
    return ext in _ALLOWED_EXTENSIONS


def _resolve_mime_type(
    upload_file: UploadFile, ext: str
) -> Optional[str]:
    """
    解析 mime_type：优先使用 UploadFile.content_type；
    若缺失或为通用类型，则回落到 ``mimetypes.guess_type``。
    """
    raw = (upload_file.content_type or '').strip()
    if raw and raw != 'application/octet-stream':
        return raw

    if upload_file.filename:
        guessed, _ = mimetypes.guess_type(upload_file.filename)
        if guessed:
            return guessed

    # 扩展名兜底
    fallback_map = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'pdf': 'application/pdf',
    }
    return fallback_map.get(ext)


async def _resolve_max_size_bytes(db: AsyncSession) -> int:
    """
    从 sys_config 读取支付凭证最大文件大小（字节），失败时回落到默认值。

    系统中 sys_config 通常通过 Redis 缓存读取，但 Service 层无法直接拿到
    Redis 句柄；此处直接查表，性能影响可接受（每次上传一次查询）。
    """
    try:
        from module_admin.entity.do.config_do import SysConfig

        row = await db.scalar(
            select(SysConfig.config_value).where(
                SysConfig.config_key == _MAX_SIZE_CONFIG_KEY
            )
        )
        if row is None or str(row).strip() == '':
            return _DEFAULT_MAX_SIZE_BYTES
        value = int(str(row).strip())
        if value <= 0:
            return _DEFAULT_MAX_SIZE_BYTES
        return value
    except Exception as exc:
        logger.warning(
            f'[PaymentEvidenceService] 读取 sys_config({_MAX_SIZE_CONFIG_KEY}) '
            f'失败，使用默认 {_DEFAULT_MAX_SIZE_BYTES} 字节: {exc}'
        )
        return _DEFAULT_MAX_SIZE_BYTES


def _build_target_path(related_type: str, related_id: int, ext: str) -> Path:
    """
    构造保存路径：
        <upload_base>/<related_type>/<related_id>/<uuid>.<ext>

    保证目录存在，文件名通过 UUID 避免冲突。
    """
    sub_dir = _UPLOAD_BASE_DIR / related_type / str(related_id)
    sub_dir.mkdir(parents=True, exist_ok=True)
    suffix = f'.{ext}' if ext else ''
    return sub_dir / f'{uuid.uuid4().hex}{suffix}'


async def _check_settlement_not_finalized(
    db: AsyncSession, settlement_id: int
) -> None:
    """关联到 SettlementDetail 时校验其状态不为 finalized（Requirement 12.6）。"""
    settlement = await db.scalar(
        select(SettlementDetail).where(SettlementDetail.id == settlement_id)
    )
    if settlement is None:
        raise ServiceException(
            message=f'关联的结算明细不存在: settlement_id={settlement_id}'
        )
    if settlement.status == 'finalized':
        raise ServiceException(
            message=(
                f'结算明细 settlement_id={settlement_id} 已确认 (finalized)，'
                f'禁止删除关联的支付凭证'
            )
        )


async def _check_payment_record_statement_not_paid(
    db: AsyncSession, payment_record_id: int
) -> None:
    """
    关联到 PaymentRecord 时，回溯 PaymentRequest → ReconciliationStatement，
    若对账单状态为 'paid' 则禁止删除（视为 finalized 等价态）。
    """
    record = await db.scalar(
        select(PaymentRecord).where(PaymentRecord.id == payment_record_id)
    )
    if record is None:
        raise ServiceException(
            message=f'关联的付款记录不存在: payment_record_id={payment_record_id}'
        )

    statement_id = record.statement_id
    if statement_id is None:
        # 付款记录必须挂在某对账单上；若缺失视为数据异常，谨慎放行
        return

    statement_status = await db.scalar(
        select(ReconciliationStatement.status).where(
            ReconciliationStatement.id == statement_id
        )
    )
    if statement_status == 'paid':
        raise ServiceException(
            message=(
                f'付款记录 payment_record_id={payment_record_id} 对应的对账单 '
                f'(statement_id={statement_id}) 已结清 (paid)，'
                f'禁止删除关联的支付凭证'
            )
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class PaymentEvidenceService:
    """支付凭证服务（上传 / 删除 / 查询）。"""

    # ------------------------------------------------------------------
    # 上传（Requirements 12.1 / 12.2 / 12.5 / 12.7 / Property 16）
    # ------------------------------------------------------------------

    @staticmethod
    async def upload_evidence(
        db: AsyncSession,
        file: UploadFile,
        related_type: str,
        related_id: int,
        uploaded_by: int,
    ) -> PaymentEvidence:
        """
        上传支付凭证。

        校验顺序：
          1. related_type 合法（payment_record / settlement_detail）
          2. 文件名后缀合法（jpg/png/pdf/jpeg，大小写不敏感）
          3. 文件大小不超过上限
          4. （payment_record/settlement_detail 关联实体的存在性由调用方
              保证；本方法仅做最基础的非空校验）

        校验通过后将文件保存到磁盘，并落库 PaymentEvidence。

        Args:
            db: AsyncSession
            file: FastAPI UploadFile 对象
            related_type: 关联类型，必须是 payment_record / settlement_detail
            related_id: 关联 ID
            uploaded_by: 上传人 user_id

        Returns:
            新创建的 PaymentEvidence ORM 实例

        Raises:
            ServiceException: 任意校验失败 / IO 失败
        """
        # 基础参数校验
        if file is None or file.filename is None:
            raise ServiceException(message='上传文件不能为空')
        if related_type not in _VALID_RELATED_TYPES:
            raise ServiceException(
                message=(
                    f'非法的关联类型: {related_type}；'
                    f'允许值: {sorted(_VALID_RELATED_TYPES)}'
                )
            )
        if not related_id or related_id <= 0:
            raise ServiceException(message='related_id 不能为空且必须大于 0')
        if not uploaded_by:
            raise ServiceException(message='上传操作必须提供 uploaded_by')

        # 扩展名校验（Requirement 12.1 / 12.5 / Property 16）
        ext = _extract_extension(file.filename)
        if not _is_allowed_extension(ext):
            raise ServiceException(
                message=(
                    f'文件类型不被允许：仅支持 jpg / jpeg / png / pdf；'
                    f'当前文件: {file.filename}'
                )
            )

        # 读取文件内容（一次性读入用于大小校验和写入；UploadFile 内部按
        # SpooledTemporaryFile 管理，常规凭证体积下不会带来内存问题）
        content = await file.read()
        size_bytes = len(content)
        max_size = await _resolve_max_size_bytes(db)
        if size_bytes <= 0:
            raise ServiceException(message='上传文件为空')
        if size_bytes > max_size:
            raise ServiceException(
                message=(
                    f'文件大小 {size_bytes} 字节超过上限 {max_size} 字节'
                )
            )

        # 写入磁盘
        target_path = _build_target_path(related_type, related_id, ext)
        try:
            async with aiofiles.open(target_path, 'wb') as f:
                await f.write(content)
        except OSError as exc:
            logger.error(
                f'[PaymentEvidenceService] 文件保存失败 path={target_path}: {exc}'
            )
            raise ServiceException(message=f'文件保存失败: {exc}')

        mime_type = _resolve_mime_type(file, ext)

        # 落库 PaymentEvidence
        evidence = PaymentEvidence(
            related_type=related_type,
            related_id=related_id,
            file_name=file.filename,
            file_path=str(target_path),
            file_size=size_bytes,
            mime_type=mime_type,
            uploaded_by=uploaded_by,
            created_at=datetime.now(),
        )
        try:
            db.add(evidence)
            await db.flush()
            await db.commit()
        except Exception as exc:
            await db.rollback()
            # 数据库写入失败时回滚磁盘文件，避免脏数据
            try:
                if target_path.exists():
                    target_path.unlink()
            except OSError:
                logger.warning(
                    f'[PaymentEvidenceService] 回滚磁盘文件失败 path={target_path}'
                )
            logger.error(
                f'[PaymentEvidenceService] 落库失败 related_type={related_type} '
                f'related_id={related_id} err={exc}'
            )
            raise

        # 审计日志：支付凭证上传（Requirement 8.1） — 失败不影响主流程
        await ReconciliationAuditService.log_action_safe(
            db=db,
            entity_type=ENTITY_TYPE_PAYMENT_EVIDENCE,
            entity_id=evidence.id,
            action=ACTION_CREATE,
            operator_id=int(uploaded_by or 0),
            detail={
                'sub_action': 'upload_evidence',
                'related_type': related_type,
                'related_id': related_id,
                'file_name': file.filename,
                'file_size': size_bytes,
                'mime_type': mime_type,
            },
            autocommit=True,
        )
        logger.info(
            f'[PaymentEvidenceService] 上传成功 evidence_id={evidence.id} '
            f'related_type={related_type} related_id={related_id} '
            f'file_name={file.filename} size={size_bytes} '
            f'uploaded_by={uploaded_by}'
        )
        return evidence

    # ------------------------------------------------------------------
    # 删除（Requirement 12.6 / Property 15）
    # ------------------------------------------------------------------

    @staticmethod
    async def delete_evidence(
        db: AsyncSession, evidence_id: int
    ) -> bool:
        """
        删除支付凭证（含磁盘文件）。

        约束：
          - 关联到 SettlementDetail 时，settlement.status != 'finalized'
          - 关联到 PaymentRecord 时，对应对账单 status != 'paid'

        删除策略：先删 DB 行，再删磁盘文件；磁盘删除失败不抛错，记录警告。

        Args:
            db: AsyncSession
            evidence_id: 凭证 ID

        Returns:
            True 表示成功

        Raises:
            ServiceException: 凭证不存在 / 关联实体处于不可变状态
        """
        evidence = await db.scalar(
            select(PaymentEvidence).where(PaymentEvidence.id == evidence_id)
        )
        if evidence is None:
            raise ServiceException(message=f'支付凭证不存在: evidence_id={evidence_id}')

        # 状态检查
        if evidence.related_type == RELATED_TYPE_SETTLEMENT_DETAIL:
            await _check_settlement_not_finalized(db, evidence.related_id)
        elif evidence.related_type == RELATED_TYPE_PAYMENT_RECORD:
            await _check_payment_record_statement_not_paid(
                db, evidence.related_id
            )
        else:
            # 历史脏数据兜底：拒绝删除未知关联类型
            raise ServiceException(
                message=(
                    f'未知的关联类型: {evidence.related_type}，'
                    f'禁止删除以保障数据可追溯性'
                )
            )

        file_path = evidence.file_path
        # 在删除前快照审计需要的字段，避免删除后访问已分离对象引发异常
        evidence_id_snapshot = evidence.id
        related_type_snapshot = evidence.related_type
        related_id_snapshot = evidence.related_id
        file_name_snapshot = evidence.file_name
        uploaded_by_snapshot = evidence.uploaded_by
        try:
            await db.delete(evidence)
            await db.flush()
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error(
                f'[PaymentEvidenceService] 删除凭证 DB 操作失败 '
                f'evidence_id={evidence_id} err={exc}'
            )
            raise

        # 磁盘清理（DB 已落库，此处失败仅记录警告）
        if file_path:
            try:
                p = Path(file_path)
                if p.exists():
                    os.remove(p)
            except OSError as exc:
                logger.warning(
                    f'[PaymentEvidenceService] 凭证磁盘文件删除失败 '
                    f'path={file_path} err={exc}'
                )

        # 审计日志：支付凭证删除（Requirement 8.1）— 失败不影响主流程
        await ReconciliationAuditService.log_action_safe(
            db=db,
            entity_type=ENTITY_TYPE_PAYMENT_EVIDENCE,
            entity_id=evidence_id_snapshot,
            action=ACTION_DELETE,
            operator_id=int(uploaded_by_snapshot or 0),
            detail={
                'sub_action': 'delete_evidence',
                'related_type': related_type_snapshot,
                'related_id': related_id_snapshot,
                'file_name': file_name_snapshot,
            },
            autocommit=True,
        )
        logger.info(
            f'[PaymentEvidenceService] 凭证已删除 evidence_id={evidence_id} '
            f'related_type={related_type_snapshot} related_id={related_id_snapshot}'
        )
        return True

    # ------------------------------------------------------------------
    # 查询（Requirement 12.3 — 多附件关联）
    # ------------------------------------------------------------------

    @staticmethod
    async def get_evidences(
        db: AsyncSession, related_type: str, related_id: int
    ) -> list[PaymentEvidence]:
        """
        查询某实体（payment_record / settlement_detail）关联的全部支付凭证，
        按上传时间倒序。

        Args:
            db: AsyncSession
            related_type: 关联类型
            related_id: 关联 ID

        Returns:
            PaymentEvidence ORM 实例列表（可能为空）

        Raises:
            ServiceException: related_type 非法
        """
        if related_type not in _VALID_RELATED_TYPES:
            raise ServiceException(
                message=(
                    f'非法的关联类型: {related_type}；'
                    f'允许值: {sorted(_VALID_RELATED_TYPES)}'
                )
            )

        stmt = (
            select(PaymentEvidence)
            .where(
                PaymentEvidence.related_type == related_type,
                PaymentEvidence.related_id == related_id,
            )
            .order_by(PaymentEvidence.created_at.desc(), PaymentEvidence.id.desc())
        )
        rows = (await db.execute(stmt)).scalars().all()
        return list(rows)


__all__ = [
    'PaymentEvidenceService',
    'RELATED_TYPE_PAYMENT_RECORD',
    'RELATED_TYPE_SETTLEMENT_DETAIL',
]
