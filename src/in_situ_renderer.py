#!/usr/bin/env python3
"""Dual-Layer In-Situ Layout-Preserving HTML Renderer for PDF Documents.

Generates self-contained, 1:1 page-faithful, interactive, editable HTML documents:
1. 1:1 Page Canvases: Each PDF page is rendered with its exact physical dimensions.
2. 2D Coordinate Preservation: Translated text is positioned at the exact (x, y, w, h)
   coordinates of the original text blocks.
3. In-Situ Editability: Every text block is marked `contenteditable="true"` for in-browser editing.
4. Optical Alignment: Background contains the original scanned page with a live opacity slider
   (0% pure translated text to 100% original scan overlay).
5. Hover Comparison: Hovering over any block reveals the original source text tooltip.
6. 1:1 Print/Export: Dedicated @media print CSS for exporting pixel-perfect A4 Chinese PDFs.
"""

from base64 import b64encode
import html
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.translator import TranslationEngine, clean_historical_ocr_text, split_sentences

logger = logging.getLogger("in_situ_renderer")


def is_clean_ocr_item(it: dict, page_w: float, page_h: float) -> bool:
    """Filter out vertical gutter artifacts, punch hole specks, and OCR scan noise."""
    w = float(it.get("width", 0.0))
    h = float(it.get("height", 0.0))
    x = float(it.get("x", 0.0))
    y = float(it.get("y", 0.0))
    txt = it.get("text", "").strip()

    # Extreme vertical smudge / gutter artifacts (e.g. punch hole edge streaks, binding shadows)
    if (h > 45.0 and w < 15.0) or (h > 20.0 and (h / max(w, 0.1)) > 4.5 and not txt.isalpha()):
        return False

    # Dust specks
    if h < 2.0 and w < 5.0:
        return False

    # Right-margin scanner border noise (specks beyond standard print margin)
    if x > page_w - 35.0 and w < 15.0 and len(txt) <= 4:
        return False

    # Never filter valid section numbers, list markers, single letters or functional short words
    is_num_or_sec = bool(re.match(r"^(\d+(\.\d+)*[\.:\)]?|\d+[\-\–]\d+[\.:\)]?|[A-Za-z][\.:\)]|\([A-Za-z0-9]+\)|\[\d+\])$", txt))
    is_valid_word = txt.lower() in {
        "is", "be", "as", "or", "of", "to", "in", "at", "by", "if", "an", "on", "no", "so",
        "a", "i", "-", "*", "†", "‡", "(a)", "(b)", "(c)", "(1)", "(2)",
    }
    if is_num_or_sec or is_valid_word:
        return True

    # Isolated stray punctuation or non-alphanumeric noise
    if not txt or (len(txt) == 1 and txt in ["~", "`", "^", "|", "§", "¦", "•"]):
        return False

    # Isolated tiny letter specks (scanner dust OCR artifacts, e.g. 'J', 's', 'g', 'R', 'L')
    if len(txt) == 1 and txt.isalpha() and txt.lower() not in ("a", "i") and not is_num_or_sec and w < 12.0:
        return False

    # Left-margin punch-hole noise: specks appear at x < 45.0 (e.g. 'v -', '» -')
    if x < 45.0 and len(txt) <= 4:
        return False

    # Left-margin punch-hole margin noise: letters or specks without delimiter in margins
    if x < 155.0 and len(txt) <= 2 and w < 10.0 and not is_num_or_sec:
        return False

    return True


def cluster_page_text_items(
    page_data: dict,
    line_v_tolerance: float = 8.0,
    column_h_gap: float = 35.0,
) -> List[dict]:
    """Cluster raw 2D text_items into lines and horizontal column blocks."""
    w = float(page_data["width"])
    h = float(page_data["height"])
    raw_items = page_data.get("text_items", [])
    if not raw_items:
        return []

    items = [it for it in raw_items if is_clean_ocr_item(it, w, h)]
    if not items:
        return []

    # Clamp anomalous PDF font matrix width (e.g. section numbers with corrupted font metrics)
    for it in items:
        it_txt = it.get("text", "").strip()
        it_font = float(it.get("font_size", 10.0))
        if len(it_txt) > 0 and float(it.get("width", 0.0)) / len(it_txt) > 18.0:
            it["width"] = len(it_txt) * it_font * 0.55

    # Sort top to bottom, left to right
    items_sorted = sorted(items, key=lambda it: (float(it["y"]), float(it["x"])))
    lines = []
    for it in items_sorted:
        placed = False
        iy = float(it["y"])
        ih = float(it["height"])
        ix = float(it["x"])
        iw = float(it["width"])
        for line in lines:
            line_y = sum(float(x["y"]) for x in line) / len(line)
            line_h = sum(float(x["height"]) for x in line) / len(line)
            # Tolerance allows tight typewriter baselines and superscript footnote asterisks
            tol = min(9.5, max(4.0, line_h * 0.85))
            if abs(iy - line_y) < tol:
                has_h_ov = any((min(ix + iw, float(ex["x"]) + float(ex["width"])) - max(ix, float(ex["x"]))) > 2.0 for ex in line)
                if not has_h_ov:
                    line.append(it)
                    placed = True
                    break
        if not placed:
            lines.append([it])

    lines.sort(key=lambda l: sum(float(x["y"]) for x in l) / len(l))

    blocks = []
    for l in lines:
        l.sort(key=lambda x: float(x["x"]))
        current = [l[0]]
        line_avg_y = sum(float(x["y"]) for x in l) / len(l)
        eff_col_gap = 35.0 if line_avg_y < 120.0 else 80.0
        for it in l[1:]:
            prev = current[-1]
            prev_txt = prev.get("text", "").strip()
            gap = float(it["x"]) - (float(prev["x"]) + float(prev["width"]))
            # Allow wider horizontal tab stop gap (up to 55pt) after section numbers / bullets
            max_gap = 55.0 if re.match(r"^(\*+\s*)?(\d+(\.\d+)*|[A-Za-z])[\.:\-]?$", prev_txt) else eff_col_gap
            if gap > max_gap:
                blocks.append(current)
                current = [it]
            else:
                current.append(it)
        if current:
            blocks.append(current)

    result = []
    for b in blocks:
        txt = " ".join(x["text"] for x in b).strip()
        txt = re.sub(r"\s+([,.:;?!])", r"\1", txt)
        txt = clean_historical_ocr_text(txt)
        if not txt:
            continue
        bx = min(float(x["x"]) for x in b)
        by = min(float(x["y"]) for x in b)
        bw = max(float(x["x"]) + float(x["width"]) for x in b) - bx
        bh = max(float(x["y"]) + float(x["height"]) for x in b) - by
        max_font = max(float(x.get("font_size", 10.0)) for x in b)
        result.append({
            "text": txt,
            "x": bx,
            "y": by,
            "w": bw,
            "h": bh,
            "font_size": max_font,
            "x_pct": round(bx / w * 100.0, 3),
            "y_pct": round(by / h * 100.0, 3),
            "w_pct": round(bw / w * 100.0, 3),
            "h_pct": round(bh / h * 100.0, 3),
        })
    return result


