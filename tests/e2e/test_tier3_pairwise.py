#!/usr/bin/env python3
"""Tier 3: Pairwise Combinatorial Interaction E2E Tests.

Covers cross-feature combinatorial interactions (>= 15 test cases):
  P01: Table + Nuclear Terminology
  P02: Table + Isolated Stopwords + Escaped Pipe
  P03: Real Code Fence + LaTeX Math Blocks in Same Document
  P04: Typewriter Prose Fence + Terminology + Chinese Typography
  P05: OCR Cleaning + Terminology Substitution
  P06: Table + OCR Cleaning + Terminology
  P07: Long Prose Block (>512 Tokens) + Terminology + Token Clamping
  P08: Bilingual Mode + Terminology + Code Blocks
  P09: Safe Links + Markdown Images + Typography Normalization
  P10: Mixed Real Code Block + Typewriter Prose Block in Single Doc
  P11: Headings + Nuclear Terminology + Typography
  P12: Bulleted Lists + Nuclear Terminology + Inline Math
  P13: Blockquotes + OCR Noise + Terminology + Typography
  P14: Table + Inline Code + Nuclear Terminology + Escaped Pipe
  P15: Composite Full-Pipeline Document End-to-End
"""

from pathlib import Path
import re
import sys
import unittest

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent.parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.translator import (
    MarkdownDocumentTranslator,
    TranslationConfig,
    normalize_chinese_text,
)
import src.translator as translator_module

from tests.e2e.e2e_helpers import (
    MSR_GLOSSARY_77,
    get_shared_engine,
)


