#!/usr/bin/env python3
"""Repair collapsed LiteParse Markdown tables from its page-coordinate JSON."""

from bisect import bisect_right
from dataclasses import dataclass
import math
import re
from statistics import median
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
import unicodedata


_DIVIDER_CELL_RE = re.compile(r"^:?-{3,}:?$")
_PAGE_BREAK_RE = re.compile(r"^\s*-{5,}\s*$")
_CJK = r"\u3400-\u4dbf\u4e00-\u9fff"


@dataclass(frozen=True)
class TableIssue:
    """A Markdown table whose one or more data columns collapsed to empty."""

    page_number: int
    start_line: int
    end_line: int
    page_end_line: int
    headers: Tuple[str, ...]
    rows: Tuple[Tuple[str, ...], ...]
    divider: Tuple[str, ...]
    missing_columns: Tuple[int, ...]
    anchor_column: int


def _split_table_row(line: str) -> List[str]:
    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|") and not value.endswith(r"\|"):
        value = value[:-1]
    return [
        cell.replace(r"\|", "|").strip()
        for cell in re.split(r"(?<!\\)\|", value)
    ]


def _divider_cells(line: str) -> Optional[List[str]]:
    cells = _split_table_row(line)
    if not cells:
        return None
    compact = [cell.replace(" ", "") for cell in cells]
    if not all(_DIVIDER_CELL_RE.match(cell) for cell in compact):
        return None
    return compact


def _plain_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"[`*_~]", "", value)
    return "".join(character for character in value if character.isalnum())


def _choose_anchor(rows: Sequence[Sequence[str]], missing: Sequence[int]) -> Optional[int]:
    missing_set = set(missing)
    candidates = []
    for column in range(len(rows[0])):
        if column in missing_set:
            continue
        values = [_plain_key(row[column]) for row in rows]
        if not values or any(not value for value in values):
            continue
        unique_ratio = len(set(values)) / len(values)
        average_length = sum(len(value) for value in values) / len(values)
        score = unique_ratio * 5.0 - average_length * 0.05 - column * 0.01
        candidates.append((score, column))
    return max(candidates)[1] if candidates else None


def find_suspicious_tables(markdown_text: str) -> List[TableIssue]:
    """Locate conservative table failures without changing the document."""

    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    page_ranges = []
    page_start = 0
    page_number = 1
    for index, line in enumerate(lines):
        if _PAGE_BREAK_RE.match(line):
            page_ranges.append((page_number, page_start, index))
            page_number += 1
            page_start = index + 1
    page_ranges.append((page_number, page_start, len(lines)))

    issues = []
    for page_number, page_start, page_end in page_ranges:
        index = page_start
        while index + 1 < page_end:
            if "|" not in lines[index]:
                index += 1
                continue
            divider = _divider_cells(lines[index + 1])
            if divider is None:
                index += 1
                continue
            headers = _split_table_row(lines[index])
            column_count = max(len(headers), len(divider))
            row_index = index + 2
            rows = []
            while row_index < page_end and "|" in lines[row_index] and lines[row_index].strip():
                rows.append(_split_table_row(lines[row_index]))
                row_index += 1
            if column_count < 3 or len(rows) < 2:
                index = row_index
                continue
            headers = (headers + [""] * column_count)[:column_count]
            divider = (divider + ["---"] * column_count)[:column_count]
            padded_rows = [tuple((row + [""] * column_count)[:column_count]) for row in rows]
            missing = tuple(
                column
                for column in range(column_count)
                if all(not row[column].strip() for row in padded_rows)
            )
            anchor = _choose_anchor(padded_rows, missing) if missing else None
            if missing and anchor is not None:
                issues.append(
                    TableIssue(
                        page_number=page_number,
                        start_line=index,
                        end_line=row_index,
                        page_end_line=page_end,
                        headers=tuple(headers),
                        rows=tuple(padded_rows),
                        divider=tuple(divider),
                        missing_columns=missing,
                        anchor_column=anchor,
                    )
                )
            index = row_index
    return issues


def normalize_table_cell_spacing(markdown_text: str) -> Tuple[str, int]:
    """Remove PDF line-wrap spaces inside CJK table cells without touching prose."""

    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    changed = 0
    index = 0
    while index + 1 < len(lines):
        if "|" not in lines[index] or _divider_cells(lines[index + 1]) is None:
            index += 1
            continue
        table_line = index
        while table_line < len(lines) and "|" in lines[table_line] and lines[table_line].strip():
            if table_line != index + 1:
                value, count = re.subn(r"(?<=[%s])\s+(?=[%s])" % (_CJK, _CJK), "", lines[table_line])
                value, after_count = re.subn(r"(?<=[，。；：！？、])\s+", "", value)
                value, before_count = re.subn(r"\s+(?=[，。；：！？、])", "", value)
                if count + after_count + before_count:
                    lines[table_line] = value
                    changed += count + after_count + before_count
            table_line += 1
        index = table_line
    return "\n".join(lines), changed


