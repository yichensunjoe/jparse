"""Unit and integration tests for OpenDataLoader-PDF upstream extractor."""

import json
from pathlib import Path
import tempfile
import unittest

from src.opendataloader_extractor import (
    ExtractedTableCell,
    ExtractedTable,
    check_opendataloader_available,
    ensure_java_environment,
    extract_pdf_pages_data,
    extract_pdf_structure,
    is_formula_element,
    _bbox_to_topleft,
    _parse_table_node,
)


class TestOpenDataLoaderEnvironment(unittest.TestCase):
    """Test Java environment resolution and OpenDataLoader package availability."""

    def test_ensure_java_environment(self):
        java_path = ensure_java_environment()
        self.assertIsNotNone(java_path, "Java runtime should be discoverable")

    def test_check_opendataloader_available(self):
        ok, msg = check_opendataloader_available()
        self.assertTrue(ok, f"OpenDataLoader should be available: {msg}")
        self.assertIn("opendataloader-pdf", msg)


class TestFormulaAndMathDetection(unittest.TestCase):
    """Test formula and mathematical equation detection logic."""

    def test_formula_by_font(self):
        el = {
            "font": "CambriaMath",
            "content": "x + y = z",
        }
        self.assertTrue(is_formula_element(el))

    def test_formula_by_math_symbols(self):
        el = {
            "font": "PalatinoLinotype-Roman",
            "content": "𝜌𝐿𝐵𝐸 = 11113.6 + 1.34𝑇 (1)",
        }
        self.assertTrue(is_formula_element(el))

    def test_formula_by_tag(self):
        el = {
            "pdfua_tag": "Formula",
            "content": "E = mc^2",
        }
        self.assertTrue(is_formula_element(el))

    def test_negative_cases(self):
        # Ordinary text should not be flagged as formula
        el1 = {
            "font": "TimesNewRoman",
            "content": "This chapter introduces the fundamental concepts of fluid dynamics.",
        }
        self.assertFalse(is_formula_element(el1))

        # Section numbers should not be flagged as formula
        el2 = {
            "font": "TimesNewRoman-Bold",
            "content": "1.2. Experimental Setup",
        }
        self.assertFalse(is_formula_element(el2))


class TestCoordinateAndTableParsing(unittest.TestCase):
    """Test PDF bottom-left to top-left coordinate conversion and table parsing."""

    def test_bbox_to_topleft(self):
        # In a 600pt high page, a box from y1=500 to y2=550 is at top: 600 - 550 = 50pt
        page_h = 600.0
        bbox = [100.0, 500.0, 300.0, 550.0]
        x, y, w, h = _bbox_to_topleft(bbox, page_h)
        self.assertEqual(x, 100.0)
        self.assertEqual(y, 50.0)
        self.assertEqual(w, 200.0)
        self.assertEqual(h, 50.0)

    def test_table_parsing_and_markdown_html(self):
        raw_table = {
            "id": "t1",
            "number of rows": 2,
            "number of columns": 2,
            "bounding box": [50.0, 400.0, 450.0, 500.0],
            "rows": [
                {
                    "cells": [
                        {
                            "pdfua_tag": "TH",
                            "is_header": True,
                            "bounding box": [50.0, 450.0, 250.0, 500.0],
                            "content": "Parameter",
                        },
                        {
                            "pdfua_tag": "TH",
                            "is_header": True,
                            "bounding box": [250.0, 450.0, 450.0, 500.0],
                            "content": "Value",
                        },
                    ]
                },
                {
                    "cells": [
                        {
                            "pdfua_tag": "TD",
                            "bounding box": [50.0, 400.0, 250.0, 450.0],
                            "content": "Temperature",
                        },
                        {
                            "pdfua_tag": "TD",
                            "bounding box": [250.0, 400.0, 450.0, 450.0],
                            "content": "650 °C",
                        },
                    ]
                },
            ],
        }
        tbl = _parse_table_node(raw_table, page_num=1, page_h=600.0)
        self.assertEqual(tbl.rows_count, 2)
        self.assertEqual(tbl.cols_count, 2)
        self.assertEqual(tbl.x, 50.0)
        self.assertEqual(tbl.y, 100.0)

        # Markdown
        md = tbl.to_markdown()
        self.assertIn("| Parameter | Value |", md)
        self.assertIn("| Temperature | 650 °C |", md)

        # HTML
        html_str = tbl.to_html()
        self.assertIn("<th>Parameter</th>", html_str)
        self.assertIn("<td>650 °C</td>", html_str)


