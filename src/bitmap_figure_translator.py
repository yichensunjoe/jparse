"""Translate text inside raster/bitmap figures while preserving diagram geometry and layout.

In academic PDFs (such as MDPI, Springer, IEEE, arXiv), authors often insert
flowcharts, block diagrams, and network architectures as embedded raster bitmap
images (e.g. PNG with SMask transparency). The PDF text stream contains 0 vector
text objects in these regions, causing standard vector text replacement to leave
these diagrams in English.

This module provides an end-to-end bitmap diagram translation engine:
1. Extracts candidate bitmap images from PDF pages with their SMask transparency preserved.
2. Gates diagrams via PaddleOCR detection (filtering out photos, scatter plots, pure numbers/ticks).
3. Preserves mathematical variables ($x_1, y_2, z$, etc.) and formulas untouched.
4. Aggregates multi-line container labels into unified phrases.
5. Inpaints and cleanly erases original English text by sampling the local container background.
6. Re-renders translated Chinese text with Source Han Sans (思源黑体), matching original typography, color, and alignment.
7. Replaces the image in-place in the PDF using PyMuPDF (`replace_image`).
"""

from __future__ import annotations

import io
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("bitmap_figure_translator")

_FONT_DIR = Path.home() / ".cache/babeldoc/fonts"
_SANS_REGULAR = _FONT_DIR / "SourceHanSansCN-Regular.ttf"
_SANS_BOLD = _FONT_DIR / "SourceHanSansCN-Bold.ttf"

# Regex for pure math variables or formulas that must NOT be translated
_MATH_VAR_RE = re.compile(
    r"^(?:[a-zA-Z_]\d*|[a-zA-Z]_[a-zA-Z0-9]+|keff|flux_?\w*|[a-zA-Z])$"
)
_FORMULA_RE = re.compile(
    r"^(?:[a-zA-Z]\s*=\s*.*|[a-zA-Z]\([a-zA-Z0-9_,\s]+\)|\\sum.*|\\int.*)$"
)
_NUMBER_ONLY_RE = re.compile(
    r"^[+-]?\d+(?:\.\d+)?(?:\s*[%°]|\s*[a-zA-Z]{1,3})?$"
)

# Domain terminology dictionary for high-precision technical translation
_DOMAIN_TERMS: Dict[str, str] = {
    "core input parameters": "堆芯输入参数",
    "core input parameter": "堆芯输入参数",
    "Monte Carlo simulation": "蒙特卡洛模拟",
    "monte carlo simulation": "蒙特卡洛模拟",
    "training dataset": "训练数据集",
    "training data": "训练数据",
    "test dataset": "测试数据集",
    "test data": "测试数据",
    "Training & optimization": "训练与优化",
    "training & optimization": "训练与优化",
    "Generalization test": "泛化测试",
    "generalization test": "泛化测试",
    "Optimal model": "最优模型",
    "optimal model": "最优模型",
    "NN model": "NN 模型",
    "nn model": "NN 模型",
    "Input layer": "输入层",
    "input layer": "输入层",
    "Hidden layer": "隐藏层",
    "hidden layer": "隐藏层",
    "Output layer": "输出层",
    "output layer": "输出层",
    "Dataset generation": "数据集生成",
    "dataset generation": "数据集生成",
    "3D data representation": "三维数据表示",
    "2D data": "二维数据",
    "ctr height": "控制棒高度",
    "nuclide": "核素",
    "outputs": "输出",
    "inputs": "输入",
}


@dataclass
class OCRItem:
    text: str
    box: List[int]  # [x0, y0, x1, y1]
    score: float


@dataclass
class TextGroup:
    source_text: str
    box: List[int]  # [x0, y0, x1, y1] union
    sub_boxes: List[List[int]]
    translated: str = ""
    is_variable: bool = False
    is_bold: bool = False
    bg_color: Tuple[int, int, int] = (255, 255, 255)
    text_color: Tuple[int, int, int] = (0, 0, 0)


