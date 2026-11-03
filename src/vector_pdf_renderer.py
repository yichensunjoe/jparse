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

    # Safe formula font regex that excludes regular Latin text italics (e.g. Palatino-Italic, Times-Italic)
    safe_vfont = r"(CM[^R]|MS.M|XY|MT|BL|RM|EU|LA|RS|LINE|LCIRCLE|TeX-|rsfs|txsy|wasy|stmary|.*Mono|.*Code|.*MathItal|.*Sym|.*Math)"

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        cmd = [
            str(pdf2zh_bin),
            str(pdf_path),
            "-o", str(tmp_dir),
            "-s", service,
            "-t", str(thread),
            "-f", safe_vfont,
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
        mono_dest: Optional[Path] = None
        dual_dest: Optional[Path] = None
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

        # pdf2zh leaves table regions untouched.  Re-insert translated cells
        # into their original boxes so the table grid stays identical.
        if mono_dest or dual_dest:
            try:
                from src.table_overlay import apply_table_translations
                painted = apply_table_translations(
                    pdf_path,
                    mono_pdf=mono_dest,
                    dual_pdf=dual_dest,
                    service=service,
                    pages=pages,
                )
                if painted:
                    logger.info("表格单元格翻译完成: %d 个单元格已回贴原网格", painted)
            except Exception as exc:
                logger.warning("表格单元格回贴失败，保留 pdf2zh 原始表格: %s", exc)

            # Vector figures are excluded by pdf2zh together with tables.
            # Put translated labels back inside the original boxes.
            try:
                from src.figure_overlay import apply_figure_translations
                figure_painted = apply_figure_translations(
                    pdf_path,
                    mono_pdf=mono_dest,
                    dual_pdf=dual_dest,
                    service=service,
                    pages=pages,
                )
                if figure_painted:
                    logger.info("矢量图内文字翻译完成: %d 组已回贴原图", figure_painted)
            except Exception as exc:
                logger.warning("矢量图内文字回贴失败，保留原始图内文字: %s", exc)

            # Bitmap figures (diagrams/flowcharts embedded as raster images).
            # In-place OCR, erasure, translation, and replacement inside PDF.
            try:
                from src.bitmap_figure_translator import apply_bitmap_figure_translations
                bitmap_figures_painted = apply_bitmap_figure_translations(
                    pdf_path,
                    mono_pdf=mono_dest,
                    dual_pdf=dual_dest,
                    service=service,
                    pages=pages,
                )
                if bitmap_figures_painted:
                    logger.info("位图图内文字翻译完成: %d 张图片已原位替换", bitmap_figures_painted)
            except Exception as exc:
                logger.warning("位图图内文字回贴失败，保留原始位图: %s", exc)

            # pdf2zh can leave an old heading underline behind after it
            # re-flows the heading text into a paragraph.
            try:
                from src.pdf_cleanup import remove_orphan_underlines
                removed = remove_orphan_underlines(
                    pdf_path,
                    mono_pdf=mono_dest,
                    dual_pdf=dual_dest,
                    pages=pages,
                )
                if removed:
                    logger.info("清理 pdf2zh 孤立标题下划线: %d 条", removed)
            except Exception as exc:
                logger.warning("孤立标题下划线清理失败: %s", exc)

            # On pages with lettered/numbered lists pdf2zh merges every item
            # into one paragraph, so labels such as "b." and "1)" end up in
            # the middle of the previous line.  Rebuild only those pages using
            # the source page's baselines and hanging indents.
            try:
                from src.text_layout_repair import repair_merged_list_layout
                repaired = repair_merged_list_layout(
                    pdf_path,
                    mono_pdf=mono_dest,
                    dual_pdf=dual_dest,
                    pages=pages,
                )
                if repaired:
                    logger.info("pdf2zh 段落合并页重排: %d 页", repaired)
            except Exception as exc:
                logger.warning("pdf2zh 段落合并页重排失败: %s", exc)

    return output_files