def _valid_items(page: Dict) -> List[Dict]:
    items = []
    for index, raw in enumerate(page.get("text_items", [])):
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text", "")).strip()
        if not text:
            continue
        try:
            x = float(raw["x"])
            y = float(raw["y"])
            width = float(raw["width"])
            height = float(raw["height"])
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(value) for value in (x, y, width, height)):
            continue
        if width < 0 or height <= 0:
            continue
        items.append(
            {
                "id": index,
                "text": text,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "cx": x + width / 2.0,
                "cy": y + height / 2.0,
            }
        )
    return items


def _needs_space(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return left[-1].isascii() and left[-1].isalnum() and right[0].isascii() and right[0].isalnum()


def _clean_cell(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"(?<=[%s])\s+(?=[%s])" % (_CJK, _CJK), "", value)
    value = re.sub(r"(?<=[，。；：！？、])\s+", "", value)
    value = re.sub(r"\s+(?=[，。；：！？、])", "", value)
    return value


def _assemble_items(items: Iterable[Dict]) -> str:
    ordered = sorted(items, key=lambda item: (item["cy"], item["x"]))
    if not ordered:
        return ""
    line_tolerance = max(2.0, median(item["height"] for item in ordered) * 0.25)
    lines: List[List[Dict]] = []
    for item in ordered:
        if not lines:
            lines.append([item])
            continue
        current_y = sum(part["cy"] for part in lines[-1]) / len(lines[-1])
        if abs(item["cy"] - current_y) <= line_tolerance:
            lines[-1].append(item)
        else:
            lines.append([item])

    rendered_lines = []
    for line in lines:
        text = ""
        for item in sorted(line, key=lambda part: part["x"]):
            part = item["text"].strip()
            text += (" " if _needs_space(text, part) else "") + part
        rendered_lines.append(text)
    value = ""
    for line in rendered_lines:
        value += (" " if _needs_space(value, line) else "") + line
    return _clean_cell(value)


def _split_header_items(items: Sequence[Dict], column_count: int) -> Optional[List[List[Dict]]]:
    ordered = sorted(items, key=lambda item: item["cx"])
    if len(ordered) < column_count:
        return None
    if len(ordered) == column_count:
        return [[item] for item in ordered]
    gaps = sorted(
        ((ordered[index + 1]["cx"] - ordered[index]["cx"], index) for index in range(len(ordered) - 1)),
        reverse=True,
    )
    split_after = {index for _gap, index in gaps[: column_count - 1]}
    groups: List[List[Dict]] = [[]]
    for index, item in enumerate(ordered):
        groups[-1].append(item)
        if index in split_after:
            groups.append([])
    return groups if len(groups) == column_count and all(groups) else None


def _header_geometry(issue: TableIssue, items: Sequence[Dict]):
    known = [
        (column, _plain_key(value))
        for column, value in enumerate(issue.headers)
        if _plain_key(value)
    ]
    if len(known) < 2:
        return None
    wanted = {value for _column, value in known}
    matches = [item for item in items if _plain_key(item["text"]) in wanted]
    best = None
    for candidate in matches:
        tolerance = max(4.0, candidate["height"] * 0.75)
        band = [item for item in matches if abs(item["cy"] - candidate["cy"]) <= tolerance]
        labels = {_plain_key(item["text"]) for item in band}
        score = (len(labels), len(band), -candidate["cy"])
        if best is None or score > best[0]:
            best = (score, band)
    if best is None or best[0][0] < 2:
        return None
    header_y = median(item["cy"] for item in best[1])
    height = median(item["height"] for item in best[1])
    row_items = [item for item in items if abs(item["cy"] - header_y) <= max(4.0, height * 0.75)]
    groups = _split_header_items(row_items, len(issue.headers))
    if groups is None:
        return None
    headers = [_assemble_items(group) for group in groups]
    anchors = [sum(item["cx"] for item in group) / len(group) for group in groups]
    if any(anchors[index] >= anchors[index + 1] for index in range(len(anchors) - 1)):
        return None
    for column, expected in known:
        if _plain_key(headers[column]) != expected:
            return None
    header_ids = {item["id"] for group in groups for item in group}
    return headers, anchors, header_y, height, header_ids


def _anchor_centers(issue: TableIssue, items: Sequence[Dict], anchors: Sequence[float], header_y: float):
    column = issue.anchor_column
    neighbor_gaps = []
    if column > 0:
        neighbor_gaps.append(anchors[column] - anchors[column - 1])
    if column + 1 < len(anchors):
        neighbor_gaps.append(anchors[column + 1] - anchors[column])
    max_distance = max(10.0, min(neighbor_gaps) * 0.45) if neighbor_gaps else 50.0
    centers = []
    previous_y = header_y
    used = set()
    for row in issue.rows:
        expected = _plain_key(row[column])
        candidates = [
            item
            for item in items
            if item["id"] not in used
            and item["cy"] > previous_y + 0.5
            and abs(item["cx"] - anchors[column]) <= max_distance
            and _plain_key(item["text"]) == expected
        ]
        if not candidates:
            return None
        chosen = min(candidates, key=lambda item: (item["cy"], abs(item["cx"] - anchors[column])))
        used.add(chosen["id"])
        centers.append(chosen["cy"])
        previous_y = chosen["cy"]
    if any(centers[index] >= centers[index + 1] for index in range(len(centers) - 1)):
        return None
    return centers


def _reconstruct_table(issue: TableIssue, page: Dict):
    items = _valid_items(page)
    geometry = _header_geometry(issue, items)
    if geometry is None:
        return None
    headers, column_anchors, header_y, _header_height, header_ids = geometry
    row_centers = _anchor_centers(issue, items, column_anchors, header_y)
    if row_centers is None:
        return None

    gaps = [row_centers[index + 1] - row_centers[index] for index in range(len(row_centers) - 1)]
    typical_gap = median(gaps) if gaps else max(12.0, row_centers[0] - header_y)
    row_boundaries = [
        (row_centers[index] + row_centers[index + 1]) / 2.0
        for index in range(len(row_centers) - 1)
    ]
    lower = (header_y + row_centers[0]) / 2.0
    upper = row_centers[-1] + typical_gap / 2.0
    cells: List[List[List[Dict]]] = [
        [[] for _column in column_anchors] for _row in row_centers
    ]
    for item in items:
        if item["id"] in header_ids or item["cy"] < lower or item["cy"] > upper:
            continue
        row = bisect_right(row_boundaries, item["cy"])
        column = min(
            range(len(column_anchors)),
            key=lambda index: abs(item["cx"] - column_anchors[index]),
        )
        cells[row][column].append(item)
    rows = [[_assemble_items(cell) for cell in row] for row in cells]

    checks = matches = 0
    for original, rebuilt in zip(issue.rows, rows):
        for column, value in enumerate(original):
            if not _plain_key(value):
                continue
            checks += 1
            if _plain_key(value) == _plain_key(rebuilt[column]):
                matches += 1
    if checks == 0 or matches / checks < 0.8:
        return None
    for column in issue.missing_columns:
        populated = sum(bool(_plain_key(row[column])) for row in rows)
        if not _plain_key(headers[column]) or populated < max(1, math.ceil(len(rows) * 0.8)):
            return None
    return headers, rows


def _escape_cell(value: str) -> str:
    return value.replace("\\", r"\\").replace("|", r"\|").strip()


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]], divider: Sequence[str]) -> List[str]:
    def row(values):
        return "| " + " | ".join(_escape_cell(value) for value in values) + " |"

    safe_divider = [cell if _DIVIDER_CELL_RE.match(cell) else "---" for cell in divider]
    return [row(headers), row(safe_divider)] + [row(values) for values in rows]


