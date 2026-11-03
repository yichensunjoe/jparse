import json
import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.html_renderer import render_markdown_document
from src.markdown_reflow import reflow_markdown_document, reflow_ocr_text
from src.scan_html_renderer import (
    extract_scan_markdown_from_html,
    write_scan_html,
    write_scan_markdown,
)
from src.table_repair import (
    find_suspicious_tables,
    normalize_table_cell_spacing,
    repair_markdown_tables,
)
from src.watcher import Config, Watcher, text_score


FAKE_LIT_TEMPLATE = r'''#!/usr/bin/env python3
import base64
from pathlib import Path
import sys

args = sys.argv[1:]
output = Path(args[args.index("--output") + 1])
mode = "noocr" if "--no-ocr" in args else "ocr"
behavior = {behavior!r}
if behavior == "fail":
    print("synthetic failure")
    raise SystemExit(7)
if "--image-output-dir" in args:
    image_dir = Path(args[args.index("--image-output-dir") + 1])
    image_dir.mkdir(parents=True, exist_ok=True)
    image_dir.joinpath("image_0.png").write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZrS8AAAAASUVORK5CYII="))
if behavior == "fallback" and mode == "noocr":
    output.write_text("", encoding="utf-8")
elif behavior == "scan" and mode == "noocr":
    output.write_text("```text\n\n```\n-----\n" * 3, encoding="utf-8")
else:
    prefix = "DIGITAL " if mode == "noocr" else "OCR "
    output.write_text("# Synthetic PDF\n\n" + prefix * 20 + "\ncontinued visual line for reflow\n\n![Embedded figure](image_0.png)\n\n| Item | Status |\n| --- | ---: |\n| HTML | Ready |\n", encoding="utf-8")
'''


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for name in ("inbox", "outbox", "processing", "processed", "failed", "logs"):
            (self.root / name).mkdir()
        self.logger = logging.getLogger("watcher-test-%s" % id(self))
        self.logger.handlers.clear()
        self.logger.addHandler(logging.NullHandler())

    def tearDown(self):
        self.temporary.cleanup()

    def make_config(self, behavior="digital", **overrides):
        fake_lit = self.root / "fake-lit"
        fake_lit.write_text(FAKE_LIT_TEMPLATE.format(behavior=behavior), encoding="utf-8")
        fake_lit.chmod(0o755)
        raw = {
            "inbox": "inbox",
            "outbox": "outbox",
            "processing": "processing",
            "processed": "processed",
            "failed": "failed",
            "logs": "logs",
            "poll_interval_seconds": 0.1,
            "settle_seconds": 0,
            "output_format": "html",
            "ocr_mode": "auto",
            "ocr_language": "eng",
            "minimum_text_characters": 10,
            "num_workers": 1,
            "max_pages": 10,
            "dpi": 150,
            "parse_timeout_seconds": 10,
            "lit_binary": str(fake_lit),
            "required_lit_version": "",
            "keep_markdown": True,
            "reflow_markdown": True,
            "scan_book_mode": False,
        }
        raw.update(overrides)
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(raw), encoding="utf-8")
        return Config(config_path)

    def drop_pdf(self, name="report.pdf"):
        path = self.root / "inbox" / name
        path.write_bytes(b"%PDF synthetic")
        return path

    def test_digital_pdf_uses_fast_result_and_archives_source(self):
        config = self.make_config("digital")
        self.drop_pdf()
        Watcher(config, self.logger).run_once()
        output = (self.root / "outbox" / "report.html").read_text()
        self.assertIn("DIGITAL", output)
        self.assertIn("<!doctype html>", output)
        self.assertIn("<table>", output)
        self.assertIn("data:image/png;base64,", output)
        markdown = (self.root / "outbox" / "report.md").read_text()
        self.assertIn("DIGITAL", markdown)
        self.assertIn("DIGITAL continued visual line for reflow", markdown)
        self.assertNotIn("\ncontinued visual line for reflow", markdown)
        self.assertIn("report_assets/image_0.png", markdown)
        self.assertTrue((self.root / "outbox" / "report_assets" / "image_0.png").is_file())
        self.assertTrue((self.root / "processed" / "report.pdf").is_file())
        self.assertFalse((self.root / "inbox" / "report.pdf").exists())
        self.assertFalse(any(self.root.joinpath("processing").iterdir()))

    def test_literature_translation_pipeline_produces_zh_outputs(self):
        config = self.make_config("digital")
        test_model_dir = self.root / "assets" / "models" / "translation"
        test_model_dir.mkdir(parents=True, exist_ok=True)
        for req_f in ("model.bin", "source.spm", "target.spm"):
            (test_model_dir / req_f).write_text("dummy", encoding="utf-8")

        raw_config = json.loads((self.root / "config.json").read_text(encoding="utf-8"))
        raw_config["translate_literature"] = True
        raw_config["translation_model_dir"] = "assets/models/translation"
        (self.root / "config.json").write_text(json.dumps(raw_config), encoding="utf-8")
        config = Config(self.root / "config.json")

        def fake_translate(source_md, **kwargs):
            out_md = source_md.parent / f"{source_md.stem}.zh.md"
            out_html = source_md.parent / f"{source_md.stem}.zh.html"
            out_md.write_text("# 译文\n\n正文", encoding="utf-8")
            out_html.write_text("<!doctype html><html><body>译文</body></html>", encoding="utf-8")
            return out_md, out_html

        self.drop_pdf()
        with patch("src.watcher.translate_document_file", side_effect=fake_translate):
            Watcher(config, self.logger).run_once()

        self.assertTrue((self.root / "outbox" / "report.html").is_file())
        self.assertTrue((self.root / "outbox" / "report.md").is_file())
        self.assertTrue((self.root / "outbox" / "report.zh.md").is_file())
        self.assertTrue((self.root / "outbox" / "report.zh.html").is_file())
        self.assertTrue((self.root / "processed" / "report.pdf").is_file())
        self.assertFalse(any(self.root.joinpath("processing").iterdir()))

        zh_md = (self.root / "outbox" / "report.zh.md").read_text(encoding="utf-8")
        self.assertTrue(len(zh_md) > 0)
        zh_html = (self.root / "outbox" / "report.zh.html").read_text(encoding="utf-8")
        self.assertIn("<!doctype html>", zh_html)

    def test_sparse_text_falls_back_to_ocr(self):
        config = self.make_config("fallback")
        self.drop_pdf()
        Watcher(config, self.logger).run_once()
        output = (self.root / "outbox" / "report.html").read_text()
        self.assertIn("OCR", output)
        self.assertIn("data:image/png;base64,", output)
        self.assertTrue((self.root / "processed" / "report.pdf").is_file())

    def test_empty_fenced_scan_output_has_zero_text_score(self):
        empty_scan = self.root / "empty.md"
        empty_scan.write_text("```text\n\n```\n-----\n" * 513, encoding="utf-8")
        real_text = self.root / "real.md"
        real_text.write_text("```text\n真实的页面内容 123\n```", encoding="utf-8")
        self.assertEqual(0, text_score(empty_scan))
        self.assertGreater(text_score(real_text), 0)

    def test_scanned_book_uses_page_faithful_route(self):
        config = self.make_config("scan")
        config.scan_book_mode = True
        config.scan_book_min_pages = 2
        self.drop_pdf()
        watcher = Watcher(config, self.logger)

        def fake_publish(_source, output, page_count):
            self.assertEqual(3, page_count)
            output.write_text("page-faithful", encoding="utf-8")
            (self.root / "outbox" / "report.md").write_text(
                "# scan OCR", encoding="utf-8"
            )

        with patch.object(watcher, "_pdf_page_count", return_value=3), patch.object(
            watcher, "_publish_scanned", side_effect=fake_publish
        ) as publish:
            watcher.run_once()
        publish.assert_called_once()
        self.assertEqual(
            "page-faithful",
            (self.root / "outbox" / "report.html").read_text(encoding="utf-8"),
        )
        self.assertTrue((self.root / "processed" / "report.pdf").is_file())
        self.assertTrue((self.root / "outbox" / "report.md").is_file())

    def test_scan_renderer_embeds_pages_and_escapes_ocr(self):
        image = self.root / "page-1.jpg"
        image.write_bytes(b"\xff\xd8synthetic-jpeg\xff\xd9")
        output = self.root / "scan.html"
        write_scan_html(
            [image],
            ["OCR <script>alert(1)</script>"],
            output,
            title="Scan <Book>",
            source_filename="scan.pdf",
            liteparse_version="2.4.0",
            dpi=120,
            jpeg_quality=68,
        )
        rendered = output.read_text(encoding="utf-8")
        self.assertIn('id="page-0001"', rendered)
        self.assertIn("data:image/jpeg;base64,", rendered)
        self.assertIn("辅助识别文字", rendered)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertNotIn("<script", rendered)

        markdown = self.root / "scan.md"
        extract_scan_markdown_from_html(
            output,
            markdown,
            title="Scan <Book>",
            source_filename="scan.pdf",
            liteparse_version="2.4.0",
        )
        extracted = markdown.read_text(encoding="utf-8")
        self.assertIn("## 第 1 页", extracted)
        self.assertIn("OCR <script>alert(1)</script>", extracted)
        self.assertIn("原页以同名 HTML 为准", extracted)

    def test_scan_markdown_uses_a_safe_dynamic_code_fence(self):
        output = self.root / "dynamic.md"
        write_scan_markdown(
            ["正文中包含 ``` 标记"],
            output,
            title="Scanned",
            source_filename="scan.pdf",
            liteparse_version="2.4.0",
        )
        rendered = output.read_text(encoding="utf-8")
        self.assertIn("````text", rendered)
        self.assertIn("正文中包含 ``` 标记", rendered)

    def test_markdown_reflow_joins_soft_wrapped_chinese_and_english(self):
        source = (
            "中文第一行，\n下一行仍属于同一个段落。\n\n"
            "An English paragraph is\nsoft wrapped here.\n\n"
            "This sufficiently long visual line has no sentence ending and should\n\n"
            "continue across a false blank separator.\n"
        )
        rendered, stats = reflow_markdown_document(source)
        self.assertIn("中文第一行，下一行仍属于同一个段落。", rendered)
        self.assertIn("An English paragraph is soft wrapped here.", rendered)
        self.assertIn(
            "This sufficiently long visual line has no sentence ending and should continue across a false blank separator.",
            rendered,
        )
        self.assertEqual(3, stats.joined_lines)

    def test_markdown_reflow_keeps_real_blank_boundaries(self):
        source = """A complete paragraph ends here.

The Next Section

| Column | Value |

- A new list item
"""
        rendered, stats = reflow_markdown_document(source)
        self.assertEqual(source, rendered)
        self.assertEqual(0, stats.joined_lines)

    def test_markdown_reflow_keeps_uppercase_record_boundaries(self):
        source = (
            "Michel Allibert Centre national de la recherche scientifique, Paris, France\n\n"
            "Antonio Cammi Polytechnic University of Milan, Milan, Italy\n"
        )
        rendered, stats = reflow_markdown_document(source)
        self.assertEqual(source, rendered)
        self.assertEqual(0, stats.joined_lines)

    def test_markdown_reflow_does_not_attach_display_equations(self):
        source = (
            "A sufficiently long explanatory line introduces Equation 2.3:\n\n"
            "~~41~~ = production - removal\n"
        )
        rendered, stats = reflow_markdown_document(source)
        self.assertEqual(source, rendered)
        self.assertEqual(0, stats.joined_lines)

    def test_markdown_reflow_does_not_attach_a_code_fence(self):
        source = (
            "A sufficiently long paragraph line has no punctuation at its visual end\n\n"
            "```text\ncode\n```\n"
        )
        rendered, stats = reflow_markdown_document(source)
        self.assertEqual(source, rendered)
        self.assertEqual(0, stats.joined_lines)

    def test_markdown_reflow_preserves_structural_blocks(self):
        source = """# 标题

正文第一行
正文第二行

- 列表第一行
  列表续行

| 列一 | 列二 |
| --- | --- |
| A | B |

```text
代码第一行
代码第二行
```

![图](image.png)

---
"""
        rendered, stats = reflow_markdown_document(source)
        self.assertIn("正文第一行正文第二行", rendered)
        self.assertIn("- 列表第一行列表续行", rendered)
        self.assertIn("| 列一 | 列二 |\n| --- | --- |\n| A | B |", rendered)
        self.assertIn("```text\n代码第一行\n代码第二行\n```", rendered)
        self.assertIn("![图](image.png)", rendered)
        self.assertIn("\n---\n", rendered)
        self.assertEqual(2, stats.joined_lines)

    def test_ocr_reflow_preserves_blank_paragraphs_and_column_rows(self):
        source = """第一段第一行
第一段第二行

第二段第一行
第二段第二行

名称    数量    单位
"""
        rendered, stats = reflow_ocr_text(source)
        self.assertEqual(
            "第一段第一行第一段第二行\n\n第二段第一行第二段第二行\n\n名称    数量    单位",
            rendered,
        )
        self.assertEqual(2, stats.joined_lines)

    def test_ocr_reflow_repairs_a_false_blank_inside_a_paragraph(self):
        source = (
            "这是扫描版正文中足够长的一行，它在版面右侧被强制截断而且末尾没有句号\n\n"
            "下一行其实仍然属于同一个自然段。"
        )
        rendered, stats = reflow_ocr_text(source)
        self.assertNotIn("\n", rendered)
        self.assertEqual(1, stats.joined_lines)

    def test_failure_is_isolated_with_error_sidecar(self):
        config = self.make_config("fail")
        self.drop_pdf()
        Watcher(config, self.logger).run_once()
        self.assertTrue((self.root / "failed" / "report.pdf").is_file())
        error = self.root / "failed" / "report.error.txt"
        self.assertIn("synthetic failure", error.read_text(encoding="utf-8"))
        self.assertFalse((self.root / "outbox" / "report.html").exists())
        self.assertFalse((self.root / "outbox" / "report.md").exists())

    def test_failure_cleans_up_partial_files_with_special_characters_in_filename(self):
        config = self.make_config("fail")
        self.drop_pdf("report[2026].pdf")
        partial_file = self.root / "processing" / ".report[2026].noocr.md.partial"
        partial_file.write_text("temporary data", encoding="utf-8")
        partial_dir = self.root / "processing" / ".report[2026].noocr.images.partial"
        partial_dir.mkdir(parents=True, exist_ok=True)
        (partial_dir / "img1.png").write_bytes(b"dummy")

        # Unrelated partial file belonging to another stem should NOT be touched
        unrelated_partial = self.root / "processing" / ".other.noocr.md.partial"
        unrelated_partial.write_text("keep me", encoding="utf-8")

        Watcher(config, self.logger).run_once()

        self.assertTrue((self.root / "failed" / "report[2026].pdf").is_file())
        self.assertFalse(partial_file.exists())
        self.assertFalse(partial_dir.exists())
        self.assertTrue(unrelated_partial.exists())

    def test_duplicate_filename_gets_a_non_destructive_suffix(self):
        config = self.make_config("digital")
        (self.root / "processed" / "report.pdf").write_bytes(b"old")
        (self.root / "outbox" / "report.html").write_text("old", encoding="utf-8")
        self.drop_pdf()
        Watcher(config, self.logger).run_once()
        self.assertTrue((self.root / "processed" / "report-2.pdf").is_file())
        self.assertIn("DIGITAL", (self.root / "outbox" / "report-2.html").read_text())
        self.assertTrue((self.root / "outbox" / "report-2.md").is_file())

    def test_existing_markdown_also_reserves_the_stem(self):
        config = self.make_config("digital")
        (self.root / "outbox" / "report.md").write_text("old", encoding="utf-8")
        self.drop_pdf()
        Watcher(config, self.logger).run_once()
        self.assertTrue((self.root / "outbox" / "report-2.html").is_file())
        self.assertTrue((self.root / "outbox" / "report-2.md").is_file())

    def test_renderer_escapes_raw_html_and_unsafe_links(self):
        rendered = render_markdown_document(
            "# Safe\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1))",
            fallback_title="Fallback",
            source_filename="safe.pdf",
        )
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertNotIn("javascript:", rendered)

    def test_renderer_is_self_contained(self):
        rendered = render_markdown_document(
            "# Offline\n\nNo model and no external stylesheet.",
            fallback_title="Fallback",
            source_filename="offline.pdf",
        )
        self.assertIn("<style>", rendered)
        self.assertNotIn("<link ", rendered)
        self.assertNotIn("<script", rendered)

    def test_collapsed_table_is_rebuilt_from_liteparse_coordinates(self):
        markdown = """# Report

-----

| No | Title |  |  |
|---|---|---|---|
| 1 | Alpha |  |  |
| 2 | Beta |  |  |

Team Org A Org B

Owner Alice Bob
"""
        layout = {
            "pages": [
                {
                    "page": 2,
                    "width": 260,
                    "height": 100,
                    "text_items": [
                        {"text": "No", "x": 10, "y": 10, "width": 10, "height": 10},
                        {"text": "Title", "x": 60, "y": 10, "width": 20, "height": 10},
                        {"text": "Team", "x": 145, "y": 10, "width": 20, "height": 10},
                        {"text": "Owner", "x": 215, "y": 10, "width": 25, "height": 10},
                        {"text": "1", "x": 14, "y": 30, "width": 5, "height": 10},
                        {"text": "Alpha", "x": 60, "y": 30, "width": 25, "height": 10},
                        {"text": "Org A", "x": 145, "y": 30, "width": 25, "height": 10},
                        {"text": "Alice", "x": 215, "y": 30, "width": 25, "height": 10},
                        {"text": "2", "x": 14, "y": 50, "width": 5, "height": 10},
                        {"text": "Beta", "x": 60, "y": 50, "width": 20, "height": 10},
                        {"text": "Org B", "x": 145, "y": 50, "width": 25, "height": 10},
                        {"text": "Bob", "x": 215, "y": 50, "width": 15, "height": 10},
                    ],
                }
            ]
        }

        issues = find_suspicious_tables(markdown)
        self.assertEqual(1, len(issues))
        self.assertEqual(2, issues[0].page_number)

        repaired, count = repair_markdown_tables(markdown, layout)
        self.assertEqual(1, count)
        self.assertIn("| No | Title | Team | Owner |", repaired)
        self.assertIn("| 1 | Alpha | Org A | Alice |", repaired)
        self.assertIn("| 2 | Beta | Org B | Bob |", repaired)
        self.assertNotIn("Team Org A Org B", repaired)
        self.assertNotIn("Owner Alice Bob", repaired)

    def test_complete_table_does_not_trigger_coordinate_pass(self):
        markdown = """| No | Title | Team |
|---|---|---|
| 1 | Alpha | Org A |
| 2 | Beta | Org B |
"""
        self.assertEqual([], find_suspicious_tables(markdown))
        repaired, count = repair_markdown_tables(markdown, {"pages": []})
        self.assertEqual(markdown, repaired)
        self.assertEqual(0, count)

    def test_table_spacing_cleanup_preserves_mixed_language_spaces(self):
        markdown = """正文中的有限 公司保持原样。

| 标题 | 单位 |
|---|---|
| ARM 与 C86 平台 | 股份有限 公司 |
| APA 液位 | 故障保护 研究， 结论 |
"""
        normalized, count = normalize_table_cell_spacing(markdown)
        self.assertEqual(3, count)
        self.assertIn("正文中的有限 公司保持原样", normalized)
        self.assertIn("ARM 与 C86 平台", normalized)
        self.assertIn("APA 液位", normalized)
        self.assertIn("股份有限公司", normalized)
        self.assertIn("故障保护研究，结论", normalized)

    def test_dual_track_deliverables_reserve_the_stem(self):
        config = self.make_config(dual_track_mode="auto")
        watcher = Watcher(config, self.logger)
        (config.outbox / "paper-中文精译版.pdf").write_bytes(b"%PDF old")
        self.assertFalse(watcher._stem_available("paper"))
        self.assertEqual(watcher._reserve_stem("paper"), "paper-2")

    def test_same_stem_different_document_is_reprocessed_not_skipped(self):
        config = self.make_config(dual_track_mode="auto")
        watcher = Watcher(config, self.logger)
        source = config.processing / "doc.pdf"
        source.write_bytes(b"%PDF-1.4 version one")
        stale = config.outbox / "doc-中文精译版.pdf"
        stale.write_bytes(b"%PDF half delivered")
        calls = []

        def fake_route(pdf_path, outbox_dir, config=None):
            calls.append(Path(pdf_path).name)
            output = Path(outbox_dir) / "doc-中文精译版.pdf"
            output.write_bytes(b"%PDF freshly translated")
            return [output]

        with patch("src.router.route_and_process_pdf", side_effect=fake_route):
            watcher.process(source)

        self.assertEqual(calls, ["doc.pdf"])
        self.assertEqual(stale.read_bytes(), b"%PDF freshly translated")
        self.assertFalse(source.exists())
        self.assertTrue((config.processed / "doc.pdf").exists())
        self.assertTrue(watcher._manifest_path("doc").exists())

    def test_completed_manifest_skips_reprocessing(self):
        config = self.make_config(dual_track_mode="auto")
        watcher = Watcher(config, self.logger)
        source = config.processing / "done.pdf"
        source.write_bytes(b"%PDF-1.4 finished")
        watcher._write_manifest(source, [config.outbox / "done-中文精译版.pdf"])

        with patch("src.router.route_and_process_pdf") as route:
            watcher.process(source)

        route.assert_not_called()
        self.assertFalse(source.exists())
        self.assertTrue((config.processed / "done.pdf").exists())

    def test_stale_half_delivery_without_manifest_is_cleaned(self):
        config = self.make_config(dual_track_mode="auto")
        watcher = Watcher(config, self.logger)
        mono = config.outbox / "half-中文精译版.pdf"
        mono.write_bytes(b"%PDF partial")
        watcher._clear_stale_deliverables("half")
        self.assertFalse(mono.exists())


if __name__ == "__main__":
    unittest.main()