def locate_paddleocr_python() -> Optional[Path]:
    """Locate the Python executable that has paddleocr installed."""
    candidates = [
        Path.home() / ".local/venvs/paddleocr/bin/python",
        Path("/Users/joe/.local/venvs/paddleocr/bin/python"),
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return c

    # Check if current python has it
    try:
        import paddleocr  # noqa: F401
        return Path(sys.executable)
    except ImportError:
        pass

    return None


def run_paddle_ocr(image_path: Path, paddle_python: Optional[Path] = None) -> List[OCRItem]:
    """Execute PaddleOCR on an image and return raw bounding boxes and texts."""
    py_bin = paddle_python or locate_paddleocr_python()
    if not py_bin:
        logger.warning("未找到 PaddleOCR Python 环境，跳过位图 OCR")
        return []

    worker_code = """
import sys, json
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False, lang='en')
res = ocr.predict(sys.argv[1])[0]
out = []
for b, t, s in zip(res['rec_boxes'], res['rec_texts'], res['rec_scores']):
    out.append({'box': [int(b[0]), int(b[1]), int(b[2]), int(b[3])], 'text': str(t), 'score': float(s)})
print('__JSON_START__' + json.dumps(out))
"""
    try:
        res = subprocess.run(
            [str(py_bin), "-c", worker_code, str(image_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        if res.returncode != 0:
            logger.warning("PaddleOCR 执行返回非零码: %s", res.stderr[:200])
            return []

        for line in res.stdout.splitlines():
            if line.startswith("__JSON_START__"):
                raw_json = line[len("__JSON_START__"):]
                data = json.loads(raw_json)
                return [
                    OCRItem(text=item["text"].strip(), box=item["box"], score=item["score"])
                    for item in data
                    if item.get("text", "").strip()
                ]
    except Exception as e:
        logger.warning("调用 PaddleOCR 子进程异常: %s", e)

    return []


def is_math_variable(text: str) -> bool:
    """Return True if text represents a math variable or formula to preserve."""
    s = text.strip()
    if not s:
        return True
    if _MATH_VAR_RE.match(s):
        return True
    if _FORMULA_RE.match(s):
        return True
    if _NUMBER_ONLY_RE.match(s):
        return True
    # Single Greek letters or variable with subscript
    if len(s) <= 2 and not s.isalpha():
        return True
    return False


def is_diagram_candidate(ocr_items: List[OCRItem], img_width: int, img_height: int) -> bool:
    """Gate check: Determine if an image contains a translatable diagram or flowchart."""
    if not ocr_items:
        return False

    translatable_words = 0
    total_text_length = 0

    for item in ocr_items:
        t = item.text.strip()
        if is_math_variable(t):
            continue
        # Words of length >= 2
        words = [w for w in re.split(r"\s+", t) if len(w) >= 2 and any(c.isalpha() for c in w)]
        if words:
            translatable_words += len(words)
            total_text_length += len(t)

    # Need at least 2 translatable words or significant text labels
    if translatable_words < 2 and total_text_length < 5:
        return False

    return True


def group_ocr_items(items: Sequence[OCRItem]) -> List[TextGroup]:
    """Group vertically adjacent multi-line text boxes inside the same container."""
    sorted_items = sorted(items, key=lambda it: (it.box[1], it.box[0]))
    groups: List[TextGroup] = []
    used = set()

    for i, it1 in enumerate(sorted_items):
        if i in used:
            continue
        group_items = [it1]
        used.add(i)

        b1 = list(it1.box)
        w1 = b1[2] - b1[0]
        h1 = b1[3] - b1[1]

        for j, it2 in enumerate(sorted_items):
            if j in used:
                continue
            b2 = it2.box
            w2 = b2[2] - b2[0]
            h2 = b2[3] - b2[1]

            overlap_x0 = max(b1[0], b2[0])
            overlap_x1 = min(b1[2], b2[2])
            overlap_w = max(0, overlap_x1 - overlap_x0)
            min_w = min(w1, w2)

            v_dist = b2[1] - b1[3]
            max_h = max(h1, h2)

            # Horizontally overlapping (>35%) and vertically stacked closely
            if overlap_w / max(1, min_w) > 0.35 and -max_h * 0.4 <= v_dist < max_h * 1.5:
                group_items.append(it2)
                used.add(j)
                b1 = [min(b1[0], b2[0]), min(b1[1], b2[1]), max(b1[2], b2[2]), max(b1[3], b2[3])]
                w1 = b1[2] - b1[0]
                h1 = b1[3] - b1[1]

        group_text = " ".join(item.text for item in group_items).strip()
        sub_boxes = [item.box for item in group_items]
        groups.append(
            TextGroup(
                source_text=group_text,
                box=b1,
                sub_boxes=sub_boxes,
                is_variable=is_math_variable(group_text),
            )
        )

    return groups


def sample_background_and_text_color(
    im_arr: np.ndarray,
    box: List[int],
) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """Sample the container background color and the contrasting text color."""
    h_img, w_img = im_arr.shape[:2]
    x0, y0, x1, y1 = box
    ex0 = max(0, x0 - 3)
    ey0 = max(0, y0 - 3)
    ex1 = min(w_img - 1, x1 + 3)
    ey1 = min(h_img - 1, y1 + 3)

    # 1. Sample border pixels around the text box
    top_strip = im_arr[max(0, ey0 - 4) : ey0, ex0:ex1]
    bot_strip = im_arr[ey1 : min(h_img, ey1 + 4), ex0:ex1]
    left_strip = im_arr[ey0:ey1, max(0, ex0 - 4) : ex0]
    right_strip = im_arr[ey0:ey1, ex1 : min(w_img, ex1 + 4)]

    border_strips = [s.reshape(-1, s.shape[-1])[:, :3] for s in [top_strip, bot_strip, left_strip, right_strip] if s.size > 0]

    if border_strips:
        all_border = np.vstack(border_strips)
        bg_col = tuple(int(c) for c in np.median(all_border, axis=0))
    else:
        bg_col = (255, 255, 255)

    # 2. Sample text color by finding pixels with highest contrast to bg_col
    crop = im_arr[y0:y1, x0:x1]
    text_col = (0, 0, 0)
    if crop.size > 0:
        crop_rgb = crop[:, :, :3]
        diff = np.linalg.norm(crop_rgb.astype(float) - np.array(bg_col, dtype=float), axis=2)
        text_mask = diff > 35
        if np.sum(text_mask) > 10:
            text_pixels = crop_rgb[text_mask]
            med_t = np.median(text_pixels, axis=0).astype(int)
            # If text is nearly dark, snap to pure black for maximum readability
            if max(med_t) < 70:
                text_col = (0, 0, 0)
            else:
                text_col = tuple(int(c) for c in med_t)

    return bg_col, text_col


def translate_groups(
    groups: List[TextGroup],
    service: str = "bing",
) -> List[TextGroup]:
    """Translate non-variable text groups using dictionary + translator."""
    from src.hd_scan_renderer import ScannedPDFTranslator

    translator = ScannedPDFTranslator(service=service)
    cache: Dict[str, str] = {}

    for g in groups:
        if g.is_variable:
            continue

        raw = g.source_text.strip()
        # Check domain dictionary first
        if raw in _DOMAIN_TERMS:
            g.translated = _DOMAIN_TERMS[raw]
            continue
        lower_raw = raw.lower()
        if lower_raw in _DOMAIN_TERMS:
            g.translated = _DOMAIN_TERMS[lower_raw]
            continue

        # Check translation cache or invoke translator
        if raw in cache:
            g.translated = cache[raw]
        else:
            try:
                res = translator.translate_single(raw)
                res = res.strip() if res else ""
                cache[raw] = res
                g.translated = res
            except Exception as e:
                logger.warning("翻译文字组失败 (%s): %s", raw, e)
                g.translated = ""

    return groups


def render_translated_diagram(
    image: Image.Image,
    groups: List[TextGroup],
) -> Image.Image:
    """Erase original English text and render translated Chinese text on the image."""
    res_img = image.copy()
    draw = ImageDraw.Draw(res_img)
    im_arr = np.array(image)

    font_path = str(_SANS_REGULAR) if _SANS_REGULAR.is_file() else None
    font_bold_path = str(_SANS_BOLD) if _SANS_BOLD.is_file() else font_path

    for g in groups:
        if g.is_variable or not g.translated:
            continue

        x0, y0, x1, y1 = g.box
        bg_col, text_col = sample_background_and_text_color(im_arr, g.box)
        g.bg_color = bg_col
        g.text_color = text_col

        # Clean erasure with 3px padding
        pad = 3
        ex0 = max(0, x0 - pad)
        ey0 = max(0, y0 - pad)
        ex1 = min(res_img.width - 1, x1 + pad)
        ey1 = min(res_img.height - 1, y1 + pad)
        draw.rectangle([ex0, ey0, ex1, ey1], fill=bg_col)

        if not font_path:
            continue

        box_w = ex1 - ex0
        box_h = ey1 - ey0
        zh_text = g.translated

        # Decide whether to wrap to 2 lines
        use_multi_line = (len(g.sub_boxes) >= 2 or box_h >= 38) and len(zh_text) >= 4 and zh_text not in ["最优模型", "NN 模型"]

        if use_multi_line:
            mid = len(zh_text) // 2
            # Balance common phrases
            if zh_text == "堆芯输入参数":
                line1, line2 = "堆芯输入", "参数"
            elif zh_text == "蒙特卡洛模拟":
                line1, line2 = "蒙特卡洛", "模拟"
            else:
                line1, line2 = zh_text[:mid], zh_text[mid:]

            font_size = 13
            font = ImageFont.truetype(font_bold_path if g.is_bold else font_path, font_size)
            b1 = font.getbbox(line1)
            b2 = font.getbbox(line2)
            w1, h1 = b1[2] - b1[0], b1[3] - b1[1]
            w2, h2 = b2[2] - b2[0], b2[3] - b2[1]
            total_h = h1 + h2 + 4
            ty1 = ey0 + (box_h - total_h) / 2
            tx1 = ex0 + (box_w - w1) / 2
            draw.text((tx1, ty1), line1, font=font, fill=text_col)

            ty2 = ty1 + h1 + 4
            tx2 = ex0 + (box_w - w2) / 2
            draw.text((tx2, ty2), line2, font=font, fill=text_col)
        else:
            font_size = 14 if g.is_bold else 13
            font = ImageFont.truetype(font_bold_path if g.is_bold else font_path, font_size)
            bbox = font.getbbox(zh_text)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            while tw > box_w - 2 and font_size > 9:
                font_size -= 1
                font = ImageFont.truetype(font_bold_path if g.is_bold else font_path, font_size)
                bbox = font.getbbox(zh_text)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

            tx = ex0 + (box_w - tw) / 2
            ty = ey0 + (box_h - th) / 2 - 1
            draw.text((tx, ty), zh_text, font=font, fill=text_col)

    return res_img


def translate_bitmap_image(
    image_pixmap: fitz.Pixmap,
    service: str = "bing",
    paddle_python: Optional[Path] = None,
) -> Optional[Image.Image]:
    """Translate an extracted PDF pixmap. Returns new PIL Image if modified, else None."""
    # Convert PyMuPDF Pixmap to PIL Image
    im_bytes = io.BytesIO(image_pixmap.tobytes("png"))
    pil_img = Image.open(im_bytes).convert("RGB")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        pil_img.save(tmp_path)
        ocr_items = run_paddle_ocr(tmp_path, paddle_python=paddle_python)

        if not is_diagram_candidate(ocr_items, pil_img.width, pil_img.height):
            return None

        groups = group_ocr_items(ocr_items)
        translatable_groups = [g for g in groups if not g.is_variable]
        if not translatable_groups:
            return None

        groups = translate_groups(groups, service=service)
        if not any(g.translated for g in groups if not g.is_variable):
            return None

        result_img = render_translated_diagram(pil_img, groups)
        return result_img
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def apply_bitmap_figure_translations(
    source_pdf: Path,
    mono_pdf: Optional[Path] = None,
    dual_pdf: Optional[Path] = None,
    service: str = "bing",
    pages: Optional[str] = None,
) -> int:
    """Detect and translate bitmap figures across mono and dual PDFs.

    Returns the count of translated and replaced figure images.
    """
    py_bin = locate_paddleocr_python()
    if not py_bin:
        logger.info("未配置 PaddleOCR 环境，跳过位图图内文字翻译")
        return 0

    target_pdfs = [p for p in [mono_pdf, dual_pdf] if p and Path(p).is_file()]
    if not target_pdfs:
        return 0

    total_replaced = 0

    for target_path in target_pdfs:
        try:
            doc = fitz.open(target_path)
            doc_replaced = 0

            # Determine page range
            if pages:
                page_indices = []
                for part in pages.split(","):
                    part = part.strip()
                    if "-" in part:
                        start, end = part.split("-", 1)
                        page_indices.extend(range(int(start) - 1, int(end)))
                    elif part.isdigit():
                        page_indices.append(int(part) - 1)
            else:
                page_indices = list(range(len(doc)))

            for pno in page_indices:
                if pno < 0 or pno >= len(doc):
                    continue
                page = doc[pno]
                img_list = page.get_images()
                if not img_list:
                    continue

                processed_xrefs = set()
                for img_info in img_list:
                    xref = img_info[0]
                    if xref in processed_xrefs:
                        continue
                    processed_xrefs.add(xref)

                    # Extract pixmap with alpha/SMask
                    try:
                        raw_pix = fitz.Pixmap(doc, xref)
                        smask_xref = img_info[1]
                        if smask_xref > 0:
                            mask_pix = fitz.Pixmap(doc, smask_xref)
                            raw_pix_rgb = fitz.Pixmap(raw_pix, 0) if raw_pix.alpha else raw_pix
                            pix = fitz.Pixmap(raw_pix_rgb, mask_pix)
                        else:
                            pix = raw_pix

                        # Composite on white background for OCR and redraw
                        im_rgba = Image.open(io.BytesIO(pix.tobytes("png")))
                        if im_rgba.mode in ("RGBA", "LA") or (im_rgba.mode == "P" and "transparency" in im_rgba.info):
                            im_white = Image.new("RGB", (pix.width, pix.height), (255, 255, 255))
                            mask = im_rgba.split()[-1] if im_rgba.mode in ("RGBA", "LA") else None
                            im_white.paste(im_rgba, mask=mask)
                            target_pil = im_white
                        else:
                            target_pil = im_rgba.convert("RGB")

                        # Run diagram translation
                        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_f:
                            tmp_p = Path(tmp_f.name)
                        try:
                            target_pil.save(tmp_p)
                            ocr_items = run_paddle_ocr(tmp_p, paddle_python=py_bin)
                            if not is_diagram_candidate(ocr_items, target_pil.width, target_pil.height):
                                continue

                            groups = group_ocr_items(ocr_items)
                            groups = translate_groups(groups, service=service)
                            if not any(g.translated for g in groups if not g.is_variable):
                                continue

                            translated_pil = render_translated_diagram(target_pil, groups)

                            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as out_f:
                                out_p = Path(out_f.name)
                            translated_pil.save(out_p)

                            # Replace image in PDF
                            page.replace_image(xref, filename=str(out_p))
                            doc_replaced += 1
                            logger.info("第 %d 页位图图例 (xref %d) 已成功原位替换翻译", pno + 1, xref)
                            if out_p.exists():
                                out_p.unlink()
                        finally:
                            if tmp_p.exists():
                                tmp_p.unlink()

                    except Exception as e:
                        logger.warning("处理第 %d 页图片 (xref %d) 失败: %s", pno + 1, xref, e)

            if doc_replaced > 0:
                tmp_save = target_path.with_suffix(".tmp.pdf")
                doc.save(tmp_save, garbage=3, deflate=True)
                doc.close()
                tmp_save.replace(target_path)
                total_replaced += doc_replaced
                logger.info("成功为 %s 原位翻译并替换 %d 张位图图例", target_path.name, doc_replaced)
            else:
                doc.close()
        except Exception as e:
            logger.warning("为 %s 执行位图图内文字翻译异常: %s", target_path.name, e)

    return total_replaced
