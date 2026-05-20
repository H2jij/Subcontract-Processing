"""
contract_toolkit — 合同邮件分发 & DOCX 自动填充 独立工具包
============================================================
无数据库依赖，可直接复用到任何 Python 项目。

模块：
  email_sender      邮件发送（SMTP，支持附件）
  docx_filler       DOCX 模板自动填充 & 下划线转占位符
  pdf_converter     DOCX → PDF 转换（LibreOffice / docx2pdf）

快速开始：
    from contract_toolkit import EmailSender, DocxFiller, PdfConverter

    # 发送邮件
    sender = EmailSender(host="smtp.163.com", port=465,
                         user="x@163.com", password="xxx")
    sender.send(to="partner@example.com",
                subject="合同确认", html="<p>请确认...</p>")

    # 填充 DOCX
    filler = DocxFiller("template.docx")
    docx_bytes = filler.fill({"乙方名称": "ABC公司", "合同期限": "1年"})

    # 转换 PDF
    pdf_path = PdfConverter.convert_docx("filled.docx", "output/")
"""

from .email_sender import EmailSender
from .docx_filler import DocxFiller
from .pdf_converter import PdfConverter

__all__ = ["EmailSender", "DocxFiller", "PdfConverter"]
__version__ = "1.0.0"
