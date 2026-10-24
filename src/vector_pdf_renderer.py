"""Vector PDF Translation and Reconstruction Pipeline using pdf2zh engine."""

import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import List, Optional

logger = logging.getLogger("vector_pdf_renderer")


def get_pdf2zh_binary() -> Path:
    """Locate the isolated pdf2zh executable."""
    candidates = [
        Path.home() / ".local/venvs/pdf2zh/bin/pdf2zh",
        Path("/Users/joe/.local/venvs/pdf2zh/bin/pdf2zh"),
        Path(shutil.which("pdf2zh") or ""),
    ]
    for c in candidates:
        if c.exists() and os.access(c, os.X_OK):
            return c
    raise FileNotFoundError("未找到可执行的 pdf2zh 虚拟环境二进制文件 (请确认 ~/.local/venvs/pdf2zh 存在)")


def process_vector_pdf_with_pdf2zh(
    pdf_path: Path,
    outbox_dir: Path,
    service: str = "bing",
    pages: Optional[str] = None,
    thread: int = 4,
    timeout: int = 600,
) -> List[Path]:
    """Translate a native digital-born vector PDF into mono and dual translated PDFs.

    Args:
        pdf_path: Source vector PDF.
        outbox_dir: Target directory to save translated PDFs.
        service: Translation service ('bing', 'google', 'deepl', 'ollama', etc.).
        pages: Optional page range (e.g. '1-3' or '1,2'). None for all pages.
        thread: Worker thread count for translation.
        timeout: Subprocess execution timeout in seconds.

    Returns:
        List of generated output PDF paths in outbox_dir.
    """
    pdf_path = Path(pdf_path).resolve()
    outbox_dir = Path(outbox_dir).resolve()
    outbox_dir.mkdir(parents=True, exist_ok=True)
    pdf2zh_bin = get_pdf2zh_binary()

    stem = pdf_path.stem
    output_files: List[Path] = []

    try:
        from src.pdf2zh_patch import ensure_pdf2zh_environment_ready
        ensure_pdf2zh_environment_ready()
    except Exception as e:
        logger.warning("检查并应用 pdf2zh 补丁失败: %s", e)

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        cmd = [
            str(pdf2zh_bin),
            str(pdf_path),
            "-o", str(tmp_dir),
            "-s", service,
            "-t", str(thread),
        ]
        if pages:
            cmd.extend(["-p", pages])

        logger.info("正在调用 pdf2zh 矢量引擎进行原位擦除与学术排版翻译: %s", " ".join(cmd))
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        if res.returncode != 0:
            logger.error("pdf2zh 执行失败: %s\n%s", res.stdout, res.stderr)
            raise RuntimeError(f"pdf2zh 翻译失败: {res.stderr or res.stdout}")

        # Find generated mono and dual PDFs
        mono_candidates = list(tmp_dir.glob("*-mono.pdf")) or list(tmp_dir.glob("*-zh.pdf"))
        dual_candidates = list(tmp_dir.glob("*-dual.pdf"))

        if not mono_candidates and not dual_candidates:
            # Fallback search any generated pdf
            all_pdfs = [p for p in tmp_dir.glob("*.pdf") if p != pdf_path]
            if not all_pdfs:
                raise FileNotFoundError(f"pdf2zh 未能在临时目录中生成翻译 PDF: {res.stdout}")
            mono_candidates = all_pdfs[:1]

        # Atomically move to outbox
        if mono_candidates:
            mono_src = mono_candidates[0]
            mono_dest = outbox_dir / f"{stem}-中文精译版.pdf"
            tmp_dest = outbox_dir / f".{stem}-中文精译版.pdf.tmp"
            shutil.copy2(mono_src, tmp_dest)
            tmp_dest.replace(mono_dest)
            output_files.append(mono_dest)
            logger.info("已交付单语矢量精译 PDF: %s (%d bytes)", mono_dest.name, mono_dest.stat().st_size)

        if dual_candidates:
            dual_src = dual_candidates[0]
            dual_dest = outbox_dir / f"{stem}-双语对照版.pdf"
            tmp_dest = outbox_dir / f".{stem}-双语对照版.pdf.tmp"
            shutil.copy2(dual_src, tmp_dest)
            tmp_dest.replace(dual_dest)
            output_files.append(dual_dest)
            logger.info("已交付双语对照矢量 PDF: %s (%d bytes)", dual_dest.name, dual_dest.stat().st_size)

    return output_files