def is_roster_entry(t: str) -> bool:
    """Detect whether a line of text represents a standalone roster / distribution list recipient."""
    txt = t.strip()
    if not txt:
        return False
    words = txt.split()
    if len(words) > 5 or len(txt) > 45:
        return False
    # Numbered item like '35. P. R. Kasten', '49-50. M. W. Rosenthal', '63. Gale Young', or OCR corrupted prefix 'Lo, R. E. MacPherson'
    if re.match(r"^(\d+([\.\,\-]\d+)*[\.\,:]|\d+\s*[\-\–]\s*|[A-Za-z0-9]{1,4}[\.\,])\s+([A-Z][\.\,]*\s*)*[A-Za-z]+(\s+[A-Za-z]+)?$", txt):
        return True
    # Name with initials like 'R. G, Affel', 'J. L. Anderson', 'F. Baes', 'L. Crowley', 'L. Hudson'
    if re.match(r"^([A-Z][\.\,]+\s*)+[A-Za-z]+(\s+[A-Za-z]+)?$", txt):
        return True
    # Standalone single surname or full name like 'Blumberg' or 'Houtgzeel'
    if re.match(r"^[A-Z][a-z]{4,}$", txt):
        return True
    # Parenthetical acronym ending like '(CRL)', '(DRS)', '(LRD)', '(LRD-RC)', '(DTIE)'
    if re.search(r"\([A-Z0-9\-]{2,}\)$", txt):
        return True
    return False


def should_merge_blocks(last_b: dict, b: dict, page_w: float, max_vgap: float = 12.5) -> bool:
    """Determine whether block b is a continuation line of paragraph last_b."""
    v_gap = b["y"] - (last_b["y"] + last_b["h"])
    # Allow small negative vertical gap (-16.0) for overlapping bounding boxes in tight typewriter OCR
    if not (-16.0 <= v_gap <= max_vgap and b["y"] >= last_b["y"] - 1.0):
        return False

    last_txt = last_b["text"].rstrip()
    curr_txt = b["text"].strip()

    # Document supersession note barrier: never merge into previous body text
    if re.search(r"This document[\.\s]+supersedes", curr_txt, re.I):
        return False

    # Isolated all-caps headers/titles (e.g. NOTICE, LEGAL NOTICE, MSRE DESIGN..., OPERATING SAFETY LIMITS)
    if last_txt.isupper() and len(last_txt) < 120 and not last_txt.endswith(("-", ",")):
        return False
    if curr_txt.isupper() and len(curr_txt) < 120:
        return False

    # Measurement units at line start are NEVER new items or section numbers (e.g. 15 gpm, 28 psig, 8.1 Mw, 12-month)
    is_measurement_start = bool(re.match(
        r"^\d+(\.\d+)?\s*(gpm|psig|psi|scfd|Mw|MW|kw|kwt|ft|in|°F|°C|percent|%|curies|c|mc|pc|μCi|months?|years?|days?|hours?|sec|seconds?|elevation)\b",
        curr_txt,
        re.I
    ))

    # Major section numbers (e.g. 5.1, 5.2, 5.3, 5.4, 4.16, 1.1, or * 6.3, or 4.10 *) ALWAYS start a brand new block!
    if not is_measurement_start and re.match(r"^(\*\s*)?\d+(\.\d+)+(\s*\*+)?\s+[A-Z]", curr_txt):
        return False
    # Major chapter headers (e.g. 5. RADIATION, 6. STAFF AND PROCEDURES, 4. CONTAINMENT)
    if re.match(r"^\d+\.\s+[A-Z\s]{3,}", curr_txt):
        return False

    # Delimiter-strict numbered items: must have explicit delimiter . or : or , followed by whitespace
    is_acronym_start = bool(re.match(r"^([A-Z]\.)\s+([A-Z]\.)", curr_txt))
    is_new_item = bool(re.match(
        r"^(\d+([\.\,\-]\d+)*[\.\,:]|\d+\s*[\-\–]\s*|\([a-zA-Z0-9]+\)|\[\d+\]|[A-Z]\.|\b[Lo|k|L]\d*[\.\,])\s+",
        curr_txt
    )) and not is_acronym_start

    if is_measurement_start:
        is_new_item = False

    # Colon continuation: intro sentences ending in : (e.g. Commission:) merge cleanly into items A. or 1.
    if is_new_item and not last_txt.endswith((",", "-", ":", " and", " or")):
        return False

    # Footnote hard barrier
    if curr_txt.startswith(("*", "†", "‡")) and not last_txt.endswith(("*", "†", "‡")):
        return False

    # Alignment & column checks: standard overlap or same column half in multi-column layouts
    h_overlap = min(b["x"] + b["w"], last_b["x"] + last_b["w"]) - max(b["x"], last_b["x"])
    is_col_aligned = (abs(b["x"] - last_b["x"]) <= 32.0) or (h_overlap > 15.0)
    is_both_right = (b["x"] >= page_w * 0.55 and last_b["x"] >= page_w * 0.55)
    is_both_left = (b["x"] + b["w"] <= page_w * 0.58 and last_b["x"] + last_b["w"] <= page_w * 0.58)
    is_same_col = is_col_aligned or is_both_right or is_both_left

    # Dangling syntax: incomplete phrases ending in preposition, conjunction, comparison, or copula MUST merge!
    dangling_words = (
        "of", "at", "in", "to", "for", "than", "any", "above", "below", "between",
        "at least", "is", "be", "and", "or", "from", "with", "into", "as", "shall",
        "will", "would", "could", "may", "not", "the", "a", "an", "having", "exceed",
    )
    last_word = re.split(r"\s+", last_txt.rstrip(".,;:"))[-1].lower() if last_txt else ""
    is_dangling = (last_word in dangling_words) or last_txt.endswith(("-", ","))

    # Hanging indent check: current line is indented continuation of previous item
    is_hanging_indent = (
        0 < (b["x"] - last_b["x"]) <= 65.0 and
        (b["x"] + b["w"] <= last_b["x"] + last_b["w"] + 50.0) and
        is_dangling
    )

    if not (is_same_col or is_hanging_indent):
        return False

    # Discrete list entries (ends with parenthetical acronym like (CRL), (DRS), (LRD), or short title)
    if re.search(r"\([A-Z0-9\-]+\)$", last_txt):
        return False

    # Discrete roster / personnel distribution list items: never merge across lines unless dangling or hanging indent
    if is_roster_entry(last_txt) or is_roster_entry(curr_txt):
        if is_hanging_indent or is_dangling:
            return True
        return False

    # Always merge hanging indents or dangling syntax
    if is_hanging_indent or is_dangling:
        return True

    # Natural prose continuation:
    # Requires true multi-word wrapping line (not a short isolated stub or list item)
    is_real_prose_line = (last_b["w"] >= 105.0 and len(last_txt.split()) >= 4) or is_dangling
    if is_same_col and is_real_prose_line and (-16.0 <= v_gap <= max_vgap):
        return True

    return False


