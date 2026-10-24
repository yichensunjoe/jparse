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
    from .in_situ_renderer import process_pdf_to_insitu_html
    from .vector_pdf_renderer import process_vector_pdf_with_pdf2zh
except ImportError:
    from in_situ_renderer import process_pdf_to_insitu_html
    from vector_pdf_renderer import process_vector_pdf_with_pdf2zh

logger = logging.getLogger("smart_router")


def probe_pdf_document_type(pdf_path: Path, max_check_pages: int = 3) -> str:
    """Probe PDF structure to distinguish modern vector academic PDFs from historical scans.

    Returns:
        'vector': Digital-born vector document with native text stream & vector fonts.
        'scanned': Raster scanned image document, microfiche, or typewriter copy.
    """
    pdf_path = Path(pdf_path).resolve()
    doc = fitz.open(pdf_path)
    total_pages = min(max_check_pages, len(doc))
    if total_pages == 0:
        doc.close()
        return "scanned"

    is_scan_scores = []

    for i in range(total_pages):
        page = doc[i]
        p_area = max(1.0, page.rect.width * page.rect.height)
        imgs = page.get_images()
        fonts = page.get_fonts()

        # 1. Full-page raster image check (typical in scanned books and microfiche)
        has_full_page_img = False
        for img in imgs:
            xref = img[0]
            try:
                for r in page.get_image_rects(xref):
                    if (r.width * r.height) / p_area > 0.75:
                        has_full_page_img = True
                        break
            except Exception:
                pass

        # 2. Font inspection: OCR layers typically use GlyphLessFont, Type3, or single generic font
        is_ocr_font = any(
            any(k in str(f).lower() for k in ("glyphless", "type3", "tesseract", "abbyy", "unknown"))
            for f in fonts
        )

        # 3. Text length: purely scanned PDFs with no OCR have 0 text
        raw_text = page.get_text("text").strip()
        has_dense_native_text = len(raw_text) > 250 and len(fonts) >= 3 and not is_ocr_font

        if has_full_page_img and not has_dense_native_text:
            is_scan_scores.append(True)
        elif len(raw_text) < 50 and not has_dense_native_text:
            is_scan_scores.append(True)
        else:
            is_scan_scores.append(False)

    doc.close()
    scanned_count = sum(is_scan_scores)
    return "scanned" if scanned_count >= (total_pages / 2.0) else "vector"


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
    elif force_mode in ("scanned", "historical", "insitu"):
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
    else:
        # Track B: Historical Scanned Literature -> LiteParse In-Situ Dual-Layer HTML
        html_out = outbox_dir / f"{pdf_path.stem}.原位双层版.html"
        tmp_html = outbox_dir / f".{pdf_path.stem}.原位双层版.html.tmp"
        res_path = process_pdf_to_insitu_html(
            pdf_path=pdf_path,
            output_html_path=tmp_html,
        )
        tmp_html.replace(html_out)
        sz = html_out.stat().st_size if html_out.exists() else 0
        logger.info("已交付原位双层可编辑 HTML: %s (%d bytes)", html_out.name, sz)
        return [html_out]
