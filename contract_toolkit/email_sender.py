"""
email_sender.py — 独立邮件发送模块
====================================
无任何数据库依赖，直接传参使用。

支持：
  - 163 / QQ / Gmail / 企业 SMTP
  - SSL（465）和 STARTTLS（587）自动切换
  - HTML 正文 + 文件附件（字节流或文件路径）
  - DEBUG 模式（不真实发送，只打印日志）

用法：
    from contract_toolkit.email_sender import EmailSender

    sender = EmailSender(
        host="smtp.163.com",
        port=465,
        user="you@163.com",
        password="your_auth_code",
        sender_name="青岛瑞利杰金属有限公司",  # 可选显示名
        debug=False,
    )

    # 发送纯 HTML 邮件
    result = sender.send(
        to="partner@example.com",
        subject="【请确认】年度采购框架合同",
        html=sender.wrap_html("合同确认", "<p>请查阅附件并确认。</p>"),
    )

    # 发送带附件的邮件（文件路径）
    result = sender.send(
        to="partner@example.com",
        subject="合同文件",
        html="<p>请查阅附件。</p>",
        attachment_path="path/to/contract.docx",
    )

    # 发送带附件的邮件（字节流，无需写入磁盘）
    result = sender.send(
        to="partner@example.com",
        subject="合同文件",
        html="<p>请查阅附件。</p>",
        attachment_bytes=docx_bytes,
        attachment_name="合同.docx",
    )

    print(result)
    # {"success": True, "smtp_message_id": "...", "error": None}
"""
from __future__ import annotations

