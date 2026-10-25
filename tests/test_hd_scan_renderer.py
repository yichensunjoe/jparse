"""Unit tests for High-Definition Scanned Document PDF Renderer (hd_scan_renderer)."""

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import fitz

from src.hd_scan_renderer import (
    ScannedPDFTranslator,
    convert_html_to_pdf_via_chrome,
    create_dual_interleaved_pdf,
    crop_page_figure,
    detect_figures_on_page,
    detect_unstructured_tables_on_page,
    find_chrome_binary,
    generate_publication_html,
    merge_caption_continuations,
    process_scanned_pdf_to_hd_pdf,
    split_chapter_and_section_titles,
)
from src.opendataloader_extractor import ExtractedDocument, ExtractedElement, ExtractedPage, ExtractedTable, ExtractedTableCell


class TestHDScanFigureDetectionAndCropping(unittest.TestCase):
    """Test figure detection, boundary calculation, and high-res cropping."""

    def setUp(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.ffr_pdf = self.project_root / "processed" / "FFR_chap06.pdf"

    def test_find_chrome_binary_exists(self):
        chrome = find_chrome_binary()
        self.assertIsNotNone(chrome)
        self.assertTrue(chrome.is_file())

    def test_crop_page_figure_on_real_page(self):
        if not self.ffr_pdf.exists():
            self.skipTest("FFR_chap06.pdf not found in processed/")

        doc = fitz.open(str(self.ffr_pdf))
        p2 = doc[1]  # Page 2 has Fig 6-1 and Fig 6-2
        data_uri = crop_page_figure(p2, fitz.Rect(35, 54, 384, 265), dpi=150)
        doc.close()

        self.assertIsNotNone(data_uri)
        self.assertTrue(data_uri.startswith("data:image/png;base64,"))
        self.assertGreater(len(data_uri), 1000)

    def test_crop_page_figure_invalid_rect(self):
        if not self.ffr_pdf.exists():
            self.skipTest("FFR_chap06.pdf not found in processed/")

        doc = fitz.open(str(self.ffr_pdf))
        p1 = doc[0]
        # 0-width or tiny rect
        res = crop_page_figure(p1, fitz.Rect(10, 10, 12, 12))
        doc.close()
        self.assertIsNone(res)

    def test_detect_figures_on_real_page_excludes_header(self):
        if not self.ffr_pdf.exists():
            self.skipTest("FFR_chap06.pdf not found in processed/")

        doc = fitz.open(str(self.ffr_pdf))
        p2 = doc[1]
        text_blocks = [
            {"text": "FIG . 6-1 . Poison effect as a function of chemical group", "y": 268.9, "h": 13.5},
            {"text": "FIG. 6-2. Conceptual flow diagram for processing fuel", "y": 441.9, "h": 13.5},
            {"text": "The biological hazards associated with a reactor...", "y": 480.9, "h": 60.0},
        ]
        fig_map = detect_figures_on_page(p2, text_blocks)
        doc.close()

        self.assertIn(0, fig_map)
        self.assertIn(1, fig_map)
        self.assertNotIn(2, fig_map)
        uri0, h0 = fig_map[0]
        self.assertTrue(uri0.startswith("data:image/png;base64,"))
        self.assertGreater(h0, 50.0)

    def test_detect_unstructured_tables_on_page(self):
        if not self.ffr_pdf.exists():
            self.skipTest("FFR_chap06.pdf not found in processed/")

        doc = fitz.open(str(self.ffr_pdf))
        p5 = doc[4]
        text_blocks = [
            {"text": "and samarium, as shown in Table 6-2.", "y": 60.0, "h": 20.0, "w": 320.0},
            {"text": "TABLE 6-2", "y": 98.9, "h": 12.0, "w": 80.0},
            {"text": "SOLUBILITY OF VARIOUS RARE-EARTH SULFATES", "y": 112.0, "h": 12.0, "w": 250.0},
            {"text": "0.005 m H2SO4 AT 280°C IN 0.02 m UO2SO4", "y": 124.0, "h": 12.0, "w": 240.0},
            {"text": "Salt Solubility, mg/kg H2O", "y": 150.0, "h": 15.0, "w": 200.0},
            {"text": "La2(SO4)3 10 Nd2(SO4)3 110", "y": 190.0, "h": 30.0, "w": 280.0},
            {"text": "In a mixture of rare-earth sulfates the solubility of an individual is less than it would be.", "y": 260.0, "h": 50.0, "w": 320.0},
        ]
        tbl_map = detect_unstructured_tables_on_page(p5, text_blocks)
        doc.close()

        self.assertIn(1, tbl_map)
        info = tbl_map[1]
        self.assertTrue(info["uri"].startswith("data:image/png;base64,"))
        self.assertIn("TABLE 6-2", info["caption"])
        self.assertIn(4, info["skip_indices"])
        self.assertIn(5, info["skip_indices"])


class TestHDScanTranslatorAndGlossary(unittest.TestCase):
    """Test neural translation, chunking, and domain term protection."""

    def setUp(self):
        self.translator = ScannedPDFTranslator(service="offline")

    def test_apply_domain_glossary(self):
        raw = "FIG. 6-1. The homogeneous reactor produces fission products and biological hazards in the core."
        norm = self.translator.apply_domain_glossary(raw)
        self.assertIn("图 6-1", norm)
        self.assertIn("均质反应堆", norm)
        self.assertIn("裂变产物", norm)
        self.assertIn("堆芯", norm)

    def test_apply_zh_corrections_fixes_mt_mistakes(self):
        raw_zh = "图 6-3. 来自两区反应堆的毛毯材料处理概念流程图，其核心中的毒化效果显著。"
        fixed = self.translator.apply_zh_corrections(raw_zh)
        self.assertIn("双区反应堆", fixed)
        self.assertIn("再生区材料", fixed)
        self.assertIn("堆芯中", fixed)
        self.assertIn("中毒效应", fixed)
        self.assertNotIn("毛毯材料", fixed)
        self.assertNotIn("毒化效果", fixed)

    def test_intro_heading_fast_path(self):
        res = self.translator.translate_single("6-1. INTRODUCTION")
        self.assertEqual(res, "6-1. 引言")

        res2 = self.translator.translate_single("6-2.1. INTRODUCTION")
        self.assertEqual(res2, "6-2.1. 引言")

    def test_translate_caching(self):
        t1 = self.translator.translate_single("12345")
        t2 = self.translator.translate_single("12345")
        self.assertEqual(t1, t2)
        self.assertIn("12345", self.translator._cache)

    def test_merge_caption_continuations(self):
        elements = [
            {"text": "FIG. 6-1. Flow diagram for fuel processing", "y": 100.0, "h": 12.0},
            {"text": "in core of two-region breeder.", "y": 114.0, "h": 12.0},
            {"text": "Regular paragraph text continues here.", "y": 150.0, "h": 50.0},
        ]
        merged = merge_caption_continuations(elements)
        self.assertEqual(len(merged), 2)
        self.assertIn("two-region breeder", merged[0]["text"])

    def test_split_chapter_and_section_titles(self):
        txt = "CHAPTER 6 CHEMICAL PROCESSING* 6-l . INTRODUCTION"
        chap, sec = split_chapter_and_section_titles(txt)
        self.assertEqual(chap, "CHAPTER 6 CHEMICAL PROCESSING*")
        self.assertIn("6-l", sec)
        self.assertIn("INTRODUCTION", sec)

        chap2, sec2 = split_chapter_and_section_titles("Regular Paragraph")
        self.assertIsNone(chap2)
        self.assertIsNone(sec2)


class TestHDScanPublicationHTMLAndPDF(unittest.TestCase):
    """Test publication-grade HTML generation and Chrome PDF rendering."""

    def test_generate_publication_html_structure(self):
        p1 = ExtractedPage(
            page_num=1,
            width=419.0,
            height=594.0,
            elements=[
                ExtractedElement(
                    type="heading", id=1, page_num=1, pdfua_tag="H1",
                    bbox=[40, 50, 380, 70], x=40, y=50, w=340, h=20,
                    text="CHAPTER 6 CHEMICAL PROCESSING* 6-1. INTRODUCTION", font="Times", font_size=14.0,
                ),
                ExtractedElement(
                    type="paragraph", id=2, page_num=1, pdfua_tag="P",
                    bbox=[40, 80, 380, 150], x=40, y=80, w=340, h=70,
                    text="One of the principal advantages of fluid fuel reactors is continuous processing.",
                    font="Times", font_size=10.0,
                ),
            ]
        )
        doc_obj = ExtractedDocument(pdf_path=Path("test.pdf"), total_pages=1, pages=[p1])
        translator = ScannedPDFTranslator(service="offline")

        html_out = generate_publication_html(
            document=doc_obj,
            translator=translator,
            page_figure_maps={},
            title="Test Paper",
            is_dual=False,
            page_dims={1: (419.0, 594.0)},
        )

        self.assertIn('<!DOCTYPE html>', html_out)
        self.assertIn('Noto Serif CJK SC', html_out)
        self.assertIn('chapter-header', html_out)
        self.assertIn('paper-page', html_out)
        self.assertNotIn('box-shadow', html_out)  # Verify absence of blog-like card shadow

    def test_dual_interleaved_pdf_creation(self):
        # Create two minimal 1-page test PDFs in memory
        doc1 = fitz.open()
        p1 = doc1.new_page(width=419, height=594)
        p1.insert_text((50, 50), "Original Page 1")

        doc2 = fitz.open()
        p2 = doc2.new_page(width=419, height=594)
        p2.insert_text((50, 50), "Translated Page 1")

        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p1_path = Path(td) / "p1.pdf"
            p2_path = Path(td) / "p2.pdf"
            dual_path = Path(td) / "dual.pdf"

            doc1.save(str(p1_path))
            doc2.save(str(p2_path))
            doc1.close()
            doc2.close()

            create_dual_interleaved_pdf(p1_path, p2_path, dual_path)
            self.assertTrue(dual_path.exists())

            dual_doc = fitz.open(str(dual_path))
            self.assertEqual(len(dual_doc), 2)
            self.assertIn("Original", dual_doc[0].get_text())
            self.assertIn("Translated", dual_doc[1].get_text())
            dual_doc.close()


if __name__ == "__main__":
    unittest.main()
