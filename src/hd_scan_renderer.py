#!/usr/bin/env python3
"""High-Definition Scanned Document PDF Translation & Publication Pipeline.

Synthesizes publication-grade, vector-quality Chinese and Dual-Language PDFs from
scanned/image-based technical and academic documents:
1. Figure Isolation & Embedding: Automatically identifies charts, diagrams, and illustrations
   on scanned pages, crops them at high resolution (DPI >= 180), strips running headers/footers,
   trims scanner borders, and embeds them cleanly into the document flow.
2. Table Isolation & High-Fidelity Rendering: Intelligently detects unstructured scanned tables,
   crops the high-resolution table grid, translates table captions, and prevents fragmented
   OCR lines from decomposing into garbled text.
3. Publication Typography: Employs Google Noto Serif CJK / Source Han Serif / Songti typography,
   strict academic margins, 1.48 line-height, elegant chapter/section headings, and clean
   academic tables without blog-like card borders or drop shadows.
4. Two-Layer Domain Translation: Bing NMT and offline CTranslate2 INT8 model with pre-translation
   heading normalization and post-translation Chinese term correction for nuclear and chemical
   engineering literature.
5. Pixel-Perfect PDF Export: Headless Google Chrome rendering with --headless=new and compositor
   stages before draw.
6. Twin Editions:
   - [stem]-中文精译版.pdf (Mono: publication-grade Chinese translation)
   - [stem]-双语对照版.pdf (Dual: 1:1 alternating original scan page & translated page)
"""

import base64
from dataclasses import dataclass, field
import html
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from PIL import Image, ImageChops
except ImportError:
    Image = None
    ImageChops = None

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.opendataloader_extractor import ExtractedDocument, extract_pdf_structure
from src.pdf2zh_patch import clean_truncated_cache, ensure_pdf2zh_environment_ready, smart_join_translated, split_into_chunks
from src.translator import TranslationConfig, TranslationEngine, clean_historical_ocr_text, normalize_chinese_text

logger = logging.getLogger("hd_scan_renderer")

# English-to-Chinese Domain Glossary (applied to English text)
SCAN_PDF_GLOSSARY: List[Tuple[str, str]] = [
    (r"\bhomogeneous reactor\b", "均质反应堆"),
    (r"\bhomogeneous reactors\b", "均质反应堆"),
    (r"\bfluid fuel reactor\b", "流体燃料反应堆"),
    (r"\bfluid fuel reactors\b", "流体燃料反应堆"),
    (r"\bfission product\b", "裂变产物"),
    (r"\bfission products\b", "裂变产物"),
    (r"\bthermal breeder\b", "热中子增殖堆"),
    (r"\bchemical processing\b", "化学处理"),
    (r"化学加工", "化学处理"),
    (r"\bneutron poisoning\b", "中子中毒"),
    (r"\bpoison effect\b", "中毒效应"),
    (r"\bINTRODUCTION\b", "引言"),
    (r"\bhydroclone\b", "水力旋流器"),
    (r"\bhydroclones\b", "水力旋流器"),
    (r"\bslurry\b", "浆液"),
    (r"\bslurries\b", "浆液"),
    (r"\buranyl sulfate\b", "硫酸双氧铀"),
    (r"\bcorrosion products\b", "腐蚀产物"),
    (r"\bbiological hazard\b", "生物危害"),
    (r"\bbiological hazards\b", "生物危害"),
    (r"\bunderflow receiver\b", "底流接收器"),
    (r"\bflowsheet\b", "流程图"),
    (r"\bflowsheets\b", "流程图"),
    (r"\bfission yield\b", "裂变产额"),
    (r"\bcore\b", "堆芯"),
    (r"\bblanket\b", "再生区"),
    (r"\bblanket material\b", "再生区材料"),
    (r"\bheavy water\b", "重水"),
    (r"\bpressurizer\b", "稳压器"),
    (r"\bdegasser\b", "脱气器"),
]

# Post-translation Chinese term correction (correcting common MT mis-translations)
SCAN_PDF_ZH_CORRECTIONS: List[Tuple[str, str]] = [
    (r"毛毯材料|毯区材料|毯材料", "再生区材料"),
    (r"毛毯|毯区", "再生区"),
    (r"毒化效果|毒害作用|中毒效果", "中毒效应"),
    (r"中子毒化", "中子中毒"),
    (r"均相反应堆|均相堆", "均质反应堆"),
    (r"流体燃料反应堆|液体燃料反应堆", "流体燃料反应堆"),
    (r"热增殖反应堆|热增殖堆", "热中子增殖堆"),
    (r"核心处理", "堆芯处理"),
    (r"反应堆核心", "反应堆堆芯"),
    (r"核心中", "堆芯中"),
    (r"两区反应堆", "双区反应堆"),
    (r"双区域反应堆", "双区反应堆"),
    (r"两区钚生产者", "双区钚反应堆"),
    (r"两区热增殖", "双区热中子增殖"),
    (r"水旋流器|旋流分离器|水力旋流", "水力旋流器"),
    (r"铀酰硫酸|硫酸铀酰", "硫酸双氧铀"),
    (r"^(\d+)[-–\.]\s*([0-9l1I])\s*\.?\s*(?:介绍|引言)", r"\1-1. 引言"),
    (r"^(\d+[-–\.]\d*(\.\d+)*)\.?\s*(?:介绍|引言)", r"\1. 引言"),
    (r"图\s*G-", "图 6-"),
    (r"表\s*G-", "表 6-"),
    (r"第\s*6\s*章化学处理", "第 6 章 化学处理"),
    (r"包覆材料", "再生区材料"),
]


