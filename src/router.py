"""Smart Layout Router: Probe PDF characteristics and route to optimal pipeline."""

import logging
from pathlib import Path
import sys
from typing import Dict, List, Optional
import fitz

_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

try:
    from .hd_scan_renderer import process_scanned_pdf_to_hd_pdf
    from .in_situ_renderer import process_pdf_to_insitu_html
    from .vector_pdf_renderer import process_vector_pdf_with_pdf2zh
except ImportError:
    from hd_scan_renderer import process_scanned_pdf_to_hd_pdf
    from in_situ_renderer import process_pdf_to_insitu_html
    from vector_pdf_renderer import process_vector_pdf_with_pdf2zh

logger = logging.getLogger("smart_router")


class PDFProbeError(RuntimeError):
    """Raised when a PDF cannot be probed for a reason the user can act on."""


def probe_pdf_document_type(pdf_path: Path, max_check_pages: int = 3) -> str:
    """Probe PDF structure to distinguish modern vector academic PDFs from historical scans.

    Returns:
        'vector': Digital-born vector document with native text stream & vector fonts.
        'scanned': Raster scanned image document, microfiche, or typewriter copy.
    """
    pdf_path = Path(pdf_path).resolve()
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        raise PDFProbeError(
            "无法打开 PDF（文件可能已损坏、被加密或并非 PDF）：%s" % exc
        ) from exc

    # fitz 句柄必须无条件关闭：长驻 watcher 里泄漏会逐个累积文件描述符。
    with doc:
        if doc.needs_pass:
            raise PDFProbeError("PDF 已加密，需要密码才能解析（当前不支持密码 PDF）")
        total_pages = min(max_check_pages, len(doc))
        if total_pages == 0:
            return "scanned"

        is_scan_scores = []

        for i in range(total_pages):
            is_scan_scores.append(_page_looks_scanned(doc[i]))

    scanned_count = sum(is_scan_scores)
    return "scanned" if scanned_count >= (total_pages / 2.0) else "vector"


def _page_looks_scanned(page) -> bool:
    """Heuristics: full-page raster, OCR font layers, or almost no text."""
    p_area = max(1.0, page.rect.width * page.rect.height)
    imgs = page.get_image_info()
    fonts = page.get_fonts()

    # 1. Full-page raster image check (typical in scanned books and microfiche)
    has_full_page_img = False
    for img in imgs:
        try:
            rect = fitz.Rect(img["bbox"])
            if (rect.width * rect.height) / p_area >= 0.5:
                has_full_page_img = True
                break
        except (KeyError, TypeError, ValueError):
            continue

    # 2. Font inspection: OCR layers typically use GlyphLessFont, Type3, or a generic font
    is_ocr_font = any(
        any(k in str(f).lower() for k in ("glyphless", "type3", "tesseract", "abbyy", "unknown"))
        for f in fonts
    )

    # 3. Text length: purely scanned PDFs with no OCR have 0 text
    raw_text = page.get_text("text").strip()
    has_dense_native_text = len(raw_text) > 250 and len(fonts) >= 3 and not is_ocr_font

    if has_full_page_img and not has_dense_native_text:
        return True
    return len(raw_text) < 50 and not has_dense_native_text


def route_and_process_pdf(
    pdf_path: Path,
    outbox_dir: Path,
    config: Optional[Dict] = None,
) -> List[Path]:
    """Inspect and dispatch a PDF to the optimal translation pipeline.

    Args:
        pdf_path: Incoming PDF file path.
        outbox_dir: Directory where final results should be stored.
        config: Optional configuration dictionary.

    Returns:
        List of generated deliverables in outbox_dir.
    """
    pdf_path = Path(pdf_path).resolve()
    outbox_dir = Path(outbox_dir).resolve()
    cfg = config or {}

    force_mode = cfg.get("force_pipeline", "auto").lower()
    if force_mode in ("vector", "modern"):
        doc_type = "vector"
    elif force_mode in ("scanned", "historical", "insitu", "insitu_legacy", "legacy_html", "opendataloader"):
        doc_type = "scanned"
    else:
        doc_type = probe_pdf_document_type(pdf_path)

    logger.info("文档 [%s] 判定为: [%s] (策略: %s)", pdf_path.name, doc_type.upper(), force_mode)

    if doc_type == "vector":
        # Track A: Modern Vector Academic Paper -> pdf2zh in-place PDF
        service = cfg.get("pdf2zh_service", "bing")
        pages = cfg.get("pdf2zh_pages", None)
        thread = int(cfg.get("pdf2zh_threads", 4))
        return process_vector_pdf_with_pdf2zh(
            pdf_path=pdf_path,
            outbox_dir=outbox_dir,
            service=service,
            pages=pages,
            thread=thread,
        )
    elif force_mode in ("insitu_legacy", "legacy_html") or cfg.get("legacy_html_only"):
        # Explicit legacy in-situ HTML fallback
        extractor_engine = cfg.get("upstream_extractor", "liteparse")
        html_out = outbox_dir / f"{pdf_path.stem}.原位双层版.html"
        tmp_html = outbox_dir / f".{pdf_path.stem}.原位双层版.html.tmp"
        res_path = process_pdf_to_insitu_html(
            pdf_path=pdf_path,
            output_html_path=tmp_html,
            extractor_engine=extractor_engine,
        )
        tmp_html.replace(html_out)
        sz = html_out.stat().st_size if html_out.exists() else 0
        logger.info("已交付原位双层可编辑 HTML: %s (%d bytes)", html_out.name, sz)
        return [html_out]
    else:
        # Track B: Publication-Grade High-Definition PDF + In-Situ Dual-Layer HTML
        extractor_engine = cfg.get("upstream_extractor", "opendataloader")
        service = cfg.get("pdf2zh_service", "bing")
        pages = cfg.get("pdf2zh_pages", None) or cfg.get("pages", None)

        return process_scanned_pdf_to_hd_pdf(
            pdf_path=pdf_path,
            outbox_dir=outbox_dir,
            service=service,
            pages=pages,
            extractor_engine=extractor_engine,
            generate_insitu_html=True,
        )