import logging
import smtplib
import uuid
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class EmailSender:
    """SMTP 邮件发送器，支持 SSL/STARTTLS，可发送 HTML + 附件。"""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        from_addr: Optional[str] = None,
        sender_name: str = "",
        debug: bool = False,
    ):
        """
        Args:
            host:        SMTP 服务器地址，如 smtp.163.com
            port:        SMTP 端口，465（SSL）或 587（STARTTLS）
            user:        发件邮箱地址
            password:    邮箱授权码（不是登录密码）
            from_addr:   发件地址（默认同 user）
            sender_name: 发件方显示名，如"青岛瑞利杰金属有限公司"
            debug:       True 时只打印日志，不真实发送
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_addr = from_addr or user
        self.sender_name = sender_name
        self.debug = debug

    # ──────────────────────────────────────────────────────────────────
    # 核心发送方法
    # ──────────────────────────────────────────────────────────────────

    def send(
        self,
        to: str | list[str],
        subject: str,
        html: str,
        attachment_path: Optional[str] = None,
        attachment_bytes: Optional[bytes] = None,
        attachment_name: Optional[str] = None,
    ) -> dict:
        """
        发送一封邮件。

        Args:
            to:               收件人邮箱（字符串或列表）
            subject:          邮件主题
            html:             HTML 正文
            attachment_path:  附件文件路径（与 attachment_bytes 二选一）
            attachment_bytes: 附件字节流（不写磁盘直接发送）
            attachment_name:  附件显示文件名

        Returns:
            {"success": bool, "smtp_message_id": str|None, "error": str|None}
        """
        recipients = [to] if isinstance(to, str) else to

        if self.debug:
            logger.info(f"[EMAIL DEBUG] To: {recipients} | Subject: {subject}")
            logger.info(f"[EMAIL DEBUG] Body: {html[:200]}")
            return {"success": True, "smtp_message_id": f"<debug-{uuid.uuid4().hex[:8]}@debug>", "error": None}

        # ── 构建邮件 ──────────────────────────────────────────────────
        msg = MIMEMultipart("mixed")
        from_header = f"{self.sender_name} <{self.from_addr}>" if self.sender_name else self.from_addr
        msg["From"] = from_header
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.attach(MIMEText(html, "html", "utf-8"))

        # 文件路径附件
        if attachment_path:
            try:
                path = Path(attachment_path)
                if path.exists():
                    with path.open("rb") as f:
                        data = f.read()
                    name = attachment_name or path.name
                    part = MIMEApplication(data)
                    part.add_header("Content-Disposition", "attachment",
                                    filename=("utf-8", "", name))
                    msg.attach(part)
            except Exception as e:
                logger.warning(f"[EmailSender] Failed to attach file {attachment_path}: {e}")

        # 字节流附件
        if attachment_bytes and attachment_name:
            part = MIMEApplication(attachment_bytes)
            part.add_header("Content-Disposition", "attachment",
                            filename=("utf-8", "", attachment_name))
            msg.attach(part)

        # ── 发送 ──────────────────────────────────────────────────────
        try:
            if self.port == 465:
                with smtplib.SMTP_SSL(self.host, self.port, timeout=15) as smtp:
                    smtp.ehlo()
                    smtp.login(self.user, self.password)
                    smtp.sendmail(self.from_addr, recipients, msg.as_string())
            else:
                with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.login(self.user, self.password)
                    smtp.sendmail(self.from_addr, recipients, msg.as_string())

            smtp_id = msg.get("Message-ID") or f"<{uuid.uuid4().hex}@{self.host}>"
            logger.info(f"[EmailSender] Sent to {recipients}: {subject}")
            return {"success": True, "smtp_message_id": smtp_id, "error": None}

        except Exception as e:
            logger.error(f"[EmailSender] Failed to send to {recipients}: {e}")
            return {"success": False, "smtp_message_id": None, "error": str(e)}

    # ──────────────────────────────────────────────────────────────────
    # HTML 模板辅助
    # ──────────────────────────────────────────────────────────────────

    def wrap_html(self, title: str, body: str, company: str = "青岛瑞利杰金属有限公司") -> str:
        """将正文包装成带样式的完整 HTML 邮件。"""
        return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<style>
  body{{font-family:'Microsoft YaHei',Arial,sans-serif;color:#1f2937;background:#f9fafb;margin:0;padding:20px}}
  .box{{max-width:600px;margin:0 auto;background:#fff;border-radius:8px;padding:32px;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
  .hdr{{border-bottom:2px solid #3b82f6;padding-bottom:12px;margin-bottom:20px}}
  .hdr h2{{color:#1e3a8a;margin:0;font-size:18px}}
  h3{{color:#1e40af}}
  .btn{{display:inline-block;background:#3b82f6;color:#fff;padding:11px 26px;border-radius:6px;text-decoration:none;font-weight:600;margin:14px 0}}
  table.info{{width:100%;border-collapse:collapse;margin:14px 0}}
  table.info td{{padding:7px 11px;border:1px solid #e5e7eb;font-size:14px}}
  table.info td:first-child{{background:#f1f5f9;font-weight:600;width:34%}}
  .warn{{background:#fef3c7;border:1px solid #fcd34d;border-radius:6px;padding:11px;margin:11px 0;color:#78350f}}
  .foot{{margin-top:28px;padding-top:14px;border-top:1px solid #e5e7eb;font-size:12px;color:#6b7280}}
</style></head><body>
<div class="box">
  <div class="hdr"><h2>{company}</h2></div>
  <h3>{title}</h3>
  {body}
  <div class="foot">本邮件由系统自动发送，请勿直接回复。© {company}</div>
</div></body></html>"""

    @staticmethod
    def from_env(env_file: Optional[str] = None, debug: Optional[bool] = None) -> "EmailSender":
        """从 .env 文件或环境变量创建 EmailSender 实例。

        环境变量：
            SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
            EMAIL_FROM (可选), EMAIL_DEBUG (可选, true/false)
        """
        import os
        if env_file:
            from dotenv import load_dotenv
            load_dotenv(env_file)

        _debug = debug if debug is not None else os.getenv("EMAIL_DEBUG", "false").lower() == "true"
        return EmailSender(
            host=os.getenv("SMTP_HOST", "smtp.163.com"),
            port=int(os.getenv("SMTP_PORT", "465")),
            user=os.getenv("SMTP_USER", ""),
            password=os.getenv("SMTP_PASSWORD", ""),
            from_addr=os.getenv("EMAIL_FROM"),
            debug=_debug,
        )