def find_chrome_binary() -> Optional[Path]:
    """Locate Google Chrome, Chromium, or Microsoft Edge executable."""
    candidates = [
        # macOS
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        # Windows
        Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
        # PATH
        Path(shutil.which("google-chrome") or ""),
        Path(shutil.which("chrome") or ""),
        Path(shutil.which("chromium") or ""),
        Path(shutil.which("msedge") or ""),
    ]
    for c in candidates:
        if str(c) and c.is_file():
            if sys.platform == "win32" or os.access(str(c), os.X_OK):
                return c
    return None


def crop_page_figure(
    page: Any,
    clip_rect: Any,
    dpi: int = 180,
    trim_whitespace: bool = True,
) -> Optional[str]:
    """Crop a high-resolution region from a PDF page and return as a Base64 PNG data URI."""
    if fitz is None or page is None or clip_rect is None:
        return None

    try:
        pix = page.get_pixmap(dpi=dpi, clip=clip_rect)
        if pix.width < 10 or pix.height < 10:
            return None

        png_bytes = pix.tobytes("png")
        if not trim_whitespace or Image is None or ImageChops is None:
            b64_data = base64.b64encode(png_bytes).decode("ascii")
            return f"data:image/png;base64,{b64_data}"

        # Trim peripheral white/uniform scanner noise
        img = Image.open(io.BytesIO(png_bytes))
        bg = Image.new(img.mode, img.size, (255, 255, 255))
        diff = ImageChops.difference(img, bg)
        # Moderate thresholding to discount faint background scanner grain
        diff = ImageChops.add(diff, diff, 2.0, -25)
        bbox = diff.getbbox()
        if bbox:
            w, h = img.size
            pad_bbox = (
                max(0, bbox[0] - 4),
                max(0, bbox[1] - 4),
                min(w, bbox[2] + 4),
                min(h, bbox[3] + 4),
            )
            cropped = img.crop(pad_bbox)
        else:
            cropped = img

        out_buf = io.BytesIO()
        cropped.save(out_buf, format="PNG", optimize=True)
        b64_data = base64.b64encode(out_buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64_data}"
    except Exception as exc:
        logger.warning("裁剪图片区域失败 %s: %s", clip_rect, exc)
        return None


def detect_figures_on_page(
    page: Any,
    text_blocks: List[Dict[str, Any]],
) -> Dict[int, Tuple[str, float]]:
    """Detect figure captions and crop the corresponding illustrations.

    Guarantees that book running headers and footers are never included in the crop.

    Returns:
        Mapping from caption block index to tuple of (base64 Data URI, original height pt).
    """
    if fitz is None or page is None:
        return {}

    pw = page.rect.width
    ph = page.rect.height
    header_guard = max(52.0, ph * 0.088)
    footer_guard = ph * 0.92
    figure_map: Dict[int, Tuple[str, float]] = {}

    for idx, b in enumerate(text_blocks):
        txt = b.get("text", "").strip()
        m = re.match(r"^(FIG|Figure|Fig|图)[\s\.\–\-]+([0-9]+([\.\-][0-9]+)*)", txt, re.IGNORECASE)
        if not m:
            continue

        # Check if this block is a figure caption
        is_caption = ("." in txt[:15] or ":" in txt[:15] or len(txt) < 120)
        if not is_caption:
            continue

        # In scientific publications, the illustration sits above the caption
        prev_bottom = header_guard
        if idx > 0:
            prev_b = text_blocks[idx - 1]
            prev_bottom = max(header_guard, float(prev_b.get("y", 0.0)) + float(prev_b.get("h", 0.0)))

        cy0 = float(b.get("y", 0.0))
        fig_top = max(header_guard, prev_bottom + 4.0)
        fig_bottom = min(footer_guard, max(fig_top + 26.0, cy0 - 4.0))
        fig_left = 30.0
        fig_right = pw - 30.0
        fig_height_pt = fig_bottom - fig_top

        # Minimum height threshold for an illustration (at least 24 pt)
        if fig_height_pt >= 24.0:
            clip_rect = fitz.Rect(fig_left, fig_top, fig_right, fig_bottom)
            data_uri = crop_page_figure(page, clip_rect, dpi=180)
            if data_uri:
                figure_map[idx] = (data_uri, fig_height_pt)
                logger.info("成功分离并裁剪原图: 页 %d 序号 %d (%s, 高度 %.1f pt, 顶部 %.1f pt)",
                            page.number + 1, idx, m.group(0), fig_height_pt, fig_top)

    return figure_map


