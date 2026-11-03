"""Repair pdf2zh pages where list paragraphs were merged into running text.

pdf2zh groups all characters that its layout model classifies as body text into
one paragraph.  On pages with several lettered/numbered list items this means
``b.``, ``c.`` and ``1)`` are emitted at the end of the previous item's last
line.  The paragraph's left edge is also the minimum x of all merged items, so
continuation lines lose their hanging indentation.

This module is deliberately narrow: it only touches pages that still contain
pdf2zh's NUL paragraph separators and whose source page has real list markers.
It keeps the existing Chinese sentences, re-wraps them inside the source
paragraph geometry, and moves the source inline underlines onto the translated
term they originally marked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from difflib import SequenceMatcher
from pathlib import Path
import re
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple
import unicodedata

import fitz

from src.translator import normalize_chinese_text

logger = logging.getLogger("text_layout_repair")

_FONT_DIR = Path.home() / ".cache/babeldoc/fonts"
_REGULAR_FONT = _FONT_DIR / "SourceHanSerifCN-Regular.ttf"
_BOLD_FONT = _FONT_DIR / "SourceHanSerifCN-Bold.ttf"

_BODY_TOP = 60.0
_BODY_BOTTOM_MARGIN = 125.0
_MAX_RULE_COUNT = 12
_MAX_LARGE_GRAPHIC_AREA = 5000.0
_LINE_STEP = 15.0

# A marker must be followed by whitespace, the end of the line, or a CJK
# character.  This prevents "2.1.d." being mistaken for a "2." list marker.
_MARKER_RE = re.compile(
    r"^((?:[a-z]|[0-9]{1,2})[.)]|[\u2022\u25cf])(?=\s|$|[\u3400-\u9fff])"
)
_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+)$")
_TOKEN_RE = re.compile(
    r"\s+|[A-Za-z0-9]+(?:[./:%+\-][A-Za-z0-9]+)*|[\u3400-\u9fff]|[^\s]"
)
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_SPACE_RE = re.compile(r"\s+")
_CLOSING_PUNCT = "。，、；：！？）】》”’"


@dataclass
class _Line:
    text: str
    bbox: fitz.Rect
    origin: float
    size: float
    bold: bool
    body_x: float


@dataclass
class _Group:
    kind: str  # "heading" or "item"
    label: str
    lines: List[_Line]
    baseline: float
    body_x: float
    cont_x: float
    right: float
    font_size: float
    bold: bool
    underline: bool = False
    target: str = ""


@dataclass
class _WrappedLine:
    text: str
    start: int
    end: int


def _marker_label(text: str) -> Optional[str]:
    match = _MARKER_RE.match(text.strip())
    return match.group(1) if match else None


def _heading_label(text: str) -> Optional[Tuple[str, str]]:
    match = _HEADING_RE.match(text.strip())
    if not match:
        return None
    return match.group(1), match.group(2).strip()


def _line_records(page: fitz.Page) -> List[_Line]:
    records: List[_Line] = []
    bottom = page.rect.height - _BODY_BOTTOM_MARGIN
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if (span.get("text") or "").strip()]
            if not spans:
                continue
            rect = fitz.Rect(line["bbox"])
            if rect.y0 < _BODY_TOP or rect.y1 > bottom:
                continue
            text = unicodedata.normalize(
                "NFKC", "".join(span.get("text", "") for span in line.get("spans", []))
            ).strip()
            if not text:
                continue
            main = max(spans, key=lambda span: float(span["bbox"][2]) - float(span["bbox"][0]))
            bold = bool(int(main.get("flags", 0)) & 16) or "Bold" in str(main.get("font", ""))
            marker = _marker_label(text)
            body_x = rect.x0
            if marker:
                seen_label = False
                for span in spans:
                    span_text = (span.get("text") or "").strip()
                    if not span_text:
                        continue
                    if not seen_label and span_text.startswith(marker):
                        seen_label = True
                        continue
                    if seen_label:
                        body_x = float(span["bbox"][0])
                        break
            else:
                heading = _heading_label(text)
                if heading:
                    font = fitz.Font("tibo" if bold else "tiro")
                    body_x = rect.x0 + font.text_length(heading[0] + "  ", float(main.get("size", 12.0)))
            records.append(
                _Line(
                    text=text,
                    bbox=rect,
                    origin=float(main.get("origin", (rect.x0, rect.y1))[1]),
                    size=float(main.get("size", 12.0)),
                    bold=bold,
                    body_x=body_x,
                )
            )
    records.sort(key=lambda item: (item.bbox.y0, item.bbox.x0))
    return records


def _is_thin_rule(drawing: dict) -> bool:
    rect = drawing.get("rect")
    fill = drawing.get("fill")
    if rect is None or fill is None:
        return False
    try:
        colour = [float(value) for value in fill[:3]]
    except (TypeError, ValueError):
        return False
    if len(colour) != 3 or max(colour) >= 0.35 or max(colour) - min(colour) >= 0.08:
        return False
    return 15.0 <= rect.width and rect.height <= 1.6


def _source_groups(page: fitz.Page) -> List[_Group]:
    groups: List[_Group] = []
    for line in _line_records(page):
        marker = _marker_label(line.text)
        heading = _heading_label(line.text)
        is_heading = bool(heading) and (line.bold or line.size >= 13.0)
        if not groups or marker is not None or is_heading:
            if marker is not None:
                groups.append(
                    _Group(
                        kind="item",
                        label=marker,
                        lines=[line],
                        baseline=line.origin,
                        body_x=0.0,
                        cont_x=0.0,
                        right=0.0,
                        font_size=line.size,
                        bold=line.bold,
                    )
                )
            elif is_heading and heading is not None:
                groups.append(
                    _Group(
                        kind="heading",
                        label=heading[0],
                        lines=[line],
                        baseline=line.origin,
                        body_x=0.0,
                        cont_x=0.0,
                        right=0.0,
                        font_size=line.size,
                        bold=line.bold,
                    )
                )
            else:
                groups.append(
                    _Group(
                        kind="item",
                        label="",
                        lines=[line],
                        baseline=line.origin,
                        body_x=0.0,
                        cont_x=0.0,
                        right=0.0,
                        font_size=line.size,
                        bold=line.bold,
                    )
                )
        else:
            groups[-1].lines.append(line)

    rules = []
    for drawing in page.get_drawings():
        if _is_thin_rule(drawing):
            rules.append(drawing["rect"])
    for group in groups:
        first = group.lines[0]
        group.baseline = first.origin
        group.font_size = first.size
        group.bold = first.bold
        group.body_x = first.body_x
        if len(group.lines) > 1 and abs(group.lines[1].bbox.y0 - first.bbox.y0) <= 1.0:
            group.body_x = max(group.body_x, group.lines[1].bbox.x0)
        group.cont_x = group.lines[1].bbox.x0 if len(group.lines) > 1 else group.body_x
        group.right = min(page.rect.width - 54.0, max(line.bbox.x1 for line in group.lines) + 1.0)
        top = min(line.bbox.y0 for line in group.lines)
        bottom = max(line.bbox.y1 for line in group.lines)
        group.underline = any(
            top - 1.0 <= rect.y0 <= bottom
            and min(group.right, rect.x1) - max(first.bbox.x0, rect.x0) > 4.0
            for rect in rules
        )
    return groups


def _safe_source_page(page: fitz.Page) -> bool:
    if page.rotation:
        return False
    if page.get_images(full=True):
        return False
    long_rules = 0
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect is None:
            continue
        if drawing.get("fill") is not None and rect.get_area() > _MAX_LARGE_GRAPHIC_AREA:
            return False
        if rect.width > 40.0 and rect.height <= 2.0:
            long_rules += 1
    return long_rules <= _MAX_RULE_COUNT


def _target_stream(page: fitz.Page) -> str:
    blocks: List[str] = []
    bottom = page.rect.height - _BODY_BOTTOM_MARGIN
    for block in sorted(page.get_text("dict").get("blocks", []), key=lambda item: item.get("bbox", (0, 0, 0, 0))[1]):
        if block.get("type") != 0:
            continue
        bbox = block.get("bbox", (0, 0, 0, 0))
        if bbox[1] < _BODY_TOP or bbox[3] > bottom:
            continue
        parts: List[str] = []
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", []))
            text = unicodedata.normalize("NFKC", text.replace("\x00", "")).strip()
            if text:
                parts.append(text)
        if parts:
            blocks.append("".join(parts))
    return _SPACE_RE.sub(" ", " ".join(blocks)).strip()


def _skip_spaces(text: str, position: int) -> int:
    while position < len(text) and text[position].isspace():
        position += 1
    return position


def _find_marker(text: str, marker: str, start: int) -> Optional[Tuple[int, int]]:
    pattern = (
        r"(?<![A-Za-z0-9.])"
        + re.escape(marker)
        + r"(?=\s|$|[\u3400-\u9fff])"
    )
    match = re.search(pattern, text[start:])
    if not match:
        return None
    return start + match.start(), start + match.end()


def _normalize_target(text: str) -> str:
    text = unicodedata.normalize("NFKC", text.replace("\x00", ""))
    text = normalize_chinese_text(text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    punctuation = {",": "，", ";": "；", ":": "：", "!": "！", "?": "？"}
    text = re.sub(
        r"(?<=[\u4e00-\u9fff\)\]])([,;:!?])(?=\s*[\u4e00-\u9fff])",
        lambda match: punctuation.get(match.group(1), match.group(1)),
        text,
    )
    return _SPACE_RE.sub(" ", text).strip()


def _strip_heading(text: str, label: str) -> Optional[str]:
    match = re.match(rf"^{re.escape(label)}\s*(.+)$", text.strip())
    return match.group(1).strip() if match else None


def _extract_targets(stream: str, groups: Sequence[_Group]) -> Optional[Dict[int, str]]:
    item_indexes = [index for index, group in enumerate(groups) if group.kind == "item" and group.label]
    heading_indexes = [index for index, group in enumerate(groups) if group.kind == "heading"]
    if len(item_indexes) < 2 or len(heading_indexes) < 2:
        return None

    positions: List[Tuple[int, int]] = []
    cursor = 0
    for index in item_indexes:
        found = _find_marker(stream, groups[index].label, cursor)
        if found is None:
            return None
        positions.append(found)
        cursor = found[1]

    title_index = heading_indexes[0]
    heading3_index = heading_indexes[-1]
    title_target = stream[: positions[0][0]].strip()
    title_body = _strip_heading(title_target, groups[title_index].label)
    if not title_body:
        return None

    bullet_position = positions[-1]
    body_start = _skip_spaces(stream, positions[-2][1])
    heading3_match = _find_marker(stream, groups[heading3_index].label, body_start)
    if heading3_match is None or heading3_match[0] >= bullet_position[0]:
        return None
    heading3_body = _strip_heading(
        stream[heading3_match[0] : bullet_position[0]].strip(),
        groups[heading3_index].label,
    )
    if not heading3_body:
        return None

    targets: Dict[int, str] = {title_index: _normalize_target(title_body)}
    targets[heading3_index] = _normalize_target(heading3_body)
    for position, index in enumerate(item_indexes):
        marker_end = positions[position][1]
        if index == item_indexes[-2]:
            item_end = heading3_match[0]
        elif position + 1 < len(positions):
            item_end = positions[position + 1][0]
        else:
            item_end = len(stream)
        body = _normalize_target(stream[marker_end:item_end])
        if not body or not _CJK_RE.search(body):
            return None
        targets[index] = body

    if any(not target for target in targets.values()):
        return None
    return targets


def _needs_cjk_space_before(text: str, token: str) -> bool:
    return bool(text) and bool(token) and text[-1].isascii() and text[-1].isalnum() and token[0].isascii() and token[0].isalnum()


def _wrap_text(
    text: str,
    font: fitz.Font,
    size: float,
    first_width: float,
    cont_width: float,
) -> List[_WrappedLine]:
    """Greedy CJK-aware wrapping with source-character indexes."""
    lines: List[_WrappedLine] = []
    current = ""
    current_start: Optional[int] = None
    current_end = 0
    width = first_width
    pending_space = False

    for match in _TOKEN_RE.finditer(text):
        token = match.group(0)
        if token.isspace():
            pending_space = True
            continue
        separator = ""
        if pending_space and current and not (current[-1].isascii() is False and token[0].isascii() is False):
            separator = " "
        candidate = current + separator + token
        if current and font.text_length(candidate, size) > width + 0.1:
            # Hanging punctuation: never leave a Chinese full stop alone on
            # the next line.  The glyph is allowed to sit in the margin by a
            # few points, as it does in normal Chinese typesetting.
            if token in _CLOSING_PUNCT:
                current += token
                current_end = match.end()
                pending_space = False
                continue
            lines.append(_WrappedLine(current, current_start or 0, current_end))
            current = token
            current_start = match.start()
            current_end = match.end()
            width = cont_width
        else:
            if not current:
                current_start = match.start()
            current += separator + token
            current_end = match.end()
        pending_space = False

    if current and current_start is not None:
        lines.append(_WrappedLine(current, current_start, current_end))
    return lines


def _fit_text(
    body: str,
    font: fitz.Font,
    source_size: float,
    body_x: float,
    cont_x: float,
    right: float,
    baseline: float,
    max_baseline: float,
) -> Tuple[float, float, List[_WrappedLine]]:
    first_width = max(20.0, right - body_x)
    cont_width = max(20.0, right - cont_x)
    sizes: List[float] = []
    step = 0.25
    value = source_size
    while value >= 10.5:
        sizes.append(round(value, 2))
        value -= step
    if not sizes:
        sizes = [source_size]

    best: Optional[Tuple[float, float, List[_WrappedLine]]] = None
    for size in sizes:
        line_step = min(17.5, max(12.8, size * 1.25))
        wrapped = _wrap_text(body, font, size, first_width, cont_width)
        if not wrapped:
            continue
        best = (size, line_step, wrapped)
        if baseline + (len(wrapped) - 1) * line_step <= max_baseline:
            return best
    assert best is not None
    return best


def _subset_font(source: Path, characters: str, output: Path) -> None:
    from fontTools import subset as ftsubset

    logging.getLogger("fontTools.subset").setLevel(logging.WARNING)

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
    ftsubset.save_font(font, str(output), options)


def _build_fonts(
    regular_text: str,
    bold_text: str,
) -> Tuple[fitz.Font, fitz.Font, Optional[tempfile.TemporaryDirectory]]:
    characters = (
        regular_text
        + bold_text
        + " 0123456789.,;:()[]{}<>/+-=%&\"'\u2022"
    )
    if not _REGULAR_FONT.is_file() or not _BOLD_FONT.is_file():
        logger.warning("未找到 SourceHanSerif 字体，回退到 PyMuPDF 内置 CJK 字体")
        return fitz.Font("china-s"), fitz.Font("china-s"), None

    try:
        from fontTools import subset  # noqa: F401
    except ImportError:
        logger.warning("fontTools 不可用，使用完整 CJK 字体")
        return (
            fitz.Font(fontfile=str(_REGULAR_FONT)),
            fitz.Font(fontfile=str(_BOLD_FONT)),
            None,
        )

    temp_dir = tempfile.TemporaryDirectory(prefix="p052-layout-fonts-")
    try:
        regular_path = Path(temp_dir.name) / "regular.ttf"
        bold_path = Path(temp_dir.name) / "bold.ttf"
        _subset_font(_REGULAR_FONT, characters, regular_path)
        _subset_font(_BOLD_FONT, characters, bold_path)
        return fitz.Font(fontfile=str(regular_path)), fitz.Font(fontfile=str(bold_path)), temp_dir
    except Exception:
        temp_dir.cleanup()
        raise


def _paint_underline(
    page: fitz.Page,
    font: fitz.Font,
    size: float,
    body: str,
    lines: Sequence[_WrappedLine],
    line_xs: Sequence[float],
    baselines: Sequence[float],
) -> None:
    sentence_end = body.find("。")
    sentence_end = len(body) if sentence_end < 0 else sentence_end + 1
    for line, x, baseline in zip(lines, line_xs, baselines):
        start = max(line.start, 0)
        end = min(line.end, sentence_end)
        if end <= start:
            continue
        prefix = body[line.start:start]
        marked = body[start:end]
        x0 = x + font.text_length(prefix, size)
        x1 = x0 + font.text_length(marked, size)
        page.draw_line(
            fitz.Point(x0, baseline + 1.8),
            fitz.Point(x1, baseline + 1.8),
            color=(0, 0, 0),
            width=0.6,
        )


def _paint_page(
    page: fitz.Page,
    groups: Sequence[_Group],
    targets: Dict[int, str],
    regular: fitz.Font,
    bold: fitz.Font,
) -> int:
    if page.rotation:
        return 0
    top = max(_BODY_TOP - 4.0, min(group.lines[0].bbox.y0 for group in groups) - 4.0)
    bottom = min(
        page.rect.height - _BODY_BOTTOM_MARGIN - 2.0,
        max(group.lines[-1].bbox.y1 for group in groups) + 6.0,
    )
    page.add_redact_annot(fitz.Rect(40.0, top, page.rect.width - 40.0, bottom), fill=False)
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_NONE,
        graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
    )

    writer = fitz.TextWriter(page.rect)
    body_fonts = {False: regular, True: bold}
    painted = 0
    for index, group in enumerate(groups):
        body = targets.get(index)
        if not body:
            continue
        font = body_fonts[group.bold]
        max_baseline = page.rect.height - _BODY_BOTTOM_MARGIN
        if index + 1 < len(groups):
            max_baseline = min(max_baseline, groups[index + 1].baseline - 1.5)
        size, step, lines = _fit_text(
            body,
            font,
            group.font_size,
            group.body_x,
            group.cont_x,
            group.right,
            group.baseline,
            max_baseline,
        )
        if not lines:
            continue

        if group.label:
            label_font = bold if group.bold else fitz.Font("tiro")
            if group.label in ("\u2022", "\u25cf"):
                label_font = fitz.Font("tiro")
            writer.append(
                fitz.Point(group.lines[0].bbox.x0, group.baseline),
                group.label,
                font=label_font,
                fontsize=size,
            )

        line_xs: List[float] = []
        baselines: List[float] = []
        for line_index, line in enumerate(lines):
            line_x = group.body_x if line_index == 0 else group.cont_x
            baseline = group.baseline + line_index * step
            line_xs.append(line_x)
            baselines.append(baseline)
            writer.append(fitz.Point(line_x, baseline), line.text, font=font, fontsize=size)

        if group.underline:
            _paint_underline(page, font, size, body, lines, line_xs, baselines)
        painted += 1

    writer.write_text(page, color=(0, 0, 0))
    return painted


def _page_indexes(spec: Optional[str], total: int) -> set[int]:
    if not spec:
        return set(range(total))
    result: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            first, last = part.split("-", 1)
            try:
                start, end = int(first), int(last)
            except ValueError:
                continue
            result.update(index - 1 for index in range(start, end + 1))
        else:
            try:
                result.add(int(part) - 1)
            except ValueError:
                continue
    return result


def _dual_offset(mono: fitz.Document, dual: fitz.Document) -> Optional[int]:
    if not len(mono) or len(dual) < len(mono) * 2:
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


def _save_atomic(document: fitz.Document, path: Path, suffix: str) -> None:
    temp = path.with_name(f".{path.name}.{suffix}.tmp")
    try:
        document.save(temp, garbage=4, deflate=True, clean=True)
    finally:
        document.close()
    temp.replace(path)


def repair_merged_list_layout(
    source_pdf: Path,
    mono_pdf: Optional[Path] = None,
    dual_pdf: Optional[Path] = None,
    pages: Optional[str] = None,
) -> int:
    """Re-flow pdf2zh list pages that lost paragraph and hanging-indent layout.

    Returns the number of pages repaired.  Any uncertainty or error leaves the
    generated PDF untouched; this is a presentation repair, not a translation
    dependency.
    """
    source_pdf = Path(source_pdf)
    if not mono_pdf or not Path(mono_pdf).is_file():
        return 0
    mono_path = Path(mono_pdf)
    dual_path = Path(dual_pdf) if dual_pdf else None

    try:
        source_doc = fitz.open(source_pdf)
        mono_doc = fitz.open(mono_path)
    except Exception as exc:
        logger.warning("段落重排无法打开 PDF: %s", exc)
        return 0

    dual_doc: Optional[fitz.Document] = None
    try:
        if dual_path and dual_path.is_file():
            try:
                dual_doc = fitz.open(dual_path)
            except Exception as exc:
                logger.warning("段落重排无法打开双语版: %s", exc)
                dual_doc = None

        allowed = _page_indexes(pages, len(source_doc))
        jobs: Dict[int, Tuple[List[_Group], Dict[int, str]]] = {}
        for index in sorted(allowed):
            if index < 0 or index >= len(source_doc) or index >= len(mono_doc):
                continue
            source_page = source_doc[index]
            target_page = mono_doc[index]
            if target_page.rotation or source_page.rotation:
                continue
            if target_page.get_text().count("\x00") < 2:
                continue
            if not _safe_source_page(source_page):
                continue
            groups = _source_groups(source_page)
            if sum(1 for group in groups if group.kind == "item" and group.label) < 2:
                continue
            targets = _extract_targets(_target_stream(target_page), groups)
            if targets is None:
                logger.info("第 %d 页未找到完整列表译文，保留原样", index + 1)
                continue
            for group, group_index in ((group, i) for i, group in enumerate(groups)):
                if group.kind == "heading":
                    group.target = targets.get(group_index, "")
                else:
                    group.target = targets.get(group_index, "")
            jobs[index] = (groups, targets)

        if not jobs:
            return 0

        all_regular = "".join(target for _groups, targets in jobs.values() for target in targets.values())
        all_bold = "".join(
            target
            for groups, targets in jobs.values()
            for index, target in targets.items()
            if groups[index].bold
        )
        regular, bold, font_temp = _build_fonts(all_regular, all_bold)
        painted = 0
        try:
            for index, (groups, targets) in jobs.items():
                painted += 1 if _paint_page(mono_doc[index], groups, targets, regular, bold) else 0
            if painted:
                _save_atomic(mono_doc, mono_path, "layout")
            else:
                mono_doc.close()

            if dual_doc is not None and dual_path is not None:
                offset: Optional[int] = None
                if mono_path.is_file():
                    probe = fitz.open(mono_path)
                    try:
                        offset = _dual_offset(probe, dual_doc)
                    finally:
                        probe.close()
                if offset is None:
                    dual_doc.close()
                else:
                    dual_painted = 0
                    for index, (groups, targets) in jobs.items():
                        dual_index = index * 2 + offset
                        if dual_index < len(dual_doc):
                            dual_painted += _paint_page(dual_doc[dual_index], groups, targets, regular, bold)
                    if dual_painted:
                        _save_atomic(dual_doc, dual_path, "layout")
                    else:
                        dual_doc.close()
        finally:
            if font_temp is not None:
                font_temp.cleanup()
        logger.info("pdf2zh 段落合并修复: %d 页正文已按源版式重排", painted)
        return painted
    except Exception as exc:
        logger.warning("pdf2zh 段落合并修复失败，保留原样: %s", exc)
        for document in (mono_doc, dual_doc):
            if document is not None and not document.is_closed:
                document.close()
        return 0
    finally:
        if not source_doc.is_closed:
            source_doc.close()
        for document in (mono_doc, dual_doc):
            if document is not None and not document.is_closed:
                document.close()
