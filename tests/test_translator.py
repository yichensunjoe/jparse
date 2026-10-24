#!/usr/bin/env python3
"""Comprehensive test suite for LiteParse local offline translation engine."""

from pathlib import Path
import re
import shutil
import tempfile
import unittest

from src.translator import (
    TranslationConfig,
    TranslationEngine,
    MarkdownDocumentTranslator,
    classify_code_block,
    clean_historical_ocr_text,
    normalize_chinese_text,
    split_sentences,
    _safe_link_url,
    translate_document_file,
    TABLE_STOPWORDS_MAP,
    MSR_GLOSSARY_77,
)
from src.watcher import Config, ConfigError, health_check


class TestTranslationUnits(unittest.TestCase):
    """Test text processing, normalization, and placeholder isolation."""

    def test_safe_link_url(self):
        self.assertEqual(_safe_link_url("https://asme.org/standard"), "https://asme.org/standard")
        self.assertEqual(_safe_link_url("http://example.com"), "http://example.com")
        self.assertEqual(_safe_link_url("#section-1"), "#section-1")
        self.assertEqual(_safe_link_url("mailto:user@example.com"), "mailto:user@example.com")
        self.assertIsNone(_safe_link_url("javascript:alert(1)"))
        self.assertIsNone(_safe_link_url("data:text/html,<script>alert(1)</script>"))

    def test_chinese_normalization(self):
        raw = "核设施 所用 主动 机械 设备 的资格 。 "
        norm = normalize_chinese_text(raw)
        self.assertEqual(norm, "核设施所用主动机械设备的资格。")

        # Test fullwidth punctuation conversion after Chinese characters
        raw_punc = "这是第一条,那是第二条;请问如何?非常好!"
        norm_punc = normalize_chinese_text(raw_punc)
        self.assertEqual(norm_punc, "这是第一条，那是第二条；请问如何？非常好！")

    def test_split_sentences_with_abbreviations(self):
        text = "This is a test (e.g. for pumps). The seismic qualification shall comply with Para. 1.5.3. All tests are complete!"
        sents = split_sentences(text)
        self.assertEqual(len(sents), 3)
        self.assertEqual(sents[0], "This is a test (e.g. for pumps).")
        self.assertEqual(sents[1], "The seismic qualification shall comply with Para. 1.5.3.")
        self.assertEqual(sents[2], "All tests are complete!")

    def test_glossary_application(self):
        cfg = TranslationConfig(
            model_dir=Path("assets/models/translation"),
            glossary=[
                (r"\bshall\b", "应"),
                ("动力驱动", "动力操作"),
                ("压力泄放阀", "泄压阀"),
            ],
        )
        engine = TranslationEngine(cfg.model_dir)
        translator = MarkdownDocumentTranslator(engine, cfg)

        applied = translator._apply_glossary("本设备shall安装压力泄放阀和动力驱动装置。")
        self.assertIn("应", applied)
        self.assertIn("泄压阀", applied)
        self.assertIn("动力操作", applied)
        self.assertNotIn("压力泄放阀", applied)
        self.assertNotIn("动力驱动", applied)


class TestMarkdownStructureTranslation(unittest.TestCase):
    """Test Markdown document translation structure preservation."""

    @classmethod
    def setUpClass(cls):
        cls.model_dir = Path(__file__).resolve().parent.parent / "assets" / "models" / "translation"
        cls.engine = TranslationEngine(cls.model_dir)
        cls.config = TranslationConfig(model_dir=cls.model_dir)
        cls.translator = MarkdownDocumentTranslator(cls.engine, cls.config)

    def test_code_blocks_and_math_blocks_preserved(self):
        md = r"""# Document Title

```python
def calculate_flow(p, t):
    # shall not be translated
    return p * 1.5
```

$$
E = mc^2 + \int_0^1 f(x) dx
$$

Regular paragraph explaining the calculation.
"""
        translated = self.translator.translate_document(md)
        # Verify code block is untouched
        self.assertIn("def calculate_flow(p, t):", translated)
        self.assertIn("# shall not be translated", translated)
        # Verify math block is untouched
        self.assertIn(r"E = mc^2 + \int_0^1 f(x) dx", translated)
        # Verify paragraph is translated
        self.assertNotIn("Regular paragraph explaining", translated)

    def test_inline_code_and_math_preserved(self):
        para = "Use function `calc_temp()` when variable $T \\le 100$ and pressure $P_0 = 1.0$."
        tr = self.translator._translate_sentence_with_placeholders(para)
        self.assertIn("`calc_temp()`", tr)
        self.assertIn(r"$T \le 100$", tr)
        self.assertIn("$P_0 = 1.0$", tr)

    def test_markdown_images_and_links(self):
        para = "See details in [ASME Standard](https://asme.org/qme) and diagram ![Pump View](assets/pump.png)."
        tr = self.translator._translate_sentence_with_placeholders(para)
        # Must retain half-width ![...]
        self.assertIn("![Pump View](assets/pump.png)", tr)
        self.assertIn("https://asme.org/qme", tr)

    def test_headings_and_anchors(self):
        h = "## 2.3 Environmental Conditions {#env-conditions}"
        lines = self.translator.translate_document(h).splitlines()
        self.assertTrue(lines[0].startswith("## "))
        self.assertIn("{#env-conditions}", lines[0])

    def test_table_translation_structure(self):
        table_md = """| Component | Function | Status |
|---|---|---|
| Main Pump | Coolant circulation | Active |
| Safety Valve | Pressure relief | Standby |"""
        translated = self.translator.translate_document(table_md)
        rows = [r.strip() for r in translated.strip().splitlines() if r.strip()]
        self.assertEqual(len(rows), 4)
        self.assertTrue(rows[0].startswith("|"))
        self.assertTrue(rows[1].startswith("|---"))
        self.assertTrue(rows[2].startswith("|"))
        self.assertTrue(rows[3].startswith("|"))

    def test_bilingual_mode(self):
        md = "This Standard provides requirements for nuclear equipment."
        tr = self.translator.translate_document(md, bilingual=True)
        self.assertIn("This Standard provides requirements for nuclear equipment.", tr)
        self.assertIn("> **译文**：", tr)


