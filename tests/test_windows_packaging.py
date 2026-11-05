"""Tests for the portable Windows application's runtime integration."""

import os
from contextlib import ExitStack
import io
import json
import re
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request
from unittest.mock import MagicMock, patch
from urllib.request import urlopen
from urllib.error import HTTPError

from src import desktop_app_windows, vector_pdf_renderer, web_app


class PortableRuntimeTests(unittest.TestCase):
    def test_workbench_script_has_valid_javascript(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed")
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", web_app.INDEX_HTML, flags=re.S)
        self.assertEqual(len(scripts), 1)
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "workbench.js"
            script.write_text(scripts[0], encoding="utf-8")
            result = subprocess.run([node, "--check", str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_packaged_fonts_are_resolved_from_bundled_directory(self):
        from src.runtime_paths import font_directory

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"JPARSE_FONT_DIR": tmp}):
                self.assertEqual(font_directory(), Path(tmp))

    def test_packaged_data_is_kept_in_configured_user_directory(self):
        with tempfile.TemporaryDirectory(prefix="jparse data ") as tmp:
            with patch.dict(os.environ, {"JPARSE_DATA_DIR": tmp}):
                self.assertEqual(web_app.get_data_root(), Path(tmp).resolve())
            self.assertFalse((Path(tmp) / "src").exists())

    def test_pdf2zh_uses_bundled_python_when_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            python = Path(tmp) / "python.exe"
            python.touch()
            with patch.dict(os.environ, {"JPARSE_BUNDLED_PYTHON": str(python), "JPARSE_LAYOUT_MODEL": ""}):
                command = vector_pdf_renderer.get_pdf2zh_command()
            self.assertEqual(command, [str(python), "-X", "utf8", "-m", "pdf2zh.pdf2zh"])

    def test_missing_bundled_python_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            python = Path(tmp) / "missing.exe"
            with patch.dict(os.environ, {"JPARSE_BUNDLED_PYTHON": str(python)}):
                with self.assertRaises(FileNotFoundError):
                    vector_pdf_renderer.get_pdf2zh_command()

    def test_bundled_layout_model_is_passed_to_pdf2zh(self):
        with tempfile.TemporaryDirectory() as tmp:
            python = Path(tmp) / "python.exe"
            model = Path(tmp) / "layout.onnx"
            python.touch()
            model.touch()
            with patch.dict(os.environ, {"JPARSE_BUNDLED_PYTHON": str(python),
                                         "JPARSE_LAYOUT_MODEL": str(model)}):
                command = vector_pdf_renderer.get_pdf2zh_command()
            self.assertEqual(command[-2:], ["--onnx", str(model)])

    def test_bitmap_ocr_uses_bundled_python(self):
        from src.bitmap_figure_translator import locate_paddleocr_python

        with tempfile.TemporaryDirectory() as tmp:
            python = Path(tmp) / "python.exe"
            python.touch()
            with patch.dict(os.environ, {"JPARSE_PADDLE_PYTHON": str(python)}):
                self.assertEqual(locate_paddleocr_python(), python)

    def test_server_start_failure_does_not_open_browser(self):
        with patch.object(desktop_app_windows, "is_backend_alive", return_value=False), \
             patch.object(desktop_app_windows, "start_backend_server", side_effect=RuntimeError("failed")), \
             patch.object(desktop_app_windows, "launch_desktop_window") as launch, \
             patch.object(desktop_app_windows.sys, "argv", ["JParse"]):
            with self.assertRaises(RuntimeError):
                desktop_app_windows.main()
            launch.assert_not_called()

    def test_pdf2zh_cannot_delete_the_original_input(self):
        # pdf2zh removes inputs under the OS temporary directory after reading
        # them; make the fake engine behave the same way.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.pdf"
            source.write_bytes(b"original pdf bytes")
            engine = root / "engine.py"
            engine.write_text(
                "import sys\nfrom pathlib import Path\n"
                "p=Path(sys.argv[1]); p.unlink()\n"
                "out=Path(sys.argv[sys.argv.index('-o')+1])\n"
                "(out/'input-mono.pdf').write_bytes(b'converted')\n",
                encoding="utf-8",
            )
            with ExitStack() as stack:
                stack.enter_context(patch.object(vector_pdf_renderer, "get_pdf2zh_command", return_value=[sys.executable, str(engine)]))
                stack.enter_context(patch("src.pdf2zh_patch.ensure_pdf2zh_environment_ready"))
                for target in ("src.table_overlay.apply_table_translations", "src.figure_overlay.apply_figure_translations",
                               "src.bitmap_figure_translator.apply_bitmap_figure_translations",
                               "src.pdf_cleanup.remove_orphan_underlines", "src.text_layout_repair.repair_merged_list_layout"):
                    stack.enter_context(patch(target, return_value=0))
                output = vector_pdf_renderer.process_vector_pdf_with_pdf2zh(source, root / "outbox")
            self.assertEqual(source.read_bytes(), b"original pdf bytes")
            self.assertEqual(output[0].read_bytes(), b"converted")

    def test_backend_early_exit_is_reported(self):
        process = MagicMock(pid=123)
        process.poll.return_value = 1
        with patch.object(desktop_app_windows.subprocess, "Popen", return_value=process), \
             patch.object(desktop_app_windows, "is_backend_alive", return_value=False):
            with self.assertRaises(RuntimeError):
                desktop_app_windows.start_backend_server()

    def test_http_requests_work_without_a_console_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = web_app.ConversionTaskManager(Path(tmp))
            previous = web_app.LiteParseAppHandler.task_manager
            web_app.LiteParseAppHandler.task_manager = manager
            server = web_app.ThreadingHTTPServer(("127.0.0.1", 0), web_app.LiteParseAppHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch.object(sys, "stderr", None):
                    with urlopen("http://127.0.0.1:%d/api/tasks" % server.server_port, timeout=3) as response:
                        self.assertEqual(response.status, 200)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
                web_app.LiteParseAppHandler.task_manager = previous

    def test_local_health_check_ignores_system_http_proxy(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = web_app.ConversionTaskManager(Path(tmp))
            previous = web_app.LiteParseAppHandler.task_manager
            web_app.LiteParseAppHandler.task_manager = manager
            server = web_app.ThreadingHTTPServer(("127.0.0.1", 0), web_app.LiteParseAppHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:9", "no_proxy": ""}), \
                     patch.object(urllib.request, "proxy_bypass", return_value=False), \
                     patch.object(urllib.request, "_opener", None):
                    self.assertTrue(desktop_app_windows.is_backend_alive(server.server_port, timeout=1))
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
                web_app.LiteParseAppHandler.task_manager = previous

    def test_packaged_runtime_uses_version_and_data_specific_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"JPARSE_RUNTIME_ID": "a" * 64, "JPARSE_DATA_DIR": tmp}):
                first = desktop_app_windows.default_port()
            with patch.dict(os.environ, {"JPARSE_RUNTIME_ID": "b" * 64, "JPARSE_DATA_DIR": tmp}):
                second = desktop_app_windows.default_port()
            self.assertNotEqual(first, second)
            self.assertTrue(20000 <= first < 60000)

    def test_packaged_runtime_refuses_a_different_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            class FakeBackend(BaseHTTPRequestHandler):
                def do_GET(self):
                    body = json.dumps({"runtime_id": "old", "data_dir": tmp}).encode("utf-8")
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *args):
                    pass

            server = web_app.ThreadingHTTPServer(("127.0.0.1", 0), FakeBackend)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch.dict(os.environ, {"JPARSE_RUNTIME_ID": "new", "JPARSE_DATA_DIR": tmp}):
                    self.assertFalse(desktop_app_windows.is_backend_alive(server.server_port))
                with patch.dict(os.environ, {"JPARSE_RUNTIME_ID": "old", "JPARSE_DATA_DIR": tmp}):
                    self.assertTrue(desktop_app_windows.is_backend_alive(server.server_port))
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_packaged_launch_skips_an_occupied_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"JPARSE_RUNTIME_ID": "c" * 64, "JPARSE_DATA_DIR": tmp}), \
                 patch.object(desktop_app_windows.sys, "argv", ["JParse"]), \
                 patch.object(desktop_app_windows, "is_backend_alive", return_value=False), \
                 patch.object(desktop_app_windows, "port_available", side_effect=[False, True]), \
                 patch.object(desktop_app_windows, "start_backend_server") as start, \
                 patch.object(desktop_app_windows, "launch_desktop_window") as launch:
                base = desktop_app_windows.default_port()
                desktop_app_windows.main()
                expected = 20000 + ((base - 20000 + 1) % 40000)
                start.assert_called_once_with(expected)
                launch.assert_called_once_with(expected)

    def test_failed_new_launch_leaves_previous_runtime_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / ".active-runtime"
            marker.write_text("old", encoding="utf-8")
            with patch.dict(os.environ, {"JPARSE_RUNTIME_ID": "new", "JPARSE_DATA_DIR": tmp}), \
                 patch.object(desktop_app_windows.sys, "argv", ["JParse"]), \
                 patch.object(desktop_app_windows, "is_backend_alive", return_value=False), \
                 patch.object(desktop_app_windows, "port_available", return_value=True), \
                 patch.object(desktop_app_windows, "start_backend_server", side_effect=RuntimeError("failed")):
                with self.assertRaises(RuntimeError):
                    desktop_app_windows.main()
            self.assertEqual(marker.read_text(encoding="utf-8"), "old")

    def test_packaged_launch_reuses_saved_port_after_collision_clears(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = "d" * 64
            saved = 25123
            (Path(tmp) / (".port-" + runtime)).write_text(str(saved), encoding="utf-8")
            with patch.dict(os.environ, {"JPARSE_RUNTIME_ID": runtime, "JPARSE_DATA_DIR": tmp}), \
                 patch.object(desktop_app_windows.sys, "argv", ["JParse"]), \
                 patch.object(desktop_app_windows, "is_backend_alive", side_effect=lambda port: port == saved), \
                 patch.object(desktop_app_windows, "port_available", return_value=True), \
                 patch.object(desktop_app_windows, "start_backend_server") as start, \
                 patch.object(desktop_app_windows, "launch_desktop_window") as launch:
                desktop_app_windows.main()
                start.assert_not_called()
                launch.assert_called_once_with(saved)

    def test_inbox_file_is_claimed_only_after_it_stabilizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = web_app.ConversionTaskManager(Path(tmp))
            source = manager.inbox_dir / "paper.pdf"
            source.write_bytes(b"sample pdf")
            with patch.object(manager, "add_file") as add_file:
                manager.scan_inbox_once(now=100.0, settle_seconds=5)
                self.assertTrue(source.is_file())
                manager.scan_inbox_once(now=106.0, settle_seconds=5)
                self.assertFalse(source.exists())
                claimed = add_file.call_args.args[0]
                self.assertEqual(claimed.parent, manager.processing_dir)
                self.assertEqual(claimed.read_bytes(), b"sample pdf")
                manager.release_reservation(claimed.stem)

    def test_interrupted_processing_is_retained_without_stealing_live_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original_manager = web_app.ConversionTaskManager(root)
            stem = original_manager.reserve_stem("paper")
            claimed = original_manager.processing_dir / (stem + ".pdf")
            claimed.write_bytes(b"original pdf")
            restarted = web_app.ConversionTaskManager(root)
            restarted.recover_interrupted()
            self.assertTrue(claimed.exists())  # A live owner still holds the lock.
            original_manager.release_reservation(stem)
            restarted.recover_interrupted()
            self.assertFalse(claimed.exists())
            self.assertEqual((restarted.failed_dir / "paper.pdf").read_bytes(), b"original pdf")
            self.assertTrue((restarted.failed_dir / "paper.error.txt").is_file())

    def test_invalid_config_does_not_strand_inbox_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = web_app.ConversionTaskManager(Path(tmp))
            source = manager.inbox_dir / "paper.pdf"
            source.write_bytes(b"sample pdf")
            (Path(tmp) / "config.json").write_text("{invalid", encoding="utf-8")
            manager.scan_inbox_once(now=100.0, settle_seconds=5)
            with self.assertRaises(RuntimeError):
                manager.scan_inbox_once(now=106.0, settle_seconds=5)
            self.assertTrue(source.is_file())
            self.assertFalse(list(manager.processing_dir.iterdir()))

    def test_service_selection_updates_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.json").write_text('{"pdf2zh_service":"bing","keep":7}', encoding="utf-8")
            manager = web_app.ConversionTaskManager(root)
            manager.set_translation_service("google")
            self.assertEqual(manager.configured_service(), "google")
            self.assertEqual(json.loads((root / "config.json").read_text(encoding="utf-8"))["keep"], 7)
            with self.assertRaises(ValueError):
                manager.set_translation_service([])

    def test_stale_upload_service_cannot_change_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.json").write_text('{"pdf2zh_service":"bing"}', encoding="utf-8")
            manager = web_app.ConversionTaskManager(root)
            previous = web_app.LiteParseAppHandler.task_manager
            web_app.LiteParseAppHandler.task_manager = manager
            server = web_app.ThreadingHTTPServer(("127.0.0.1", 0), web_app.LiteParseAppHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            boundary = "ServiceSwitchBoundary"
            body = (
                f'--{boundary}\r\nContent-Disposition: form-data; name="service"\r\n\r\ngoogle\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="paper.pdf"\r\n'
                f'Content-Type: application/pdf\r\n\r\n%PDF-1.4 test\r\n--{boundary}--\r\n'
            ).encode("ascii")
            try:
                request = urllib.request.Request(
                    "http://127.0.0.1:%d/api/upload" % server.server_port, data=body,
                    headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
                )
                with patch.object(manager, "add_file", return_value={"id": "test"}):
                    with self.assertRaises(HTTPError) as failure:
                        urlopen(request, timeout=3)
                self.assertEqual(failure.exception.code, 409)
                self.assertEqual(manager.configured_service(), "bing")
            finally:
                manager.release_reservation("paper")
                server.shutdown()
                server.server_close()
                thread.join()
                web_app.LiteParseAppHandler.task_manager = previous

    def test_inbox_watcher_ignores_symbolic_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = web_app.ConversionTaskManager(root / "data")
            outside = root / "outside.pdf"
            outside.write_bytes(b"external pdf")
            link = manager.inbox_dir / "link.pdf"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("This system cannot create symlinks")
            with patch.object(manager, "add_file") as add_file:
                manager.scan_inbox_once(now=100.0, settle_seconds=5)
                manager.scan_inbox_once(now=106.0, settle_seconds=5)
                add_file.assert_not_called()
            self.assertEqual(outside.read_bytes(), b"external pdf")

    def test_image_only_scan_is_not_reported_as_success(self):
        import fitz
        from PIL import Image
        from src.hd_scan_renderer import ensure_scanned_pages_have_text
        from src.opendataloader_extractor import ExtractedDocument, ExtractedPage

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "scan.pdf"
            image = io.BytesIO()
            Image.new("RGB", (100, 100), "white").save(image, format="PNG")
            pdf = fitz.open()
            page = pdf.new_page()
            page.insert_image(page.rect, stream=image.getvalue())
            pdf.save(source)
            pdf.close()
            extracted = ExtractedDocument(source, 1, pages=[ExtractedPage(1, 595, 842)])
            with self.assertRaisesRegex(RuntimeError, "扫描.*文字"):
                ensure_scanned_pages_have_text(source, extracted)

    def test_scan_with_only_page_number_is_not_treated_as_ocr(self):
        import fitz
        from PIL import Image
        from src.hd_scan_renderer import ensure_scanned_pages_have_text
        from src.opendataloader_extractor import ExtractedDocument, ExtractedElement, ExtractedPage

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "scan.pdf"
            image = io.BytesIO()
            Image.new("RGB", (100, 100), "white").save(image, format="PNG")
            pdf = fitz.open()
            page = pdf.new_page()
            page.insert_image(page.rect, stream=image.getvalue())
            page.insert_text((50, 50), "1")
            pdf.save(source)
            pdf.close()
            element = ExtractedElement("heading", 1, 1, "H1", [0, 0, 10, 10],
                                       0, 0, 10, 10, "1", "Helvetica", 10)
            extracted = ExtractedDocument(source, 1, pages=[ExtractedPage(1, 595, 842, elements=[element])])
            with self.assertRaisesRegex(RuntimeError, "扫描.*文字"):
                ensure_scanned_pages_have_text(source, extracted)

    def test_scan_with_inline_image_is_not_treated_as_blank(self):
        import fitz
        from src.hd_scan_renderer import ensure_scanned_pages_have_text
        from src.opendataloader_extractor import ExtractedDocument, ExtractedPage

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "inline.pdf"
            pdf = fitz.open()
            page = pdf.new_page(width=200, height=200)
            xref = pdf.get_new_xref()
            pdf.update_object(xref, "<<>>")
            pdf.update_stream(xref, b"q 200 0 0 200 0 0 cm BI /W 1 /H 1 /CS /RGB /BPC 8 ID \xff\xff\xff EI Q", compress=0)
            page.set_contents(xref)
            pdf.save(source)
            pdf.close()
            extracted = ExtractedDocument(source, 1, pages=[ExtractedPage(1, 200, 200)])
            with self.assertRaisesRegex(RuntimeError, "扫描.*文字"):
                ensure_scanned_pages_have_text(source, extracted)

    def test_inline_scan_with_long_watermark_is_routed_as_scan(self):
        import fitz
        from src.router import probe_pdf_document_type

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "inline.pdf"
            pdf = fitz.open()
            page = pdf.new_page(width=595, height=842)
            xref = pdf.get_new_xref()
            pdf.update_object(xref, "<<>>")
            pdf.update_stream(xref, b"q 595 0 0 842 0 0 cm BI /W 1 /H 1 /CS /RGB /BPC 8 ID \xff\xff\xff EI Q", compress=0)
            page.set_contents(xref)
            page.insert_text((30, 820), "Copyright applies to this publication. Downloaded from the public library. All rights reserved.", fontsize=8)
            pdf.save(source)
            pdf.close()
            self.assertEqual(probe_pdf_document_type(source), "scanned")

    def test_scan_with_long_footer_is_not_treated_as_body_ocr(self):
        import fitz
        from PIL import Image
        from src.hd_scan_renderer import ensure_scanned_pages_have_text
        from src.opendataloader_extractor import ExtractedDocument, ExtractedElement, ExtractedPage

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "scan.pdf"
            image = io.BytesIO()
            Image.new("RGB", (100, 100), "white").save(image, format="PNG")
            pdf = fitz.open()
            page = pdf.new_page()
            page.insert_image(page.rect, stream=image.getvalue())
            footer = "Downloaded from the library. Copyright applies. All rights reserved. " * 2
            page.insert_text((30, 820), footer, fontsize=5)
            pdf.save(source)
            pdf.close()
            element = ExtractedElement("paragraph", 1, 1, "P", [30, 810, 560, 820],
                                       30, 810, 530, 10, footer, "Helvetica", 5)
            extracted = ExtractedDocument(source, 1, pages=[ExtractedPage(1, 595, 842, elements=[element])])
            with self.assertRaisesRegex(RuntimeError, "扫描.*文字"):
                ensure_scanned_pages_have_text(source, extracted)

    def test_scan_with_margins_and_page_number_is_rejected(self):
        import fitz
        from PIL import Image
        from src.hd_scan_renderer import ensure_scanned_pages_have_text
        from src.opendataloader_extractor import ExtractedDocument, ExtractedElement, ExtractedPage

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "scan.pdf"
            image = io.BytesIO()
            Image.new("RGB", (100, 100), "white").save(image, format="PNG")
            pdf = fitz.open()
            page = pdf.new_page(width=200, height=200)
            page.insert_image(fitz.Rect(16, 16, 184, 184), stream=image.getvalue())
            page.insert_text((100, 195), "1")
            pdf.save(source)
            pdf.close()
            element = ExtractedElement("heading", 1, 1, "H1", [98, 185, 105, 195],
                                       98, 185, 7, 10, "1", "Helvetica", 10)
            extracted = ExtractedDocument(source, 1, pages=[ExtractedPage(1, 200, 200, elements=[element])])
            with self.assertRaisesRegex(RuntimeError, "扫描.*文字"):
                ensure_scanned_pages_have_text(source, extracted)

    def test_scan_google_translation_uses_selected_service(self):
        from src.hd_scan_renderer import ScannedPDFTranslator

        translator = ScannedPDFTranslator(service="google")
        online = MagicMock()
        online.translate.return_value = "冷却系统"
        with patch.object(translator, "_get_online_translator", return_value=online):
            self.assertIn("冷却", translator.translate_single("cooling system"))
        online.translate.assert_called_once()

    def test_scan_translation_service_failure_is_not_silent(self):
        from src.hd_scan_renderer import ScannedPDFTranslator

        translator = ScannedPDFTranslator(service="bing")
        online = MagicMock()
        online.translate.side_effect = OSError("service unavailable")
        with patch.object(translator, "_get_online_translator", return_value=online):
            with self.assertRaisesRegex(RuntimeError, "翻译"):
                translator.translate_single("ordinary reactor text")


if __name__ == "__main__":
    unittest.main()
