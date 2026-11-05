"""Tests for the portable Windows application's runtime integration."""

import os
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
from urllib.request import urlopen

from src import desktop_app_windows, vector_pdf_renderer, web_app


class PortableRuntimeTests(unittest.TestCase):
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
            with patch.dict(os.environ, {"JPARSE_BUNDLED_PYTHON": str(python)}):
                command = vector_pdf_renderer.get_pdf2zh_command()
            self.assertEqual(command, [str(python), "-m", "pdf2zh.pdf2zh"])

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


if __name__ == "__main__":
    unittest.main()
