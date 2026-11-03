"""Translate text inside vector figures while keeping the figure layout.

pdf2zh intentionally treats a whole figure as an image-like region and leaves
its labels in English.  This module finds vector figure labels, translates each
text group as a unit, erases only the original text, and writes Chinese back
into the same box or column.  Fills, borders, arrows and the original
positioning are not touched.
"""

from __future__ import annotations

import html
import logging
import math
import re
import tempfile
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple

import fitz

from src.opendataloader_extractor import ExtractedDocument, ExtractedElement, extract_pdf_structure

logger = logging.getLogger("figure_overlay")

_FONT_DIR = Path.home() / ".cache/babeldoc/fonts"
_SANS_REGULAR = _FONT_DIR / "SourceHanSansCN-Regular.ttf"
_SANS_BOLD = _FONT_DIR / "SourceHanSansCN-Bold.ttf"

_CSS = """
@font-face {font-family: figure-sans; src: url(figure-regular.ttf);}
@font-face {font-family: figure-sans-bold; src: url(figure-bold.ttf);}
* {margin: 0; padding: 0; box-sizing: border-box;}
"""

_CAPTION_RE = re.compile(r"^(Figure|Fig\.?|图)\s*\.?\s*\d+", re.IGNORECASE)
_MARKER_RE = re.compile(r"^([A-Z])\.\s*")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_SPACE_RE = re.compile(r"\s+")

_MEASURE_FONT: Optional[fitz.Font] = None
_MEASURE_FONT_LOADED = False

def _measure_font() -> Optional[fitz.Font]:
    global _MEASURE_FONT, _MEASURE_FONT_LOADED
    if _MEASURE_FONT_LOADED:
        return _MEASURE_FONT
    _MEASURE_FONT_LOADED = True
    try:
        if _SANS_REGULAR.is_file():
            _MEASURE_FONT = fitz.Font(fontfile=str(_SANS_REGULAR))
    except Exception:
        _MEASURE_FONT = None
    return _MEASURE_FONT

def _text_width(text: str, size: float) -> float:
    font = _measure_font()
    if font is not None:
        try:
            return float(font.text_length(text, fontsize=size))
        except Exception:
            pass
    return _char_units(text) * size

# Keep the figure terminology closer to the DOE source than raw NMT.
_TERM_FIXES = {
    "协议 - 对齐": "协议—对齐",
    "操作反应堆": "反应堆运行",
    "运营设施": "运行设施",
    "单一准备活动": "单项准备就绪活动",
    "联合测试小组": "联合试验组",
}


@dataclass
class _Container:
    rect: fitz.Rect
    fill: Tuple[float, float, float]
    kind: str


@dataclass
class _Paragraph:
    page_index: int
    elements: List[ExtractedElement]
    bbox: fitz.Rect
    source: str
    container: Optional[_Container]
    font_size: float
    bold: bool
    color: str
    target: fitz.Rect = field(default_factory=fitz.Rect)
    translated: str = ""

    @property
    def color_rgb(self) -> Tuple[float, float, float]:
        value = self.color.lstrip("#")
        return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def _clean(text: str) -> str:
    return _SPACE_RE.sub(" ", text or "").strip()


def _needs_translation(text: str) -> bool:
    return (
        len(text) >= 2
        and bool(_LATIN_RE.search(text))
        and not _CJK_RE.search(text)
    )


def _element_rect(element: ExtractedElement) -> fitz.Rect:
    return fitz.Rect(
        float(element.x),
        float(element.y),
        float(element.x + element.w),
        float(element.y + element.h),
    )


def _container_kind(fill: Tuple[float, float, float]) -> str:
    r, g, b = fill
    if max(fill) < 0.35:
        return "dark"
    if g > 0.45 and r < 0.50 and b < 0.45:
        return "green"
    if 0.65 <= r <= 0.92 and abs(r - g) < 0.08 and abs(g - b) < 0.08:
        return "gray"
    return "other"


