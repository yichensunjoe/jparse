"""Fill translated table cells back into vector PDFs without changing the grid.

pdf2zh intentionally excludes table regions from translation, so table cells
keep their English text.  This module uses OpenDataLoader's per-cell bounding
boxes to erase the original cell text and types the Chinese translation into
the same cell box.  Table borders, shading, column widths and row heights are
left untouched.
"""

from __future__ import annotations

import html
import logging
import re
import tempfile
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz

from src.opendataloader_extractor import ExtractedDocument, extract_pdf_structure

logger = logging.getLogger("table_overlay")

_FONT_DIR = Path.home() / ".cache/babeldoc/fonts"
_REGULAR_FONT = _FONT_DIR / "SourceHanSerifCN-Regular.ttf"
_BOLD_FONT = _FONT_DIR / "SourceHanSerifCN-Bold.ttf"

_CSS = """
@font-face {font-family: table-serif; src: url(regular.ttf);}
@font-face {font-family: table-serif-bold; src: url(bold.ttf);}
* {margin: 0; padding: 0;}
"""

# Keep text away from the cell borders so redaction never eats a table rule.
_INSET = 1.6
_MIN_CELL_SIZE = 4.0
_ALPHA_RE = re.compile(r"[A-Za-z]")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_SPACE_RE = re.compile(r"\s+")


@dataclass
class _CellJob:
    page_index: int
    rect: fitz.Rect
    source: str
    translated: str
    bold: bool
    font_size: float


def _clean(text: str) -> str:
    return _SPACE_RE.sub(" ", text or "").strip()


def _needs_translation(text: str) -> bool:
    """Only cells carrying Latin prose need a translation pass."""
    return (
        len(text) >= 2
        and bool(_ALPHA_RE.search(text))
        and not _CJK_RE.search(text)
    )


def _cell_rect(cell) -> Optional[fitz.Rect]:
    """Build a fitz rectangle from OpenDataLoader's top-left cell geometry."""
    x = float(cell.x)
    y = float(cell.y)
    w = float(cell.w)
    h = float(cell.h)
    rect = fitz.Rect(
        x + _INSET,
        y + _INSET,
        x + w - _INSET,
        y + h - _INSET,
    )
    if rect.width < _MIN_CELL_SIZE or rect.height < _MIN_CELL_SIZE:
        return None
    return rect


def _collect_jobs(document: ExtractedDocument) -> List[Tuple[int, fitz.Rect, str, bool, float]]:
    jobs: List[Tuple[int, fitz.Rect, str, bool, float]] = []
    for page in document.pages:
        page_index = int(page.page_num) - 1
        for table in page.tables:
            for row in table.rows:
                for cell in row:
                    source = _clean(cell.text)
                    if not _needs_translation(source):
                        continue
                    rect = _cell_rect(cell)
                    if rect is None:
                        continue
                    size = float(cell.font_size or 10.0)
                    if not 5.0 <= size <= 30.0:
                        size = 10.0
                    jobs.append((page_index, rect, source, bool(cell.is_header), size))

        # Small numbered notes directly under a table belong to that table.
        # pdf2zh usually classifies them as table footnotes and leaves them in
        # English, so translate them with the same in-place overlay.
        if page.tables:
            for element in page.elements:
                if element.is_table:
                    continue
                source = _clean(element.text)
                if not _needs_translation(source):
                    continue
                if not re.match(r"^\d{1,2}\s+\S", source):
                    continue
                size = float(element.font_size or 0.0)
                if size <= 0.0 or size > 10.6:
                    continue
                if float(element.y) < page.height * 0.78:
                    continue
                if any(
                    float(element.y) < float(t.y + t.h)
                    and float(element.y + element.h) > float(t.y)
                    for t in page.tables
                ):
                    continue
                rect = fitz.Rect(
                    element.x + 1.0,
                    element.y + 0.5,
                    element.x + element.w - 1.0,
                    min(page.height - 42.0, element.y + max(element.h * 2.0, 26.0)),
                )
                if rect.height >= _MIN_CELL_SIZE and rect.width >= _MIN_CELL_SIZE:
                    jobs.append((page_index, rect, source, False, size))
    return jobs


