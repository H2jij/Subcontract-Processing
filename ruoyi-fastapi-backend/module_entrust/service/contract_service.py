"""
委外加工 — 合同生成 & 邮件分发 Service
=========================================
功能：
  1. 从数据库读取询价单 + 加工方信息，自动填充 DOCX 合同模板
  2. 通过 SMTP 将合同附件发送给加工方联系邮箱
  3. 持久化发送历史记录（成功/失败/时间/Message-ID）
  4. 甲方信息优先从 sys_config 读，回落到 .env CompanyConfig
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.env import SmtpConfig, CompanyConfig
from contract_toolkit.docx_filler import DocxFiller
from contract_toolkit.email_sender import EmailSender
from module_entrust.entity.do.entrust_do import (
    EntrustOutsourceRequest,
    EntrustSupplier,
    EntrustInvitation,
    EntrustContractRecord,
)

# ---------------------------------------------------------------------------
# 模板路径
# ---------------------------------------------------------------------------
_BACKEND_ROOT = Path(__file__).parent.parent.parent   # ruoyi-fastapi-backend/
_PROJECT_ROOT = _BACKEND_ROOT.parent                   # Subcontract-Processing/

TEMPLATE_DIR = _PROJECT_ROOT / "律师修订框架合同"

TEMPLATE_MAP: dict[str, str] = {
    "钢料":   "律师修订版_年度采购框架合同（钢料).docx",
    "全工序": "律师修订版_年度采购框架合同（全工序加工）.docx",
    "五金":   "律师修订版_年度采购框架合同(五金加工）.docx",
}
DEFAULT_TEMPLATE = "律师修订版_年度采购框架合同（钢料).docx"

# sys_config 键名 → CompanyConfig 属性名
_PARTY_A_CONFIG_MAP = {
    "contract:party_a:name":        "company_name",        # 甲方名称（合同抬头用，非占位符）
    "contract:party_a:address":     "company_address",     # 甲方地址（合同抬头用，非占位符）
    "contract:party_a:legal_rep":   "company_legal_rep",   # 甲方法定代表人/授权负责人
    "contract:party_a:contact":     "company_contact",     # 甲方联系方式
    "contract:party_a:credit_code": "company_credit_code", # 甲方统一社会信用代码
    "contract:party_a:pkg_guide_no":"company_pkg_guide_no",# 包装指导书编号
}

_PARTY_A_PLACEHOLDER_MAP = {
    # sys_config attr   → [DOCX 占位符, ...]
    "company_legal_rep":   ["甲方法定代表人", "甲方签字"],
    "company_contact":     ["甲方联系方式"],
    "company_credit_code": ["甲方信用代码"],
    "company_pkg_guide_no":["包装指导书编号"],
    # name/address 不是 DOCX 占位符，供邮件正文使用
}


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _pick_template(category: Optional[str]) -> Path:
    """根据供应商分类选择合同模板。"""
    if category:
        for key, filename in TEMPLATE_MAP.items():
            if key in category:
                return TEMPLATE_DIR / filename
    return TEMPLATE_DIR / DEFAULT_TEMPLATE


def _format_date(d: Optional[date | datetime]) -> tuple[str, str, str]:
    """将日期拆为 (年, 月, 日)，None 时返回三个空串。"""
    if d is None:
        return "", "", ""
    if isinstance(d, datetime):
        d = d.date()
    return str(d.year), f"{d.month:02d}", f"{d.day:02d}"


async def _get_party_a_config(db: AsyncSession) -> dict[str, str]:
    """
    从 sys_config 读甲方信息，缺失时回落到 CompanyConfig（.env）。
    返回 {DOCX占位符名: 值} 字典，以及 _raw 键存放原始数据（名称/地址）。
    """
    try:
        from module_admin.entity.do.config_do import SysConfig
        cfg_stmt = select(SysConfig).where(
            SysConfig.config_key.in_(list(_PARTY_A_CONFIG_MAP.keys()))
        )
        rows = (await db.execute(cfg_stmt)).scalars().all()
        db_cfg = {r.config_key: r.config_value for r in rows}
    except Exception as e:
        logger.warning(f"[ContractService] 读取 sys_config 甲方信息失败，使用 .env 回落: {e}")
        db_cfg = {}

    result: dict[str, str] = {}

    for cfg_key, attr_name in _PARTY_A_CONFIG_MAP.items():
        value = db_cfg.get(cfg_key) or getattr(CompanyConfig, attr_name, "") or ""

        # 写入 DOCX 占位符
        placeholders = _PARTY_A_PLACEHOLDER_MAP.get(attr_name, [])
        for ph in placeholders:
            result[ph] = value or "【待填写】"

        # 保存原始值供邮件正文使用
        result[f"_raw_{attr_name}"] = value

    return result


def _build_field_values(
    inquiry: EntrustOutsourceRequest,
    supplier: EntrustSupplier,
    party_a: dict[str, str],
    extra_values: Optional[dict[str, str]] = None,
) -> tuple[dict[str, str], list[str]]:
    """
    组装占位符 → 值 映射，同时返回缺失字段列表。
    Returns: (values_dict, missing_fields)
    """
    today = date.today()
    sign_year, sign_month, sign_day = str(today.year), f"{today.month:02d}", f"{today.day:02d}"

    start_y, start_m, start_d = _format_date(inquiry.inquiry_date or today)

    # 合同止期：缺失时用【待确认】
    missing: list[str] = []
    if inquiry.delivery_date:
        end_y, end_m, end_d = _format_date(inquiry.delivery_date)
    else:
        end_y, end_m, end_d = "【待确认】", "【待确认】", "【待确认】"
        missing += ["合同期限_止_年", "合同期限_止_月", "合同期限_止_日"]

    values: dict[str, str] = {
        # ── 乙方信息（从供应商档案自动提取）──────────────────────────
        "乙方名称":         supplier.name or "",
        "乙方地址":         f"{supplier.province or ''}{supplier.city or ''}{supplier.address or ''}".strip() or "【待填写】",
        "乙方法定代表人":   supplier.legal_rep or supplier.contact_name or "【待填写】",
        "乙方联系电话":     supplier.contact_phone or "【待填写】",
        "统一社会信用代码": supplier.credit_code or "【待填写】",

        # ── 合同期限 ─────────────────────────────────────────────────
        "合同期限_起_年": start_y,
        "合同期限_起_月": start_m,
        "合同期限_起_日": start_d,
        "合同期限_止_年": end_y,
        "合同期限_止_月": end_m,
        "合同期限_止_日": end_d,

        # ── 签订日期 ─────────────────────────────────────────────────
        "签订日期_年": sign_year,
        "签订日期_月": sign_month,
        "签订日期_日": sign_day,

        # ── 金额（询价阶段通常无固定额度）───────────────────────────
        "合同额度": "【待填写】",

        # ── 乙方签署区（对方填写）────────────────────────────────────
        "乙方印章":        "【待盖章】",
        "乙方签字":        "【待签字】",
        "乙方签字日期_年": "",
        "乙方签字日期_月": "",
        "乙方签字日期_日": "",
    }

    # 合并甲方信息
    values.update(party_a)

    # 调用方额外覆盖
    if extra_values:
        values.update(extra_values)

    return values, missing


async def _save_record(
    db: AsyncSession,
    inquiry_id: int,
    supplier_id: int,
    recipient_email: str,
    status: str,
    smtp_message_id: Optional[str],
    error_message: Optional[str],
    created_by: int,
) -> int:
    """持久化一条发送记录，返回记录 ID。"""
    record = EntrustContractRecord(
        inquiry_id=inquiry_id,
        supplier_id=supplier_id,
        recipient_email=recipient_email,
        status=status,
        smtp_message_id=smtp_message_id,
        error_message=error_message,
        sent_at=datetime.now(),
        created_by=created_by,
    )
    db.add(record)
    await db.flush()
    await db.commit()
    return record.id


def _build_sender() -> EmailSender:
    """构建 EmailSender 实例，启动时检查 SMTP 配置完整性。"""
    if not SmtpConfig.smtp_host or not SmtpConfig.smtp_user or not SmtpConfig.smtp_password:
        logger.warning("[ContractService] SMTP 配置不完整，合同邮件功能不可用")
    return EmailSender(
        host=SmtpConfig.smtp_host,
        port=SmtpConfig.smtp_port,
        user=SmtpConfig.smtp_user,
        password=SmtpConfig.smtp_password,
        sender_name=SmtpConfig.smtp_sender_name,
        debug=SmtpConfig.smtp_debug,
    )


# ---------------------------------------------------------------------------
# 主服务类
# ---------------------------------------------------------------------------

class ContractService:
    """合同生成与邮件分发服务。"""

    @staticmethod
    async def send_contract(
        db: AsyncSession,
        inquiry_id: int,
        supplier_id: int,
        recipient_email: Optional[str] = None,
        extra_values: Optional[dict[str, str]] = None,
        created_by: int = 0,
    ) -> dict:
        """
        填充合同 DOCX 并发送给指定加工方，记录发送结果。

        recipient_email 为空时自动从 Supplier.contact_email 获取。

        Returns:
            {"success": bool, "message": str, "smtp_message_id": str|None,
             "record_id": int|None, "missing_fields": list[str]}
        """
        # 1. 读取数据
        inquiry = await db.scalar(
            select(EntrustOutsourceRequest).where(EntrustOutsourceRequest.id == inquiry_id)
        )
        if not inquiry:
            return {"success": False, "message": f"询价单 {inquiry_id} 不存在",
                    "smtp_message_id": None, "record_id": None, "missing_fields": []}

        supplier = await db.scalar(
            select(EntrustSupplier).where(EntrustSupplier.id == supplier_id)
        )
        if not supplier:
            return {"success": False, "message": f"加工方 {supplier_id} 不存在",
                    "smtp_message_id": None, "record_id": None, "missing_fields": []}

        # 2. 确定收件邮箱
        email = recipient_email or supplier.contact_email
        if not email:
            return {"success": False,
                    "message": "供应商邮箱未配置，无法发送合同（请在供应商档案中填写联系邮箱，或在请求中传入 recipient_email）",
                    "smtp_message_id": None, "record_id": None, "missing_fields": []}

        # 3. 选模板
        template_path = _pick_template(supplier.category)
        if not template_path.exists():
            return {"success": False, "message": f"合同模板文件不存在：{template_path}",
                    "smtp_message_id": None, "record_id": None, "missing_fields": []}

        # 4. 读甲方信息
        party_a = await _get_party_a_config(db)

        # 5. 填充 DOCX
        try:
            filler = DocxFiller(str(template_path))
            values, missing_fields = _build_field_values(inquiry, supplier, party_a, extra_values)
            docx_bytes = filler.fill(values)
            logger.info(
                f"[ContractService] 合同填充完成 inquiry={inquiry_id} supplier={supplier.name} "
                f"template={template_path.name} size={len(docx_bytes)//1024}KB "
                f"converted={filler.is_converted} missing={missing_fields}"
            )
        except Exception as e:
            logger.error(f"[ContractService] DOCX 填充失败: {e}")
            record_id = await _save_record(
                db, inquiry_id, supplier_id, email, "failed", None, f"填充失败: {e}", created_by
            )
            return {"success": False, "message": f"合同填充失败：{e}",
                    "smtp_message_id": None, "record_id": record_id, "missing_fields": []}

        # 6. 构建邮件
        attachment_name = f"年度采购框架合同_{supplier.name}_{inquiry.order_no or inquiry_id}.docx"
        sender = _build_sender()
        company_name = party_a.get("_raw_company_name") or SmtpConfig.smtp_sender_name
        html = sender.wrap_html(
            title=f"年度采购框架合同确认 — {inquiry.title}",
            body=f"""
            <p>尊敬的 <strong>{supplier.name}</strong>，您好：</p>
            <p>请查阅附件中的年度采购框架合同，并在 <strong>72 小时</strong>内回复确认意见。</p>
            <table class="info">
              <tr><td>询价单号</td><td><strong>{inquiry.order_no or '—'}</strong></td></tr>
              <tr><td>询价标题</td><td>{inquiry.title}</td></tr>
              <tr><td>加工方</td><td>{supplier.name}</td></tr>
              <tr><td>联系人</td><td>{supplier.contact_name or '—'}</td></tr>
              <tr><td>计划交付日期</td><td>{inquiry.delivery_date or '待确认'}</td></tr>
            </table>
            <div class="warn">⚠️ 请核对合同内容，如有异议请及时联系我司（{company_name}）。</div>
            """,
            company=company_name,
        )

        # 7. 发送
        send_result = sender.send(
            to=email,
            subject=f"【请确认】年度采购框架合同 — {inquiry.title}",
            html=html,
            attachment_bytes=docx_bytes,
            attachment_name=attachment_name,
        )

        # 8. 持久化记录
        status = "sent" if send_result["success"] else "failed"
        record_id = await _save_record(
            db, inquiry_id, supplier_id, email, status,
            send_result.get("smtp_message_id"),
            None if send_result["success"] else send_result.get("error"),
            created_by,
        )

        if send_result["success"]:
            logger.info(
                f"[ContractService] 发送成功 to={email} supplier={supplier.name} "
                f"record_id={record_id}"
            )
        else:
            logger.error(
                f"[ContractService] 发送失败 to={email} error={send_result.get('error')} "
                f"record_id={record_id}"
            )

        return {
            "success": send_result["success"],
            "message": "发送成功" if send_result["success"] else send_result.get("error", "发送失败"),
            "smtp_message_id": send_result.get("smtp_message_id"),
            "record_id": record_id,
            "missing_fields": missing_fields,
        }

    @staticmethod
    async def batch_send_contract(
        db: AsyncSession,
        inquiry_id: int,
        email_map: Optional[dict[int, str]] = None,
        extra_values: Optional[dict[str, str]] = None,
        created_by: int = 0,
    ) -> dict:
        """
        批量向询价单所有受邀加工方发送合同。
        email_map 为覆盖映射 {supplier_id: email}，留空则从供应商档案自动获取。
        单个失败不影响其他供应商。
        """
        invitations = (
            await db.scalars(
                select(EntrustInvitation).where(EntrustInvitation.request_id == inquiry_id)
            )
        ).all()

        results = []
        for inv in invitations:
            # 获取供应商名称（用于响应）
            sup = await db.scalar(
                select(EntrustSupplier).where(EntrustSupplier.id == inv.supplier_id)
            )
            supplier_name = sup.name if sup else f"supplier_{inv.supplier_id}"

            # email_map 中有则覆盖，否则用档案邮箱
            override_email = (email_map or {}).get(inv.supplier_id)

            r = await ContractService.send_contract(
                db=db,
                inquiry_id=inquiry_id,
                supplier_id=inv.supplier_id,
                recipient_email=override_email,
                extra_values=extra_values,
                created_by=created_by,
            )
            results.append({
                "supplier_id": inv.supplier_id,
                "supplier_name": supplier_name,
                "success": r["success"],
                "recipient_email": override_email or (sup.contact_email if sup else None),
                "record_id": r.get("record_id"),
                "error": None if r["success"] else r["message"],
                "missing_fields": r.get("missing_fields", []),
            })

        success_count = sum(1 for r in results if r["success"])
        return {
            "success_count": success_count,
            "total": len(results),
            "results": results,
        }

    @staticmethod
    async def get_contract_records(db: AsyncSession, inquiry_id: int) -> list[dict]:
        """获取询价单的所有合同发送历史，按时间降序。"""
        stmt = (
            select(EntrustContractRecord, EntrustSupplier.name)
            .outerjoin(EntrustSupplier, EntrustContractRecord.supplier_id == EntrustSupplier.id)
            .where(EntrustContractRecord.inquiry_id == inquiry_id)
            .order_by(EntrustContractRecord.sent_at.desc())
        )
        rows = (await db.execute(stmt)).all()
        return [
            {
                "id": rec.id,
                "inquiry_id": rec.inquiry_id,
                "supplier_id": rec.supplier_id,
                "supplier_name": supplier_name,
                "recipient_email": rec.recipient_email,
                "status": rec.status,
                "smtp_message_id": rec.smtp_message_id,
                "error_message": rec.error_message,
                "sent_at": rec.sent_at.isoformat() if rec.sent_at else None,
                "created_by": rec.created_by,
                "created_at": rec.created_at.isoformat() if rec.created_at else None,
            }
            for rec, supplier_name in rows
        ]

    @staticmethod
    async def get_contract_record(db: AsyncSession, record_id: int) -> Optional[dict]:
        """获取单条发送记录详情。"""
        stmt = (
            select(EntrustContractRecord, EntrustSupplier.name)
            .outerjoin(EntrustSupplier, EntrustContractRecord.supplier_id == EntrustSupplier.id)
            .where(EntrustContractRecord.id == record_id)
        )
        row = (await db.execute(stmt)).one_or_none()
        if not row:
            return None
        rec, supplier_name = row
        return {
            "id": rec.id,
            "inquiry_id": rec.inquiry_id,
            "supplier_id": rec.supplier_id,
            "supplier_name": supplier_name,
            "recipient_email": rec.recipient_email,
            "status": rec.status,
            "smtp_message_id": rec.smtp_message_id,
            "error_message": rec.error_message,
            "sent_at": rec.sent_at.isoformat() if rec.sent_at else None,
            "created_by": rec.created_by,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
        }

    @staticmethod
    def generate_docx_only(
        inquiry: EntrustOutsourceRequest,
        supplier: EntrustSupplier,
        party_a: Optional[dict[str, str]] = None,
        extra_values: Optional[dict[str, str]] = None,
    ) -> tuple[bytes, str]:
        """仅生成 DOCX 字节流（预览/下载用），不发邮件不写记录。"""
        template_path = _pick_template(supplier.category)
        if not template_path.exists():
            raise FileNotFoundError(f"合同模板不存在：{template_path}")

        filler = DocxFiller(str(template_path))
        values, _ = _build_field_values(inquiry, supplier, party_a or {}, extra_values)
        docx_bytes = filler.fill(values)
        filename = f"年度采购框架合同_{supplier.name}_{inquiry.order_no or inquiry.id}.docx"
        return docx_bytes, filename