def merge_smart_paragraphs(
    blocks: List[dict],
    page_w: float,
    max_vgap: float = 12.5,
) -> List[dict]:
    """Merge lines into cohesive visual paragraph blocks preserving layout bounding boxes."""
    if not blocks:
        return []
    sorted_blocks = sorted(blocks, key=lambda b: (b["y"], b["x"]))
    paras: List[List[dict]] = []

    for b in sorted_blocks:
        merged = False
        # Search backwards through recent open paragraphs to find matching column/paragraph
        for p in reversed(paras[-8:]):
            last_b = p[-1]
            if should_merge_blocks(last_b, b, page_w, max_vgap):
                p.append(b)
                merged = True
                break
        if not merged:
            paras.append([b])

    result = []
    for p in paras:
        text = " ".join(b["text"] for b in p)
        # Unhyphenate typewriter hyphenated line wraps (e.g. con-\n trol -> control)
        text = re.sub(r"(\b[a-zA-Z]+)-\s+([a-zA-Z]+\b)", r"\1\2", text)
        bx = min(b["x"] for b in p)
        by = min(b["y"] for b in p)
        bw = max(b["x"] + b["w"] for b in p) - bx
        bh = max(b["y"] + b["h"] for b in p) - by
        total_len = sum(len(b["text"]) for b in p) or 1
        font = sum(b["font_size"] * len(b["text"]) for b in p) / total_len

        # Determine alignment: only short headers or tags are centered
        center_offset = abs((bx + bw / 2.0) - (page_w / 2.0))
        if center_offset < 28.0 and bw < page_w * 0.65 and len(p) <= 2 and len(text) < 60:
            align = "center"
        elif bx + bw > page_w - 60.0 and bw < 140.0 and bx > page_w * 0.7:
            # Only true page numbers or top right headers
            align = "right"
        else:
            align = "left"

        result.append({
            "text": text,
            "x": bx,
            "y": by,
            "w": bw,
            "h": bh,
            "font_size": round(font, 1),
            "align": align,
            "lines_count": len(p),
        })
    return result