def _translate_jobs(
    raw_jobs: List[Tuple[int, fitz.Rect, str, bool, float]],
    service: str,
) -> List[_CellJob]:
    if not raw_jobs:
        return []

    from src.hd_scan_renderer import ScannedPDFTranslator

    translator = ScannedPDFTranslator(service=service)
    cache: Dict[str, str] = {}
    jobs: List[_CellJob] = []

    for page_index, rect, source, bold, size in raw_jobs:
        translated = cache.get(source)
        if translated is None:
            try:
                translated = translator.translate_single(source)
            except Exception as exc:  # keep the English cell if this one fails
                logger.warning("表格单元格翻译失败 (%s): %s", source[:40], exc)
                translated = ""
            translated = _clean(translated or "")
            # Keep footnote / row markers such as "2 Scoping ..." even when
            # the NMT service drops the leading number.
            marker = re.match(r"^(\d{1,2})\s+\S", source)
            if translated and marker and not re.match(
                rf"^{re.escape(marker.group(1))}(?:[\.、\)]\s*|\s|$)", translated
            ):
                translated = f"{marker.group(1)} {translated}"
            cache[source] = translated

        if not translated or translated == source or not _CJK_RE.search(translated):
            continue
        jobs.append(
            _CellJob(
                page_index=page_index,
                rect=rect,
                source=source,
                translated=translated,
                bold=bold,
                font_size=size,
            )
        )
    return jobs


def _build_subset_fonts(jobs: List[_CellJob]) -> Tuple[Optional[fitz.Archive], str, Optional[tempfile.TemporaryDirectory]]:
    """Subset the two Source Han fonts to the characters actually used.

    Embedding the full 14 MB CJK font into every PDF is wasteful, while
    PyMuPDF's document-wide subset_fonts() can crash on pdf2zh dual files.
    A per-run font subset keeps the original typeface and avoids both issues.
    """
    regular = _REGULAR_FONT
    bold = _BOLD_FONT
    if not regular.is_file() or not bold.is_file():
        return None, _CSS, None

    try:
        from fontTools import subset as ftsubset
        logging.getLogger("fontTools.subset").setLevel(logging.WARNING)
    except ImportError:
        logger.warning("fontTools 不可用，表格回退到内置 CJK 字体")
        return None, _CSS, None

    characters = "".join(job.translated for job in jobs) + " 0123456789.,;:()[]{}<>/+-=%&\"'"
    temp_dir = tempfile.TemporaryDirectory(prefix="table-fonts-")
    try:
        for filename, source in (("regular.ttf", regular), ("bold.ttf", bold)):
            options = ftsubset.Options()
            options.name_IDs = ["*"]
            options.name_legacy = True
            options.name_languages = ["*"]
            options.notdef_outline = True
            options.recalc_bounds = True
            options.layout_features = ["*"]
            font = ftsubset.load_font(str(source), options)
            subsetter = ftsubset.Subsetter(options=options)
            subsetter.populate(unicodes={ord(ch) for ch in characters})
            subsetter.subset(font)
            ftsubset.save_font(font, str(Path(temp_dir.name) / filename), options)
        archive = fitz.Archive(temp_dir.name)
        return archive, _CSS, temp_dir
    except Exception:
        temp_dir.cleanup()
        raise


def _paint_page(
    page: fitz.Page,
    jobs: List[_CellJob],
    archive: Optional[fitz.Archive],
    css: str,
) -> int:
    """Erase the English text, then insert Chinese inside the same cell boxes."""
    if not jobs:
        return 0
    if page.rotation:
        logger.warning("第 %d 页为旋转页，跳过表格回贴以避免坐标错位", page.number + 1)
        return 0

    for job in jobs:
        # fill=False removes the text but leaves background shading and rules.
        page.add_redact_annot(job.rect, fill=False)
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_NONE,
        graphics=fitz.PDF_REDACT_LINE_ART_NONE,
    )

    painted = 0
    for job in jobs:
        family = "table-serif-bold" if job.bold else "table-serif"
        body = (
            f'<div style="font-family:{family}; font-size:{job.font_size:.2f}pt; '
            f'line-height:1.32; color:#000;">{html.escape(job.translated)}</div>'
        )
        try:
            if archive is not None:
                page.insert_htmlbox(
                    job.rect,
                    body,
                    css=css,
                    archive=archive,
                    scale_low=0,
                )
            else:
                page.insert_textbox(
                    job.rect,
                    job.translated,
                    fontsize=job.font_size,
                    fontname="china-s",
                    color=(0, 0, 0),
                    align=fitz.TEXT_ALIGN_LEFT,
                )
            painted += 1
        except Exception as exc:
            logger.warning("表格单元格回贴失败 (%s): %s", job.source[:40], exc)
    return painted


def _page_text(doc: fitz.Document, index: int) -> str:
    if index < 0 or index >= len(doc):
        return ""
    return doc[index].get_text()[:600]