def _containers(page: fitz.Page, caption_y: float) -> List[_Container]:
    page_area = page.rect.get_area()
    result: List[_Container] = []
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        fill = drawing.get("fill")
        if rect is None or fill is None:
            continue
        if rect.width <= 10 or rect.height <= 5:
            continue
        if rect.y1 > caption_y + 2:
            continue
        if rect.get_area() > page_area * 0.5:
            continue
        try:
            rgb = tuple(float(c) for c in fill[:3])
        except (TypeError, ValueError):
            continue
        if len(rgb) != 3:
            continue
        result.append(_Container(fitz.Rect(rect), rgb, _container_kind(rgb)))
    return result


def _source_spans(page: fitz.Page) -> List[dict]:
    spans: List[dict] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if (span.get("text") or "").strip():
                    spans.append(span)
    return spans


def _dominant_color(spans: Sequence[dict], bbox: fitz.Rect) -> Optional[int]:
    counts: Dict[int, int] = {}
    for span in spans:
        span_rect = fitz.Rect(span["bbox"])
        if not span_rect.intersects(bbox):
            continue
        color = int(span.get("color", 0))
        counts[color] = counts.get(color, 0) + max(1, len((span.get("text") or "").strip()))
    if not counts:
        return None
    return max(counts, key=counts.get)


def _color_hex(value: Optional[int], fallback: str) -> str:
    if value is None:
        return fallback
    return f"#{value:06x}"


def _merge_text(elements: Sequence[ExtractedElement]) -> str:
    ordered = sorted(elements, key=lambda element: (float(element.y), float(element.x)))
    return _clean(" ".join(str(element.text or "").strip() for element in ordered))


def _target_rect(paragraph: _Paragraph) -> fitz.Rect:
    container = paragraph.container
    if container is not None and container.kind == "dark":
        return fitz.Rect(
            container.rect.x0 + 5.2,
            container.rect.y0 + 5.2,
            container.rect.x1 - 5.2,
            container.rect.y1 - 5.2,
        )
    if container is not None and container.kind == "gray":
        # Header: keep the original top/bottom but use the full column width
        # so two-line Chinese headings do not collide with the column edge.
        return fitz.Rect(
            container.rect.x0 + 6.0,
            max(container.rect.y0 + 4.0, paragraph.bbox.y0 - 2.0),
            container.rect.x1 - 6.0,
            min(container.rect.y1 - 4.0, paragraph.bbox.y1 + 2.0),
        )
    if container is not None and container.kind == "green":
        return fitz.Rect(
            paragraph.bbox.x0 - 1.0,
            paragraph.bbox.y0 - 1.0,
            paragraph.bbox.x1 + 1.0,
            paragraph.bbox.y1 + 1.0,
        )
    return fitz.Rect(
        paragraph.bbox.x0 - 2.0,
        paragraph.bbox.y0 - 2.0,
        paragraph.bbox.x1 + 2.0,
        paragraph.bbox.y1 + 2.0,
    )