def quantize_typography(blk: dict, page_w: float, page_h: float) -> Tuple[float, str]:
    """Map erratic OCR character font sizes into a clean, uniform, professional typographic scale."""
    raw_font = float(blk.get("font_size", 10.0))
    txt = blk.get("orig_text", blk.get("text", "")).strip()
    by = float(blk.get("y", 0.0))
    bw = float(blk.get("w", 0.0))
    align = blk.get("align", "left")
    lines_count = blk.get("lines_count", 1)

    # 1. Main Document Titles (cover page main title)
    if raw_font >= 15.0 or (align == "center" and raw_font >= 13.0 and by < page_h * 0.3):
        return 15.5, "700"

    # 2. Main Chapter / Major Part Headings (e.g. 5. RADIATION, 3. COOLANT, 6. STAFF, PART VI)
    is_part_heading = bool(re.match(r"^PART\s+[IVXLCDM]+", txt, re.I))
    is_num_chapter = bool(re.match(r"^(\d+\.|\b[IVXLCDM]+\b\.?)\s+[A-Z\s]{3,}", txt)) and not re.match(r"^[A-Z]\.\s+[A-Z][a-z]+", txt)
    is_chapter_heading = is_part_heading or is_num_chapter
    if is_chapter_heading or (raw_font >= 12.5 and len(txt) < 50 and txt.isupper()) or (raw_font >= 13.0 and len(txt) < 40 and txt.isupper()):
        return 12.5, "700"

    # 3. Section clauses (e.g. 1.8, * 1.8, 6.3, * 6.3, 4.16, etc.) ALWAYS get standard body font 11.0pt!
    is_sec = bool(re.match(r"^(\*+\s*)?(\d+(\.\d+)+)\s+", txt))
    if is_sec:
        font_weight = "600" if raw_font >= 11.0 else "400"
        return 11.0, font_weight

    # 4. Footnotes (ONLY true bottom-of-page footnotes, NOT mid-page section clauses)
    is_bottom_footnote = (
        by > page_h * 0.78 and
        (txt.startswith(("*", "†", "‡")) or raw_font <= 9.0) and
        len(txt) > 20 and
        not is_sec
    )
    if is_bottom_footnote:
        return 9.5, "400"

    # 5. Dense single-line roster / distribution list items (e.g. Page 11 personnel names)
    is_roster_item = (
        bw < page_w * 0.45 and
        not txt.rstrip().endswith("-") and
        not is_sec and
        not is_chapter_heading and
        (
            (lines_count == 1 and len(txt) < 55 and not re.search(r"[。，；,;]", txt))
            or is_roster_entry(txt)
        )
    )
    if is_roster_item:
        return 9.5, "400"

    # 6. Standard Body Paragraphs, Section Clauses, and Notice Blocks (Universal Default)
    # Scaled to 11.0pt (standard 5-hao book typography) for enhanced fullness and legibility
    return 11.0, "400"


def compute_block_typography(
    blk: dict,
    page_w: float,
    page_h: float,
) -> Tuple[float, str, float, str]:
    """Compute quantized font size, weight, adaptive line-height, and letter-spacing.

    Dynamically balances font size and line height so translated Chinese paragraphs
    occupy approximately the same vertical and horizontal footprint as the original English text.
    """
    render_font_pt, font_weight = quantize_typography(blk, page_w, page_h)
    bw = float(blk.get("w", 0.0))
    bh = float(blk.get("h", 0.0))
    lines_count = blk.get("lines_count", 1)
    zh_text = blk.get("zh_text", "")
    zh_len = len(zh_text)

    # Single line or very short block: clean, compact line height
    if lines_count == 1 or bh < 24.0 or zh_len < 25:
        line_height = 1.45
        letter_spacing = "0.02em"
    else:
        # Estimate how many lines this Chinese text will wrap into at render_font_pt
        char_w = render_font_pt * 0.95
        chars_per_line = max(1.0, bw / char_w)
        est_lines = max(1, int(math.ceil(zh_len / chars_per_line)))

        # Target line height to fill the original bounding box height bh
        target_lh = bh / (est_lines * render_font_pt)
        # Keep line-height within visually comfortable, breathable bounds (1.60 to 2.15)
        line_height = round(min(2.15, max(1.60, target_lh)), 2)
        letter_spacing = "0.035em"

    return render_font_pt, font_weight, line_height, letter_spacing


