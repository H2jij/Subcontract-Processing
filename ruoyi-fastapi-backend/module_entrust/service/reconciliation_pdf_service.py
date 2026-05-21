"""
对账系统 — PDF 生成 Service
=========================================
覆盖需求 7.2 / 7.4 / 11.1 ~ 11.6

职责：
  1. ``generate_statement_pdf(statement_id)``
       生成正式对账单 PDF：
         - 公司信息、对账单编号、供应商、对账周期、汇总金额
         - 行项明细表
         - 公司印章区域
         - 甲方 / 乙方签名栏位

  2. ``generate_settlement_pdf(settlement_id)``
       生成结算 PDF：
         - 订单信息头（order_no、supplier、date）
         - 加工费用明细（process_fee）
         - 物流费用（logistics）
         - 扣款明细（deduction）
         - 补发费用（re_shipment）
         - 重新加工费用（rework）
         - 客户付款金额（customer_payment / customer_payment 字段）
         - 支付凭证附录：列出已上传文件名；jpg/png 直接嵌入图片

  3. ``export_batch_pdf(statement_ids)``
       批量导出对账单 PDF（按顺序生成，单个失败不影响其他）。

设计要点：
  - 使用 ReportLab（已在 requirements.txt）。中文支持采用 ReportLab 自带的
    CID 字体 ``STSong-Light``（Adobe-GB1-0），无需依赖系统字体文件，跨平台稳定。
  - PDF 输出至 ``UploadConfig.DOWNLOAD_PATH/reconciliation/{kind}/{YYYYMM}/...``，
    与现有 common_service 下载目录约定一致。
  - 失败时：写入 ``ReconciliationAuditLog`` (action=export_failed) 并通过
    ``ReconciliationNotificationService`` 当前渠道通知操作人 / 财务，
    再向调用方抛 ``ServiceException``（保持与上层接口语义一致）。
  - 不修改任何业务实体；纯读模型 + 文件落地。
"""
from __future__ import annotations

import os
import traceback
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.env import UploadConfig
from exceptions.exception import ServiceException
from module_entrust.entity.do.entrust_do import EntrustOutsourceOrder, EntrustSupplier
from module_entrust.entity.do.reconciliation_do import (
    PaymentEvidence,
    ReconciliationAuditLog,
    ReconciliationLineItem,
    ReconciliationStatement,
    SettlementDetail,
    SettlementLineItem,
)
from module_entrust.service.reconciliation_notification_service import (
    ReconciliationNotificationService,
)


# ---------------------------------------------------------------------------
# ReportLab 导入与字体注册（懒加载，避免无 reportlab 环境直接 import 报错）
# ---------------------------------------------------------------------------

_DEFAULT_CN_FONT = 'STSong-Light'
_DEFAULT_CN_FONT_BOLD = 'STSong-Light'  # CID 字体没有粗体，加粗通过样式表达
_FALLBACK_FONT = 'Helvetica'

_font_registered: bool = False
_active_font: str = _FALLBACK_FONT


def _ensure_font_registered() -> str:
    """
    懒加载并注册 PDF 字体。

    优先使用 ReportLab 自带 CID 字体 ``STSong-Light``（Adobe-GB1-0，支持简体中文）。
    若注册失败（极少见），退回到 ``Helvetica``，仅 ASCII 可正常显示，
    中文字符会转为 ``?``，并在日志中提示。
    """
    global _font_registered, _active_font
    if _font_registered:
        return _active_font

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont

        pdfmetrics.registerFont(UnicodeCIDFont(_DEFAULT_CN_FONT))
        _active_font = _DEFAULT_CN_FONT
        logger.info(
            '[ReconciliationPdfService] 已注册中文字体 {}', _DEFAULT_CN_FONT
        )
    except Exception as exc:  # noqa: BLE001
        _active_font = _FALLBACK_FONT
        logger.warning(
            '[ReconciliationPdfService] 中文字体注册失败 ({}), '
            '降级使用 {}，中文可能显示为问号',
            exc, _FALLBACK_FONT,
        )

    _font_registered = True
    return _active_font


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _to_decimal(value) -> Decimal:
    if value is None or value == '':
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _format_money(value) -> str:
    """格式化金额为 ``1,234.56`` 形式。"""
    d = _to_decimal(value)
    # 保留 2 位小数，千位分隔
    return f'{d:,.2f}'