def _collect_paragraphs(structure: ExtractedDocument, source_doc: fitz.Document) -> List[_Paragraph]:
    paragraphs: List[_Paragraph] = []
    for page in structure.pages:
        page_index = int(page.page_num) - 1
        if page_index < 0 or page_index >= len(source_doc):
            continue
        captions = [
            element
            for element in page.elements
            if _CAPTION_RE.match(_clean(element.text))
        ]
        if not captions:
            continue
        caption = max(captions, key=lambda element: float(element.y))
        caption_y = float(caption.y)
        source_page = source_doc[page_index]
        if source_page.rotation:
            logger.warning("第 %d 页为旋转页，跳过图内文字翻译", page_index + 1)
            continue

        containers = _containers(source_page, caption_y)
        if len(containers) < 2:
            continue
        figure_rect = fitz.Rect(containers[0].rect)
        for container in containers[1:]:
            figure_rect.include_rect(container.rect)
        if figure_rect.get_area() < 5000:
            continue

        elements: List[ExtractedElement] = []
        for element in page.elements:
            rect = _element_rect(element)
            center = fitz.Point((rect.x0 + rect.x1) / 2.0, (rect.y0 + rect.y1) / 2.0)
            if not figure_rect.contains(center):
                continue
            if rect.y1 > caption_y - 1.0:
                continue
            if element.is_table:
                continue
            elements.append(element)
        if len(elements) < 3:
            continue

        grouped: Dict[object, List[ExtractedElement]] = {}
        for element in elements:
            center = fitz.Point(
                (float(element.x) + float(element.w) / 2.0),
                (float(element.y) + float(element.h) / 2.0),
            )
            inside = [
                container
                for container in containers
                if container.rect.x0 <= center.x <= container.rect.x1
                and container.rect.y0 <= center.y <= container.rect.y1
            ]
            if inside:
                container = min(inside, key=lambda item: item.rect.get_area())
                key: object = (round(container.rect.x0, 2), round(container.rect.y0, 2))
            else:
                container = None
                key = ("standalone", round(float(element.x), 2), round(float(element.y), 2))
            grouped.setdefault(key, []).append(element)

        spans = _source_spans(source_page)
        for grouped_elements in grouped.values():
            bbox = fitz.Rect(_element_rect(grouped_elements[0]))
            for element in grouped_elements[1:]:
                bbox.include_rect(_element_rect(element))
            source = _merge_text(grouped_elements)
            if not _needs_translation(source):
                continue
            # Recompute the smallest containing drawing for the whole group.
            # This also handles a multi-line label whose individual elements
            # sit in the same cell but whose union centre is just outside it.
            center = fitz.Point((bbox.x0 + bbox.x1) / 2.0, (bbox.y0 + bbox.y1) / 2.0)
            inside = [
                item
                for item in containers
                if item.rect.x0 <= center.x <= item.rect.x1
                and item.rect.y0 <= center.y <= item.rect.y1
            ]
            container = min(inside, key=lambda item: item.rect.get_area()) if inside else None
            sizes = [float(element.font_size or 0.0) for element in grouped_elements]
            sizes = [size for size in sizes if size > 0]
            font_size = median(sizes) if sizes else 10.0
            color_value = _dominant_color(spans, bbox)
            fallback = "#ffffff" if container is not None and container.kind == "dark" else "#000000"
            color = _color_hex(color_value, fallback)
            bold = font_size >= 15.0
            paragraph = _Paragraph(
                page_index=page_index,
                elements=sorted(grouped_elements, key=lambda item: (float(item.y), float(item.x))),
                bbox=bbox,
                source=source,
                container=container,
                font_size=font_size,
                bold=bold,
                color=color,
            )
            paragraph.target = _target_rect(paragraph)
            paragraphs.append(paragraph)
    return paragraphs


def _char_units(text: str) -> float:
    units = 0.0
    for char in text:
        if char.isspace():
            units += 0.30
        elif ord(char) > 0x2E7F:
            units += 1.0
        elif char.isupper():
            units += 0.58
        elif char.isdigit():
            units += 0.52
        elif char in ".,;:!?'()[]{}":
            units += 0.32
        else:
            units += 0.50
    return units