def render_insitu_html_document(
    pages_data: List[dict],
    page_image_paths: List[Path],
    translated_pages: List[List[dict]],
    title: str,
    output_path: Path,
) -> int:
    """Build a standalone, single-file In-Situ Dual-Layer HTML document."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_title = html.escape(title)

    # Encode page images as JPEG Data URIs
    page_data_uris = []
    for img_path in page_image_paths:
        if img_path.exists():
            data = b64encode(img_path.read_bytes()).decode("ascii")
            page_data_uris.append(f"data:image/jpeg;base64,{data}")
        else:
            page_data_uris.append("")

    html_parts = []
    html_parts.append(f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="generator" content="LiteParse In-Situ Dual-Layer Engine">
  <title>{escaped_title} (原位可编辑译本)</title>
  <style>
    :root {{
      --bg: #1e293b;
      --card-bg: #ffffff;
      --ink: #0f172a;
      --accent: #2563eb;
      --accent-hover: #1d4ed8;
      --line: #cbd5e1;
      --scan-opacity: 0.0;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      -webkit-font-smoothing: antialiased;
    }}

    /* Floating Toolbar */
    .toolbar {{
      position: sticky;
      top: 0;
      z-index: 1000;
      background: rgba(15, 23, 42, 0.94);
      backdrop-filter: blur(12px);
      color: #f8fafc;
      padding: 10px 24px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.12);
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35);
    }}
    .toolbar-title {{
      font-weight: 700;
      font-size: 15px;
      letter-spacing: 0.02em;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .badge {{
      background: #0284c7;
      color: #fff;
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 999px;
      font-weight: 600;
    }}
    .controls {{
      display: flex;
      align-items: center;
      gap: 18px;
      font-size: 13px;
    }}
    .slider-group {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .slider-group input[type="range"] {{
      width: 130px;
      cursor: pointer;
    }}
    .btn {{
      background: #334155;
      color: #f8fafc;
      border: 1px solid rgba(255, 255, 255, 0.2);
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 12px;
      cursor: pointer;
      font-weight: 500;
      transition: all 0.15s ease;
    }}
    .btn:hover {{ background: #475569; }}
    .btn.active {{
      background: var(--accent);
      border-color: var(--accent);
    }}
    .btn-primary {{
      background: #059669;
      border-color: #059669;
    }}
    .btn-primary:hover {{ background: #047857; }}

    /* Canvas / Pages */
    .viewport {{
      padding: 24px 12px 64px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 36px;
    }}
    .page-pair {{
      display: flex;
      flex-direction: row;
      justify-content: center;
      gap: 28px;
      max-width: 100%;
    }}
    .page-side {{
      position: relative;
      background: var(--card-bg);
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.35);
      border-radius: 4px;
      overflow: hidden;
      transform-origin: top center;
    }}
    .scan-side {{
      display: none;
    }}
    body.split-mode .scan-side {{
      display: block;
    }}
    .page-header {{
      position: absolute;
      top: -24px;
      left: 0;
      color: #94a3b8;
      font-size: 12px;
      font-weight: 600;
    }}

    /* Scan Background Image */
    .page-scan {{
      position: absolute;
      left: 0;
      top: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
      opacity: var(--scan-opacity);
      transition: opacity 0.2s ease;
      z-index: 1;
    }}

    /* Foreground In-Situ Text Layer */
    .text-layer {{
      position: absolute;
      left: 0;
      top: 0;
      width: 100%;
      height: 100%;
      z-index: 2;
    }}
    .text-block {{
      position: absolute;
      outline: none;
      color: #0f172a;
      line-height: 1.65;
      letter-spacing: 0.025em;
      word-break: break-word;
      padding: 1px 2px;
      border-radius: 3px;
      transition: background 0.15s, box-shadow 0.15s;
    }}
    .text-block:hover {{
      background: rgba(37, 99, 235, 0.08);
      box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.4);
    }}
    .text-block:focus {{
      background: #ffffff;
      box-shadow: 0 0 0 2px var(--accent);
      z-index: 10;
    }}
    body.show-boxes .text-block {{
      box-shadow: 0 0 0 1px rgba(100, 116, 139, 0.3);
    }}

    /* Tooltip */
    .text-block[data-en]::after {{
      content: attr(data-en);
      position: absolute;
      bottom: calc(100% + 6px);
      left: 0;
      min-width: 220px;
      max-width: 480px;
      background: rgba(15, 23, 42, 0.95);
      color: #e2e8f0;
      font-size: 11px;
      line-height: 1.45;
      padding: 6px 10px;
      border-radius: 6px;
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.3);
      pointer-events: none;
      opacity: 0;
      visibility: hidden;
      transition: opacity 0.15s ease;
      z-index: 999;
      white-space: normal;
    }}
    .text-block:hover::after {{
      opacity: 1;
      visibility: visible;
    }}

    /* Print Styles: 1:1 A4 PDF Export */
    @page {{
      size: auto;
      margin: 0;
    }}
    @media print {{
      body {{
        background: #fff !important;
      }}
      .toolbar {{ display: none !important; }}
      .viewport {{ padding: 0 !important; gap: 0 !important; }}
      .scan-side {{ display: none !important; }}
      .page-pair {{ display: block !important; margin: 0 !important; }}
      .pdf-page {{
        margin: 0 !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        page-break-after: always !important;
      }}
      .page-header {{ display: none !important; }}
      .page-scan {{ display: none !important; }}
      .text-block::after {{ display: none !important; }}
      .text-block {{ box-shadow: none !important; }}
    }}
  </style>
</head>
<body>

  <!-- Floating Control Bar -->
  <header class="toolbar">
    <div class="toolbar-title">
      <span>{escaped_title}</span>
      <span class="badge">原位双层可编辑排版</span>
    </div>
    <div class="controls">
      <div class="slider-group">
        <label for="opacitySlider">原件透光度:</label>
        <input type="range" id="opacitySlider" min="0" max="100" value="0" oninput="updateScanOpacity(this.value)">
        <span id="opacityVal">0%</span>
      </div>
      <button class="btn" id="btnToggleBoxes" onclick="toggleBoundingBoxes()">标注文档框</button>
      <button class="btn" id="btnSplitMode" onclick="toggleSplitMode()">左右双栏对照</button>
      <button class="btn" id="btnOverlayMode" onclick="setOverlayMode(40)">透视比对 (40%)</button>
      <button class="btn" id="btnPureZhMode" onclick="setOverlayMode(0)">纯净中文 (0%)</button>
      <button class="btn btn-primary" onclick="window.print()">导出打印 (1:1)</button>
    </div>
  </header>

  <!-- Viewport containing all pages -->
  <main class="viewport">
""")

    for p_idx, (p_data, p_img_uri, p_trans) in enumerate(zip(pages_data, page_data_uris, translated_pages), start=1):
        pw = float(p_data["width"])
        ph = float(p_data["height"])

        html_parts.append(f"""
    <!-- Page {p_idx} Pair -->
    <div class="page-pair" id="pair-{p_idx}">
      <!-- Left: Original Scan in Split Mode -->
      <section class="page-side scan-side" style="width: {pw}pt; height: {ph}pt;">
        <div class="page-header">原文扫描件 · 第 {p_idx} / {len(pages_data)} 页</div>
        <img src="{p_img_uri}" alt="Page {p_idx} Original Scan" style="width: 100%; height: 100%; object-fit: contain;">
      </section>

      <!-- Right: In-Situ Translated Editable Page -->
      <section class="page-side pdf-page" id="page-{p_idx}" style="width: {pw}pt; height: {ph}pt;">
        <div class="page-header">原位可编辑译文 · 第 {p_idx} / {len(pages_data)} 页</div>
        <img class="page-scan" src="{p_img_uri}" alt="Page {p_idx} Background Scan">
        <div class="text-layer">
""")

        for blk in p_trans:
            bx = blk["x"]
            by = blk["y"]
            bw = blk["w"]
            bh = blk["h"]
            font_size = blk["font_size"]
            align = blk.get("align", "left")
            orig_text = blk["orig_text"]
            zh_text = blk["zh_text"]

            left_pct = round(bx / pw * 100.0, 3)
            top_pct = round(by / ph * 100.0, 3)
            width_pct = round(bw / pw * 100.0, 3)
            min_height_pct = round(bh / ph * 100.0, 3)

            lines_count = blk.get("lines_count", 1)
            render_font_pt, font_weight, line_height, letter_spacing = compute_block_typography(blk, pw, ph)

            # Prevent text clipping and collision for tight single-line list entries
            if lines_count == 1 and bw < pw * 0.45 and not orig_text.rstrip().endswith("-"):
                nowrap_css = "white-space: nowrap; overflow: visible; display: flex; align-items: center;"
            else:
                nowrap_css = ""

            escaped_orig = html.escape(orig_text)
            escaped_zh = html.escape(zh_text)

            html_parts.append(f"""        <div class="text-block"
             contenteditable="true"
             data-en="{escaped_orig}"
             style="left: {left_pct}%; top: {top_pct}%; width: {width_pct}%; min-height: {min_height_pct}%; font-size: {render_font_pt}pt; font-weight: {font_weight}; line-height: {line_height}; letter-spacing: {letter_spacing}; text-align: {align}; {nowrap_css}">
          {escaped_zh}
        </div>
""")

        html_parts.append("""      </div>
      </section>
    </div>
""")

    html_parts.append("""  </main>

  <script>
    function updateScanOpacity(val) {
      document.documentElement.style.setProperty('--scan-opacity', val / 100);
      document.getElementById('opacityVal').innerText = val + '%';
    }

    function setOverlayMode(val) {
      document.getElementById('opacitySlider').value = val;
      updateScanOpacity(val);
      if (val > 0) {
        document.getElementById('btnOverlayMode').classList.add('active');
        document.getElementById('btnPureZhMode').classList.remove('active');
      } else {
        document.getElementById('btnPureZhMode').classList.add('active');
        document.getElementById('btnOverlayMode').classList.remove('active');
      }
    }

    function toggleBoundingBoxes() {
      const isShowing = document.body.classList.toggle('show-boxes');
      const btn = document.getElementById('btnToggleBoxes');
      if (isShowing) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    }

    function toggleSplitMode() {
      const isSplit = document.body.classList.toggle('split-mode');
      const btn = document.getElementById('btnSplitMode');
      if (isSplit) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    }

    // Hotkey: Space toggles 50% opacity / 0% opacity for instant in-situ optical comparison
    window.addEventListener('keydown', function(e) {
      if (e.target.isContentEditable) return;
      if (e.code === 'Space') {
        e.preventDefault();
        const current = parseInt(document.getElementById('opacitySlider').value, 10);
        setOverlayMode(current > 0 ? 0 : 50);
      }
    });
  </script>
</body>
</html>
""")

    full_html = "".join(html_parts)
    output_path.write_text(full_html, encoding="utf-8")
    return len(full_html.encode("utf-8"))