def _safe_str(value) -> str:
    if value is None:
        return ''
    return str(value)


def _resolve_evidence_abs_path(file_path: str) -> Optional[str]:
    """
    解析支付凭证文件的绝对路径。

    PaymentEvidence.file_path 可能存储为：
      - 绝对路径（如 ``/data/.../upload.png``）
      - 以 UploadConfig.UPLOAD_PREFIX 开头的访问路径（如 ``/profile/...``）
      - 相对 UPLOAD_PATH 的相对路径

    若文件不存在则返回 None。
    """
    if not file_path:
        return None

    candidates: list[str] = []

    # 1. 绝对路径
    if os.path.isabs(file_path):
        candidates.append(file_path)

    # 2. 通过上传前缀映射（/profile/xxx -> UPLOAD_PATH/xxx）
    prefix = UploadConfig.UPLOAD_PREFIX
    if prefix and file_path.startswith(prefix):
        rel = file_path[len(prefix):].lstrip('/').lstrip('\\')
        candidates.append(os.path.join(UploadConfig.UPLOAD_PATH, rel))

    # 3. 视为相对路径，相对 UPLOAD_PATH 拼接
    rel_path = file_path.lstrip('/').lstrip('\\')
    candidates.append(os.path.join(UploadConfig.UPLOAD_PATH, rel_path))
    # 4. 相对 cwd
    candidates.append(rel_path)

    for c in candidates:
        try:
            if os.path.exists(c) and os.path.isfile(c):
                return os.path.abspath(c)
        except OSError:
            continue
    return None


def _is_image_extension(name: str) -> bool:
    if not name:
        return False
    lower = name.lower()
    return lower.endswith(('.jpg', '.jpeg', '.png'))


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _output_dir(kind: str, period: Optional[datetime] = None) -> str:
    """
    返回 PDF 输出目录： ``DOWNLOAD_PATH/reconciliation/{kind}/{YYYYMM}/``
    """
    base = os.path.join(
        UploadConfig.DOWNLOAD_PATH, 'reconciliation', kind
    )
    ymd = (period or datetime.now()).strftime('%Y%m')
    full = os.path.join(base, ymd)
    _ensure_dir(full)
    return full


def _safe_filename(name: str) -> str:
    """剥离文件名中不安全字符。"""
    return ''.join(
        ch if ch.isalnum() or ch in ('-', '_', '.') else '_'
        for ch in (name or '')
    ).strip('_') or 'file'


# ---------------------------------------------------------------------------
# 失败通知
# ---------------------------------------------------------------------------