def _wrap_text(text: str, width: float, size: float) -> List[str]:
    lines: List[str] = []
    # An explicit newline is a deliberate header break (for example
    # "协议\n- 对齐"); keep it rather than collapsing it into a space.
    for section in text.split("\n"):
        tokens = re.findall(
            r"\s+|[（(][A-Za-z0-9%./:+\-]+[）)]|[A-Za-z0-9][A-Za-z0-9%./:+\-]*|[\u4e00-\u9fff]|.",
            section,
        )
        current = ""
        current_width = 0.0
        for token in tokens:
            if token.isspace():
                if current and current_width + 0.30 * size <= width:
                    current += " "
                    current_width += 0.30 * size
                continue
            token_width = _text_width(token, size)
            # A single Latin token can be wider than the box; keep it intact
            # and let the fitter reduce the font size instead of breaking an
            # acronym or a parenthesized abbreviation.
            if current and current_width + token_width > width:
                # If only one or two CJK characters follow the final space,
                # move that short fragment to the next line.  This avoids
                # breaking a word such as "协议" into "协 / 议".
                cut = current.rfind(" ")
                tail = current[cut + 1 :].strip() if cut > 0 else ""
                if cut > 0 and 0 < len(tail) <= 2 and _CJK_RE.search(tail):
                    head = current[:cut].rstrip()
                    if head:
                        lines.append(head)
                        current = tail
                        current_width = _text_width(tail, size)
                if current_width + token_width > width:
                    lines.append(current.rstrip())
                    current = ""
                    current_width = 0.0
            current += token
            current_width += token_width
        if current.strip():
            lines.append(current.rstrip())
    return lines or [_clean(text)]


def _has_orphan_line(lines: Sequence[str]) -> bool:
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) == 1 and _CJK_RE.search(stripped):
            return True
        if not _CJK_RE.search(stripped) and not _LATIN_RE.search(stripped):
            return True
    return False


def _fits(text: str, rect: fitz.Rect, size: float) -> bool:
    lines = _wrap_text(text, max(20.0, rect.width - 6.0), size)
    if any(_text_width(line, size) > rect.width + 0.5 for line in lines):
        return False
    if _has_orphan_line(lines):
        return False
    line_height = size * 1.22
    return len(lines) * line_height + 2.0 <= rect.height


def _fit_size(text: str, rect: fitz.Rect, base: float) -> float:
    size = base
    # Short CJK headers look much better on one line if they can be reduced
    # slightly, rather than being split into "操作反 / 应堆".
    if " " not in text and len(text) <= 7:
        # Measure the actual glyphs; CJK and embedded acronyms have different
        # advances, and a rough 1em estimate can cause insert_htmlbox to reflow
        # a line even after our own wrapper thinks it fits.
        one_line = size
        while one_line > base * 0.68 and _text_width(text, one_line) > rect.width - 6.0:
            one_line -= 0.2
        if one_line < size:
            size = one_line
    floor = max(5.5, base * 0.55)
    # Round down rather than to the nearest tenth: rounding 9.96 to 10.0 can
    # push the final line just over the box width, producing an orphan line.
    size = math.floor(size * 10.0) / 10.0
    while size > floor and not _fits(text, rect, size):
        size -= 0.1
    return round(max(size, floor), 1)


def _translate_paragraphs(paragraphs: List[_Paragraph], service: str) -> List[_Paragraph]:
    if not paragraphs:
        return []
    from src.hd_scan_renderer import ScannedPDFTranslator

    translator = ScannedPDFTranslator(service=service)
    cache: Dict[str, str] = {}
    result: List[_Paragraph] = []
    for paragraph in paragraphs:
        translated = cache.get(paragraph.source)
        if translated is None:
            try:
                translated = translator.translate_single(paragraph.source)
            except Exception as exc:
                logger.warning("图内文字翻译失败 (%s): %s", paragraph.source[:50], exc)
                translated = ""
            translated = _clean(translated or "")
            for old, new in _TERM_FIXES.items():
                translated = translated.replace(old, new)
            if paragraph.bold and " - " in translated:
                translated = translated.replace(" - ", "\n- ", 1)
            marker = _MARKER_RE.match(paragraph.source)
            if translated and marker and not re.match(
                rf"^{re.escape(marker.group(1))}(?:[\.\、\)]\s*|\s|$)", translated
            ):
                translated = f"{marker.group(1)}. {translated}"
            cache[paragraph.source] = translated
        if not translated or translated == paragraph.source or not _CJK_RE.search(translated):
            continue
        paragraph.translated = translated
        paragraph.target = _target_rect(paragraph)
        result.append(paragraph)
    return result