def apply_in_situ_glossary(text: str) -> str:
    """Normalize translations with verified nuclear domain glossary & scan hallucination fixes."""
    if not text:
        return text

    rules = [
        # Reactor & safety terminology
        (r"^法律通知$", "法定声明"),
        (r"移动卫星安全限制", "熔盐堆运行安全限值规程"),
        (r"移动卫星", "熔盐堆"),
        (r"REACTRATIRODR\s*限制", "反应堆实验装置 (MSRE)"),
        (r"REACTRATIRODR", "反应堆实验"),
        (r"联合纳集业公司", "联合碳化物公司"),
        (r"美籍原子能委员会", "美国原子能委员会"),
        (r"蒸气流", "缓冲容积"),
        (r"过度反应性", "过剩反应性"),
        (r"应小于临界值", "应置于次临界状态"),
        (r"通航三重点", "中子通量停堆整定值"),
        (r"安全机械断层", "安全棒紧急停堆"),
        (r"导致安全杆裂断", "触发安全棒紧急停堆"),
        (r"安全杆裂断", "安全棒紧急停堆"),
        (r"安全杆突飞猛进", "安全棒紧急停堆"),
        (r"导致安全杆突飞猛进", "触发安全棒紧急停堆"),
        (r"探空港期间", "周期停堆整定值"),
        (r"螺旋藻试验", "停堆跳闸回路试验"),
        (r"倾斜时间", "停堆落棒时间"),
        (r"控制杆", "控制棒"),
        (r"黄水", "核仪表井水"),
        (r"漏泄探测器", "泄漏检测器"),
        (r"有效期\s*--\s*--\s*在核运行期间", "反应堆周期监测仪表 -- 在核运行期间"),
        (r"细胞防护屏障", "反应堆仓屏蔽块"),
        (r"细胞氧浓度", "反应堆仓氧浓度"),
        (r"细胞漏泄率", "仓室泄漏率"),
        (r"反应堆电池", "反应堆舱室"),
        (r"排气罐电池", "排盐罐舱室"),
        (r"排水罐电池", "排盐罐舱室"),
        (r"电池漏泄率", "仓室泄漏率"),
        (r"电池", "仓室"),
        (r"反应堆电池休眠水", "反应堆仓环形水密封"),
        (r"反应器电池废墟", "反应堆仓环形空间"),
        (r"废墟的水位", "环形空间水位"),
        (r"蒸汽浓缩系统", "蒸汽冷凝系统"),
        (r"蒸汽-凝聚系统", "蒸汽冷凝系统"),
        (r"蒸气-凝结罐", "蒸汽冷凝罐"),
        (r"顶头压力", "联箱压力"),
        (r"气气供应压力", "气体供应压力"),
        (r"二丁基硫酸盐", "邻苯二甲酸二辛酯 (DOP)"),
        (r"辐射辐射", "辐射"),
        (r"堆叠释放放射性物质", "排气烟囱放射性释放"),
        (r"堆叠的木炭床", "活性炭吸附床至烟囱"),
        (r"通风库", "排气烟囱"),
        (r"堆积监测器", "烟囱辐射监测器"),
        (r"燃料应下水道", "燃料盐应排入排盐罐"),
        (r"燃料必须下水道", "燃料盐必须排入排盐罐"),
        (r"燃料盐应下水道", "燃料盐应排入排盐罐"),
        (r"下水道", "排入排盐罐"),
        (r"10\s*年中", "10"),
        (r"申国", ""),
        (r"Ty\s*的播种拖拉机[^。\n]*", ""),
        (r"非洲经济中心", "美国原子能委员会 (AEC)"),
        (r"欧洲办事处", "橡树岭业务办公室 (ORO)"),
        (r"J\.\s*现状", "J. 迪托 (Ditto)"),
        (r"P\.\s*食食", "P. 伊瑟利 (Eatherly)"),
        (r"S\.\s*贝蒂斯人", "S. 贝蒂斯 (Bettis)"),
        (r"E\.\s*铃", "E. 比尔 (Beall)"),
        (r"蓝白", "布伦伯格 (Blumberg)"),
        (r"Gale\s*Young\b", "盖尔·杨"),
        (r"加尔永", "盖尔·杨"),
        (r"工作\s*加尔永", "盖尔·杨"),
        (r"49\s*[-–]\s*50\s*号", "49-50."),
        (r"5151\s*号", "51."),
        (r"37\s*号", "37."),
        (r"E,\s*McNeese,\s*L\.E", "L. E. 麦克尼斯"),
        (r"L、A、J\.米勒", "A. J. 米勒"),
        (r"k5,\s*R\.\s*L\.\s*Moore", "45. R. L. 摩尔"),
        (r"4\.\s*E、L\.\s*Nicholson", "46. E. L. 尼科尔森"),
        (r"4\.\s*4\s*个\s*E、L\.\s*Nicholson", "46. E. L. 尼科尔森"),
        (r"48,M\.理查森", "48. M. 理查森"),
        (r"工作\s*D\.\s*斯科特", "D. 斯科特"),
        (r"5k,TI。斯皮瓦", "54. I. 斯皮瓦"),
        (r"建议\s*J\.\s*R\.\s*Weir", "J. R. 威尔"),
        (r"61l。M\.\s*E\.\s*莱夫利", "61. M. E. 沃特利"),
        (r"法兰西州\s*J\.\s*C\.\s*怀特", "J. C. 怀特"),
        (r"哈德逊", "T. L. 哈德逊"),
        (r"Houtgzeel\s*公司", "A. 豪策尔 (Houtzeel)"),
        (r"Houtgzeel", "A. 豪策尔 (Houtzeel)"),
        (r"(?:Y\s*——\s*)?12\s*文件参考资料科\(DRS\)", "Y-12 文件参考资料科 (DRS)"),
        (r"中央研究图书馆\(CRL\)", "中心研究图书馆 (CRL)"),

        # Section titles
        (r"^\*+\s*(\d+(\.\d+)+)\s+([^—\n\*]+?)\s*(——|--|-)", r"\1 \3* \4"),
        (r"4\.6\s*高压\*", "4.6 高压下的隔室泄漏试验*"),
        (r"4\.5\s*运行期间的[细胞仓漏气]+\s*率", "4.5 运行期间的隔室泄漏率"),
        (r"4\.3\s*[电池仓室]+\s*压力", "4.3 隔室压力"),
        (r"4\.4\s*[电池仓室]+\s*温度", "4.4 隔室温度"),
        (r"4\.7\s*反应堆[电池舱室]*\s*(?:休眠水|Annulus Water)", "4.7 反应堆隔室环形水密封"),
        (r"4\.16\s*热[盾屏蔽]+水流[量]*", "4.16 热屏蔽冷却水流量"),
        (r"1\.3\s*蒸发量", "1.3 缓冲容积"),
        (r"油泵喷洒冲[淡洗]盐", "冲洗盐经燃料泵循环"),
        (r"反应反常", "反应性反常"),
        (r"活性反常", "反应性反常"),
        (r"4,10\s*\*?\s*Vapor", "4.10 高压下的蒸汽冷凝系统试验*"),
        (r"\*\s*高压蒸气浓缩系统试验", "4.10 高压下的蒸汽冷凝系统试验*"),
        (r"5\s*个\s*辐射", "5. 辐射"),
        (r"5\.3\s*堆放放射性物质", "5.3 排气烟囱放射性释放"),
        (r"通风[炉室]", "排气烟囱"),
        (r"非洲经济共同体", "美国原子能委员会 (AEC)"),
        (r"欧洲区域办事处", "橡树岭业务办公室 (ORO)"),
        (r"87-96\s*年[。度]*", "87-96. "),
        (r"97\s*-98\s*号", "97-98. "),
        (r"99\s*岁[。度]*", "99. "),

        # Units and engineering quantities
        (r"([\-\+]?\d+)\s*皮[西希格]+", r"\1 psig"),
        (r"([\-\+]?\d+)\s*皮格", r"\1 psig"),
        (r"(\d+)\s*折叠", r"\1 scfd"),
        (r"不超过\s*(\d+)\s*秒", r"不应大于 \1 scfd"),
        (r"(\d+)\s*塞克", r"\1 scfd"),
        (r"(\d+)\s*克/帕", r"\1 gpm"),
        (r"(\d+)\s*克/厘米", r"\1 gpm"),
        (r"15\s*gpm", r"15 gpm"),

        # Nuclear operations and equipment
        (r"漏出率", "泄漏率"),
        (r"漏气速度", "泄漏率"),
        (r"漏气率", "泄漏率"),
        (r"漏泄试验", "泄漏试验"),
        (r"对漏泄试验", "进行泄漏试验"),
        (r"危急状态", "临界状态"),
        (r"反应器为\s*XFH3X", "反应堆处于临界状态"),
        (r"燃料应为排空", "燃料盐应排入排盐罐"),
        (r"燃料应排干", "燃料盐应排入排盐罐"),
        (r"燃料应排水", "燃料盐应排入排盐罐"),
        (r"燃料应下水道", "燃料盐应排入排盐罐"),
        (r"应对燃料进行排水", "燃料盐应排入排盐罐"),
        (r"反应器电池废墟的水位", "反应堆隔室环形空间水位"),
        (r"在\s*L\s*小时内", "在 4 小时内"),
        (r"船只。如果", "容器。如果"),
        (r"增加细胞中的氮净化量", "增加隔室中的氮气吹扫量"),
        (r"加大对细胞的氮净化力度", "增加隔室中的氮气吹扫量"),
        (r"反应器电池和排水罐电池", "反应堆隔室和排盐罐隔室"),
        (r"反应堆电池和排气罐电池", "反应堆隔室和排盐罐隔室"),

        # Em-dash normalization
        (r"\s*--\s*--\s*", " —— "),
        (r"\s+--\s+", " —— "),
        (r"(?<=[^\d\s\-])\s*-\s*(?=[^\d\s\-])", " —— "),
    ]
    for pat, repl in rules:
        text = re.sub(pat, repl, text)
    return text