def detect_unstructured_tables_on_page(
    page: Any,
    text_blocks: List[Dict[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    """Detect unstructured tables on scanned pages and crop their grid regions.

    Returns:
        Mapping from table caption block index to dict with:
        'uri': base64 Data URI of cropped table grid,
        'height': height in pt,
        'caption': full combined caption text,
        'skip_indices': list of internal element indices inside the table body to skip.
    """
    if fitz is None or page is None:
        return {}

    pw = page.rect.width
    ph = page.rect.height
    header_guard = max(52.0, ph * 0.088)
    footer_guard = ph * 0.92
    tables_map: Dict[int, Dict[str, Any]] = {}

    i = 0
    while i < len(text_blocks):
        b = text_blocks[i]
        txt = b.get("text", "").strip()
        m = re.match(r"^(TABLE|Table|表)[\s\.\–\-]+([0-9]+([\.\-][0-9]+)*)", txt, re.IGNORECASE)
        if not m:
            i += 1
            continue

        cap_texts = [txt]
        cap_top = float(b.get("y", 0.0))
        cap_bottom = cap_top + float(b.get("h", 0.0))
        j = i + 1

        # Collect continuation lines of table title
        while j < len(text_blocks):
            nxt = text_blocks[j]
            nxt_txt = nxt.get("text", "").strip()
            # Stop if this is clearly a section header, another table, or a figure
            if re.match(r"^(TABLE|Table|FIG|Fig|[1-9]\d*[-–\.]\d+(\.\d+)*\.?\s+[A-Za-z])", nxt_txt, re.I):
                break
            # Stop if line is clearly tabular data cell content
            if any(k in nxt_txt for k in ["mg/kg", "Solubility,", "ppm", "La2(", "Ce2(", "Nd2("]):
                break
            if (nxt_txt.isupper() or len(nxt_txt) < 80) and not any(ch in nxt_txt for ch in ["|", "\t"]):
                cap_texts.append(nxt_txt)
                cap_bottom = float(nxt.get("y", 0.0)) + float(nxt.get("h", 0.0))
                j += 1
            else:
                break

        full_caption = " ".join(cap_texts)

        # Collect table body elements
        body_indices: List[int] = []
        grid_top = cap_bottom + 2.0
        grid_bottom = grid_top
        k = j

        while k < len(text_blocks):
            cur = text_blocks[k]
            cur_txt = cur.get("text", "").strip()
            # Stop condition: another table, figure, or section heading
            if re.match(r"^(TABLE|Table|FIG|Fig|[1-9]\d*[-–\.]\d+(\.\d+)*\.?\s+[A-Za-z])", cur_txt, re.I):
                break
            if len(cur_txt) > 80 and cur_txt[0].isupper() and float(cur.get("w", 0.0)) > (pw * 0.65):
                break
            body_indices.append(k)
            grid_bottom = max(grid_bottom, float(cur.get("y", 0.0)) + float(cur.get("h", 0.0)))
            k += 1

        grid_height = grid_bottom - grid_top
        if body_indices and grid_height >= 20.0:
            clip_top = max(header_guard, grid_top - 2.0)
            clip_bottom = min(footer_guard, grid_bottom + 4.0)
            clip_rect = fitz.Rect(30.0, clip_top, pw - 30.0, clip_bottom)
            data_uri = crop_page_figure(page, clip_rect, dpi=180)
            if data_uri:
                tables_map[i] = {
                    "uri": data_uri,
                    "height": clip_bottom - clip_top,
                    "caption": full_caption,
                    "skip_indices": list(range(i + 1, k)),
                }
                logger.info("成功探测并隔离表格: 页 %d 序号 %d (%s, 高度 %.1f pt, 涵盖块 %d..%d)",
                            page.number + 1, i, m.group(0), clip_bottom - clip_top, i, k - 1)

        i = max(i + 1, k)

    return tables_map


class ScannedPDFTranslator:
    """Translation manager supporting Bing NMT and local CTranslate2 with domain protection."""

    def __init__(self, service: str = "bing", model_dir: Optional[Path] = None):
        self.service = service.lower()
        self.model_dir = model_dir or (_ROOT / "assets/models/translation")
        self._bing_translator = None
        self._ct2_engine = None
        self._cache: Dict[str, str] = {}

    def _get_bing_translator(self):
        if self._bing_translator is not None:
            return self._bing_translator

        ensure_pdf2zh_environment_ready()
        cand_venvs = [
            Path.home() / ".local/venvs/pdf2zh",
            Path("/Users/joe/.local/venvs/pdf2zh"),
        ]
        for v in cand_venvs:
            sites = list(v.glob("lib/python*/site-packages"))
            if sites and str(sites[0]) not in sys.path:
                sys.path.insert(0, str(sites[0]))
                break

        try:
            from pdf2zh.translator import BingTranslator
            self._bing_translator = BingTranslator(lang_in="en", lang_out="zh", model="")
            return self._bing_translator
        except Exception as e:
            logger.warning("无法初始化 BingTranslator (%s)，降级为本地离线引擎", e)
            return None

    def _get_ct2_engine(self) -> TranslationEngine:
        if self._ct2_engine is None:
            self._ct2_engine = TranslationEngine(self.model_dir)
        return self._ct2_engine

    def apply_domain_glossary(self, text: str) -> str:
        """Apply specialized technical terminology protection to English input."""
        for pattern, replacement in SCAN_PDF_GLOSSARY:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        # Standardize figure/table captions
        text = re.sub(r"^(FIG|Figure|Fig)\.?\s*([0-9]+([\.\-][0-9]+)*)", r"图 \2", text, flags=re.IGNORECASE)
        text = re.sub(r"^(TABLE|Table)\s*([0-9]+([\.\-][0-9]+)*)", r"表 \2", text, flags=re.IGNORECASE)
        return text

    def apply_zh_corrections(self, text: str) -> str:
        """Post-correct common machine translation defects in nuclear/chemical terminology."""
        for pattern, replacement in SCAN_PDF_ZH_CORRECTIONS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def translate_single(self, text: str) -> str:
        """Translate a single paragraph or heading with caching."""
        text = text.strip()
        if not text:
            return ""

        if text in self._cache:
            return self._cache[text]

        cleaned = clean_historical_ocr_text(text)

        # Fast path for structural section / chapter headers
        m_intro = re.match(r"^(\*+\s*)?(\d+[-–\.]\s*[0-9l1I](\.\d+)*)\s*\.?\s*INTRODUCTION\b", cleaned, re.IGNORECASE)
        if m_intro:
            sec_num = m_intro.group(2).replace("l", "1").replace("I", "1").replace(" ", "")
            res = f"{sec_num}. 引言"
            self._cache[text] = res
            return res

        translated = ""
        if self.service == "bing":
            bt = self._get_bing_translator()
            if bt:
                try:
                    chunks = split_into_chunks(cleaned, max_len=750)
                    tr_chunks = []
                    for chunk in chunks:
                        tr_chunk = bt.translate(chunk)
                        tr_chunks.append(tr_chunk)
                    translated = smart_join_translated(tr_chunks)
                except Exception as exc:
                    logger.warning("Bing 翻译失败 (%s)，使用本地离线模型回退: %s", exc, cleaned[:40])
                    translated = ""

        if not translated:
            engine = self._get_ct2_engine()
            try:
                from src.translator import split_sentences
                sents = split_sentences(cleaned) or [cleaned]
                tr_sents = engine.translate_sentences(sents)
                joined = "".join(
                    s if s.endswith(("。", "；", "！", "？", ":", "：", "，", ",")) else s + " "
                    for s in tr_sents
                ).strip()
                translated = joined
            except Exception as e:
                logger.error("本地离线翻译失败: %s", e)
                translated = cleaned

        translated = normalize_chinese_text(translated)
        translated = self.apply_domain_glossary(translated)
        translated = self.apply_zh_corrections(translated)

        self._cache[text] = translated
        return translated

    def translate_batch(self, texts: List[str]) -> List[str]:
        return [self.translate_single(t) for t in texts]


def merge_caption_continuations(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Join fragmented caption continuation lines into a cohesive block."""
    merged = []
    skip = False
    for i in range(len(elements)):
        if skip:
            skip = False
            continue
        cur = dict(elements[i])
        txt = cur.get("text", "").strip()
        if i + 1 < len(elements) and re.match(r"^(FIG|Figure|Fig|图)[\s\.\–\-]+([0-9]+([\.\-][0-9]+)*)", txt, re.I):
            nxt = elements[i + 1]
            nxt_txt = nxt.get("text", "").strip()
            v_gap = nxt.get("y", 0.0) - (cur.get("y", 0.0) + cur.get("h", 0.0))
            if v_gap < 16.0 and len(nxt_txt) < 90 and not re.match(r"^(FIG|TABLE|\d+\.|\d+[\-\–]\d+)", nxt_txt, re.I):
                cur["text"] = txt + " " + nxt_txt
                cur["h"] = (nxt.get("y", 0.0) + nxt.get("h", 0.0)) - cur.get("y", 0.0)
                skip = True
        merged.append(cur)
    return merged


def split_chapter_and_section_titles(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Split joint title blocks such as 'CHAPTER 6 CHEMICAL PROCESSING* 6-1. INTRODUCTION'."""
    m = re.search(r"(\b\d+[-–\.]\s*[0-9l1I]\b[\s\.]+[A-Z\s]{3,})", text)
    if m and re.match(r"^(CHAPTER|PART)\s+\d+", text, re.IGNORECASE):
        chap = text[:m.start()].strip()
        sec = text[m.start():].strip()
        return chap, sec
    return None, None


def generate_publication_html(
    document: ExtractedDocument,
    translator: ScannedPDFTranslator,
    page_figure_maps: Dict[int, Dict[int, Tuple[str, float]]],
    page_table_maps: Optional[Dict[int, Dict[int, Dict[str, Any]]]] = None,
    title: str = "Translated Paper",
    is_dual: bool = False,
    page_dims: Optional[Dict[int, Tuple[float, float]]] = None,
) -> str:
    """Generate publication-grade HTML with Google Noto / Source Han Serif typography."""
    first_page_w = 419.0
    first_page_h = 594.0
    if page_dims and 1 in page_dims:
        first_page_w, first_page_h = page_dims[1]

    tables_by_page = page_table_maps or {}

    css = f"""
@page {{
    size: {first_page_w:.1f}pt {first_page_h:.1f}pt;
    margin: 20pt 24pt 20pt 24pt;
    @bottom-center {{
        content: counter(page);
        font-family: "Noto Serif CJK SC", "Source Han Serif SC", "Songti SC", serif;
        font-size: 8.0pt;
        color: #777;
    }}
}}
* {{
    box-sizing: border-box;
}}
body {{
    margin: 0;
    padding: 0;
    background: #ffffff;
    color: #1a1a1a;
    font-family: "Noto Serif CJK SC", "Source Han Serif SC", "Songti SC", "STSong", "SimSun", serif;
    font-size: 8.8pt;
    line-height: 1.48;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
}}
.paper-page {{
    position: relative;
}}
.paper-page:not(:last-child) {{
    page-break-after: always;
}}
.chapter-header {{
    text-align: center;
    margin: 8pt 0 14pt 0;
    padding-bottom: 6pt;
    border-bottom: 1.2pt solid #222;
}}
.chapter-badge {{
    font-family: "Noto Sans CJK SC", "PingFang SC", sans-serif;
    font-size: 9.5pt;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #555;
    text-transform: uppercase;
}}
.chapter-main-title {{
    font-size: 14pt;
    font-weight: 800;
    margin-top: 4pt;
    letter-spacing: 0.03em;
    color: #111;
}}
h2.section-heading {{
    font-family: "Noto Serif CJK SC", "Songti SC", serif;
    font-size: 10.5pt;
    font-weight: 700;
    margin: 12pt 0 5pt 0;
    color: #111;
    page-break-after: avoid;
    letter-spacing: 0.01em;
}}
h3.subsection-heading {{
    font-family: "Noto Serif CJK SC", "Songti SC", serif;
    font-size: 9.2pt;
    font-weight: 700;
    margin: 10pt 0 4pt 0;
    color: #2b2b2b;
    page-break-after: avoid;
}}
p.body-para {{
    margin: 4.5pt 0;
    text-align: justify;
    text-justify: inter-ideograph;
    text-indent: 2em;
}}
.bilingual-pair {{
    margin: 6pt 0;
    page-break-inside: avoid;
}}
.orig-en {{
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 8.0pt;
    line-height: 1.35;
    color: #555555;
    margin-bottom: 2pt;
    text-align: justify;
}}
.trans-zh {{
    font-family: "Noto Serif CJK SC", "Songti SC", serif;
    font-size: 8.8pt;
    line-height: 1.48;
    color: #111111;
    text-indent: 2em;
    text-align: justify;
}}
figure.paper-figure {{
    margin: 6pt auto 8pt auto;
    text-align: center;
    page-break-inside: avoid;
}}
figure.paper-figure img {{
    max-width: 96%;
    height: auto;
    display: block;
    margin: 0 auto;
    border: none;
    image-rendering: -webkit-optimize-contrast;
}}
figcaption {{
    font-family: "Noto Serif CJK SC", "Songti SC", serif;
    font-size: 8.2pt;
    font-weight: 600;
    color: #222;
    margin-top: 3pt;
    line-height: 1.32;
    text-align: center;
}}
.figcaption-en {{
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 7.2pt;
    color: #666;
    font-weight: normal;
    display: block;
    margin-top: 1pt;
}}
.table-container {{
    margin: 8pt auto 10pt auto;
    text-align: center;
    page-break-inside: avoid;
}}
.table-caption {{
    font-family: "Noto Serif CJK SC", "Songti SC", serif;
    font-size: 8.4pt;
    font-weight: 700;
    text-align: center;
    margin-bottom: 4pt;
    color: #111;
}}
table.paper-table {{
    width: 100%;
    margin: 0 auto;
    border-collapse: collapse;
    border-top: 1.5pt solid #111;
    border-bottom: 1.5pt solid #111;
    font-size: 8.0pt;
}}
table.paper-table th {{
    border-bottom: 0.75pt solid #333;
    padding: 4pt 5pt;
    font-weight: bold;
    text-align: center;
    background-color: #fafafa;
}}
table.paper-table td {{
    padding: 3.5pt 5pt;
    border-bottom: 0.5pt solid #eee;
    text-align: left;
    vertical-align: middle;
}}
.page-footnote {{
    border-top: 0.5pt solid #aaa;
    margin-top: 12pt;
    padding-top: 3pt;
    font-size: 7.5pt;
    color: #555;
    line-height: 1.3;
}}
.reference-item {{
    font-size: 8.0pt;
    line-height: 1.4;
    margin: 3.5pt 0;
    padding-left: 2em;
    text-indent: -2em;
    color: #333;
}}
"""

    html_parts = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '  <meta charset="utf-8">',
        f"  <title>{html.escape(title)}</title>",
        f"  <style>{css}</style>",
        "</head>",
        "<body>",
    ]

    for page_obj in document.pages:
        p_num = page_obj.page_num
        pw = page_obj.width
        ph = page_obj.height

        raw_elements = [el.to_dict() for el in page_obj.elements]
        elements = merge_caption_continuations(raw_elements)
        figure_map = page_figure_maps.get(p_num, {})
        page_tables = tables_by_page.get(p_num, {})

        # Compute all indices that belong to table bodies to skip emitting as paragraphs
        skip_element_indices: Set[int] = set()
        for tbl_info in page_tables.values():
            skip_element_indices.update(tbl_info.get("skip_indices", []))

        html_parts.append(f'  <div class="paper-page" id="page-{p_num}">')

        for idx, el in enumerate(elements):
            if idx in skip_element_indices:
                continue

            txt = el.get("text", "").strip()
            if not txt and not el.get("is_table"):
                continue

            # Check if this element is an unstructured table caption with cropped grid
            tbl_info = page_tables.get(idx)
            if tbl_info:
                tbl_uri = tbl_info["uri"]
                grid_h = tbl_info["height"]
                full_cap = tbl_info["caption"]
                zh_tbl_cap = translator.translate_single(full_cap)
                html_parts.append('    <div class="table-container">')
                if is_dual:
                    html_parts.append(f'      <div class="table-caption">{html.escape(zh_tbl_cap)}<span class="figcaption-en">{html.escape(full_cap)}</span></div>')
                else:
                    html_parts.append(f'      <div class="table-caption">{html.escape(zh_tbl_cap)}</div>')
                max_h_style = f' style="max-height: {min(grid_h + 10, ph * 0.75):.1f}pt;"'
                html_parts.append('      <figure class="paper-figure" style="margin: 2pt auto 8pt auto;">')
                html_parts.append(f'        <img src="{tbl_uri}" alt="{html.escape(full_cap)}"{max_h_style} />')
                html_parts.append("      </figure>")
                html_parts.append("    </div>")
                continue

            # Check if this element has an attached cropped figure
            fig_info = figure_map.get(idx)
            if fig_info:
                fig_uri, orig_h = fig_info
                zh_cap = translator.translate_single(txt)
                max_h_style = f' style="max-height: {min(orig_h + 10, ph * 0.75):.1f}pt;"'
                html_parts.append('    <figure class="paper-figure">')
                html_parts.append(f'      <img src="{fig_uri}" alt="{html.escape(txt)}"{max_h_style} />')
                if is_dual:
                    html_parts.append('      <figcaption>')
                    html_parts.append(f'        <span>{html.escape(zh_cap)}</span>')
                    html_parts.append(f'        <span class="figcaption-en">{html.escape(txt)}</span>')
                    html_parts.append("      </figcaption>")
                else:
                    html_parts.append(f"      <figcaption>{html.escape(zh_cap)}</figcaption>")
                html_parts.append("    </figure>")
                continue

            # Table Element (Structured HTML table)
            if el.get("is_table") or el.get("table_data"):
                tbl = el.get("table_data")
                if tbl and tbl.get("rows"):
                    html_parts.append('    <div class="table-container">')
                    html_parts.append('      <table class="paper-table">')
                    for r_idx, row in enumerate(tbl["rows"]):
                        html_parts.append("        <tr>")
                        for cell in row:
                            tag = "th" if cell.get("is_header") else "td"
                            attrs = []
                            r_span = int(cell.get("row_span") or 1)
                            c_span = int(cell.get("col_span") or 1)
                            if r_span > 1:
                                attrs.append(f'rowspan="{r_span}"')
                            if c_span > 1:
                                attrs.append(f'colspan="{c_span}"')
                            attr_str = (" " + " ".join(attrs)) if attrs else ""
                            cell_raw = cell.get("text", "").strip()
                            if cell_raw and not cell_raw.isdigit():
                                cell_zh = translator.translate_single(cell_raw)
                            else:
                                cell_zh = cell_raw
                            html_parts.append(f"          <{tag}{attr_str}>{html.escape(cell_zh)}</{tag}>")
                        html_parts.append("        </tr>")
                    html_parts.append("      </table>")
                    html_parts.append("    </div>")
                continue

            # Footnote at page bottom
            if txt.startswith(("*By", "* By", "By R. A.", "Contribution from")) or (
                el.get("y", 0.0) > ph * 0.88 and txt.startswith("*")
            ):
                zh_fn = translator.translate_single(txt)
                html_parts.append(f'    <div class="page-footnote">{html.escape(zh_fn)}</div>')
                continue

            # Joint Chapter and Section Header
            chap_part, sec_part = split_chapter_and_section_titles(txt)
            if chap_part and sec_part:
                zh_chap = translator.translate_single(chap_part)
                zh_sec = translator.translate_single(sec_part)
                html_parts.append('    <div class="chapter-header">')
                if is_dual:
                    html_parts.append(f'      <div class="chapter-badge">{html.escape(chap_part)}</div>')
                html_parts.append(f'      <div class="chapter-main-title">{html.escape(zh_chap)}</div>')
                html_parts.append("    </div>")
                html_parts.append(f'    <h2 class="section-heading">{html.escape(zh_sec)}</h2>')
                continue

            # Chapter Title alone
            if re.match(r"^(CHAPTER|PART)\s+\d+", txt, re.IGNORECASE):
                zh_chap = translator.translate_single(txt)
                html_parts.append('    <div class="chapter-header">')
                if is_dual:
                    html_parts.append(f'      <div class="chapter-badge">{html.escape(txt)}</div>')
                html_parts.append(f'      <div class="chapter-main-title">{html.escape(zh_chap)}</div>')
                html_parts.append("    </div>")
                continue

            # Section Header (e.g. 6-1. INTRODUCTION, 6-2. CHEMICAL PROCESSING...)
            if re.match(r"^(\*+\s*)?(\d+[-–\.]\s*[0-9l1I]\b[\s\.]+[A-Z\s]{3,})", txt):
                zh_sec = translator.translate_single(txt)
                html_parts.append(f'    <h2 class="section-heading">{html.escape(zh_sec)}</h2>')
                continue

            # Subsection Header (e.g. 6-2.1 Insoluble fission...)
            if re.match(r"^(\*+\s*)?(\d+[-–\.]\d+(\.\d+)*)\s+", txt):
                zh_subsec = translator.translate_single(txt)
                html_parts.append(f'    <h3 class="subsection-heading">{html.escape(zh_subsec)}</h3>')
                continue

            # References Section Header or Item
            if txt.strip() == "REFERENCES":
                html_parts.append('    <h2 class="section-heading" style="border-top: 1pt solid #ccc; padding-top: 8pt; margin-top: 14pt;">参考文献 (REFERENCES)</h2>')
                continue
            if re.match(r"^(\[\d+\]|\d+\.)\s+[A-Z]", txt):
                html_parts.append(f'    <div class="reference-item">{html.escape(txt)}</div>')
                continue

            # Standard Body Paragraph
            zh_para = translator.translate_single(txt)
            if is_dual:
                html_parts.append('    <div class="bilingual-pair">')
                html_parts.append(f'      <div class="orig-en">{html.escape(txt)}</div>')
                html_parts.append(f'      <div class="trans-zh">{html.escape(zh_para)}</div>')
                html_parts.append("    </div>")
            else:
                html_parts.append(f'    <p class="body-para">{html.escape(zh_para)}</p>')

        html_parts.append("  </div>")  # Close paper-page

    html_parts.append("</body>")
    html_parts.append("</html>")
    return "\n".join(html_parts)


def convert_html_to_pdf_via_chrome(
    html_path: Path,
    pdf_path: Path,
    timeout: int = 120,
) -> bool:
    """Convert an HTML document to a publication-grade PDF using headless Google Chrome."""
    chrome_bin = find_chrome_binary()
    if not chrome_bin:
        raise FileNotFoundError("未找到 Google Chrome 浏览器 (请安装 Google Chrome 以获得出版级高清打印输出)")

    pdf_path = Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_pdf = pdf_path.with_suffix(".pdf.tmp")

    cmd = [
        str(chrome_bin),
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={tmp_pdf}",
        str(html_path.resolve()),
    ]

    logger.info("正在调用无头 Google Chrome 渲染出版级高清 PDF: %s -> %s", html_path.name, pdf_path.name)
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    if res.returncode != 0 or not tmp_pdf.exists() or tmp_pdf.stat().st_size == 0:
        logger.error("Chrome 打印失败: code=%d, err=%s", res.returncode, res.stderr)
        if tmp_pdf.exists():
            tmp_pdf.unlink()
        return False

    tmp_pdf.replace(pdf_path)
    logger.info("高清 PDF 渲染交付成功: %s (%d bytes)", pdf_path.name, pdf_path.stat().st_size)
    return True


def create_dual_interleaved_pdf(
    original_pdf_path: Path,
    translated_pdf_path: Path,
    output_dual_pdf_path: Path,
    pages: Optional[str] = None,
) -> Path:
    """Create a dual-language PDF interleaving original scan pages and translated pages."""
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required to build dual-track PDF")

    orig_doc = fitz.open(str(original_pdf_path))
    trans_doc = fitz.open(str(translated_pdf_path))
    dual_doc = fitz.open()

    if pages:
        selected_pages = []
        for part in pages.split(","):
            part = part.strip()
            if "-" in part:
                s, e = part.split("-", 1)
                selected_pages.extend(range(int(s) - 1, int(e)))
            else:
                selected_pages.append(int(part) - 1)
    else:
        selected_pages = list(range(min(len(orig_doc), len(trans_doc))))

    for p_idx in selected_pages:
        if p_idx < len(orig_doc):
            dual_doc.insert_pdf(orig_doc, from_page=p_idx, to_page=p_idx)
        if p_idx < len(trans_doc):
            dual_doc.insert_pdf(trans_doc, from_page=p_idx, to_page=p_idx)

    output_dual_pdf_path = Path(output_dual_pdf_path).resolve()
    # 必须是隐藏临时名，否则崩溃后 `_cleanup_partials`（只清 `.<stem>*`）接不住它。
    tmp_dual = output_dual_pdf_path.parent / (".%s.tmp" % output_dual_pdf_path.name)
    try:
        dual_doc.save(str(tmp_dual))
        tmp_dual.replace(output_dual_pdf_path)
    except Exception:
        tmp_dual.unlink(missing_ok=True)
        raise
    finally:
        for document in (dual_doc, orig_doc, trans_doc):
            try:
                document.close()
            except Exception:
                pass

    logger.info("双语对照交替 PDF 交付完成: %s (%d pages, %d bytes)",
                output_dual_pdf_path.name, len(selected_pages) * 2, output_dual_pdf_path.stat().st_size)
    return output_dual_pdf_path


def process_scanned_pdf_to_hd_pdf(
    pdf_path: Union[str, Path],
    outbox_dir: Union[str, Path],
    service: str = "bing",
    pages: Optional[str] = None,
    extractor_engine: str = "opendataloader",
    generate_insitu_html: bool = True,
) -> List[Path]:
    """Process an image/scanned PDF into publication-grade Mono & Dual HD PDFs."""
    pdf_path = Path(pdf_path).resolve()
    outbox_dir = Path(outbox_dir).resolve()
    outbox_dir.mkdir(parents=True, exist_ok=True)
    stem = pdf_path.stem
    output_files: List[Path] = []

    logger.info("=== 开始启动扫描件高清出版级翻译管线: [%s] (service=%s, pages=%s) ===",
                pdf_path.name, service, pages)

    # 1. Structured Document Extraction via OpenDataLoader
    doc_res = extract_pdf_structure(pdf_path, pages=pages)

    # 2. Extract and crop high-definition figures and unstructured tables per page
    page_figure_maps: Dict[int, Dict[int, Tuple[str, float]]] = {}
    page_table_maps: Dict[int, Dict[int, Dict[str, Any]]] = {}
    page_dims: Dict[int, Tuple[float, float]] = {}

    if fitz is not None:
        src_fitz_doc = fitz.open(str(pdf_path))
        for page_obj in doc_res.pages:
            p_num = page_obj.page_num
            page_dims[p_num] = (page_obj.width, page_obj.height)
            if p_num <= len(src_fitz_doc):
                fitz_page = src_fitz_doc[p_num - 1]
                raw_elements = [el.to_dict() for el in page_obj.elements]
                merged_elements = merge_caption_continuations(raw_elements)
                fig_map = detect_figures_on_page(fitz_page, merged_elements)
                tbl_map = detect_unstructured_tables_on_page(fitz_page, merged_elements)
                page_figure_maps[p_num] = fig_map
                page_table_maps[p_num] = tbl_map
        src_fitz_doc.close()

    # 3. Translation Engine
    translator = ScannedPDFTranslator(service=service)

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)

        # 4. Synthesize Publication-Grade Mono HTML & Render PDF
        mono_html_content = generate_publication_html(
            document=doc_res,
            translator=translator,
            page_figure_maps=page_figure_maps,
            page_table_maps=page_table_maps,
            title=f"{stem} - 中文精译版",
            is_dual=False,
            page_dims=page_dims,
        )
        mono_html_path = tmp_dir / f"{stem}-mono.html"
        mono_html_path.write_text(mono_html_content, encoding="utf-8")

        mono_pdf_tmp = tmp_dir / f"{stem}-中文精译版.pdf"
        if not convert_html_to_pdf_via_chrome(mono_html_path, mono_pdf_tmp):
            raise RuntimeError(
                "无头 Chrome 未能生成中文精译版 PDF（请确认 Google Chrome 可用且可无头启动）"
            )

        # Atomic copy to outbox
        mono_dest = outbox_dir / f"{stem}-中文精译版.pdf"
        tmp_dest = outbox_dir / f".{stem}-中文精译版.pdf.tmp"
        try:
            shutil.copy2(mono_pdf_tmp, tmp_dest)
            tmp_dest.replace(mono_dest)
            output_files.append(mono_dest)
        except Exception:
            if tmp_dest.exists():
                tmp_dest.unlink()
            raise

        # 5. Synthesize Dual Edition PDF (Alternating Original & Translated Page)
        dual_dest = outbox_dir / f"{stem}-双语对照版.pdf"
        create_dual_interleaved_pdf(
            original_pdf_path=pdf_path,
            translated_pdf_path=mono_pdf_tmp,
            output_dual_pdf_path=dual_dest,
            pages=pages,
        )
        output_files.append(dual_dest)

    # 6. Optionally also deliver the interactive .原位双层版.html
    if generate_insitu_html:
        try:
            from src.in_situ_renderer import process_pdf_to_insitu_html
            insitu_out = outbox_dir / f"{stem}.原位双层版.html"
            tmp_insitu = outbox_dir / f".{stem}.原位双层版.html.tmp"
            process_pdf_to_insitu_html(
                pdf_path=pdf_path,
                output_html_path=tmp_insitu,
                extractor_engine=extractor_engine,
            )
            tmp_insitu.replace(insitu_out)
            output_files.append(insitu_out)
            logger.info("已交付交互式原位双层 HTML: %s", insitu_out.name)
        except Exception as e:
            logger.warning("生成交互式原位双层 HTML 失败 (跳过): %s", e)

    logger.info("=== 扫描件高清出版级翻译交付完成，生成 %d 份成果: %s ===",
                len(output_files), [p.name for p in output_files])
    return output_files


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    test_pdf = _ROOT / "processed" / "FFR_chap06.pdf"
    if test_pdf.exists():
        res = process_scanned_pdf_to_hd_pdf(
            test_pdf,
            outbox_dir=_ROOT / "outbox",
            service="bing",
            pages="1-5",
        )
        print("Generated:", res)