def _build_fonts(paragraphs: Sequence[_Paragraph]) -> Tuple[Optional[fitz.Archive], str, Optional[tempfile.TemporaryDirectory]]:
    if not _SANS_REGULAR.is_file() or not _SANS_BOLD.is_file():
        return None, _CSS, None
    try:
        from fontTools import subset as ftsubset
        logging.getLogger("fontTools.subset").setLevel(logging.WARNING)
    except ImportError:
        logger.warning("fontTools 不可用，图内文字回退到内置 CJK 字体")
        return None, _CSS, None

    characters = "".join(item.translated for item in paragraphs)
    characters += " 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,;:()[]{}<>/+-=%&"
    temp_dir = tempfile.TemporaryDirectory(prefix="figure-fonts-")
    try:
        for filename, source in (("figure-regular.ttf", _SANS_REGULAR), ("figure-bold.ttf", _SANS_BOLD)):
            options = ftsubset.Options()
            options.name_IDs = ["*"]
            options.name_legacy = True
            options.name_languages = ["*"]
            options.notdef_outline = True
            options.recalc_bounds = True
            options.layout_features = ["*"]
            font = ftsubset.load_font(str(source), options)
            subsetter = ftsubset.Subsetter(options=options)
            subsetter.populate(unicodes={ord(char) for char in characters})
            subsetter.subset(font)
            ftsubset.save_font(font, str(Path(temp_dir.name) / filename), options)
        archive = fitz.Archive(temp_dir.name)
        return archive, _CSS, temp_dir
    except Exception:
        temp_dir.cleanup()
        raise


def _html_body(paragraph: _Paragraph, size: float, lines: Sequence[str]) -> str:
    line_height = size * 1.22
    total_height = len(lines) * line_height
    padding = max(0.0, (paragraph.target.height - total_height) / 2.0)
    family = "figure-sans-bold" if paragraph.bold else "figure-sans"
    body = "<br/>".join(html.escape(line) for line in lines)
    return (
        f'<div style="font-family:{family}; font-size:{size:.2f}pt; '
        f'line-height:1.22; color:{paragraph.color}; text-align:center; '
        f'padding-top:{padding:.2f}pt; white-space:nowrap;">{body}</div>'
    )


def _paint_page(
    page: fitz.Page,
    paragraphs: Sequence[_Paragraph],
    archive: Optional[fitz.Archive],
    css: str,
) -> int:
    if not paragraphs:
        return 0
    if page.rotation:
        logger.warning("第 %d 页为旋转页，跳过图内文字回贴", page.number + 1)
        return 0

    jobs = []
    for paragraph in paragraphs:
        size = _fit_size(paragraph.translated, paragraph.target, paragraph.font_size)
        lines = _wrap_text(paragraph.translated, max(20.0, paragraph.target.width - 6.0), size)
        jobs.append((paragraph, size, lines))

    for paragraph, _size, _lines in jobs:
        page.add_redact_annot(paragraph.target, fill=False)
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_NONE,
        graphics=fitz.PDF_REDACT_LINE_ART_NONE,
    )

    painted = 0
    for paragraph, size, lines in jobs:
        try:
            if archive is not None:
                page.insert_htmlbox(
                    paragraph.target,
                    _html_body(paragraph, size, lines),
                    css=css,
                    archive=archive,
                    scale_low=0,
                )
            else:
                page.insert_textbox(
                    paragraph.target,
                    "\n".join(lines),
                    fontsize=size,
                    fontname="china-s",
                    color=paragraph.color_rgb,
                    align=fitz.TEXT_ALIGN_CENTER,
                )
            painted += 1
        except Exception as exc:
            logger.warning("图内文字回贴失败 (%s): %s", paragraph.source[:50], exc)
    return painted


def _page_text(doc: fitz.Document, index: int) -> str:
    if index < 0 or index >= len(doc):
        return ""
    return doc[index].get_text()[:600]