class TestAtomicDocumentTranslation(unittest.TestCase):
    """Test file-based translation with atomic publication and rollback."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_trans_"))
        self.model_dir = Path(__file__).resolve().parent.parent / "assets" / "models" / "translation"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_translate_document_file_success(self):
        src_md = self.temp_dir / "literature.md"
        src_md.write_text(
            "# Qualification of Active Equipment\n\n"
            "This Standard establishes technical criteria.\n\n"
            "- Pumps shall be tested.\n",
            encoding="utf-8",
        )

        out_md = self.temp_dir / "literature.zh.md"
        out_html = self.temp_dir / "literature.zh.html"

        res_md, res_html = translate_document_file(
            source_md=src_md,
            output_md=out_md,
            output_html=out_html,
            model_dir=self.model_dir,
            bilingual=False,
        )

        self.assertTrue(res_md.is_file())
        self.assertTrue(res_html.is_file())
        self.assertFalse((self.temp_dir / ".literature.zh.md.partial").exists())
        self.assertFalse((self.temp_dir / ".literature.zh.html.partial").exists())

        md_content = res_md.read_text(encoding="utf-8")
        self.assertIn("资格", md_content)
        self.assertIn("-", md_content)

        html_content = res_html.read_text(encoding="utf-8")
        self.assertIn("<!doctype html>", html_content)
        self.assertIn("LiteParse 本地文档", html_content)

    def test_translate_document_file_rollback_on_error(self):
        src_md = self.temp_dir / "faulty.md"
        src_md.write_text("# Test Title\n\nContent", encoding="utf-8")

        out_md = self.temp_dir / "faulty.zh.md"
        out_html = self.temp_dir / "faulty.zh.html"

        # Point to non-existent model dir to trigger failure during initialization
        with self.assertRaises(Exception):
            translate_document_file(
                source_md=src_md,
                output_md=out_md,
                output_html=out_html,
                model_dir=self.temp_dir / "nonexistent_model",
            )

        # Neither target nor partial files should exist
        self.assertFalse(out_md.exists())
        self.assertFalse(out_html.exists())
        self.assertFalse((self.temp_dir / ".faulty.zh.md.partial").exists())


class TestWatcherTranslationIntegration(unittest.TestCase):
    """Test watcher Config and health_check integration with translation settings."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_watcher_trans_"))
        self.config_path = self.temp_dir / "config.json"
        self.root = Path(__file__).resolve().parent.parent

        base_config = {
            "inbox": str(self.temp_dir / "inbox"),
            "outbox": str(self.temp_dir / "outbox"),
            "processing": str(self.temp_dir / "processing"),
            "processed": str(self.temp_dir / "processed"),
            "failed": str(self.temp_dir / "failed"),
            "logs": str(self.temp_dir / "logs"),
            "lit_binary": "/Users/joe/.local/share/agent-tools/bin/lit",
            "ocr_engine": "paddleocr",
            "paddleocr_python": "/Users/joe/.local/venvs/paddleocr/bin/python",
            "ocr_mode": "auto",
            "scan_book_mode": False,
            "translate_literature": True,
            "translation_model_dir": "assets/models/translation",
            "translation_batch_size": 16,
            "translation_beam_size": 2,
            "translation_bilingual": False,
        }
        # Create mock translation model inside test temp directory
        mock_model_dir = self.temp_dir / "assets" / "models" / "translation"
        mock_model_dir.mkdir(parents=True, exist_ok=True)
        for req_file in ("model.bin", "source.spm", "target.spm"):
            (mock_model_dir / req_file).write_text("dummy", encoding="utf-8")

        import json
        self.config_path.write_text(json.dumps(base_config), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_config_parsing(self):
        cfg = Config(self.config_path)
        self.assertTrue(cfg.translate_literature)
        self.assertEqual(cfg.translation_batch_size, 16)
        self.assertEqual(cfg.translation_beam_size, 2)
        self.assertFalse(cfg.translation_bilingual)
        self.assertTrue(cfg.translation_model_dir.is_dir())

    def test_health_check_passes_with_valid_model(self):
        cfg = Config(self.config_path)
        # Health check should not raise ConfigError
        version = health_check(cfg)
        self.assertIn("lit", version.lower())

    def test_health_check_fails_with_missing_model(self):
        import json
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        raw["translation_model_dir"] = "nonexistent/dir"
        self.config_path.write_text(json.dumps(raw), encoding="utf-8")

        cfg = Config(self.config_path)
        with self.assertRaises(ConfigError) as ctx:
            health_check(cfg)
        self.assertIn("翻译模型目录不存在", str(ctx.exception))


class TestTranslatorEdgeCases(unittest.TestCase):
    """Test boundary values, empty inputs, adversarial syntax, and complex LaTeX."""

    @classmethod
    def setUpClass(cls):
        cls.model_dir = Path(__file__).resolve().parent.parent / "assets" / "models" / "translation"
        cls.engine = TranslationEngine(cls.model_dir)
        cls.config = TranslationConfig(model_dir=cls.model_dir)
        cls.translator = MarkdownDocumentTranslator(cls.engine, cls.config)

    def test_empty_and_whitespace_inputs(self):
        self.assertEqual(self.translator.translate_document(""), "")
        self.assertEqual(self.translator.translate_document("   \n\n   \n"), "")
        self.assertEqual(self.translator.translate_paragraph(""), "")
        self.assertEqual(self.translator.translate_table([]), [])

    def test_untrusted_html_and_malicious_links(self):
        md = "Click [here](javascript:evil()) or visit [good site](https://safe.org). Tag: <script>alert(1)</script>"
        tr = self.translator.translate_document(md)
        # Dangerous javascript scheme must be sanitized to #
        self.assertNotIn("javascript:evil()", tr)
        self.assertIn("https://safe.org", tr)

    def test_complex_latex_and_backslashes(self):
        md = r"Navier-Stokes equation: $\frac{\partial u}{\partial t} + (u \cdot \nabla) u = -\frac{1}{\rho}\nabla p + \nu \nabla^2 u$."
        tr = self.translator.translate_document(md)
        # All LaTeX equations with backslashes must remain intact
        self.assertIn(r"\frac{\partial u}{\partial t}", tr)
        self.assertIn(r"\nabla^2 u", tr)

    def test_table_with_inline_code_and_math(self):
        table = r"""| Symbol | Definition | Unit |
|---|---|---|
| `flow_rate` | Volume per time $\dot{V}$ | $\text{m}^3/\text{s}$ |"""
        tr = self.translator.translate_document(table)
        self.assertIn("`flow_rate`", tr)
        self.assertIn(r"$\dot{V}$", tr)
        self.assertIn(r"$\text{m}^3/\text{s}$", tr)

    def test_code_block_exact_indentation_and_newlines_preserved(self):
        code = '''```python
def calculate_metrics(values):
    # 4 spaces indentation must be preserved
    total = sum(values)
    avg = total / len(values)
    return avg
```'''
        tr = self.translator.translate_document(code)
        self.assertEqual(code.strip(), tr.strip())
        self.assertIn("    # 4 spaces indentation must be preserved\n    total = sum(values)", tr)
        self.assertNotIn("total = sum(values)\n\navg = total", tr)

    def test_math_block_multiline_matrix_preserved(self):
        math_block = r'''$$
\begin{matrix}
1 & 0 \\
0 & 1
\end{matrix}
$$'''
        tr = self.translator.translate_document(math_block)
        self.assertEqual(math_block.strip(), tr.strip())
        self.assertNotIn(r"1 & 0 \\" + "\n\n" + r"0 & 1", tr)

    def test_table_with_escaped_pipe_integrity(self):
        table_with_escaped_pipe = r"""| Norm | Formula | Description |
|---|---|---|
| $L_1$ | \|x\| | Absolute value \|x\| |
| $L_2$ | \|\|x\|\|_2 | Euclidean norm \|\|x\|\| |"""
        tr = self.translator.translate_document(table_with_escaped_pipe)
        lines = [line.strip() for line in tr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 4)
        for row in lines:
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", row)[1:-1]]
            self.assertEqual(len(cells), 3)

    def test_stuttering_word_suppression(self):
        words = ["Name", "Formula", "Status", "Function", "Symbol", "Unit", "Title", "Date"]
        results = self.engine.translate_sentences(words)
        for w, res in zip(words, results):
            # Assert no obvious degenerate 3-char repetitions
            for char in set(res):
                if '\u4e00' <= char <= '\u9fa5':
                    self.assertNotIn(char * 3, res, f"Degenerate repetition found in translation of {w}: {res}")

    def test_link_with_nested_parentheses(self):
        doc = "See [Flow Formulation](https://en.wikipedia.org/wiki/Flow_(mathematics)) for details."
        tr = self.translator.translate_document(doc)
        self.assertIn("https://en.wikipedia.org/wiki/Flow_(mathematics)", tr)
        self.assertNotIn("https://en.wikipedia.org/wiki/Flow_(mathematics) 。", tr)

    def test_translate_sentences_batch_linearity(self):
        sents = [f"This is sentence number {i} for testing." for i in range(8)]
        # Translate once
        res = self.engine.translate_sentences(sents, batch_size=4)
        self.assertEqual(len(res), 8)
        for r in res:
            self.assertTrue(len(r) > 0)


class TestMilestone1Features(unittest.TestCase):
    """Test Milestone 1 (M1: 结构解阻与打字机 OCR 预清洗, R1 & R4)."""

    @classmethod
    def setUpClass(cls):
        cls.model_dir = Path(__file__).resolve().parent.parent / "assets" / "models" / "translation"
        cls.engine = TranslationEngine(cls.model_dir)
        cls.config = TranslationConfig(model_dir=cls.model_dir)
        cls.translator = MarkdownDocumentTranslator(cls.engine, cls.config)

    def test_classify_code_block_genuine_code(self):
        """Verify real programming code in various languages is classified as CODE (True)."""
        samples = [
            ("python", "def calculate_flow(p, t):\n    # Calculate flow\n    return p * 1.5"),
            ("python", "import os\nclass Worker:\n    def __init__(self):\n        self.active = True"),
            ("c", '#include <stdio.h>\nint main(void) {\n    printf("Hello\\n");\n    return 0;\n}'),
            ("bash", '#!/bin/bash\nset -euo pipefail\nexport ENV=production\necho "Running..."'),
            ("json", '{\n  "system": "MSRE",\n  "status": "operational",\n  "limits": [1, 2, 3]\n}'),
            ("yaml", "server:\n  port: 8080\n  host: 0.0.0.0\ndatabase:\n  user: root"),
            ("sql", "SELECT id, name, status FROM reactors WHERE temp > 1200;"),
            ("ini", "port = 8080\nhost = localhost\ntimeout = 30"),
        ]
        for lang, code in samples:
            with self.subTest(lang=lang):
                self.assertTrue(classify_code_block(lang, code), f"Failed to identify real code for {lang}")

    def test_classify_code_block_typewriter_prose(self):
        """Verify typewriter monospace prose and scan blocks are classified as PROSE (False)."""
        samples = [
            ("text", "The reactor cell ventilation system shall be inspected periodically in accordance with safety limits."),
            ("", "1.8 System Test at Elevated Pressure\nThe system was subjected to pressure testing to ensure integrity."),
            (
                "python",
                "A. Makes any warranty or representation, expressed or implied, with respect to the accuracy, "
                "completeness, or usefulness of the information contained in this report...\n"
                "B. Assumes any liabilities with respect to the use of any information disclosed."
            ),
            (
                "python",
                "k11 Ventilation Filters Test*-- The high~efficiency particulate filters at the stack shall be "
                "tested in place at least once a year and after each change of filter elements."
            ),
            ("plaintext", "Operations shall be delayed until the abnormality is corrected."),
            ("", ""),
            ("text", "   \n   \n"),
        ]
        for lang, prose in samples:
            with self.subTest(lang=lang, preview=prose[:30]):
                self.assertFalse(classify_code_block(lang, prose), f"Failed to identify prose for lang={lang!r}")

    def test_clean_historical_ocr_text_all_rules(self):
        """Verify 30+ deterministic heuristic cleaning rules for historical typewriter OCR."""
        # 1. Digit/letter confusions
        self.assertEqual(clean_historical_ocr_text("4o years of operation in 20oo"), "40 years of operation in 2000")
        self.assertEqual(clean_historical_ocr_text("It ts expected that limit 1s reached"), "It is expected that limit is reached")
        self.assertEqual(clean_historical_ocr_text("safety 1limits and 1imit"), "safety limits and limit")
        self.assertEqual(clean_historical_ocr_text("Section 2.h Rod Speed"), "Section 2.4 Rod Speed")
        self.assertEqual(clean_historical_ocr_text("L.2, L.k, L.5, L.6, L.t, L.8, L1k"), "4.2, 4.4, 4.5, 4.6, 4.7, 4.8, 4.14")
        self.assertEqual(clean_historical_ocr_text("k11 Ventilation Filters"), "4.11 Ventilation Filters")
        self.assertEqual(clean_historical_ocr_text("elevation 8Lg-ft"), "elevation 849-ft")
        self.assertEqual(clean_historical_ocr_text("OFERATING SAFETY at O RNL"), "OPERATING SAFETY at ORNL")
        self.assertEqual(clean_historical_ocr_text("for internal vse only"), "for internal use only")
        self.assertEqual(clean_historical_ocr_text("If tais limit is reached, operations shall bhe delayed"), "If this limit is reached, operations shall be delayed")
        self.assertEqual(clean_historical_ocr_text("delayed uwatil corrected intec the cell"), "delayed until corrected into the cell")
        self.assertEqual(clean_historical_ocr_text("wmain-tained and wmain-"), "maintained and main-")

        # 2. Apparatus, notice, and organization typos
        self.assertEqual(clean_historical_ocr_text("any information, apparotus, method, or process"), "any information, apparatus, method, or process")
        self.assertEqual(clean_historical_ocr_text("may not iniringe privately owned righta"), "may not infringe privately owned rights")
        self.assertEqual(clean_historical_ocr_text("accuracy, completenens"), "accuracy, completeness")
        self.assertEqual(clean_historical_ocr_text("R. H. Guymnon"), "R. H. Guymon")
        self.assertEqual(clean_historical_ocr_text("To Government Agsicies and Thair Contractors"), "To Government Agencies and Their Contractors")
        self.assertEqual(clean_historical_ocr_text("ab- normality"), "abnormality")
        self.assertEqual(clean_historical_ocr_text("high~efficiency filter"), "high-efficiency filter")
        self.assertEqual(clean_historical_ocr_text("Test*-- High"), "Test -- High")

        # 3. Ligatures and conjoined words
        self.assertEqual(clean_historical_ocr_text("energydemands and economyfrcm coal"), "energy demands and economy from coal")
        self.assertEqual(clean_historical_ocr_text("Itis clear that madeit plusthe cost"), "It is clear that made it plus the cost")
        self.assertEqual(clean_historical_ocr_text("Thejustificatlon for the project"), "The justification for the project")
        self.assertEqual(clean_historical_ocr_text("OAKRIDGENATIONALLABORATORY CENTRAL FILESNUMBER"), "OAK RIDGE NATIONAL LABORATORY CENTRAL FILES NUMBER")
        self.assertEqual(clean_historical_ocr_text("Hamogeneous reactor with flsslonable and fertlle materials"), "Homogeneous reactor with fissionable and fertile materials")

        # 4. Units and physics symbols
        self.assertEqual(clean_historical_ocr_text("flow 1.0 ft°/min and volume 5.0 ft°"), "flow 1.0 ft³/min and volume 5.0 ft³")
        self.assertEqual(clean_historical_ocr_text("reactivity anomaly 0.5% 3k/k"), "reactivity anomaly 0.5% Δk/k")
        self.assertEqual(clean_historical_ocr_text("L5 psig"), "45 psig")

        # 5. Broken hyphenation
        self.assertEqual(clean_historical_ocr_text("ex-\nceeded"), "exceeded")
        self.assertEqual(clean_historical_ocr_text("ele-\nments"), "elements")

        # 6. Inline code and formula protection
        self.assertEqual(clean_historical_ocr_text("Use variable `4o` and formula `$3k/k$` here."), "Use variable `4o` and formula `$3k/k$` here.")

    def test_normalize_chinese_text_pangu_spacing_and_typography(self):
        """Verify GB/T 15834-2011 Pangu spacing and punctuation typography."""
        # Pangu spacing between CJK and ASCII letters/digits
        raw = "在1210°F时，核反应堆MSRE运行规程第4.4节达到临界。"
        norm = normalize_chinese_text(raw)
        self.assertEqual(norm, "在 1210°F 时，核反应堆 MSRE 运行规程第 4.4 节达到临界。")

        # Zero whitespace adjacent to fullwidth punctuation
        raw_spaces = "在 1210°F 时 ， 反应堆达到临界 。 功率不超过 10Mw 。"
        norm_spaces = normalize_chinese_text(raw_spaces)
        self.assertEqual(norm_spaces, "在 1210°F 时，反应堆达到临界。功率不超过 10Mw。")

        # Inline code spacing
        raw_code = "系统处于`active`状态，参数为$T\\le 100$。"
        norm_code = normalize_chinese_text(raw_code)
        self.assertIn("系统处于 `active` 状态", norm_code)
        self.assertIn("参数为 $T\\le 100$。", norm_code)

        # Markdown image syntax protection
        raw_img = "详见 [标准](https://asme.org) 和图示 ![泵图](assets/pump.png)。"
        norm_img = normalize_chinese_text(raw_img)
        self.assertIn("![泵图](assets/pump.png)", norm_img)
        self.assertIn("https://asme.org", norm_img)

    def test_translate_document_unwraps_typewriter_prose_and_protects_code(self):
        """Verify translate_document unwraps prose code blocks while keeping real code byte-protected."""
        md = '''# Test Chapter

```text
The reactor cell ventilation system shall be inspected periodically in accordance with safety limits.
If this limit is reached, operations shall be delayed until the abnormality is corrected.
```

```python
def calculate_flow(p, t):
    # 4 spaces indentation must be byte-protected
    return p * 1.5
```
'''
        tr = self.translator.translate_document(md)

        # Genuine Python code must be preserved verbatim inside code fence
        self.assertIn("```python\ndef calculate_flow(p, t):", tr)
        self.assertIn("    # 4 spaces indentation must be byte-protected", tr)
        self.assertIn("    return p * 1.5\n```", tr)

        # Typewriter prose fence must be unwrapped (no ```text fence remaining)
        self.assertNotIn("```text", tr)
        self.assertNotIn("The reactor cell ventilation system", tr)
        self.assertIn("通风系统", tr)
        self.assertIn("安全限度", tr)

    def test_ornl_benchmark_coverage_simulation(self):
        """Verify translation coverage of substantive prose on benchmark document is >= 98%."""
        benchmark_path = Path(__file__).resolve().parent.parent / "outbox" / "ORNL-TM-0733REV3_MSRE_Design_Operations_Part_VI_Rev3.md"
        if not benchmark_path.is_file():
            self.skipTest(f"Benchmark file not found: {benchmark_path}")

        text = benchmark_path.read_text(encoding="utf-8")
        total_chars = len(text)
        blocks = re.findall(r"```([^\n]*)\n([\s\S]*?)```", text)
        self.assertEqual(len(blocks), 64)

        prose_blocks = 0
        code_blocks = 0
        for lang, content in blocks:
            if classify_code_block(lang, content):
                code_blocks += 1
            else:
                prose_blocks += 1

        # 63 out of 64 blocks are typewriter prose
        self.assertEqual(prose_blocks, 63)
        self.assertEqual(code_blocks, 1)

        retained_code_chars = sum(len(c) for lang_tag, c in blocks if classify_code_block(lang_tag, c))
        effective_coverage = (total_chars - retained_code_chars) / total_chars
        self.assertGreaterEqual(effective_coverage, 0.98, f"Coverage {effective_coverage*100:.2f}% < 98%")


class TestReviewerFindingsM1(unittest.TestCase):
    """Specific regression tests covering all 5 Reviewer Findings for Milestone 1."""

    @classmethod
    def setUpClass(cls):
        cls.model_dir = Path(__file__).resolve().parent.parent / "assets" / "models" / "translation"
        cls.engine = TranslationEngine(cls.model_dir)
        cls.config = TranslationConfig(model_dir=cls.model_dir)
        cls.translator = MarkdownDocumentTranslator(cls.engine, cls.config)

    def test_reviewer_finding_1_genuine_code_with_domain_comments_and_docstrings(self):
        """[Finding 1]: Ensure real code containing domain terms in comments/docstrings is classified as CODE (True)."""
        adversarial_code_blocks = [
            ("python", 'def check_safety(temp):\n    """Verify reactor temperature is within operating safety limits."""\n    return temp <= 1200'),
            ("python", "# The safety limit of the reactor shall be maintained.\ndef monitor():\n    return True"),
            ("bash", "#!/bin/bash\n# The safety limit of the reactor shall be maintained.\nif [ $temp -gt 1200 ]; then\n    echo Limit\n    exit 1\nfi"),
            ("yaml", "# Reactor safety configuration\nsystem: MSRE\nlimit: 1200"),
            ("json", '{\n  "system": "MSRE",\n  "comment": "The reactor safety limit shall apply"\n}'),
            ("sql", "SELECT safety_limit, reactor_status FROM system_table WHERE limit > 10 AND temperature < 1000;"),
            ("c", "/* Reactor cell cooling system operation in accordance with limits */\nint check_temp(double temp) {\n    if (temp > 1200.0) return -1;\n    return 0;\n}"),
        ]
        for lang, code in adversarial_code_blocks:
            with self.subTest(lang=lang):
                self.assertTrue(classify_code_block(lang, code), f"Failed for {lang}")

        doc_with_code = '''# Test Doc\n\n```python\ndef check_safety(temp):\n    """Verify reactor temperature is within operating safety limits."""\n    return temp <= 1200\n```\n'''
        translated = self.translator.translate_document(doc_with_code)
        self.assertIn("```python", translated)
        self.assertIn("def check_safety(temp):", translated)
        self.assertIn("    return temp <= 1200", translated)

    def test_reviewer_finding_2_historical_ocr_escalated_rules(self):
        """[Finding 2]: Verify missing OCR cleaning rules escalated in review are implemented."""
        self.assertEqual(
            clean_historical_ocr_text("it is possgible and obove the limit with con=- centration"),
            "it is possible and above the limit with concentration",
        )
        self.assertEqual(clean_historical_ocr_text("high con=-\ncentration of fuel salt"), "high concentration of fuel salt")
        self.assertEqual(clean_historical_ocr_text("Administ  strator approval is possgible"), "Administrator approval is possible")
        self.assertEqual(clean_historical_ocr_text("requi  guires testing obove normal limits"), "requires testing above normal limits")

    def test_currency_and_inline_math_shielding(self):
        """Verify currency strings ($4o and $5o) are cleaned while math formulas ($3k/k$) are preserved."""
        raw = "The cost was $4o and $5o, with formula $3k/k$."
        cleaned = clean_historical_ocr_text(raw)
        self.assertIn("$40 and $50", cleaned)
        self.assertIn("$3k/k$", cleaned)

    def test_reviewer_finding_3_chinese_reduplication_grammar_preservation(self):
        """[Finding 3]: Verify legitimate Chinese 2-occurrence phrases are NOT mutilated while 3+ stutter loops are suppressed."""
        valid_grammar_samples = [
            ("通过该系统系统地进行评估。", "通过该系统系统地进行评估。"),
            ("设计设计图纸，管理管理人员。", "设计设计图纸，管理管理人员。"),
            ("研究研究生教育体系。", "研究研究生教育体系。"),
            ("发展发展中国家的核能事业。", "发展发展中国家的核能事业。"),
            ("天天向上，人人有责。", "天天向上，人人有责。"),
        ]
        for inp, expected in valid_grammar_samples:
            with self.subTest(sample=inp):
                self.assertEqual(normalize_chinese_text(inp), expected)

        stutter_samples = [
            ("包含公式公式公式和名称名称名称名称。", "包含公式和名称。"),
            ("系统系统系统", "系统"),
            ("的的的", "的"),
        ]
        for inp, expected in stutter_samples:
            with self.subTest(stutter=inp):
                self.assertEqual(normalize_chinese_text(inp), expected)

    def test_reviewer_finding_4_sentence_ending_period_adjacent_to_western_text(self):
        """[Finding 4]: Verify period after Chinese sentence before Western acronyms/numbers is normalized to fullwidth 。."""
        period_normalization_samples = [
            ("这是核反应堆规程. MSRE 必须遵守此安全限值.", "这是核反应堆规程。MSRE 必须遵守此安全限值。"),
            ("规程. MSRE 必须遵守。", "规程。MSRE 必须遵守。"),
            ("根据操作手册. 1200 MW 是反应堆功率上限.", "根据操作手册。1200 MW 是反应堆功率上限。"),
            ("这是核工程规程. \"MSRE\" 是重点堆型.", "这是核工程规程。\"MSRE\" 是重点堆型。"),
            ("（这是核反应堆规程.）", "（这是核反应堆规程。）"),
            ("“这是核反应堆规程.”", "“这是核反应堆规程。”"),
        ]
        for inp, expected in period_normalization_samples:
            with self.subTest(inp=inp):
                self.assertEqual(normalize_chinese_text(inp), expected)

        negative_samples = [
            ("这是核反应堆规程... 之后就没有了。", "这是核反应堆规程... 之后就没有了。"),
            ("详见附件文档.pdf 和架构.md 文件。", "详见附件文档.pdf 和架构.md 文件。"),
            ("访问示例.cn 网站。", "访问示例.cn 网站。"),
            ("在 1210°F 时达到临界第 4.4 节。", "在 1210°F 时达到临界第 4.4 节。"),
        ]
        for inp, expected in negative_samples:
            with self.subTest(neg=inp):
                self.assertEqual(normalize_chinese_text(inp), expected)

    def test_reviewer_finding_5_nested_code_fences_multibacktick(self):
        """[Finding 5]: Verify 4+ backtick documentation fences enclosing 3-backtick code blocks do not close prematurely."""
        nested_md = """````markdown
Example of Python code:
```python
def inner_func():
    return 42
```
End of inner example.
````
"""
        translated = self.translator.translate_document(nested_md)
        self.assertIn("````", translated, "Outer 4-backtick fence destroyed or closed prematurely!")
        self.assertIn("```python", translated, "Inner 3-backtick python fence missing!")
        self.assertIn("def inner_func():", translated, "Inner python function name translated or stripped!")
        self.assertIn("    return 42", translated, "Inner return statement translated or stripped!")


class TestMilestone2Features(unittest.TestCase):
    """M2: 熔盐堆与核工程专属术语注入与表格对齐幻觉消除 (R2 & R3) + M1 Final Polish."""

    @classmethod
    def setUpClass(cls):
        cls.model_dir = Path(__file__).resolve().parent.parent / "assets" / "models" / "translation"
        cls.engine = TranslationEngine(cls.model_dir)
        cls.config = TranslationConfig(model_dir=cls.model_dir)
        cls.translator = MarkdownDocumentTranslator(cls.engine, cls.config)

    def test_glossary_and_stopwords_data_structures(self):
        """[R2 & R3]: Verify MSR_GLOSSARY_77 has at least 77 items and TABLE_STOPWORDS_MAP contains essential prepositions."""
        self.assertGreaterEqual(len(MSR_GLOSSARY_77), 77)
        glossary_dict = dict(MSR_GLOSSARY_77)
        self.assertIn("scram", glossary_dict)
        self.assertIn("fuel drain tank", glossary_dict)
        self.assertIn("of", TABLE_STOPWORDS_MAP)
        self.assertEqual(TABLE_STOPWORDS_MAP["of"], "的")

    def test_m1_surgical_defect1_ocr_cleaning_whitespace_flexibility(self):
        """[M1 Polish 1]: Verify 0.62 yc/sec is cleaned to 0.62 μCi/sec regardless of spacing."""
        samples = [
            ("shall not exceed 0.62 yc/sec of iodine", "shall not exceed 0.62 μCi/sec of iodine"),
            ("shall not exceed 0.62yc/sec of iodine", "shall not exceed 0.62 μCi/sec of iodine"),
            ("limit: 0.62  yc/sec stack release", "limit: 0.62 μCi/sec stack release"),
        ]
        for raw, expected in samples:
            with self.subTest(raw=raw):
                cleaned = clean_historical_ocr_text(raw)
                self.assertIn("0.62 μCi/sec", cleaned)
                self.assertNotIn("yc/sec", cleaned)

    def test_m1_surgical_defect2_markdown_language_tag_classification(self):
        """[M1 Polish 2]: Verify outer documentation fences tagged markdown or md are classified as CODE (True)."""
        samples = [
            ("markdown", "```python\nx = 1\n```"),
            ("md", "```bash\necho 1\n```"),
            ("markdown", "# Architecture Documentation\n\n- System item 1\n- System item 2"),
            ("md", "> Quoted specification rule in markdown format"),
        ]
        for tag, content in samples:
            with self.subTest(tag=tag, content=content[:20]):
                is_code = classify_code_block(tag, content)
                self.assertTrue(is_code, f"Language tag {tag} should be classified as code to protect documentation fence")

    def test_all_30_benchmark_nuclear_terms_accuracy(self):
        """[R2]: Verify all 30 benchmark nuclear and MSR terms translate accurately without fatal blunders."""
        # 30 Benchmark Terms: (English key, required Chinese concepts, forbidden false translations)
        benchmark_checks = [
            ("scram", ["停堆"], ["螺旋藻", "碎裂", "倾斜", "争先恐后"]),
            ("scram test", ["停堆试验"], ["螺旋藻气候试验", "倾斜测试"]),
            ("scram trip", ["停堆跳闸"], ["滚动旅行旅费", "倾斜旅行"]),
            ("scram circuit", ["停堆"], ["碎裂电路", "螺旋藻回路"]),
            ("fuel drain tank", ["燃料排盐罐"], ["排水池", "排油罐", "坦克"]),
            ("drain tank", ["排盐罐"], ["排水池", "坦克"]),
            ("drain-tank cell", ["排盐罐舱"], ["排气罐", "电池"]),
            ("reactor cell", ["反应堆舱"], ["反应堆电池", "反应堆细胞"]),
            ("cell shield blocks", ["舱室屏蔽块"], ["保护罩区块", "电池屏蔽"]),
            ("reactor vessel", ["反应堆容器"], ["反应堆船舶", "船只", "飞船"]),
            ("fuel salt", ["燃料盐"], ["软化盐", "燃料盐盐"]),
            ("coolant salt", ["冷却盐"], ["冷却液食盐"]),
            ("flush salt", ["冲洗盐"], ["刷新盐", "冲水盐"]),
            ("cover gas", ["覆盖气体"], ["封面气体", "盖气体"]),
            ("offgas", ["尾气"], ["沼气", "天然气气体"]),
            ("ventilation stack", ["通风烟囱"], ["堆叠", "堆栈"]),
            ("graphite moderator", ["石墨慢化剂"], ["游戏主持人", "主持人"]),
            ("control rod", ["控制棒"], ["控制杆", "棍子"]),
            ("safety rod", ["安全棒"], ["安全杆"]),
            ("subcritical", ["次临界"], ["亚关键", "次关键"]),
            ("critical", ["临界"], ["关键", "危急"]),
            ("reactivity", ["反应性"], ["反应过度"]),
            ("reactivity anomaly", ["反应性异常"], ["自由异常点"]),
            ("period trip", ["周期停堆跳闸"], ["时期旅行", "时段跳闸"]),
            ("thermal shield", ["热屏蔽"], ["热护盾"]),
            ("vapor-condensing system", ["蒸汽冷凝系统"], ["水汽凝结"]),
            ("containment", ["安全壳"], ["遏制"]),
            ("tellurium embrittlement", ["碲脆化"], ["碲脆"]),
            ("breeder reactor", ["增殖堆"], ["饲养堆", "育种反应堆"]),
            ("FLiBe", ["FLiBe"], ["飞利贝", "飞利浦"]),
        ]
        for term, required_matches, forbidden_matches in benchmark_checks:
            with self.subTest(term=term):
                sentence = f"The operating procedure requires inspection of the {term} during maintenance."
                translated = self.translator.translate_paragraph(sentence)
                clean_check = translated
                for req in required_matches:
                    self.assertIn(req, translated, f"Term '{term}' should translate to contain '{req}', got '{translated}'")
                    clean_check = clean_check.replace(req, "")
                for forb in forbidden_matches:
                    self.assertNotIn(forb, clean_check, f"Term '{term}' must NOT produce blunder '{forb}', got '{translated}'")

    def test_hyphenated_compound_terms(self):
        """[R2]: Verify hyphen-tolerant regex matches hyphenated terms like fuel-pump bowl and fuel drain-tank."""
        text = "The fuel-pump bowl and fuel drain-tank were inspected. The vapor-condensing system was tested."
        translated = self.translator.translate_paragraph(text)
        self.assertIn("燃料泵泵池", translated)
        self.assertIn("燃料排盐罐", translated)
        self.assertIn("蒸汽冷凝系统", translated)
        self.assertNotIn("泵碗", translated)
        self.assertNotIn("排油罐", translated)

    def test_inline_code_inside_sentences_with_domain_terms(self):
        """[R2]: Verify inline code words (`scram`) inside sentences are preserved byte-for-byte and not corrupted by terminology placeholders."""
        text = "The function `scram` initiates emergency scram when the reactor period is too short."
        translated = self.translator.translate_paragraph(text)
        self.assertIn("`scram`", translated, "Inline code `scram` must be preserved verbatim in backticks")
        self.assertIn("停堆", translated, "Domain term scram outside backticks must be translated to 停堆")
        self.assertNotIn("`停堆`", translated, "Inline code must NOT be translated inside backticks")

    def test_table_translation_isolated_stopwords_no_hallucinations(self):
        """[R3]: Verify table with isolated stopwords does NOT produce alignment hallucinations (e.g. 联年月日, be be, or stutter loops)."""
        tbl = [
            "| Item | Preposition | Spec | Condition | Status | Type |",
            "| --- | --- | --- | --- | --- | --- |",
            "| Pump | of | the | Commission | for | gas |",
            "| Flow | in | each | reactor | with | total |",
            "| Valve | to | its | position | as | is |",
            "| Sensor | by | all | channels | at | are |",
            "| Limit | from | on | boundary | than | be |",
            "| Count | per | min | or | sec | ref |",
            "| State | not | no | error | and | ok |",
        ]
        translated = self.translator.translate_table(tbl)
        full_text = "\n".join(translated)
        # Check zero alignment hallucinations
        self.assertNotIn("联年月日", full_text)
        self.assertNotIn("联联年月日", full_text)
        self.assertNotIn("be be", full_text)
        self.assertNotIn("天然气气体", full_text)
        self.assertNotIn("总计共计", full_text)
        self.assertNotIn("其 其 其", full_text)
        # Check table structure preserved
        self.assertEqual(len(translated), len(tbl))

    def test_table_column_count_conservation_and_pipe_protection(self):
        """[R3]: Verify table column count N invariance (padding short rows and merging long rows) and escaped pipe \\| preservation."""
        tbl = [
            "| Col 1 | Col 2 | Col 3 | Col 4 |",
            "| :--- | :---: | ---: | :--- |",
            "| Normal Cell | Option A \\| Option B | Formula $\\|x\\| \\le 1$ | Standby |",
            "| Only Two | Columns |",
            "| Col A | Col B | Col C | Col D | Extra Col E | Extra Col F |",
        ]
        translated = self.translator.translate_table(tbl)
        self.assertEqual(len(translated), 5)
        # Verify header is 4 columns
        header_cols = len(re.split(r"(?<!\\)\|", translated[0])[1:-1])
        self.assertEqual(header_cols, 4)

        # Row 2 (Data row with escaped pipes)
        row2_cols = len(re.split(r"(?<!\\)\|", translated[2])[1:-1])
        self.assertEqual(row2_cols, 4, "Escaped pipes must not split into additional columns")
        self.assertIn(r"\|", translated[2], "Escaped pipe must be preserved in cell")

        # Row 3 (Padded row: originally 2 columns, padded to 4)
        row3_cols = len(re.split(r"(?<!\\)\|", translated[3])[1:-1])
        self.assertEqual(row3_cols, 4, "Ragged row must be padded to match N=4 columns exactly")

        # Row 4 (Merged row: originally 6 columns, merged to 4)
        row4_cols = len(re.split(r"(?<!\\)\|", translated[4])[1:-1])
        self.assertEqual(row4_cols, 4, "Overlong row must have excess cells merged into last column to maintain N=4")


if __name__ == "__main__":
    unittest.main()
