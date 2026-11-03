"""Small post-processing fixes for pdf2zh output.

pdf2zh replaces heading text but sometimes leaves the original horizontal
underline rectangles behind.  Once the heading has been re-flowed into body
text the underline becomes a stray line in the middle of the page.  This
module removes only thin filled rules that no longer have text immediately
above or below them, and never touches table rules.
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional

import fitz

from src.opendataloader_extractor import ExtractedDocument, extract_pdf_structure

logger = logging.getLogger("pdf_cleanup")

_MIN_WIDTH = 15.0
_MAX_HEIGHT = 1.6
_NEAR_ABOVE = 3.2
_NEAR_BELOW = 6.2


def _is_neutral_dark(fill) -> bool:
    """Avoid deleting coloured hyperlink underlines or blue accent rules."""
    if fill is None:
        return False
    try:
        values = [float(c) for c in fill[:3]]
    except (TypeError, ValueError):
        return False
    return len(values) == 3 and max(values) < 0.35 and max(values) - min(values) < 0.08


def _touches_source_text(page: fitz.Page, rect: fitz.Rect) -> bool:
    """True only for an inline underline that actually crosses source text.

    This deliberately rejects standalone separator rules, footnote rules and
    cover-page lines.  Those should never be removed just because translation
    moved the nearby text.
    """
    probe = fitz.Rect(rect.x0, rect.y0 - 0.5, rect.x1, rect.y1 + 0.5)
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if not (span.get("text") or "").strip():
                    continue
                span_rect = fitz.Rect(span["bbox"])
                if min(probe.x1, span_rect.x1) - max(probe.x0, span_rect.x0) <= 1.0:
                    continue
                if span_rect.y0 <= probe.y1 and span_rect.y1 >= probe.y0:
                    return True
    return False


def _near_text(page: fitz.Page, rect: fitz.Rect) -> bool:
    """Return True when a rule is still visually attached to text.

    An underline has text immediately above it.  A footnote rule legitimately
    has its note just below it.  Decorative rules in a figure are excluded
    earlier by the "large filled shape" page-level guard.
    """
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = (span.get("text") or "").strip()
                if not text:
                    continue
                span_rect = fitz.Rect(span["bbox"])
                overlap = min(rect.x1, span_rect.x1) - max(rect.x0, span_rect.x0)
                if overlap <= 1.0:
                    continue
                # Text sitting on the rule (normal underline).  Some
                # translated headings overlap the old underline rectangle, so
                # check both the text bottom and the full span box.
                if rect.y0 - _NEAR_ABOVE <= span_rect.y1 <= rect.y0 + 1.8:
                    return True
                if span_rect.y0 - 1.5 <= rect.y0 <= span_rect.y1 + 1.5:
                    return True
                # Footnote text just below its separator rule.
                if rect.y1 - 1.0 <= span_rect.y0 <= rect.y1 + _NEAR_BELOW:
                    return True
    return False


def _table_rects(structure: ExtractedDocument) -> Dict[int, List[fitz.Rect]]:
    result: Dict[int, List[fitz.Rect]] = {}
    for page in structure.pages:
        index = int(page.page_num) - 1
        rects = []
        for table in page.tables:
            rects.append(
                fitz.Rect(
                    float(table.x) - 2.0,
                    float(table.y) - 2.0,
                    float(table.x + table.w) + 2.0,
                    float(table.y + table.h) + 2.0,
                )
            )
        result[index] = rects
    return result


def _candidate_rules(page: fitz.Page, table_rects: List[fitz.Rect]) -> List[fitz.Rect]:
    candidates: List[fitz.Rect] = []
    page_area = page.rect.get_area()
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect is None or not _is_neutral_dark(drawing.get("fill")):
            continue
        if rect.height > _MAX_HEIGHT or rect.width < _MIN_WIDTH:
            continue
        if rect.width > page.rect.width * 0.65:
            continue
        if rect.y0 < 60.0 or rect.y1 > page.rect.height - 65.0:
            continue
        if rect.x0 < 40.0 or rect.x1 > page.rect.width - 40.0:
            continue
        if rect.width / max(rect.height, 0.1) < 8.0:
            continue
        if any(rect.intersects(table_rect) for table_rect in table_rects):
            continue
        if not _touches_source_text(page, rect):
            continue
        candidates.append(rect)
    return candidates


def _page_has_large_graphics(page: fitz.Page) -> bool:
    """Skip pages containing figures/tables with large filled shapes.

    Those pages can contain legitimate rules whose nearby text is absent from
    PyMuPDF's span list (clipped labels, vector outlines).  Cleanup is safest
    on text-only pages, which is where pdf2zh leaves the orphan underlines.
    """
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect is not None and drawing.get("fill") is not None and rect.get_area() > 5000:
            return True
    return False


def _dual_offset(mono: fitz.Document, dual: fitz.Document) -> Optional[int]:
    if len(mono) == 0 or len(dual) < len(mono) * 2:
        return None
    sample = min(len(mono), 10)
    best_offset = 1
    best_score = -1.0
    for offset in (0, 1):
        score = 0.0
        for index in range(sample):
            left = mono[index].get_text()[:600]
            right = dual[index * 2 + offset].get_text()[:600]
            score += SequenceMatcher(None, left, right).ratio()
        if score > best_score:
            best_score = score
            best_offset = offset
    return best_offset


def _apply_to_page(page: fitz.Page, rules: List[fitz.Rect]) -> int:
    if page.rotation:
        logger.warning("第 %d 页为旋转页，跳过孤立下划线清理", page.number + 1)
        return 0
    removed = 0
    for rule in rules:
        if _near_text(page, rule):
            continue
        page.add_redact_annot(
            fitz.Rect(rule.x0 - 0.4, rule.y0 - 0.4, rule.x1 + 0.4, rule.y1 + 0.4),
            fill=False,
        )
        removed += 1
    if not removed:
        return 0
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_NONE,
        graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
    )
    return removed


def _save_atomic(doc: fitz.Document, path: Path) -> None:
    temp = path.with_name(f".{path.name}.cleanup.tmp")
    try:
        doc.save(temp, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()
    temp.replace(path)


def remove_orphan_underlines(
    source_pdf: Path,
    mono_pdf: Optional[Path] = None,
    dual_pdf: Optional[Path] = None,
    pages: Optional[str] = None,
) -> int:
    """Remove orphan heading underlines from translated PDFs.

    Returns the number of rules removed.  Failures are logged by the caller
    and never affect delivery of the translated PDF.
    """
    source_pdf = Path(source_pdf)
    if not mono_pdf and not dual_pdf:
        return 0
    mono_path = Path(mono_pdf) if mono_pdf else None
    structure = extract_pdf_structure(source_pdf, pages=pages)
    table_map = _table_rects(structure)
    page_numbers = {int(page.page_num) - 1 for page in structure.pages}

    try:
        source_doc = fitz.open(source_pdf)
    except Exception as exc:
        logger.warning("孤立下划线清理无法打开源 PDF: %s", exc)
        return 0

    candidates: Dict[int, List[fitz.Rect]] = {}
    try:
        for index in sorted(page_numbers):
            if index < 0 or index >= len(source_doc):
                continue
            source_page = source_doc[index]
            if source_page.rotation or _page_has_large_graphics(source_page):
                continue
            if table_map.get(index):
                continue
            rules = _candidate_rules(source_page, table_map.get(index, []))
            if rules:
                candidates[index] = rules
    finally:
        source_doc.close()

    if not candidates:
        return 0

    removed = 0
    try:
        if mono_path and mono_path.is_file():
            mono_doc = fitz.open(mono_path)
            try:
                for index, rules in candidates.items():
                    if index < len(mono_doc):
                        removed += _apply_to_page(mono_doc[index], rules)
                if removed:
                    _save_atomic(mono_doc, mono_path)
                else:
                    mono_doc.close()
            except Exception:
                if not mono_doc.is_closed:
                    mono_doc.close()
                raise
            logger.info("单语版孤立下划线清理: %d 条", removed)

        if dual_pdf and (removed or not mono_path or not mono_path.is_file()):
            dual_path = Path(dual_pdf)
            if dual_path.is_file():
                dual_doc = fitz.open(dual_path)
                try:
                    mono_doc_for_offset = fitz.open(mono_path) if mono_path and mono_path.is_file() else None
                    try:
                        offset = _dual_offset(mono_doc_for_offset, dual_doc) if mono_doc_for_offset else 1
                    finally:
                        if mono_doc_for_offset is not None:
                            mono_doc_for_offset.close()
                    if offset is None:
                        logger.info("双语版页序无法匹配，跳过孤立下划线清理")
                        dual_doc.close()
                    else:
                        dual_removed = 0
                        for index, rules in candidates.items():
                            target_index = index * 2 + offset
                            if target_index < len(dual_doc):
                                dual_removed += _apply_to_page(dual_doc[target_index], rules)
                        if dual_removed:
                            _save_atomic(dual_doc, dual_path)
                            removed += dual_removed
                            logger.info("双语版孤立下划线清理: %d 条", dual_removed)
                        else:
                            dual_doc.close()
                except Exception:
                    if not dual_doc.is_closed:
                        dual_doc.close()
                    raise
    except Exception as exc:
        logger.warning("孤立下划线清理失败，保留原样: %s", exc)
        return removed
    return removed