def process_pdf_to_insitu_html(
    pdf_path: Path,
    output_html_path: Path,
    lit_binary: str = "/Users/joe/.local/share/agent-tools/bin/lit",
    model_dir: str = "assets/models/translation",
    dpi: int = 150,
) -> Path:
    """Full pipeline: PDF -> lit json + pdftoppm -> cluster -> translate -> In-Situ HTML."""
    start_time = time.time()
    pdf_path = Path(pdf_path).resolve()
    output_html_path = Path(output_html_path).resolve()

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        json_path = tmp_dir / "layout.json"
        img_prefix = tmp_dir / "page"

        # 1. Parse PDF layout coordinates with lit
        logger.info("正在提取 PDF 2D 坐标版面...")
        lit_cmd = [
            lit_binary, "parse", str(pdf_path),
            "--format", "json",
            "--output", str(json_path),
            "--dpi", str(dpi),
            "-q",
        ]
        res = subprocess.run(lit_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0 or not json_path.exists():
            raise RuntimeError(f"LiteParse 提取失败: {res.stderr}")

        doc_data = json.loads(json_path.read_text(encoding="utf-8"))
        pages_data = doc_data.get("pages", [])
        if not pages_data:
            raise RuntimeError("LiteParse 未提取到任何有效页面数据")

        # 2. Render 150 DPI page scans with pdftoppm
        logger.info("正在渲染高保真页面底图...")
        ppm_cmd = ["pdftoppm", "-jpeg", "-r", str(dpi), str(pdf_path), str(img_prefix)]
        res_ppm = subprocess.run(ppm_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res_ppm.returncode != 0:
            raise RuntimeError(f"pdftoppm 渲染失败: {res_ppm.stderr}")

        # Collect rendered page images
        page_imgs = sorted(tmp_dir.glob("page-*.jpg"))

        # 3. Cluster into visual paragraphs
        logger.info("正在聚合并规整原位视觉段落...")
        all_pages_paragraphs = []
        all_sents = []
        para_sent_map = []  # list of (start_idx, count) for each paragraph

        for p in pages_data:
            pw = float(p["width"])
            blocks = cluster_page_text_items(p)
            paras = merge_smart_paragraphs(blocks, pw)
            all_pages_paragraphs.append(paras)
            for pr in paras:
                cl = clean_historical_ocr_text(pr["text"])
                sents = split_sentences(cl)
                if not sents:
                    sents = [cl]
                para_sent_map.append((len(all_sents), len(sents)))
                all_sents.extend(sents)

        # 4. Batch translate using local TranslationEngine
        logger.info("正在调用本地离线翻译引擎进行高精度句子级并行翻译 (共 %d 个句子)...", len(all_sents))
        engine = TranslationEngine(model_dir)
        tr_sents = engine.translate_sentences(all_sents)

        # Re-pack translations into pages
        para_idx = 0
        translated_pages = []
        for paras in all_pages_paragraphs:
            p_blocks = []
            for pr in paras:
                start_i, count_i = para_sent_map[para_idx]
                para_idx += 1
                para_tr_sents = tr_sents[start_i : start_i + count_i]
                joined_zh = "".join(
                    s if s.endswith(("。", "；", "！", "？", ":", "：", "，", ",")) else s + " "
                    for s in para_tr_sents
                ).strip()
                zh_normalized = apply_in_situ_glossary(joined_zh)
                p_blocks.append({
                    "orig_text": pr["text"],
                    "zh_text": zh_normalized,
                    "x": pr["x"],
                    "y": pr["y"],
                    "w": pr["w"],
                    "h": pr["h"],
                    "font_size": pr["font_size"],
                    "align": pr["align"],
                    "lines_count": pr.get("lines_count", 1),
                })
            translated_pages.append(p_blocks)

        # 5. Build Dual-Layer In-Situ HTML
        logger.info("正在生成原位双层可编辑 HTML...")
        partial_output = output_html_path.with_suffix(".html.partial")
        render_insitu_html_document(
            pages_data=pages_data,
            page_image_paths=page_imgs,
            translated_pages=translated_pages,
            title=pdf_path.stem,
            output_path=partial_output,
        )

        # Atomic replacement
        os.replace(str(partial_output), str(output_html_path))
        elapsed = time.time() - start_time
        logger.info("原位 HTML 交付成功: %s (耗时 %.2f 秒)", output_html_path.name, elapsed)

    return output_html_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    src_pdf = _ROOT / "processed" / "ORNL-TM-0733REV3_MSRE_Design_Operations_Part_VI_Rev3.pdf"
    out_html = _ROOT / "outbox" / "ORNL-TM-0733REV3_MSRE_Design_Operations_Part_VI_Rev3.原位双层版.html"
    process_pdf_to_insitu_html(src_pdf, out_html)
