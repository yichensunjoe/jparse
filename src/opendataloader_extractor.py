#!/usr/bin/env python3
"""OpenDataLoader-PDF Upstream Extraction Engine.

Integrates opendataloader-pdf as the high-accuracy upstream layout analysis,
XY-Cut++ reading order extraction, bounding box localization, structured table,
and formula detection engine.
"""

from dataclasses import dataclass, field
import html
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
from typing import Any, Dict, Generator, List, Optional, Sequence, Tuple, Union

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

logger = logging.getLogger("opendataloader_extractor")

# Potential Java locations on macOS / Apple Silicon
_CANDIDATE_JAVA_DIRS = [
    Path("/Users/joe/.local/bin"),
    Path("/opt/homebrew/opt/openjdk/bin"),
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
]


def ensure_java_environment() -> Optional[str]:
    """Ensure a functional Java runtime is discoverable in PATH and JAVA_HOME."""
    # Test if java currently in PATH works (reject macOS stub which exits with 1)
    current_java = shutil.which("java")
    if current_java:
        try:
            res = subprocess.run(
                ["java", "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            # macOS stub prints "Unable to locate a Java Runtime" and exits with 1
            if res.returncode == 0 and "unable to locate a java runtime" not in res.stderr.lower():
                return current_java
        except Exception:
            pass

    # Search candidate paths
    for cand_dir in _CANDIDATE_JAVA_DIRS:
        java_bin = cand_dir / "java"
        if java_bin.is_file() and os.access(str(java_bin), os.X_OK):
            try:
                res = subprocess.run(
                    [str(java_bin), "-version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5,
                )
                if res.returncode == 0 and "unable to locate a java runtime" not in res.stderr.lower():
                    # Prepend to PATH so child processes and opendataloader-pdf find it
                    cand_str = str(cand_dir)
                    current_path = os.environ.get("PATH", "")
                    if cand_str not in current_path.split(os.pathsep):
                        os.environ["PATH"] = f"{cand_str}{os.pathsep}{current_path}"
                    
                    # Set JAVA_HOME if homebrew openjdk
                    if "openjdk" in str(cand_dir):
                        java_home = cand_dir.parent
                        os.environ["JAVA_HOME"] = str(java_home)
                    return str(java_bin)
            except Exception:
                continue

    return None


def check_opendataloader_available() -> Tuple[bool, str]:
    """Verify opendataloader-pdf package and Java runtime availability."""
    ensure_java_environment()

    try:
        import opendataloader_pdf
    except ImportError as exc:
        return False, f"opendataloader-pdf Python 包未安装: {exc}"

    java_bin = shutil.which("java")
    if not java_bin:
        return False, "未找到 Java 运行时 (java 命令不可用)"

    try:
        res = subprocess.run(
            ["java", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        version_info = (res.stderr or res.stdout or "").strip().splitlines()
        v_str = version_info[0] if version_info else "Java OK"
        pkg_version = getattr(opendataloader_pdf, "__version__", "installed")
        return True, f"opendataloader-pdf ({pkg_version}), {v_str}"
    except Exception as exc:
        return False, f"Java 运行时执行失败: {exc}"


def is_formula_element(element: Dict[str, Any]) -> bool:
    """Detect whether an extracted element represents a mathematical formula or equation."""
    # 1. Semantic Tag
    tag = str(element.get("pdfua_tag", "")).lower()
    if tag in ("formula", "math"):
        return True

    # 2. Font check
    font = str(element.get("font", "")).lower()
    math_fonts = ("math", "sym", "cmmi", "cmsy", "msam", "msbm", "eufm", "cambriamath")
    if any(mf in font for mf in math_fonts):
        return True

    # 3. Content heuristics for formulas/equations
    content = str(element.get("content") or element.get("text") or "").strip()
    if not content:
        return False

    # Check for Unicode math symbols with equation/relation syntax
    math_syms = ["𝜌", "𝑐𝑝", "𝜆", "𝜇", "∂", "∫", "∑", "√", "≤", "≥", "≠", "≈", "±", "×"]
    has_math_sym = any(sym in content for sym in math_syms)
    has_eq = bool(re.search(r"[=<>]", content))
    has_numbered_eq = bool(re.search(r"\(\d+\)\s*$", content))

    if has_math_sym and (has_eq or has_numbered_eq):
        return True

    # LaTeX equation pattern
    if re.search(r"\\(frac|sum|int|sqrt|partial|alpha|beta|gamma|rho|mu|lambda)\b", content):
        return True

    return False


@dataclass
class ExtractedTableCell:
    """A cell in an extracted table."""
    row_idx: int
    col_idx: int
    row_span: int
    col_span: int
    is_header: bool
    bbox: List[float]
    x: float
    y: float
    w: float
    h: float
    text: str
    font: str
    font_size: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row_idx": self.row_idx,
            "col_idx": self.col_idx,
            "row_span": self.row_span,
            "col_span": self.col_span,
            "is_header": self.is_header,
            "bbox": self.bbox,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "text": self.text,
            "font": self.font,
            "font_size": self.font_size,
        }


@dataclass
class ExtractedTable:
    """A table detected by opendataloader-pdf."""
    id: Any
    page_num: int
    bbox: List[float]
    x: float
    y: float
    w: float
    h: float
    rows_count: int
    cols_count: int
    rows: List[List[ExtractedTableCell]] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render table as GitHub-Flavored Markdown."""
        if not self.rows:
            return ""
        md_lines = []
        for r_idx, row in enumerate(self.rows):
            row_texts = [cell.text.replace("\n", " ").replace("|", "\\|").strip() for cell in row]
            md_lines.append("| " + " | ".join(row_texts) + " |")
            if r_idx == 0:
                md_lines.append("| " + " | ".join(["---"] * len(row)) + " |")
        return "\n".join(md_lines)

    def to_html(self) -> str:
        """Render table as semantic HTML."""
        if not self.rows:
            return ""
        parts = ['<table class="insitu-table">']
        for r_idx, row in enumerate(self.rows):
            parts.append("  <tr>")
            for cell in row:
                tag = "th" if cell.is_header else "td"
                attrs = []
                if cell.row_span > 1:
                    attrs.append(f'rowspan="{cell.row_span}"')
                if cell.col_span > 1:
                    attrs.append(f'colspan="{cell.col_span}"')
                attr_str = (" " + " ".join(attrs)) if attrs else ""
                escaped_text = html.escape(cell.text)
                parts.append(f"    <{tag}{attr_str}>{escaped_text}</{tag}>")
            parts.append("  </tr>")
        parts.append("</table>")
        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "page_num": self.page_num,
            "bbox": self.bbox,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "rows_count": self.rows_count,
            "cols_count": self.cols_count,
            "rows": [[c.to_dict() for c in r] for r in self.rows],
            "markdown": self.to_markdown(),
            "html": self.to_html(),
        }


@dataclass
class ExtractedElement:
    """A semantic structural element (paragraph, heading, table, formula, etc.)."""
    type: str
    id: Any
    page_num: int
    pdfua_tag: str
    bbox: List[float]
    x: float
    y: float
    w: float
    h: float
    text: str
    font: str
    font_size: float
    is_heading: bool = False
    heading_level: int = 0
    is_formula: bool = False
    is_table: bool = False
    table_data: Optional[ExtractedTable] = None
    image_source: Optional[str] = None

    def to_text_item(self) -> Dict[str, Any]:
        """Convert to legacy text_item format for compatibility."""
        return {
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "width": self.w,
            "height": self.h,
            "font_name": self.font,
            "font_size": self.font_size,
            "confidence": 1.0,
            "type": self.type,
            "is_heading": self.is_heading,
            "heading_level": self.heading_level,
            "is_formula": self.is_formula,
            "is_table": self.is_table,
        }

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "type": self.type,
            "id": self.id,
            "page_num": self.page_num,
            "pdfua_tag": self.pdfua_tag,
            "bbox": self.bbox,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "text": self.text,
            "font": self.font,
            "font_size": self.font_size,
            "is_heading": self.is_heading,
            "heading_level": self.heading_level,
            "is_formula": self.is_formula,
            "is_table": self.is_table,
        }
        if self.table_data:
            d["table_data"] = self.table_data.to_dict()
            d["table_html"] = self.table_data.to_html()
            d["table_markdown"] = self.table_data.to_markdown()
        if self.image_source:
            d["image_source"] = self.image_source
        return d


@dataclass
class ExtractedPage:
    """A page with full dimensions, text, and structured elements."""
    page_num: int
    width: float
    height: float
    elements: List[ExtractedElement] = field(default_factory=list)
    tables: List[ExtractedTable] = field(default_factory=list)
    formulas: List[ExtractedElement] = field(default_factory=list)
    text: str = ""
    text_items: List[Dict[str, Any]] = field(default_factory=list)
    markdown: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page": self.page_num,
            "width": self.width,
            "height": self.height,
            "text": self.text,
            "text_items": self.text_items,
            "structured_elements": [el.to_dict() for el in self.elements],
            "tables": [t.to_dict() for t in self.tables],
            "formulas": [f.to_dict() for f in self.formulas],
            "markdown": self.markdown,
        }


@dataclass
class ExtractedDocument:
    """A fully extracted and structured PDF document."""
    pdf_path: Path
    total_pages: int
    pages: List[ExtractedPage] = field(default_factory=list)
    markdown: str = ""

    def to_pages_data(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self.pages]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_name": self.pdf_path.name,
            "number_of_pages": self.total_pages,
            "markdown": self.markdown,
            "pages": self.to_pages_data(),
        }


def _traverse_raw_elements(node_or_list: Any) -> Generator[Dict[str, Any], None, None]:
    """Recursively traverse opendataloader JSON nodes in reading order (XY-Cut++)."""
    if isinstance(node_or_list, list):
        for item in node_or_list:
            yield from _traverse_raw_elements(item)
        return

    if not isinstance(node_or_list, dict):
        return

    node = node_or_list
    ntype = node.get("type", "")

    # Tables are composite entities
    if ntype == "table":
        yield node
        return

    # Check if this node has direct text content
    content = node.get("content") or node.get("text")
    if content:
        yield node

    # Traverse subkids and list items
    for sub in node.get("kids", []):
        yield from _traverse_raw_elements(sub)
    for sub in node.get("list items", []):
        yield from _traverse_raw_elements(sub)


def _bbox_to_topleft(bbox: Sequence[float], page_h: float) -> Tuple[float, float, float, float]:
    """Convert PDF bottom-left bbox [x1, y1, x2, y2] to top-left [x, y, w, h]."""
    if not bbox or len(bbox) < 4:
        return 0.0, 0.0, 0.0, 0.0
    x1, y1, x2, y2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    x = round(x1, 2)
    y = round(max(0.0, page_h - y2), 2)
    w = round(max(0.0, x2 - x1), 2)
    h = round(max(0.0, y2 - y1), 2)
    return x, y, w, h


def _parse_table_node(
    table_node: Dict[str, Any],
    page_num: int,
    page_h: float,
    words: Optional[List[Any]] = None,
) -> ExtractedTable:
    """Parse an opendataloader table node into ExtractedTable with rows and cells."""
    bbox = table_node.get("bounding box", [0.0, 0.0, 0.0, 0.0])
    x, y, w, h = _bbox_to_topleft(bbox, page_h)
    rows_count = int(table_node.get("number of rows") or 0)
    cols_count = int(table_node.get("number of columns") or 0)

    extracted_rows: List[List[ExtractedTableCell]] = []
    for r_idx, raw_row in enumerate(table_node.get("rows", []), start=1):
        cell_list: List[ExtractedTableCell] = []
        for c_idx, raw_cell in enumerate(raw_row.get("cells", []), start=1):
            c_bbox = raw_cell.get("bounding box", [0.0, 0.0, 0.0, 0.0])
            cx, cy, cw, ch = _bbox_to_topleft(c_bbox, page_h)
            
            # Extract cell text from paragraphs inside cell kids
            cell_texts = []
            font = "sans-serif"
            font_size = 10.0
            if "content" in raw_cell and raw_cell["content"]:
                cell_texts.append(str(raw_cell["content"]).strip())
            for k in raw_cell.get("kids", []):
                kc = k.get("content") or k.get("text")
                if kc:
                    cell_texts.append(str(kc).strip())
                if "font" in k and k["font"]:
                    font = str(k["font"])
                if "font size" in k and k["font size"]:
                    try:
                        font_size = float(k["font size"])
                    except (ValueError, TypeError):
                        pass

            cell_text = " ".join(cell_texts).strip()

            # Font-drop repair for table cells
            if words and cell_text:
                cell_words = [
                    wrd[4] for wrd in words
                    if (cx - 3.0 <= (wrd[0] + wrd[2]) / 2.0 <= cx + cw + 3.0) and
                       (cy - 3.0 <= (wrd[1] + wrd[3]) / 2.0 <= cy + ch + 3.0)
                ]
                if cell_words:
                    reconstructed = " ".join(cell_words).strip()
                    has_broken = bool(re.search(r'\b[a-zA-Z]{1,2}\s+[a-zA-Z]{1,2}\b', cell_text))
                    fitz_more = len(re.findall(r'[a-zA-Z0-9]', reconstructed)) > len(re.findall(r'[a-zA-Z0-9]', cell_text)) * 1.03
                    if has_broken and fitz_more:
                        cell_text = reconstructed

            is_header = bool(raw_cell.get("is_header", False)) or (raw_cell.get("pdfua_tag") == "TH") or (r_idx == 1)

            cell_list.append(ExtractedTableCell(
                row_idx=int(raw_cell.get("row number") or r_idx),
                col_idx=int(raw_cell.get("column number") or c_idx),
                row_span=int(raw_cell.get("row span") or 1),
                col_span=int(raw_cell.get("column span") or 1),
                is_header=is_header,
                bbox=c_bbox,
                x=cx,
                y=cy,
                w=cw,
                h=ch,
                text=cell_text,
                font=font,
                font_size=font_size,
            ))
        extracted_rows.append(cell_list)

    if not rows_count:
        rows_count = len(extracted_rows)
    if not cols_count and extracted_rows:
        cols_count = max(len(r) for r in extracted_rows)

    return ExtractedTable(
        id=table_node.get("id", f"tbl_{page_num}_{int(time.time()*1000)}"),
        page_num=page_num,
        bbox=bbox,
        x=x,
        y=y,
        w=w,
        h=h,
        rows_count=rows_count,
        cols_count=cols_count,
        rows=extracted_rows,
    )


def extract_pdf_structure(
    pdf_path: Union[str, Path],
    pages: Optional[str] = None,
    reading_order: str = "xycut",
    table_method: str = "cluster",
    image_output: str = "off",
    quiet: bool = True,
) -> ExtractedDocument:
    """Extract structured document layout, reading order, coordinates, tables, and formulas.

    Args:
        pdf_path: Path to input PDF document.
        pages: Optional page range (e.g. "1", "1-5", "1,3,5").
        reading_order: Reading order algorithm, default 'xycut' (XY-Cut++).
        table_method: Table extraction algorithm, default 'cluster'.
        image_output: Image extraction mode ('off', 'embedded', 'external').
        quiet: Suppress stdout logging from jar.

    Returns:
        ExtractedDocument object containing structured pages, elements, tables, and formulas.
    """
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    ensure_java_environment()
    import opendataloader_pdf

    # Read page dimensions and words from fitz
    page_dims: Dict[int, Tuple[float, float]] = {}
    page_words: Dict[int, List[Any]] = {}
    if fitz is not None:
        try:
            doc = fitz.open(pdf_path)
            for i, p in enumerate(doc, start=1):
                page_dims[i] = (float(p.rect.width), float(p.rect.height))
                try:
                    page_words[i] = p.get_text("words")
                except Exception:
                    page_words[i] = []
            total_pdf_pages = len(doc)
            doc.close()
        except Exception as e:
            logger.warning("无法使用 fitz 读取 PDF 页面尺寸与文字 (%s)，将尝试默认尺寸", e)
            total_pdf_pages = 1
    else:
        total_pdf_pages = 1

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        t0 = time.time()
        logger.info("OpenDataLoader-PDF 正在抽取: %s (reading_order=%s, table_method=%s)...",
                    pdf_path.name, reading_order, table_method)

        opendataloader_pdf.convert(
            input_path=str(pdf_path),
            output_dir=str(tmp_dir),
            format=["json", "markdown"],
            pages=pages,
            reading_order=reading_order,
            table_method=table_method,
            image_output=image_output,
            quiet=quiet,
        )
        elapsed = time.time() - t0
        logger.info("OpenDataLoader-PDF 核心解析完成，用时 %.2f 秒", elapsed)

        # Locate generated JSON and Markdown
        json_files = list(tmp_dir.glob("*.json"))
        md_files = list(tmp_dir.glob("*.md"))

        if not json_files:
            raise RuntimeError(f"OpenDataLoader-PDF 未生成 JSON 结果: {pdf_path.name}")

        json_data = json.loads(json_files[0].read_text(encoding="utf-8", errors="replace"))
        full_markdown = md_files[0].read_text(encoding="utf-8", errors="replace") if md_files else ""

    # Parse JSON document tree
    raw_kids = json_data.get("kids", [])

    # Determine extracted pages from kids
    pages_seen = set()
    for node in raw_kids:
        p_num = node.get("page number")
        if p_num is not None:
            pages_seen.add(int(p_num))

    # Initialize ExtractedPages for extracted pages
    extracted_pages: Dict[int, ExtractedPage] = {}
    target_pages = sorted(pages_seen) if pages_seen else list(range(1, total_pdf_pages + 1))
    for p_num in target_pages:
        pw, ph = page_dims.get(p_num, (595.3, 841.9))
        extracted_pages[p_num] = ExtractedPage(
            page_num=p_num,
            width=pw,
            height=ph,
        )

    # Flatten elements in reading order
    raw_flat_elements = list(_traverse_raw_elements(raw_kids))

    for node in raw_flat_elements:
        p_num = int(node.get("page number", 1))
        if p_num not in extracted_pages:
            pw, ph = page_dims.get(p_num, (595.3, 841.9))
            extracted_pages[p_num] = ExtractedPage(page_num=p_num, width=pw, height=ph)

        page_obj = extracted_pages[p_num]
        ph = page_obj.height

        ntype = node.get("type", "paragraph")
        bbox = node.get("bounding box", [0.0, 0.0, 0.0, 0.0])
        x, y, w, h = _bbox_to_topleft(bbox, ph)
        tag = node.get("pdfua_tag", "P")

        if ntype == "table":
            table_obj = _parse_table_node(node, p_num, ph, words=page_words.get(p_num))
            page_obj.tables.append(table_obj)
            el = ExtractedElement(
                type="table",
                id=table_obj.id,
                page_num=p_num,
                pdfua_tag="Table",
                bbox=bbox,
                x=table_obj.x,
                y=table_obj.y,
                w=table_obj.w,
                h=table_obj.h,
                text=table_obj.to_markdown(),
                font="sans-serif",
                font_size=10.0,
                is_table=True,
                table_data=table_obj,
            )
            page_obj.elements.append(el)
            page_obj.text_items.append(el.to_text_item())
            continue

        # Text/Heading/Formula Element
        content = str(node.get("content") or node.get("text") or "").strip()
        if not content:
            continue

        font = str(node.get("font", "sans-serif"))
        try:
            font_size = float(node.get("font size", 10.0))
        except (ValueError, TypeError):
            font_size = 10.0

        is_heading = ntype == "heading" or str(tag).startswith("H")
        heading_lvl = int(node.get("heading level", 1 if is_heading else 0))
        is_formula = is_formula_element(node)

        # Font-drop repair: Check if ODL has fragmented characters (e.g. Type1 unmapped glyphs)
        if not is_formula and p_num in page_words and page_words[p_num]:
            words = page_words[p_num]
            node_words = [
                wrd[4] for wrd in words
                if (x - 3.0 <= (wrd[0] + wrd[2]) / 2.0 <= x + w + 3.0) and
                   (y - 3.0 <= (wrd[1] + wrd[3]) / 2.0 <= y + h + 3.0)
            ]
            if node_words:
                reconstructed = " ".join(node_words).strip()
                has_broken_letters = bool(re.search(r'\b[a-zA-Z]{1,2}\s+[a-zA-Z]{1,2}\b', content))
                fitz_has_more_letters = len(re.findall(r'[a-zA-Z0-9]', reconstructed)) > len(re.findall(r'[a-zA-Z0-9]', content)) * 1.03
                if has_broken_letters and fitz_has_more_letters:
                    content = reconstructed

        el = ExtractedElement(
            type="formula" if is_formula else ("heading" if is_heading else ntype),
            id=node.get("id", len(page_obj.elements) + 1),
            page_num=p_num,
            pdfua_tag=tag,
            bbox=bbox,
            x=x,
            y=y,
            w=w,
            h=h,
            text=content,
            font=font,
            font_size=font_size,
            is_heading=is_heading,
            heading_level=heading_lvl,
            is_formula=is_formula,
        )

        page_obj.elements.append(el)
        page_obj.text_items.append(el.to_text_item())
        if is_formula:
            page_obj.formulas.append(el)

    # Finalize text representation per page
    for p_num, page_obj in extracted_pages.items():
        page_obj.text = "\n\n".join(el.text for el in page_obj.elements if el.text)

    sorted_pages = [extracted_pages[k] for k in sorted(extracted_pages.keys())]

    return ExtractedDocument(
        pdf_path=pdf_path,
        total_pages=len(sorted_pages),
        pages=sorted_pages,
        markdown=full_markdown,
    )


def extract_pdf_pages_data(
    pdf_path: Union[str, Path],
    pages: Optional[str] = None,
    image_output: str = "off",
    quiet: bool = True,
) -> Dict[str, Any]:
    """High-level entrypoint returning pages_data format for layout rendering."""
    doc = extract_pdf_structure(
        pdf_path=pdf_path,
        pages=pages,
        reading_order="xycut",
        table_method="cluster",
        image_output=image_output,
        quiet=quiet,
    )
    return doc.to_dict()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    test_pdf = Path(__file__).resolve().parent.parent / "processed" / "FFR_chap06.pdf"
    if test_pdf.exists():
        doc_res = extract_pdf_structure(test_pdf, pages="1-2")
        print(f"Extracted {doc_res.total_pages} pages, Markdown length: {len(doc_res.markdown)}")
        for p in doc_res.pages:
            print(f"Page {p.page_num}: {len(p.elements)} elements, {len(p.tables)} tables, {len(p.formulas)} formulas")