async def _record_export_failure(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    operator_id: int,
    operator_name: Optional[str],
    reason: str,
) -> None:
    """
    记录 PDF 生成失败：
      1. ``ReconciliationAuditLog`` 写入 action='export_failed'，detail 含原因
      2. 通过通知渠道告知操作人/财务（best-effort，失败不抛）

    注意：本函数自管事务，仅写入审计日志这一行，避免污染调用方事务。
    """
    log = ReconciliationAuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action='export_failed',
        operator_id=operator_id or 0,
        operator_name=operator_name or 'system',
        detail={'kind': 'pdf', 'reason': reason},
    )
    try:
        db.add(log)
        await db.flush()
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.error(
            '[ReconciliationPdfService] 写入失败审计日志失败 '
            'entity={}/{} reason={} err={}',
            entity_type, entity_id, reason, exc,
        )

    # best-effort 通知
    try:
        channel = ReconciliationNotificationService.get_channel()
        recipient = (
            f'user:{operator_id}' if operator_id else 'role:finance'
        )
        subject = f'[PDF生成失败] {entity_type}#{entity_id}'
        body = (
            f'生成 PDF 失败：{entity_type}#{entity_id}\n'
            f'失败原因：{reason}'
        )
        await channel.send(
            recipient,
            subject,
            body,
            metadata={
                'kind': 'pdf_export_failed',
                'entity_type': entity_type,
                'entity_id': entity_id,
                'reason': reason,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            '[ReconciliationPdfService] 失败通知发送失败 '
            'entity={}/{} err={}',
            entity_type, entity_id, exc,
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ReconciliationPdfService:
    """对账 / 结算 PDF 生成服务。"""

    COMPANY_NAME = '委外加工管理平台'

    # ------------------------------------------------------------------
    # 1. 对账单 PDF
    # ------------------------------------------------------------------

    @classmethod
    async def generate_statement_pdf(
        cls,
        db: AsyncSession,
        statement_id: int,
        operator_id: int = 0,
        operator_name: Optional[str] = None,
    ) -> str:
        """
        生成对账单正式 PDF。

        输出文件路径：
          ``DOWNLOAD_PATH/reconciliation/statement/{YYYYMM}/REC-xxx.pdf``

        Args:
            statement_id: 对账单 ID
            operator_id: 操作人ID（用于审计日志/失败通知）
            operator_name: 操作人姓名

        Returns:
            生成的 PDF 绝对路径

        Raises:
            ServiceException: 对账单不存在 / PDF 生成失败
        """
        # 加载数据
        statement = await db.scalar(
            select(ReconciliationStatement).where(
                ReconciliationStatement.id == statement_id
            )
        )
        if not statement:
            reason = f'对账单不存在: id={statement_id}'
            await _record_export_failure(
                db, 'statement', statement_id, operator_id, operator_name, reason,
            )
            raise ServiceException(message=reason)

        line_items = (
            (await db.execute(
                select(ReconciliationLineItem)
                .where(ReconciliationLineItem.statement_id == statement_id)
                .order_by(ReconciliationLineItem.id.asc())
            )).scalars().all()
        )

        supplier = await db.scalar(
            select(EntrustSupplier).where(
                EntrustSupplier.id == statement.supplier_id
            )
        )

        try:
            out_dir = _output_dir(
                'statement',
                datetime.combine(statement.period_end, datetime.min.time()),
            )
            file_name = f'{_safe_filename(statement.statement_no)}.pdf'
            out_path = os.path.abspath(os.path.join(out_dir, file_name))

            cls._render_statement_pdf(
                out_path, statement, line_items, supplier,
            )
        except Exception as exc:
            reason = f'{exc}'
            logger.error(
                '[ReconciliationPdfService] 对账单 PDF 生成失败 '
                'statement_id={} err={} traceback={}',
                statement_id, exc, traceback.format_exc(),
            )
            await _record_export_failure(
                db, 'statement', statement_id, operator_id,
                operator_name, reason,
            )
            raise ServiceException(message=f'对账单 PDF 生成失败: {reason}')

        # 成功审计
        try:
            db.add(ReconciliationAuditLog(
                entity_type='statement',
                entity_id=statement_id,
                action='export',
                operator_id=operator_id or 0,
                operator_name=operator_name or 'system',
                detail={'kind': 'pdf', 'path': out_path},
            ))
            await db.flush()
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            logger.warning(
                '[ReconciliationPdfService] 写入导出审计日志失败 '
                'statement_id={} err={}',
                statement_id, exc,
            )

        logger.info(
            '[ReconciliationPdfService] 对账单 PDF 已生成 '
            'statement_id={} path={}',
            statement_id, out_path,
        )
        return out_path

    # ------------------------------------------------------------------
    # 2. 结算 PDF
    # ------------------------------------------------------------------

    @classmethod
    async def generate_settlement_pdf(
        cls,
        db: AsyncSession,
        settlement_id: int,
        operator_id: int = 0,
        operator_name: Optional[str] = None,
    ) -> str:
        """
        生成结算明细 PDF。

        输出文件路径：
          ``DOWNLOAD_PATH/reconciliation/settlement/{YYYYMM}/SETTLE-{id}-{order_no}.pdf``

        Returns:
            生成的 PDF 绝对路径

        Raises:
            ServiceException: 结算明细不存在 / PDF 生成失败
        """
        settlement = await db.scalar(
            select(SettlementDetail).where(
                SettlementDetail.id == settlement_id
            )
        )
        if not settlement:
            reason = f'结算明细不存在: id={settlement_id}'
            await _record_export_failure(
                db, 'settlement', settlement_id, operator_id,
                operator_name, reason,
            )
            raise ServiceException(message=reason)

        line_items = (
            (await db.execute(
                select(SettlementLineItem)
                .where(SettlementLineItem.settlement_id == settlement_id)
                .order_by(SettlementLineItem.id.asc())
            )).scalars().all()
        )

        supplier = await db.scalar(
            select(EntrustSupplier).where(
                EntrustSupplier.id == settlement.supplier_id
            )
        )

        order = None
        if settlement.order_id is not None:
            order = await db.scalar(
                select(EntrustOutsourceOrder).where(
                    EntrustOutsourceOrder.id == settlement.order_id
                )
            )

        # 关联的支付凭证（related_type=settlement_detail）
        evidences = (
            (await db.execute(
                select(PaymentEvidence)
                .where(
                    PaymentEvidence.related_type == 'settlement_detail',
                    PaymentEvidence.related_id == settlement_id,
                )
                .order_by(PaymentEvidence.id.asc())
            )).scalars().all()
        )

        try:
            out_dir = _output_dir('settlement')
            order_part = _safe_filename(settlement.order_no or f'order{settlement.order_id}')
            file_name = f'SETTLE-{settlement.id}-{order_part}.pdf'
            out_path = os.path.abspath(os.path.join(out_dir, file_name))

            cls._render_settlement_pdf(
                out_path, settlement, line_items, supplier, order, evidences,
            )
        except Exception as exc:
            reason = f'{exc}'
            logger.error(
                '[ReconciliationPdfService] 结算 PDF 生成失败 '
                'settlement_id={} err={} traceback={}',
                settlement_id, exc, traceback.format_exc(),
            )
            await _record_export_failure(
                db, 'settlement', settlement_id, operator_id,
                operator_name, reason,
            )
            raise ServiceException(message=f'结算 PDF 生成失败: {reason}')

        # 成功审计
        try:
            db.add(ReconciliationAuditLog(
                entity_type='settlement',
                entity_id=settlement_id,
                action='export',
                operator_id=operator_id or 0,
                operator_name=operator_name or 'system',
                detail={'kind': 'pdf', 'path': out_path},
            ))
            await db.flush()
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            logger.warning(
                '[ReconciliationPdfService] 写入结算导出审计日志失败 '
                'settlement_id={} err={}',
                settlement_id, exc,
            )

        logger.info(
            '[ReconciliationPdfService] 结算 PDF 已生成 '
            'settlement_id={} path={}',
            settlement_id, out_path,
        )
        return out_path

    # ------------------------------------------------------------------
    # 3. 批量导出
    # ------------------------------------------------------------------

    @classmethod
    async def export_batch_pdf(
        cls,
        db: AsyncSession,
        statement_ids: Iterable[int],
        operator_id: int = 0,
        operator_name: Optional[str] = None,
    ) -> dict:
        """
        批量导出对账单 PDF。单个失败不影响其他对账单生成。

        Args:
            statement_ids: 对账单 ID 集合
            operator_id: 操作人ID
            operator_name: 操作人姓名

        Returns:
            ``{
                'total': N,
                'succeeded': [{'statement_id': X, 'path': '...'}],
                'failed': [{'statement_id': X, 'reason': '...'}],
            }``
        """
        ids = list(dict.fromkeys(int(i) for i in statement_ids if i is not None))
        succeeded: list[dict] = []
        failed: list[dict] = []

        for sid in ids:
            try:
                path = await cls.generate_statement_pdf(
                    db, sid, operator_id=operator_id,
                    operator_name=operator_name,
                )
                succeeded.append({'statement_id': sid, 'path': path})
            except ServiceException as exc:
                failed.append({'statement_id': sid, 'reason': exc.message})
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    '[ReconciliationPdfService] 批量导出意外错误 '
                    'statement_id={} err={}',
                    sid, exc,
                )
                failed.append({'statement_id': sid, 'reason': str(exc)})

        result = {
            'total': len(ids),
            'succeeded': succeeded,
            'failed': failed,
        }
        logger.info(
            '[ReconciliationPdfService] 批量导出完成 total={} ok={} fail={}',
            result['total'], len(succeeded), len(failed),
        )
        return result

    # ==================================================================
    # 渲染：对账单
    # ==================================================================

    @classmethod
    def _render_statement_pdf(
        cls,
        out_path: str,
        statement: ReconciliationStatement,
        line_items: list[ReconciliationLineItem],
        supplier: Optional[EntrustSupplier],
    ) -> None:
        """构造并写入对账单 PDF 文件。"""
        # 延迟导入，确保字体已注册
        font = _ensure_font_registered()

        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        styles = cls._build_styles(font)

        doc = SimpleDocTemplate(
            out_path,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            title=f'对账单 {statement.statement_no}',
            author=cls.COMPANY_NAME,
        )

        story: list = []
        # 公司信息 / 标题
        story.append(Paragraph(cls.COMPANY_NAME, styles['CompanyHeader']))
        story.append(Paragraph('对　账　单', styles['DocTitle']))
        story.append(Spacer(1, 0.4 * cm))

        # 对账单元信息
        supplier_name = supplier.name if supplier else f'供应商#{statement.supplier_id}'
        meta_data = [
            ['对账单编号', _safe_str(statement.statement_no),
             '供应商', _safe_str(supplier_name)],
            ['对账周期',
             f'{statement.period_start} ~ {statement.period_end}',
             '汇总金额',
             f'¥ {_format_money(statement.total_amount)}'],
            ['确认状态', _safe_str(statement.confirmation_status),
             '生成时间',
             _safe_str(
                 statement.created_at.strftime('%Y-%m-%d %H:%M:%S')
                 if statement.created_at else ''
             )],
        ]
        meta_table = Table(
            meta_data,
            colWidths=[2.5 * cm, 5.5 * cm, 2.5 * cm, 5.5 * cm],
        )
        meta_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f5f7fa')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f5f7fa')),
            ('BOX', (0, 0), (-1, -1), 0.4, colors.grey),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 0.6 * cm))

        # 行项明细表
        story.append(Paragraph('明细行项', styles['SectionHeader']))
        story.append(Spacer(1, 0.2 * cm))

        header_row = [
            '序号', '委外单号', '工序', '零件编号',
            '零件名称', '单价', '数量', '行项金额',
        ]
        body_rows = []
        for idx, li in enumerate(line_items, start=1):
            body_rows.append([
                str(idx),
                _safe_str(li.order_no),
                _safe_str(li.process_name),
                _safe_str(li.part_no),
                _safe_str(li.part_name),
                _format_money(li.unit_price)
                if li.unit_price is not None else '',
                str(li.quantity) if li.quantity is not None else '',
                _format_money(li.total_amount)
                if li.total_amount is not None else '',
            ])

        # 末行：合计
        body_rows.append([
            '', '', '', '', '合计',
            '', '', f'¥ {_format_money(statement.total_amount)}',
        ])

        items_table = Table(
            [header_row] + body_rows,
            colWidths=[
                1.2 * cm, 3.0 * cm, 2.4 * cm, 2.6 * cm,
                3.6 * cm, 2.0 * cm, 1.4 * cm, 2.4 * cm,
            ],
            repeatRows=1,
        )
        items_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dde6f0')),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (5, 1), (-1, -1), 'RIGHT'),  # 数字右对齐
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f5f7fa')),
            ('FONTSIZE', (0, -1), (-1, -1), 10),
        ]))
        story.append(items_table)
        story.append(Spacer(1, 1.0 * cm))

        # 公司印章 + 甲方/乙方签名栏（Requirement 7.4 / 11.5）
        story.append(cls._build_seal_signature_block(font))

        # 页脚说明
        story.append(Spacer(1, 0.6 * cm))
        story.append(Paragraph(
            '注：本对账单一式两份，甲乙双方核对无误后签字盖章生效。',
            styles['Footnote'],
        ))

        doc.build(story)

    # ==================================================================
    # 渲染：结算明细
    # ==================================================================

    @classmethod
    def _render_settlement_pdf(
        cls,
        out_path: str,
        settlement: SettlementDetail,
        line_items: list[SettlementLineItem],
        supplier: Optional[EntrustSupplier],
        order: Optional[EntrustOutsourceOrder],
        evidences: list[PaymentEvidence],
    ) -> None:
        """构造并写入结算明细 PDF 文件。"""
        font = _ensure_font_registered()

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Image,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        styles = cls._build_styles(font)

        doc = SimpleDocTemplate(
            out_path,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            title=f'结算单 {settlement.order_no or settlement.id}',
            author=cls.COMPANY_NAME,
        )

        story: list = []
        story.append(Paragraph(cls.COMPANY_NAME, styles['CompanyHeader']))
        story.append(Paragraph('订单结算单', styles['DocTitle']))
        story.append(Spacer(1, 0.4 * cm))

        # 订单信息头（Requirement 11.2）
        supplier_name = supplier.name if supplier else f'供应商#{settlement.supplier_id}'
        order_date = ''
        if order is not None:
            for attr in ('actual_delivery_date', 'created_at'):
                v = getattr(order, attr, None)
                if v is not None:
                    try:
                        order_date = v.strftime('%Y-%m-%d')
                    except Exception:  # noqa: BLE001
                        order_date = str(v)
                    break

        header_data = [
            ['订单编号', _safe_str(settlement.order_no),
             '供应商', _safe_str(supplier_name)],
            ['日期', _safe_str(order_date) or
             (settlement.created_at.strftime('%Y-%m-%d')
              if settlement.created_at else ''),
             '结算状态', _safe_str(settlement.status)],
            ['关联对账单',
             _safe_str(settlement.statement_id) if settlement.statement_id else '—',
             '净利润',
             f'¥ {_format_money(settlement.net_profit)}'],
        ]
        header_table = Table(
            header_data,
            colWidths=[2.5 * cm, 5.5 * cm, 2.5 * cm, 5.5 * cm],
        )
        header_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f5f7fa')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f5f7fa')),
            ('BOX', (0, 0), (-1, -1), 0.4, colors.grey),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 0.6 * cm))

        # 按 item_type 分组（Requirement 11.2）
        groups: dict[str, list[SettlementLineItem]] = {
            'process_fee': [],
            'logistics': [],
            'deduction': [],
            're_shipment': [],
            'rework': [],
            'customer_payment': [],
        }
        # 同时把未知类型作为 "其他" 单独显示
        others: list[SettlementLineItem] = []
        for li in line_items:
            if li.item_type in groups:
                groups[li.item_type].append(li)
            else:
                others.append(li)

        section_definitions: list[tuple[str, str, list[SettlementLineItem]]] = [
            ('加工费用明细', 'process_fee', groups['process_fee']),
            ('物流费用', 'logistics', groups['logistics']),
            ('扣款明细', 'deduction', groups['deduction']),
            ('补发费用', 're_shipment', groups['re_shipment']),
            ('返工/重新加工费用', 'rework', groups['rework']),
            ('客户付款金额', 'customer_payment', groups['customer_payment']),
        ]
        if others:
            section_definitions.append(('其他费用', 'other', others))

        for title, _key, items in section_definitions:
            story.append(Paragraph(title, styles['SectionHeader']))
            story.append(Spacer(1, 0.15 * cm))
            story.append(cls._build_section_table(items, font))
            story.append(Spacer(1, 0.4 * cm))

        # 汇总
        story.append(Paragraph('汇总', styles['SectionHeader']))
        story.append(Spacer(1, 0.15 * cm))
        summary_table = Table(
            [
                ['总成本', f'¥ {_format_money(settlement.total_cost)}'],
                ['客户付款', f'¥ {_format_money(settlement.customer_payment)}'],
                ['净利润', f'¥ {_format_money(settlement.net_profit)}'],
            ],
            colWidths=[4 * cm, 12 * cm],
        )
        summary_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f5f7fa')),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.6 * cm))

        # 公司印章 + 签名栏
        story.append(cls._build_seal_signature_block(font))

        # 支付凭证附录（Requirement 11.3 / 12.4）
        if evidences:
            story.append(PageBreak())
            story.append(Paragraph('支付凭证附录', styles['SectionHeader']))
            story.append(Spacer(1, 0.3 * cm))

            # 凭证清单
            evidence_rows = [
                ['序号', '文件名', '大小(字节)', '上传时间'],
            ]
            for idx, ev in enumerate(evidences, start=1):
                upload_time = (
                    ev.created_at.strftime('%Y-%m-%d %H:%M:%S')
                    if ev.created_at else ''
                )
                evidence_rows.append([
                    str(idx),
                    _safe_str(ev.file_name),
                    str(ev.file_size) if ev.file_size is not None else '',
                    upload_time,
                ])
            ev_table = Table(
                evidence_rows,
                colWidths=[1.2 * cm, 9 * cm, 2.5 * cm, 4.5 * cm],
                repeatRows=1,
            )
            ev_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), font),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dde6f0')),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('ALIGN', (0, 1), (0, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(ev_table)
            story.append(Spacer(1, 0.4 * cm))

            # 图片凭证（jpg/png）嵌入（Requirement 12.4）
            for ev in evidences:
                if not _is_image_extension(ev.file_name or ''):
                    # 非图片仅在清单中记录
                    continue
                abs_path = _resolve_evidence_abs_path(ev.file_path)
                if not abs_path:
                    story.append(Paragraph(
                        f'[凭证文件未找到: {_safe_str(ev.file_name)}]',
                        styles['Footnote'],
                    ))
                    story.append(Spacer(1, 0.2 * cm))
                    continue
                try:
                    img = Image(abs_path)
                    # 缩放到不超过 14cm 宽度，保持比例
                    iw, ih = img.imageWidth, img.imageHeight
                    if iw <= 0 or ih <= 0:
                        raise ValueError('invalid image dimensions')
                    max_w = 14 * cm
                    max_h = 18 * cm
                    scale = min(max_w / iw, max_h / ih, 1.0)
                    img.drawWidth = iw * scale
                    img.drawHeight = ih * scale
                    story.append(Paragraph(
                        f'凭证: {_safe_str(ev.file_name)}', styles['EvidenceCaption'],
                    ))
                    story.append(Spacer(1, 0.1 * cm))
                    story.append(img)
                    story.append(Spacer(1, 0.4 * cm))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        '[ReconciliationPdfService] 嵌入凭证图片失败 '
                        'evidence_id={} path={} err={}',
                        ev.id, abs_path, exc,
                    )
                    story.append(Paragraph(
                        f'[凭证图片加载失败: {_safe_str(ev.file_name)}]',
                        styles['Footnote'],
                    ))
                    story.append(Spacer(1, 0.2 * cm))

        doc.build(story)

    # ==================================================================
    # 通用：样式 / 子组件
    # ==================================================================

    @staticmethod
    def _build_styles(font: str):
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

        base = getSampleStyleSheet()
        styles = {
            'CompanyHeader': ParagraphStyle(
                'CompanyHeader', parent=base['Normal'],
                fontName=font, fontSize=10, alignment=TA_CENTER,
                textColor=colors.grey, spaceAfter=2,
            ),
            'DocTitle': ParagraphStyle(
                'DocTitle', parent=base['Title'],
                fontName=font, fontSize=18, alignment=TA_CENTER,
                spaceBefore=2, spaceAfter=6, leading=22,
            ),
            'SectionHeader': ParagraphStyle(
                'SectionHeader', parent=base['Heading3'],
                fontName=font, fontSize=12, alignment=TA_LEFT,
                textColor=colors.HexColor('#274472'),
                spaceBefore=4, spaceAfter=2,
            ),
            'Footnote': ParagraphStyle(
                'Footnote', parent=base['Normal'],
                fontName=font, fontSize=9, alignment=TA_LEFT,
                textColor=colors.grey,
            ),
            'EvidenceCaption': ParagraphStyle(
                'EvidenceCaption', parent=base['Normal'],
                fontName=font, fontSize=9, alignment=TA_LEFT,
                textColor=colors.HexColor('#274472'),
            ),
            'SignatureLabel': ParagraphStyle(
                'SignatureLabel', parent=base['Normal'],
                fontName=font, fontSize=11, alignment=TA_LEFT,
                spaceAfter=2,
            ),
        }
        return styles

    @staticmethod
    def _build_section_table(items: list[SettlementLineItem], font: str):
        """渲染一个结算分组的表格（无内容时显示一行 ‘—’）。"""
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import Table, TableStyle

        rows = [['序号', '描述', '金额']]
        if not items:
            rows.append(['', '（无）', '—'])
            subtotal: Decimal = Decimal('0')
        else:
            subtotal = Decimal('0')
            for idx, li in enumerate(items, start=1):
                amount = _to_decimal(li.amount)
                # 成本项保持正数显示；客户付款 / is_income=True 在金额前加 '+'
                amount_str = (
                    f'+ {_format_money(amount)}'
                    if bool(li.is_income) else _format_money(amount)
                )
                rows.append([str(idx), _safe_str(li.description), amount_str])
                # 小计：不论收入/支出按 amount 求和
                subtotal += amount

        rows.append(['', '小计', _format_money(subtotal)])

        table = Table(
            rows,
            colWidths=[1.5 * cm, 11.5 * cm, 4 * cm],
            repeatRows=1,
        )
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dde6f0')),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),
            ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f5f7fa')),
            ('FONTSIZE', (0, -1), (-1, -1), 10),
        ]))
        return table

    @staticmethod
    def _build_seal_signature_block(font: str):
        """
        甲方 / 乙方签名 + 公司印章区域（Requirement 7.4 / 11.5）。

        采用 2 列布局，左甲方右乙方；每列内含 “签字”、“盖章” 两行预留空白。
        """
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, Table, TableStyle

        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.styles import ParagraphStyle

        label_style = ParagraphStyle(
            'SealLabel',
            fontName=font, fontSize=11, alignment=TA_LEFT, leading=14,
        )
        sub_style = ParagraphStyle(
            'SealSub',
            fontName=font, fontSize=10, alignment=TA_LEFT, leading=22,
            textColor=colors.HexColor('#444'),
        )

        cell_a = [
            Paragraph('甲方（委托方）', label_style),
            Paragraph('授权代表签字：______________________', sub_style),
            Paragraph('公司盖章：', sub_style),
            Paragraph('日期：______年______月______日', sub_style),
        ]
        cell_b = [
            Paragraph('乙方（供应商）', label_style),
            Paragraph('授权代表签字：______________________', sub_style),
            Paragraph('公司盖章：', sub_style),
            Paragraph('日期：______年______月______日', sub_style),
        ]
        table = Table(
            [[cell_a, cell_b]],
            colWidths=[8 * cm, 8 * cm],
        )
        table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 30),  # 留出印章空间
            ('BOX', (0, 0), (-1, -1), 0.4, colors.grey),
            ('LINEAFTER', (0, 0), (0, 0), 0.4, colors.grey),
        ]))
        return table


__all__ = ['ReconciliationPdfService']