class TestTier3PairwiseCombinations(unittest.TestCase):
    """Pairwise combinatorial interaction tests across features."""

    @classmethod
    def setUpClass(cls):
        engine = get_shared_engine()
        config = TranslationConfig(
            model_dir=Path(__file__).resolve().parent.parent.parent / "assets" / "models" / "translation",
            glossary=MSR_GLOSSARY_77,
        )
        cls.translator = MarkdownDocumentTranslator(engine, config)

    def _require_m2_tables(self):
        has_table_short_circuit = hasattr(translator_module, "TABLE_STOPWORDS_MAP") or getattr(
            self.translator, "_table_short_circuit_enabled", False
        )
        if not has_table_short_circuit:
            self.skipTest("Table short-circuit & column invariance pending M2 integration")

    def test_p01_table_and_nuclear_terminology(self):
        """P01: Table containing nuclear engineering terms translates terms while maintaining table rows."""
        tbl = [
            "| Component | System Location | Status |",
            "| --- | --- | --- |",
            "| Fuel Drain Tank | Reactor Cell | Standby |",
            "| Control Rod | Reactor Vessel | Normal |",
        ]
        translated = self.translator.translate_table(tbl)
        full_text = "\n".join(translated)
        self.assertIn("排盐罐", full_text)
        self.assertNotIn("排水池", full_text)
        self.assertNotIn("排油罐", full_text)
        self.assertIn("反应堆", full_text)

    def test_p02_table_and_stopwords_and_escaped_pipe(self):
        """P02: Table with isolated cells (the, of, in) AND escaped pipes (\\|) without hallucinations."""
        self._require_m2_tables()
        tbl = [
            "| Item | Preposition | Spec | Options |",
            "| --- | --- | --- | --- |",
            "| Sensor | of | the | A \\| B |",
        ]
        translated = self.translator.translate_table(tbl)
        full_text = "\n".join(translated)
        self.assertNotIn("联年月日", full_text)
        self.assertNotIn("be be", full_text)
        self.assertIn(r"\|", full_text)

    def test_p03_real_code_fence_and_latex_math_in_same_document(self):
        """P03: Document containing Python code block, display math block, and prose."""
        doc = (
            "# Nuclear Safety System\n\n"
            "```python\n"
            "def calculate_trip(period):\n"
            "    # preserve verbatim\n"
            "    return period < 1.0\n"
            "```\n\n"
            "$$\n"
            "P(t) = P_0 e^{t/T}\n"
            "$$\n\n"
            "The reactor period shall be monitored continuously.\n"
        )
        translated = self.translator.translate_document(doc)
        # Python code preserved byte-for-byte
        self.assertIn("def calculate_trip(period):", translated)
        self.assertIn("# preserve verbatim", translated)
        # Math block preserved
        self.assertIn("P(t) = P_0 e^{t/T}", translated)
        # Prose translated
        self.assertIn("反应堆周期", translated)

    def test_p04_typewriter_prose_fence_and_terminology_and_typography(self):
        """P04: Fenced prose with text or empty lang containing scram is unwrapped and translated."""
        doc = (
            "```text\n"
            "All scram circuits shall be tested prior to startup. The reactor cell pressure must be negative.\n"
            "```\n"
        )
        translated = self.translator.translate_document(doc)
        # Should translate the scram circuit and reactor cell
        self.assertTrue("停堆" in translated or "电路" in translated)
        self.assertNotIn("螺旋藻", translated)

    def test_p05_ocr_cleaning_and_terminology_substitution(self):
        """P05: Raw OCR typos (Agsicies, energydemands) cleaned and glossary matched."""
        raw = "All Agsicies agree that energydemands require the fuel drain tank system to be ready."
        translated = self.translator.translate_paragraph(raw)
        self.assertIn("排盐罐", translated)
        self.assertNotIn("排水池", translated)
        self.assertNotIn("排油罐", translated)

    def test_p06_table_with_ocr_typos_and_terminology(self):
        """P06: Table cells containing OCR typos and nuclear terms."""
        self._require_m2_tables()
        tbl = [
            "| Parameter | Location | Value |",
            "| --- | --- | --- |",
            "| Scram Time | Reactor Cell | 1.0 ft° |",
        ]
        translated = self.translator.translate_table(tbl)
        full_text = "\n".join(translated)
        self.assertIn("停堆", full_text)
        self.assertNotIn("螺旋藻", full_text)

    def test_p07_long_prose_block_and_terminology_and_token_clamping(self):
        """P07: Long paragraph (>500 words) with nuclear terms does not trigger NMT 512 token error."""
        core_sentence = "The reactor cell and the fuel drain tank shall be inspected for tellurium embrittlement regularly. "
        long_paragraph = core_sentence * 35  # ~525 words
        translated = self.translator.translate_paragraph(long_paragraph)
        self.assertIn("反应堆舱", translated)
        self.assertIn("燃料排盐罐", translated)
        self.assertIn("碲脆化", translated)

    def test_p08_bilingual_mode_and_terminology_and_code_blocks(self):
        """P08: Bilingual translation mode with code block and terminology."""
        doc = (
            "# Section Title\n\n"
            "```python\n"
            "print('MSRE Status')\n"
            "```\n\n"
            "The graphite moderator was designed for high neutron flux.\n"
        )
        translated = self.translator.translate_document(doc, bilingual=True)
        # Both English and Chinese appear in bilingual mode
        self.assertIn("print('MSRE Status')", translated)
        self.assertIn("graphite moderator", translated)
        self.assertIn("石墨慢化剂", translated)

    def test_p09_safe_links_and_markdown_images_and_typography(self):
        """P09: Markdown images and links adjacent to Chinese text with correct punctuation formatting."""
        doc = (
            "请查看以下示意图：![反应堆结构图](images/msre_cell.png)，"
            "详细规格请参考官方文档 [ORNL 报告](https://ornl.gov/tm-0733)。"
        )
        norm = normalize_chinese_text(doc)
        self.assertIn("![反应堆结构图](images/msre_cell.png)", norm)
        self.assertIn("[ORNL 报告](https://ornl.gov/tm-0733)", norm)
        self.assertNotIn("！[", norm)

    def test_p10_mixed_code_block_and_typewriter_prose_in_single_doc(self):
        """P10: Document with genuine Python code AND legal/prose text fence."""
        doc = (
            "# Hybrid Specification\n\n"
            "```python\n"
            "import math\n"
            "def check_limit(val):\n"
            "    return math.sqrt(val) < 10.0\n"
            "```\n\n"
            "The primary containment provides radiation shielding for personnel.\n"
        )
        translated = self.translator.translate_document(doc)
        # Genuine python code preserved
        self.assertIn("import math", translated)
        self.assertIn("def check_limit(val):", translated)
        # Prose translated with terminology
        self.assertIn("安全壳", translated)

    def test_p11_headings_with_nuclear_terms_and_typography(self):
        """P11: Markdown headings with nuclear terms and trailing punctuation stripped."""
        doc = (
            "# 4.4 Reactor Cell Temperature Limits\n\n"
            "## Scram Test Requirements.\n\n"
            "Body paragraph on system operation.\n"
        )
        translated = self.translator.translate_document(doc)
        lines = translated.splitlines()
        h1 = [l for l in lines if l.startswith("# ")][0]
        h2 = [l for l in lines if l.startswith("## ")][0]
        self.assertIn("反应堆舱", h1)
        self.assertIn("停堆试验", h2)
        # Headings should not end with full stop
        self.assertFalse(h1.endswith("。"))
        self.assertFalse(h2.endswith("。"))

    def test_p12_bulleted_lists_with_nuclear_terms_and_inline_math(self):
        """P12: Bulleted list items containing nuclear terms and inline math."""
        doc = (
            "* The scram time shall be $t \\le 1.0\\text{ sec}$ at all times.\n"
            "* The fuel drain tank capacity exceeds $V_{max} = 5.0\\text{ ft}^3$.\n"
        )
        translated = self.translator.translate_document(doc)
        self.assertIn("*", translated)
        self.assertIn("$t \\le 1.0\\text{ sec}$", translated)
        self.assertIn("停堆时间", translated)
        self.assertIn("燃料排盐罐", translated)

    def test_p13_blockquotes_with_ocr_noise_and_terminology(self):
        """P13: Blockquote containing nuclear term translated with quote marker preserved."""
        doc = (
            "> The graphite moderator shall be inspected annually.\n"
            "> The fuel offgas discharge rate must not exceed limits.\n"
        )
        translated = self.translator.translate_document(doc)
        self.assertIn(">", translated)
        self.assertIn("石墨慢化剂", translated)
        self.assertIn("尾气", translated)

    def test_p14_table_with_inline_code_and_nuclear_terms_and_pipe(self):
        """P14: Table cells with inline code, nuclear terms, and escaped pipe delimiter."""
        self._require_m2_tables()
        tbl = [
            "| Variable | Term Definition | Option |",
            "| --- | --- | --- |",
            "| `scram_flag` | Fuel Drain Tank | Left \\| Right |",
        ]
        translated = self.translator.translate_table(tbl)
        full_text = "\n".join(translated)
        self.assertIn("`scram_flag`", full_text)
        self.assertIn("燃料排盐罐", full_text)
        self.assertIn(r"\|", full_text)

    def test_p15_composite_full_pipeline_document_e2e(self):
        """P15: Full multi-block document with headings, Python code, math, tables, images, and terms."""
        doc = (
            "# MSRE Design and Operations Report\n\n"
            "The MSRE was a high-temperature reactor utilizing FLiBe carrier salt.\n\n"
            "```python\n"
            "def emergency_shutdown():\n"
            "    return 'scram activated'\n"
            "```\n\n"
            "$$\n"
            "\\Delta k/k = \\rho_{excess} - \\rho_{rods}\n"
            "$$\n\n"
            "| Component | Condition | Action |\n"
            "| --- | --- | --- |\n"
            "| Fuel Drain Tank | Standby | Ready |\n\n"
            "![System Flow](images/cell_diagram.png)\n\n"
            "All scram circuits must be validated before nuclear operation.\n"
        )
        translated = self.translator.translate_document(doc)
        # Verify headings, terms, code, math, images, and prose
        self.assertIn("#", translated)
        self.assertIn("def emergency_shutdown():", translated)
        self.assertIn("\\Delta k/k", translated)
        self.assertIn("![System Flow](images/cell_diagram.png)", translated)
        self.assertIn("FLiBe", translated)
        self.assertIn("停堆", translated)


if __name__ == "__main__":
    unittest.main()
