"""
pdf_converter.py — DOCX → PDF 转换模块
=========================================
无数据库依赖。优先使用 LibreOffice headless，降级到 docx2pdf。

用法：
    from contract_toolkit.pdf_converter import PdfConverter

    # 从文件转换
    pdf_path = PdfConverter.from_file("filled.docx", "output/")

    # 从字节流转换
    pdf_bytes = PdfConverter.from_bytes(docx_bytes)
    with open("output.pdf", "wb") as f:
        f.write(pdf_bytes)

    # 检查 LibreOffice 是否可用
    print(PdfConverter.is_available())  # True / False
"""
from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Union


class PdfConverter:
    """DOCX → PDF 转换器（LibreOffice headless 优先，降级 docx2pdf）。"""

    TIMEOUT = 30  # 秒

    @staticmethod
    def is_available() -> dict:
        """检查 PDF 转换工具是否可用。"""
        result = {"libreoffice": False, "docx2pdf": False}
        try:
            r = subprocess.run(["soffice", "--version"], capture_output=True, timeout=5)
            result["libreoffice"] = r.returncode == 0
        except Exception:
            pass
        try:
            import docx2pdf  # noqa: F401
            result["docx2pdf"] = True
        except ImportError:
            pass
        return result

    @staticmethod
    def from_file(
        docx_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
    ) -> Path:
        """
        将 DOCX 文件转换为 PDF。

        Args:
            docx_path:  输入 DOCX 文件路径
            output_dir: 输出目录（默认与 docx_path 同目录）

        Returns:
            生成的 PDF 文件路径

        Raises:
            RuntimeError: LibreOffice 和 docx2pdf 均不可用
        """
        docx_path = Path(docx_path)
        out_dir = Path(output_dir) if output_dir else docx_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        # LibreOffice
        try:
            result = subprocess.run(
                ["soffice", "--headless", "--convert-to", "pdf",
                 str(docx_path), "--outdir", str(out_dir)],
                capture_output=True, timeout=PdfConverter.TIMEOUT,
            )
            pdf = out_dir / (docx_path.stem + ".pdf")
            if result.returncode == 0 and pdf.exists():
                return pdf.resolve()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # docx2pdf
        try:
            from docx2pdf import convert
            pdf = out_dir / (docx_path.stem + ".pdf")
            convert(str(docx_path), str(pdf))
            if pdf.exists():
                return pdf.resolve()
        except Exception:
            pass

        raise RuntimeError(
            "PDF 转换失败：LibreOffice 未安装（运行 winget install TheDocumentFoundation.LibreOffice）"
            "或 docx2pdf 不可用（pip install docx2pdf）"
        )

    @staticmethod
    def from_bytes(docx_bytes: bytes, output_path: Optional[Union[str, Path]] = None) -> bytes:
        """
        将 DOCX 字节流转换为 PDF 字节流。

        Args:
            docx_bytes:  DOCX 文件字节流
            output_path: 可选，同时保存 PDF 到此路径

        Returns:
            PDF 文件字节流

        Raises:
            RuntimeError: LibreOffice 和 docx2pdf 均不可用
        """
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            tmp_docx = tmp_dir / "input.docx"
            tmp_docx.write_bytes(docx_bytes)
            pdf_path = PdfConverter.from_file(tmp_docx, tmp_dir)
            pdf_bytes = pdf_path.read_bytes()

            if output_path:
                out = Path(output_path)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(pdf_bytes)

            return pdf_bytes
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