def _detached_range(lines: Sequence[str], issue: TableIssue, headers, rows):
    target = "".join(
        _plain_key(headers[column])
        + "".join(_plain_key(row[column]) for row in rows)
        for column in issue.missing_columns
    )
    if not target:
        return None
    limit = min(issue.page_end_line, len(lines))
    for start in range(issue.end_line, limit):
        first = _plain_key(lines[start])
        if not first or not target.startswith(first):
            continue
        accumulated = ""
        for end in range(start, limit):
            chunk = _plain_key(lines[end])
            if not chunk:
                continue
            proposed = accumulated + chunk
            if not target.startswith(proposed):
                break
            accumulated = proposed
            if accumulated == target:
                return start, end + 1
    return None


def repair_markdown_tables(markdown_text: str, layout_json: Dict) -> Tuple[str, int]:
    """Rebuild only high-confidence collapsed tables; otherwise preserve original text."""

    issues = find_suspicious_tables(markdown_text)
    if not issues:
        return markdown_text, 0
    pages = {
        int(page.get("page", index + 1)): page
        for index, page in enumerate(layout_json.get("pages", []))
        if isinstance(page, dict)
    }
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    repaired = 0
    for issue in sorted(issues, key=lambda item: item.start_line, reverse=True):
        page = pages.get(issue.page_number)
        if page is None:
            continue
        rebuilt = _reconstruct_table(issue, page)
        if rebuilt is None:
            continue
        headers, rows = rebuilt
        detached = _detached_range(lines, issue, headers, rows)
        replace_end = issue.end_line
        if detached and all(not line.strip() for line in lines[issue.end_line : detached[0]]):
            replace_end = detached[1]
        replacement = _markdown_table(headers, rows, issue.divider) + [""]
        lines[issue.start_line : replace_end] = replacement
        repaired += 1
    return "\n".join(lines), repaired