class TestRealPdfExtraction(unittest.TestCase):
    """End-to-end extraction tests on real sample PDFs in the repository."""

    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent

    def test_extract_headings_and_paragraphs_ffr_chap06(self):
        pdf_path = self.root / "processed" / "FFR_chap06.pdf"
        if not pdf_path.exists():
            self.skipTest("FFR_chap06.pdf not found")

        doc = extract_pdf_structure(pdf_path, pages="1")
        self.assertEqual(doc.total_pages, 1)
        p1 = doc.pages[0]
        self.assertGreater(len(p1.elements), 0)

        # Check reading order: first paragraph contains CHAPTER 6
        p1_texts = [el.text for el in p1.elements]
        self.assertTrue(any("CHAPTER 6" in t for t in p1_texts[:2]))
        # Footnote at bottom
        self.assertTrue(any("By R. A." in t or "Brown" in t for t in p1_texts[-2:]))

    def test_extract_table_from_notification_pdf(self):
        pdf_path = self.root / "processed" / "中国电机工程学会核能发电分会关于公布2026年学术论文评选结果的通知(3)(1).pdf"
        if not pdf_path.exists():
            self.skipTest("Notification PDF not found")

        doc = extract_pdf_structure(pdf_path, pages="2")
        self.assertEqual(doc.total_pages, 1)
        p2 = doc.pages[0]
        self.assertGreaterEqual(len(p2.tables), 1)

        t = p2.tables[0]
        self.assertGreaterEqual(t.rows_count, 5)
        self.assertGreaterEqual(t.cols_count, 3)

        # Verify header cells
        headers = [c.text for c in t.rows[0]]
        self.assertIn("序号", headers)
        self.assertIn("论文名称", headers)

    def test_extract_formulas_from_academic_paper(self):
        pdf_path = self.root / "processed" / "EN13_MDPI_HybridChannel_2025.pdf"
        if not pdf_path.exists():
            self.skipTest("MDPI paper PDF not found")

        doc = extract_pdf_structure(pdf_path, pages="4")
        self.assertEqual(doc.total_pages, 1)
        p4 = doc.pages[0]
        self.assertGreater(len(p4.formulas), 0)

        # Formula text check
        formula_texts = " ".join(f.text for f in p4.formulas)
        self.assertTrue(any(sym in formula_texts for sym in ["𝜌", "𝑐𝑝", "𝜆", "𝜇", "11113.6"]))

    def test_extract_pdf_pages_data_compatibility(self):
        pdf_path = self.root / "processed" / "FFR_chap06.pdf"
        if not pdf_path.exists():
            self.skipTest("FFR_chap06.pdf not found")

        data = extract_pdf_pages_data(pdf_path, pages="1")
        self.assertIn("pages", data)
        self.assertEqual(len(data["pages"]), 1)
        p = data["pages"][0]
        self.assertEqual(p["page"], 1)
        self.assertGreater(p["width"], 300)
        self.assertGreater(p["height"], 400)
        self.assertIn("text_items", p)
        self.assertIn("structured_elements", p)

    def test_table_parsing_with_none_values(self):
        """Test defensive parsing of null/None values in raw table JSON."""
        raw_table = {
            "id": "t_null",
            "number of rows": None,
            "number of columns": None,
            "bounding box": [10.0, 10.0, 100.0, 100.0],
            "rows": [
                {
                    "cells": [
                        {
                            "row number": None,
                            "column number": None,
                            "row span": None,
                            "column span": None,
                            "bounding box": [10.0, 50.0, 50.0, 100.0],
                            "content": "Cell 1",
                        }
                    ]
                }
            ],
        }
        tbl = _parse_table_node(raw_table, page_num=1, page_h=500.0)
        self.assertEqual(tbl.rows_count, 1)
        self.assertEqual(tbl.cols_count, 1)
        self.assertEqual(tbl.rows[0][0].row_span, 1)
        self.assertEqual(tbl.rows[0][0].col_span, 1)

    def test_table_with_rowspan_and_colspan_rendering(self):
        """Test that ExtractedTable HTML preserves rowspan and colspan."""
        cell1 = ExtractedTableCell(
            row_idx=1, col_idx=1, row_span=2, col_span=3, is_header=True,
            bbox=[0, 0, 10, 10], x=0, y=0, w=10, h=10, text="Merged Header", font="sans", font_size=10
        )
        tbl = ExtractedTable(
            id="t_spans", page_num=1, bbox=[0, 0, 10, 10], x=0, y=0, w=10, h=10,
            rows_count=1, cols_count=1, rows=[[cell1]]
        )
        html_out = tbl.to_html()
        self.assertIn('rowspan="2"', html_out)
        self.assertIn('colspan="3"', html_out)
        self.assertIn('Merged Header', html_out)

    def test_font_drop_repair_ffr_chap06(self):
        """Test that Type1 font glyph drops in FFR_chap06 are automatically repaired by fitz."""
        pdf_path = self.root / "processed" / "FFR_chap06.pdf"
        if not pdf_path.exists():
            self.skipTest("FFR_chap06.pdf not found")

        doc = extract_pdf_structure(pdf_path, pages="1")
        p1 = doc.pages[0]
        p1_text = " ".join(el.text for el in p1.elements)

        # Check that 'principal' is restored and NOT 'pr nc pal'
        self.assertIn("principal advantages", p1_text)
        self.assertNotIn("pr nc pal", p1_text)
        # Check that 'fluid fuel' is restored and NOT 'flu d'
        self.assertIn("fluid fuel", p1_text)
        self.assertNotIn("flu d fuel", p1_text)
        # Check that 'fission products' is restored and NOT 'f ss on'
        self.assertIn("fission products", p1_text)
        self.assertNotIn("f ss on", p1_text)

    def test_render_insitu_html_empty_images_preserves_pages(self):
        """Test that render_insitu_html_document does not drop pages when images are missing."""
        from src.in_situ_renderer import render_insitu_html_document
        pages_data = [
            {"page": 1, "width": 595.0, "height": 842.0},
            {"page": 2, "width": 595.0, "height": 842.0},
        ]
        translated_pages = [
            [{"x": 10, "y": 10, "w": 200, "h": 30, "orig_text": "Hello", "zh_text": "你好", "font_size": 11, "lines_count": 1}],
            [{"x": 10, "y": 10, "w": 200, "h": 30, "orig_text": "World", "zh_text": "世界", "font_size": 11, "lines_count": 1}],
        ]
        with tempfile.TemporaryDirectory() as td:
            out_file = Path(td) / "test.html"
            render_insitu_html_document(
                pages_data=pages_data,
                page_image_paths=[],  # Empty images
                translated_pages=translated_pages,
                title="Test Empty Images",
                output_path=out_file,
            )
            html_content = out_file.read_text(encoding="utf-8")
            self.assertIn("id=\"page-1\"", html_content)
            self.assertIn("id=\"page-2\"", html_content)
            self.assertIn("你好", html_content)
            self.assertIn("世界", html_content)


if __name__ == "__main__":
    unittest.main()
