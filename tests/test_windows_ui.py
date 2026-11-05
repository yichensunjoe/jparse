"""User-visible Windows workbench contract and isolation from the legacy UI."""

from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from src.web_app import ConversionTaskManager, LiteParseAppHandler, ThreadingHTTPServer
from src.windows_folder_picker import _CANCELLED, choose_output_folder


class _ExternalScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            source = dict(attrs).get("src")
            if source:
                self.sources.append(source)


class WindowsWorkbenchTests(unittest.TestCase):
    def test_reserved_upload_keeps_folder_used_for_collision_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = ConversionTaskManager(root)
            original_output = manager.outbox_dir
            new_output = root / "new-output"
            new_output.mkdir()
            existing = new_output / "paper-中文精译版.pdf"
            existing.write_bytes(b"old result")
            stem = manager.reserve_stem("paper")
            manager.set_outbox_dir(str(new_output))
            source = manager.processing_dir / (stem + ".pdf")
            source.write_bytes(b"%PDF-1.4 test")
            def convert(pdf_path, outbox_dir, config):
                result = outbox_dir / (pdf_path.stem + "-中文精译版.pdf")
                result.write_bytes(b"new result")
                return [result]
            with patch("src.web_app.probe_pdf_document_type", return_value="vector"), \
                 patch("src.web_app.route_and_process_pdf", side_effect=convert):
                task = manager.add_file(source, "paper.pdf")
                for _ in range(150):
                    result = next(item for item in manager.get_tasks() if item["id"] == task["id"])
                    if result["status"] in {"completed", "failed"}:
                        break
                    time.sleep(0.02)
            manager._executor.shutdown(wait=True)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(existing.read_bytes(), b"old result")
            self.assertEqual((original_output / "paper-中文精译版.pdf").read_bytes(), b"new result")

    def test_output_folder_cannot_be_inbox_or_inside_it(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = ConversionTaskManager(Path(directory))
            for bad in (manager.inbox_dir, manager.inbox_dir / "results"):
                with self.subTest(path=bad), self.assertRaises(ValueError):
                    manager.set_outbox_dir(str(bad), persist=True)
            self.assertEqual(manager.outbox_dir, manager.default_outbox_dir)

    def test_queued_task_keeps_its_output_folder_and_old_result_remains_accessible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = ConversionTaskManager(root)
            previous = LiteParseAppHandler.task_manager
            LiteParseAppHandler.task_manager = manager
            server = ThreadingHTTPServer(("127.0.0.1", 0), LiteParseAppHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            entered, proceed = threading.Event(), threading.Event()
            source = manager.processing_dir / "paper.pdf"
            source.write_bytes(b"%PDF-1.4 test")
            old_output = manager.outbox_dir
            def probe(_):
                entered.set()
                self.assertTrue(proceed.wait(3))
                return "vector"
            def convert(pdf_path, outbox_dir, config):
                result = outbox_dir / "result.pdf"
                result.write_bytes(b"%PDF-1.4 result")
                return [result]
            try:
                with patch("src.web_app.probe_pdf_document_type", side_effect=probe), \
                     patch("src.web_app.route_and_process_pdf", side_effect=convert):
                    task = manager.add_file(source, "paper.pdf")
                    self.assertTrue(entered.wait(3))
                    manager.set_outbox_dir(str(root / "new-output"))
                    proceed.set()
                    for _ in range(150):
                        result = next(item for item in manager.get_tasks() if item["id"] == task["id"])
                        if result["status"] in {"completed", "failed"}:
                            break
                        time.sleep(0.02)
                self.assertEqual(result["status"], "completed")
                artifact = old_output / "result.pdf"
                self.assertTrue(artifact.is_file())
                base = "http://127.0.0.1:%d" % server.server_port
                encoded = quote(str(artifact), safe="")
                with urlopen(base + "/api/download?path=" + encoded, timeout=3) as response:
                    self.assertEqual(response.read(), b"%PDF-1.4 result")
                with patch("src.web_app.reveal_in_finder", return_value=True) as reveal:
                    with urlopen(Request(base + "/api/reveal_output?path=" + encoded, data=b"", method="POST"), timeout=3) as response:
                        self.assertTrue(json.load(response)["revealed"])
                    reveal.assert_called_once_with(old_output)
                secret = old_output / "unrelated.txt"
                secret.write_text("private", encoding="utf-8")
                with self.assertRaises(HTTPError) as denied:
                    urlopen(base + "/api/download?path=" + quote(str(secret), safe=""), timeout=3)
                self.assertEqual(denied.exception.code, 403)
                artifact.unlink()
                try:
                    artifact.symlink_to(secret)
                except OSError:  # Creating symlinks can require extra privileges on Windows.
                    pass
                else:
                    with self.assertRaises(HTTPError) as denied:
                        urlopen(base + "/api/download?path=" + encoded, timeout=3)
                    self.assertEqual(denied.exception.code, 403)
            finally:
                proceed.set()
                server.shutdown()
                server.server_close()
                thread.join()
                LiteParseAppHandler.task_manager = previous

    @unittest.skipUnless(sys.platform == "win32", "Windows COM picker")
    def test_native_picker_initializes_and_cleans_up_when_cancelled(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("src.windows_folder_picker._show_dialog", return_value=_CANCELLED):
                self.assertIsNone(choose_output_folder(Path(directory)))

    @unittest.skipUnless(sys.platform == "win32" and os.environ.get("JPARSE_BUILT_EXE"), "Windows packaged CI only")
    def test_native_picker_returns_selected_folder_on_interactive_desktop(self):
        import ctypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_size_t, ctypes.c_ssize_t]
        user32.PostMessageW.restype = ctypes.c_int
        code = ("import json,sys; sys.path.insert(0,sys.argv[1]); "
                "from src.windows_folder_picker import choose_output_folder; "
                "print(json.dumps(str(choose_output_folder(sys.argv[2]))), flush=True)")
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.Popen([sys.executable, "-c", code, str(Path(__file__).resolve().parent.parent), directory],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
            try:
                deadline = time.monotonic() + 15
                window = None
                while time.monotonic() < deadline:
                    window = user32.FindWindowW(None, "选择成果文件夹")
                    if window or process.poll() is not None:
                        break
                    time.sleep(0.1)
                if not window:
                    if process.poll() is not None:
                        stdout, stderr = process.communicate()
                        self.fail("Folder picker exited before appearing: %s %s" % (stdout, stderr))
                    self.skipTest("No interactive Windows desktop available to the CI runner")
                self.assertTrue(user32.PostMessageW(window, 0x0111, 1, 0))  # WM_COMMAND / IDOK.
                stdout, stderr = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertEqual(Path(json.loads(stdout)).resolve(), Path(directory).resolve())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_native_output_picker_saves_selection_and_cancel_keeps_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.json").write_text('{"pdf2zh_service":"bing"}', encoding="utf-8")
            with patch.dict(os.environ, {"JPARSE_UI_STYLE": "windows"}):
                manager = ConversionTaskManager(root)
                previous = LiteParseAppHandler.task_manager
                LiteParseAppHandler.task_manager = manager
                server = ThreadingHTTPServer(("127.0.0.1", 0), LiteParseAppHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                endpoint = "http://127.0.0.1:%d/api/choose_outbox" % server.server_port
                chosen = root / "chosen-output"
                try:
                    with patch("src.web_app.choose_output_folder", return_value=chosen):
                        with urlopen(Request(endpoint, data=b"", method="POST"), timeout=3) as response:
                            result = json.load(response)
                    self.assertTrue(result["selected"])
                    self.assertEqual(manager.outbox_dir, chosen.resolve())
                    with patch("src.web_app.choose_output_folder", return_value=None):
                        with urlopen(Request(endpoint, data=b"", method="POST"), timeout=3) as response:
                            self.assertFalse(json.load(response)["selected"])
                    self.assertEqual(ConversionTaskManager(root).outbox_dir, chosen.resolve())
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()
                    LiteParseAppHandler.task_manager = previous

    def test_windows_preferences_survive_backend_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.json").write_text('{"pdf2zh_service":"bing"}', encoding="utf-8")
            with patch.dict(os.environ, {"JPARSE_UI_STYLE": "windows"}):
                first = ConversionTaskManager(root)
                output = root / "chosen-output"
                first.set_outbox_dir(str(output), persist=True)
                first.set_windows_appearance("forest", "mist")
                second = ConversionTaskManager(root)
                self.assertEqual(second.outbox_dir, output.resolve())
                self.assertEqual(second.windows_appearance(), {"accent": "forest", "canvas": "mist"})
                config = json.loads((root / "config.json").read_text(encoding="utf-8"))
                self.assertEqual(config["pdf2zh_service"], "bing")

    def test_unavailable_saved_output_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad = root / "not-a-folder"
            bad.write_text("file", encoding="utf-8")
            (root / "config.json").write_text(json.dumps({"pdf2zh_service":"bing", "windows_studio_outbox":str(bad)}), encoding="utf-8")
            with patch.dict(os.environ, {"JPARSE_UI_STYLE": "windows"}):
                manager = ConversionTaskManager(root)
            self.assertTrue(manager.output_settings_error)
            self.assertIn("输出", manager.output_settings_error)
            source = manager.processing_dir / "paper.pdf"
            source.write_bytes(b"%PDF-1.4 test")
            with patch("src.web_app.probe_pdf_document_type") as probe:
                task = manager.add_file(source, "paper.pdf")
                for _ in range(100):
                    result = next(item for item in manager.get_tasks() if item["id"] == task["id"])
                    if result["status"] in {"completed", "failed"}:
                        break
                    time.sleep(0.02)
                self.assertEqual(result["status"], "failed")
                self.assertTrue((manager.failed_dir / "paper.pdf").is_file())
                probe.assert_not_called()

    def test_windows_workbench_has_mac_style_actions_and_local_script(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = LiteParseAppHandler.task_manager
            LiteParseAppHandler.task_manager = ConversionTaskManager(Path(directory))
            server = ThreadingHTTPServer(("127.0.0.1", 0), LiteParseAppHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch.dict(os.environ, {"JPARSE_UI_STYLE": "windows"}):
                    with urlopen("http://127.0.0.1:%d/" % server.server_port, timeout=3) as response:
                        html = response.read().decode("utf-8")
                        csp = response.headers["Content-Security-Policy"]
                for label in ("JParse", "Studio", "添加文献，开始处理", "选取文献", "导入目录", "设置"):
                    self.assertIn(label, html, "Missing expected label: " + label)
                self.assertNotIn("双轨智能版面路由器", html, "Legacy Windows layout is still shown")
                self.assertIn("script-src 'nonce-", csp)
                self.assertNotIn("__CSP_NONCE__", html)
                parser = _ExternalScripts()
                parser.feed(html)
                self.assertEqual(parser.sources, [])
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
                LiteParseAppHandler.task_manager = previous


if __name__ == "__main__":
    unittest.main()