def _dual_offset(mono: fitz.Document, dual: fitz.Document) -> Optional[int]:
    if len(mono) == 0 or len(dual) < len(mono) * 2:
        return None
    best_offset = 1
    best_score = -1.0
    sample = min(len(mono), 10)
    for offset in (0, 1):
        score = 0.0
        for index in range(sample):
            left = _page_text(mono, index)
            right = _page_text(dual, index * 2 + offset)
            score += SequenceMatcher(None, left, right).ratio()
        if score > best_score:
            best_score = score
            best_offset = offset
    return best_offset


def _save_atomic(doc: fitz.Document, path: Path) -> None:
    temp = path.with_name(f".{path.name}.figure.tmp")
    try:
        doc.save(temp, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()
    temp.replace(path)


def apply_figure_translations(
    source_pdf: Path,
    mono_pdf: Optional[Path] = None,
    dual_pdf: Optional[Path] = None,
    service: str = "bing",
    pages: Optional[str] = None,
) -> int:
    """Translate vector figure labels in already-generated mono/dual PDFs.

    Returns the number of text groups painted.  Any failure leaves the PDF
    untouched so a figure never blocks the main delivery pipeline.
    """
    source_pdf = Path(source_pdf)
    if not mono_pdf and not dual_pdf:
        return 0

    try:
        structure = extract_pdf_structure(source_pdf, pages=pages)
        source_doc = fitz.open(source_pdf)
        try:
            paragraphs = _collect_paragraphs(structure, source_doc)
        finally:
            source_doc.close()
    except Exception as exc:
        logger.warning("图内文字结构抽取失败，保留原图: %s", exc)
        return 0

    if not paragraphs:
        logger.info("未发现需要翻译的矢量图内文字")
        return 0

    paragraphs = _translate_paragraphs(paragraphs, service)
    if not paragraphs:
        logger.info("图内文字没有产生有效译文")
        return 0

    by_page: Dict[int, List[_Paragraph]] = {}
    for paragraph in paragraphs:
        by_page.setdefault(paragraph.page_index, []).append(paragraph)

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
            logger.warning("双语版页序探测失败，按默认页序处理: %s", exc)

    try:
        archive, css, font_temp = _build_fonts(paragraphs)
    except Exception as exc:
        logger.warning("图内字体子集化失败，使用内置 CJK 字体: %s", exc)
        archive, css, font_temp = None, _CSS, None

    painted = 0
    try:
        if mono_pdf:
            mono_path = Path(mono_pdf)
            if mono_path.is_file():
                mono_doc = fitz.open(mono_path)
                try:
                    for page_index, page_paragraphs in by_page.items():
                        if page_index < len(mono_doc):
                            painted += _paint_page(mono_doc[page_index], page_paragraphs, archive, css)
                    if painted:
                        _save_atomic(mono_doc, mono_path)
                    else:
                        mono_doc.close()
                except Exception:
                    if not mono_doc.is_closed:
                        mono_doc.close()
                    raise
                logger.info("单语版图内文字回贴: %d 组", painted)

        if dual_pdf and (painted or not mono_pdf):
            dual_path = Path(dual_pdf)
            if dual_path.is_file():
                dual_doc = fitz.open(dual_path)
                try:
                    offset = dual_offset if dual_offset is not None else (1 if not mono_pdf else None)
                    if offset is None:
                        logger.info("双语版页序无法匹配，跳过图内文字回贴")
                        dual_doc.close()
                    else:
                        dual_painted = 0
                        for page_index, page_paragraphs in by_page.items():
                            dual_index = page_index * 2 + offset
                            if dual_index < len(dual_doc):
                                dual_painted += _paint_page(dual_doc[dual_index], page_paragraphs, archive, css)
                        if dual_painted:
                            _save_atomic(dual_doc, dual_path)
                            painted += dual_painted
                            logger.info("双语版图内文字回贴: %d 组", dual_painted)
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
