#!/usr/bin/env python3
"""Conservatively remove visual line wraps from Markdown and OCR text."""

from dataclasses import dataclass
import re
from typing import List, Tuple


@dataclass(frozen=True)
class ReflowStats:
    joined_lines: int = 0
    reflowed_blocks: int = 0


_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(?:\s+|$)")
_SETEXT_OR_RULE_RE = re.compile(
    r"^\s{0,3}(?:={3,}|-{3,}|\*\s*\*\s*\*.*|_\s*_\s*_.*)\s*$"
)
_LIST_RE = re.compile(
    r"^\s*(?:"
    r"[-+*•·▪▫◦‣⁃]\s+|"
    r"\d{1,4}[.)、）]\s*|"
    r"[（(]?[一二三四五六七八九十百]+[）)、.]\s*|"
    r"`?[oO]`?\s+|"
    r"\*\*[•]\*\*\s*"
    r")"
)
_LINK_DEFINITION_RE = re.compile(r"^\s{0,3}\[(?:\^)?[^]]+\]:\s*")
_PAGE_NUMBER_RE = re.compile(
    r"^\s*(?:(?:第\s*)?\d{1,4}(?:\s*页)?|[A-Za-z]{1,3}\s*\d{1,4}[.。]?)\s*$"
)
_CAPTION_RE = re.compile(
    r"^\s*(?:图|表|附图|附表|Figure|Fig\.?|Table)\s*[A-Za-z0-9一二三四五六七八九十.-]+",
    re.IGNORECASE,
)
_CJK_RE = re.compile(
    r"[\u2e80-\u2fff\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
)
_NO_SPACE_BEFORE = set(",.;:!?%)]}>，。；：！？、％）】》〉」』〕…")
_NO_SPACE_AFTER = set("([{<（【《〈「『〔")
_PARAGRAPH_END_RE = re.compile(
    r"[.!?:。！？；;：][\"'”’」』）》】〕]*(?:\s+\d{1,4})?$"
)
_STRONG_LABEL_RE = re.compile(
    r"^\s*(?:注|说明|备注|来源|资料来源|Note|Notes?|Source)\s*[:：]",
    re.IGNORECASE,
)
_NUMBERED_HEADING_RE = re.compile(
    r"^\s*(?:第[一二三四五六七八九十百0-9]+[章节篇]|\d+(?:\.\d+){1,5}\s+)"
)


def _is_cjk(character: str) -> bool:
    return bool(character and _CJK_RE.fullmatch(character))


def _join_pair(left: str, right: str) -> str:
    left = left.rstrip()
    right = right.lstrip()
    if not left:
        return right
    if not right:
        return left
    left_character = left[-1]
    right_character = right[0]
    if (
        left_character in _NO_SPACE_AFTER
        or right_character in _NO_SPACE_BEFORE
        or _is_cjk(left_character)
        or _is_cjk(right_character)
        or (left_character in "-/" and right_character.isalnum())
    ):
        separator = ""
    else:
        separator = " "
    return left + separator + right


def _join_lines(lines: List[str]) -> Tuple[str, int]:
    if not lines:
        return "", 0
    joined = lines[0].strip()
    for line in lines[1:]:
        joined = _join_pair(joined, line.strip())
    return joined, max(0, len(lines) - 1)