def _dual_offset(mono: fitz.Document, dual: fitz.Document) -> Optional[int]:
    """Return 0/1 for where the translated page sits in each dual page pair."""
    if len(dual) < len(mono) * 2 or len(mono) == 0:
        return None

    best_offset = 1
    best_score = -1.0
    sample = min(len(mono), 10)
    for offset in (0, 1):
        score = 0.0
        for i in range(sample):
            left = _page_text(mono, i)
            right = _page_text(dual, i * 2 + offset)
            score += SequenceMatcher(None, left, right).ratio()
        if score > best_score:
            best_score = score
            best_offset = offset
    return best_offset


def _save_atomic(doc: fitz.Document, path: Path) -> None:
    temp = path.with_name(f".{path.name}.table.tmp")
    try:
        # Do NOT call doc.subset_fonts(): PyMuPDF segfaults on some pdf2zh
        # dual files.  The fonts inserted here are already subset per run.
        doc.save(temp, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()
    temp.replace(path)


def apply_table_translations(
    source_pdf: Path,
    mono_pdf: Optional[Path] = None,
    dual_pdf: Optional[Path] = None,
    service: str = "bing",
    pages: Optional[str] = None,
) -> int:
    """Translate table cells in already-generated mono/dual PDFs.

    Returns the number of cells painted.  Any failure is logged and leaves the
    original PDF untouched, so a table problem never breaks the main pipeline.
    """
    source_pdf = Path(source_pdf)
    if not mono_pdf and not dual_pdf:
        return 0

    try:
        structure = extract_pdf_structure(source_pdf, pages=pages)
    except Exception as exc:
        logger.warning("表格结构抽取失败，保留原始表格: %s", exc)
        return 0

    raw_jobs = _collect_jobs(structure)
    if not raw_jobs:
        logger.info("未发现需要翻译的矢量表格单元格")
        return 0

    jobs = _translate_jobs(raw_jobs, service)
    if not jobs:
        logger.info("表格单元格没有产生有效译文")
        return 0

    by_page: Dict[int, List[_CellJob]] = {}
    for job in jobs:
        by_page.setdefault(job.page_index, []).append(job)

    # Determine the dual-page order before the mono copy is modified, so the
    # table pages themselves do not skew the text-similarity comparison.
    dual_offset: Optional[int] = None
    if mono_pdf and dual_pdf and Path(mono_pdf).is_file() and Path(dual_pdf).is_file():
        try:
            mono_probe = fitz.open(Path(mono_pdf))
            dual_probe = fitz.open(Path(dual_pdf))
            try:
                dual_offset = _dual_offset(mono_probe, dual_probe)
            finally:
                mono_probe.close()
                dual_probe.close()
        except Exception as exc:
            logger.warning("双语版页序探测失败，按 pdf2zh 默认页序处理: %s", exc)

    try:
        archive, css, font_temp = _build_subset_fonts(jobs)
    except Exception as exc:
        logger.warning("表格字体子集化失败，使用内置 CJK 字体: %s", exc)
        archive, css, font_temp = None, _CSS, None

    painted = 0
    try:
        if mono_pdf:
            mono_path = Path(mono_pdf)
            if mono_path.is_file():
                mono_doc = fitz.open(mono_path)
                try:
                    for page_index, page_jobs in by_page.items():
                        if page_index < len(mono_doc):
                            painted += _paint_page(mono_doc[page_index], page_jobs, archive, css)
                    _save_atomic(mono_doc, mono_path)
                except Exception:
                    if not mono_doc.is_closed:
                        mono_doc.close()
                    raise
                logger.info("单语版表格回贴完成: %d 个单元格", painted)

        if dual_pdf and (painted or not mono_pdf):
            dual_path = Path(dual_pdf)
            if dual_path.is_file():
                dual_doc = fitz.open(dual_path)
                try:
                    offset = dual_offset if dual_offset is not None else (1 if not mono_pdf else None)
                    if offset is None:
                        logger.info("双语版页序无法匹配，跳过表格回贴")
                        dual_doc.close()
                    else:
                        dual_painted = 0
                        for page_index, page_jobs in by_page.items():
                            dual_index = page_index * 2 + offset
                            if dual_index < len(dual_doc):
                                dual_painted += _paint_page(dual_doc[dual_index], page_jobs, archive, css)
                        if dual_painted:
                            _save_atomic(dual_doc, dual_path)
                            logger.info("双语版表格回贴完成: %d 个单元格", dual_painted)
                        else:
                            dual_doc.close()
                except Exception:
                    if not dual_doc.is_closed:
                        dual_doc.close()
                    raise
    finally:
        if font_temp is not None:
            font_temp.cleanup()

    return painted