def _looks_like_table_row(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("|") or stripped.endswith("|"):
        return True
    return len(re.findall(r"(?<!\\)\|", stripped)) >= 2


def _is_preserved_markdown_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    return bool(
        _FENCE_RE.match(line)
        or _HEADING_RE.match(line)
        or _SETEXT_OR_RULE_RE.match(line)
        or _LINK_DEFINITION_RE.match(line)
        or _looks_like_table_row(line)
        or stripped.startswith((">", "<!--", "</", "<!", "<?", "$$", "\\[", "\\]"))
        or stripped.startswith("![")
        or line.startswith(("    ", "\t"))
        or line.endswith("  ")
    )


def _is_long_visual_line(line: str) -> bool:
    stripped = line.strip()
    cjk_count = sum(1 for character in stripped if _is_cjk(character))
    return len(stripped) >= 40 or cjk_count >= 16


def _is_short_english_title(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 60 or _CJK_RE.search(stripped):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", stripped)
    if not 2 <= len(words) <= 9:
        return False
    significant = [word for word in words if word.lower() not in {"a", "an", "and", "for", "in", "of", "on", "the", "to"}]
    return bool(significant) and all(word[0].isupper() for word in significant)


def _looks_like_equation_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(("$", "\\", "~~", "[[", "]]", "=")) or "~~" in stripped:
        return True
    if stripped[-1:] in {"=", "×", "÷", "+", "−"} or "[[" in stripped[-12:]:
        return True
    if re.match(r"^\(\s*\d+(?:[-.]\d+)+\s*\)", stripped):
        return True
    if re.search(r"[=≈≅]", stripped[:24]):
        return True
    if len(stripped) <= 8 and not re.search(r"[A-Za-z\u3400-\u9fff]{2,}", stripped):
        return True
    return False


def _starts_with_uppercase_latin(line: str) -> bool:
    stripped = line.strip()
    if _CJK_RE.search(stripped):
        return False
    match = re.search(r"[A-Za-z]", stripped)
    return bool(match and match.group(0).isupper())


def _can_merge_false_break(left: str, right: str, *, markdown: bool) -> bool:
    left_stripped = left.strip()
    right_stripped = right.strip()
    if not left_stripped or not right_stripped:
        return False
    if not _is_long_visual_line(left_stripped):
        return False
    if _PARAGRAPH_END_RE.search(left_stripped):
        return False
    if (
        _LIST_RE.match(right_stripped)
        or _PAGE_NUMBER_RE.match(right_stripped)
        or _CAPTION_RE.match(right_stripped)
        or _STRONG_LABEL_RE.match(right_stripped)
        or _NUMBERED_HEADING_RE.match(right_stripped)
        or _is_short_english_title(right_stripped)
        or _starts_with_uppercase_latin(right_stripped)
        or _looks_like_equation_line(left_stripped)
        or _looks_like_equation_line(right_stripped)
    ):
        return False
    if markdown:
        if _is_preserved_markdown_line(left) or _is_preserved_markdown_line(right):
            return False
    elif (
        _looks_like_ocr_columns(left)
        or _looks_like_ocr_columns(right)
        or _looks_like_table_row(left)
        or _looks_like_table_row(right)
    ):
        return False
    return True


def _merge_false_blank_breaks(
    lines: List[str], *, markdown: bool
) -> Tuple[List[str], int]:
    """Remove blank separators only when surrounding lines strongly imply a wrap."""
    current = lines
    total_merges = 0
    while True:
        merged: List[str] = []
        merge_count = 0
        index = 0
        while index < len(current):
            line = current[index]
            if line != "":
                merged.append(line)
                index += 1
                continue
            next_index = index
            while next_index < len(current) and current[next_index] == "":
                next_index += 1
            if (
                merged
                and next_index < len(current)
                and _can_merge_false_break(
                    merged[-1], current[next_index], markdown=markdown
                )
            ):
                merged[-1] = _join_pair(merged[-1], current[next_index])
                merge_count += 1
                index = next_index + 1
                continue
            merged.extend(current[index:next_index])
            index = next_index
        total_merges += merge_count
        if not merge_count:
            return merged, total_merges
        current = merged


def reflow_markdown_document(markdown_text: str) -> Tuple[str, ReflowStats]:
    """Join soft-wrapped prose while preserving Markdown block structure."""
    normalized = markdown_text.replace("\r\n", "\n").replace("\r", "\n")
    had_final_newline = normalized.endswith("\n")
    output: List[str] = []
    paragraph: List[str] = []
    joined_lines = 0
    reflowed_blocks = 0
    fence_character = ""
    fence_length = 0

    def flush_paragraph():
        nonlocal joined_lines, reflowed_blocks
        if not paragraph:
            return
        joined, count = _join_lines(paragraph)
        output.append(joined)
        joined_lines += count
        if count:
            reflowed_blocks += 1
        paragraph.clear()

    for line in normalized.splitlines():
        fence_match = _FENCE_RE.match(line)
        if fence_character:
            output.append(line)
            if (
                fence_match
                and fence_match.group(1)[0] == fence_character
                and len(fence_match.group(1)) >= fence_length
            ):
                fence_character = ""
                fence_length = 0
            continue
        if fence_match:
            flush_paragraph()
            marker = fence_match.group(1)
            fence_character = marker[0]
            fence_length = len(marker)
            output.append(line)
            continue
        if not line.strip():
            flush_paragraph()
            output.append("")
            continue
        if _LIST_RE.match(line):
            flush_paragraph()
            paragraph.append(line.rstrip())
            continue
        if _is_preserved_markdown_line(line):
            flush_paragraph()
            output.append(line)
            continue
        paragraph.append(line.rstrip())

    flush_paragraph()
    output, false_break_count = _merge_false_blank_breaks(output, markdown=True)
    joined_lines += false_break_count
    reflowed_blocks += false_break_count
    result = "\n".join(output)
    if had_final_newline:
        result += "\n"
    return result, ReflowStats(joined_lines, reflowed_blocks)


def _looks_like_ocr_columns(line: str) -> bool:
    return len(re.findall(r"[ \t]{3,}", line.rstrip())) >= 2


def _reflow_ocr_text_once(ocr_text: str) -> Tuple[str, ReflowStats]:
    """Join OCR visual lines inside paragraphs without flattening obvious rows."""
    normalized = ocr_text.replace("\r\n", "\n").replace("\r", "\n")
    output: List[str] = []
    paragraph: List[str] = []
    joined_lines = 0
    reflowed_blocks = 0

    def flush_paragraph():
        nonlocal joined_lines, reflowed_blocks
        if not paragraph:
            return
        joined, count = _join_lines(paragraph)
        output.append(joined)
        joined_lines += count
        if count:
            reflowed_blocks += 1
        paragraph.clear()

    for line in normalized.splitlines():
        if not line.strip():
            flush_paragraph()
            if output and output[-1] != "":
                output.append("")
            continue
        if _LIST_RE.match(line):
            flush_paragraph()
            paragraph.append(line.rstrip())
            continue
        if (
            _PAGE_NUMBER_RE.match(line)
            or _CAPTION_RE.match(line)
            or _looks_like_ocr_columns(line)
        ):
            flush_paragraph()
            output.append(line.strip())
            continue
        paragraph.append(line.rstrip())

    flush_paragraph()
    while output and output[-1] == "":
        output.pop()
    output, false_break_count = _merge_false_blank_breaks(output, markdown=False)
    joined_lines += false_break_count
    reflowed_blocks += false_break_count
    return "\n".join(output), ReflowStats(joined_lines, reflowed_blocks)


def reflow_ocr_text(ocr_text: str) -> Tuple[str, ReflowStats]:
    """Reflow OCR text until no additional deterministic join is exposed."""
    current = ocr_text
    total_joined = 0
    total_blocks = 0
    maximum_passes = max(2, current.count("\n") + 2)
    for _pass in range(maximum_passes):
        rendered, stats = _reflow_ocr_text_once(current)
        total_joined += stats.joined_lines
        total_blocks += stats.reflowed_blocks
        if rendered == current:
            return rendered, ReflowStats(total_joined, total_blocks)
        current = rendered
    return current, ReflowStats(total_joined, total_blocks)
