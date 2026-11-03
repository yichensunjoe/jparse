"""Unit tests for LiteParse Interactive Web Application."""

import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from unittest.mock import patch

from src.web_app import (
    ConversionTaskManager,
    LiteParseAppHandler,
    ThreadingHTTPServer,
    reveal_in_finder,
)


class TestLiteParseWebApp(unittest.TestCase):
    """Test web application server and task manager."""

    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.project_root = Path(cls.tmp_dir.name)
        cls.task_mgr = ConversionTaskManager(project_root=cls.project_root)
        LiteParseAppHandler.task_manager = cls.task_mgr

        # Bind to ephemeral port
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), LiteParseAppHandler)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.tmp_dir.cleanup()

    def test_get_index_html(self):
        req = Request(f"{self.base_url}/")
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
            self.assertIn("LiteParse 交互式工作台", body)
            self.assertIn("webkitdirectory", body)
            self.assertIn("拖入单个 PDF", body)

    def test_get_tasks_empty(self):
        req = Request(f"{self.base_url}/api/tasks")
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIsInstance(data, list)

    def test_get_settings_reports_default_outbox(self):
        with urlopen(Request(f"{self.base_url}/api/settings")) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(Path(data["outbox_dir"]), self.task_mgr.default_outbox_dir.resolve())
        self.assertEqual(Path(data["default_outbox_dir"]), self.task_mgr.default_outbox_dir.resolve())

    def test_post_settings_switches_outbox_and_download_scope(self):
        custom = self.project_root / "custom-output"
        self.addCleanup(
            self.task_mgr.set_outbox_dir,
            str(self.task_mgr.default_outbox_dir),
        )

        body = json.dumps({"outbox_dir": str(custom)}).encode("utf-8")
        req = Request(
            f"{self.base_url}/api/settings",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))

        self.assertTrue(data["ok"])
        self.assertEqual(Path(data["outbox_dir"]), custom.resolve())
        self.assertTrue(custom.is_dir())

        artifact = custom / "switched.html"
        artifact.write_text("<p>switched</p>", encoding="utf-8")
        with urlopen(Request(f"{self.base_url}/api/download?path={artifact}")) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.read().decode("utf-8"), "<p>switched</p>")

    def test_post_settings_rejects_file_path(self):
        not_a_dir = self.project_root / "not-a-directory.txt"
        not_a_dir.write_text("file", encoding="utf-8")
        body = json.dumps({"outbox_dir": str(not_a_dir)}).encode("utf-8")
        req = Request(
            f"{self.base_url}/api/settings",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req)
        self.assertEqual(ctx.exception.code, 400)
        self.assertEqual(self.task_mgr.outbox_dir, self.task_mgr.default_outbox_dir.resolve())

    def test_upload_file_multipart(self):
        boundary = "----WebKitFormBoundaryLiteParseTest"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="relativePath"\r\n\r\n'
            f"papers/subfolder/test_upload.pdf\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="pipelineMode"\r\n\r\n'
            f"auto\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="service"\r\n\r\n'
            f"bing\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="test_upload.pdf"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
            f"%PDF-1.4 mock content\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")

        req = Request(
            f"{self.base_url}/api/upload",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res_data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res_data.get("ok"))
            task = res_data.get("task")
            self.assertEqual(task["filename"], "test_upload.pdf")
            self.assertEqual(task["relative_path"], "papers/subfolder/test_upload.pdf")

    def test_upload_boundary_with_parameters_and_quotes(self):
        raw_boundary = "WebKitFormBoundaryQuotes123"
        body = (
            f"--{raw_boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="quoted.pdf"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
            f"%PDF-1.4 sample\r\n"
            f"--{raw_boundary}--\r\n"
        ).encode("utf-8")

        req = Request(
            f"{self.base_url}/api/upload",
            data=body,
            headers={"Content-Type": f'multipart/form-data; boundary="{raw_boundary}"; charset=utf-8'},
            method="POST",
        )
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("ok"))
            self.assertEqual(data["task"]["filename"], "quoted.pdf")

    def test_upload_duplicate_disambiguation(self):
        boundary = "BoundaryDupeTest"
        for i in range(2):
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="relativePath"\r\n\r\n'
                f"folder{i+1}/common.pdf\r\n"
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="common.pdf"\r\n'
                f"Content-Type: application/pdf\r\n\r\n"
                f"%PDF-1.4 mock content {i}\r\n"
                f"--{boundary}--\r\n"
            ).encode("utf-8")
            req = Request(
                f"{self.base_url}/api/upload",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            with urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                if i == 0:
                    self.assertEqual(data["task"]["filename"], "common.pdf")
                else:
                    # 重名不再下划线递增，而是与 watcher 一致的 -2 发号
                    self.assertEqual(data["task"]["filename"], "common-2.pdf")

    def test_upload_reject_non_pdf(self):
        boundary = "BoundaryTextTest"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="notes.txt"\r\n'
            f"Content-Type: text/plain\r\n\r\n"
            f"Hello World\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        req = Request(
            f"{self.base_url}/api/upload",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

    def test_upload_binary_trailing_bytes_preserved(self):
        boundary = "BoundaryBinaryTest"
        # Content ending with 3 trailing newlines/returns which must not be lost
        payload = b"%PDF-1.4 binary data\x00\xff\r\n\r\n"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="binary_exact.pdf"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
        ).encode("utf-8") + payload + f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = Request(
            f"{self.base_url}/api/upload",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            task = json.loads(resp.read().decode("utf-8"))["task"]

        finished = self._wait_status(task["id"])
        name = Path(finished["input_path"]).name
        candidates = [self.task_mgr.failed_dir / name, self.task_mgr.processed_dir / name]
        saved = next((path for path in candidates if path.exists()), None)
        self.assertIsNotNone(saved, "上传的字节应当在 failed/ 或 processed/ 中原样归档")
        self.assertEqual(saved.read_bytes(), payload)

    def _wait_status(self, task_id, timeout=15.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for task in self.task_mgr.get_tasks():
                if task["id"] == task_id and task["status"] in ("completed", "failed"):
                    return task
            time.sleep(0.05)
        self.fail("任务 %s 未在 %.0f 秒内结束" % (task_id, timeout))

    def test_index_sends_csp_nonce_without_inline_handlers(self):
        req = Request(f"{self.base_url}/")
        with urlopen(req) as resp:
            csp = resp.headers.get("Content-Security-Policy", "")
            body = resp.read().decode("utf-8")
        self.assertIn("script-src 'nonce-", csp)
        self.assertIn("default-src 'none'", csp)
        self.assertNotIn("__CSP_NONCE__", body)
        self.assertNotIn("onclick=", body)
        nonce = csp.split("script-src 'nonce-", 1)[1].split("'", 1)[0]
        self.assertIn('nonce="%s"' % nonce, body)

    def test_rejects_foreign_host(self):
        req = Request(f"{self.base_url}/api/tasks", headers={"Host": "evil.example:8765"})
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_rejects_cross_origin_post(self):
        req = Request(
            f"{self.base_url}/api/reveal_inbox",
            data=b"",
            headers={"Origin": "http://evil.example"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_download_rejects_path_outside_outbox(self):
        secret = self.project_root / "secret.txt"
        secret.write_text("top secret", encoding="utf-8")
        target = f"{self.base_url}/api/download?path={secret}"
        with self.assertRaises(HTTPError) as ctx:
            urlopen(target)
        self.assertEqual(ctx.exception.code, 403)

    def test_download_rejects_sibling_prefix_directory(self):
        sibling = Path(str(self.project_root) + "-backup")
        sibling.mkdir(exist_ok=True)
        self.addCleanup(shutil.rmtree, sibling, True)
        leaked = sibling / "leak.txt"
        leaked.write_text("leak", encoding="utf-8")
        target = f"{self.base_url}/api/download?path={leaked}"
        with self.assertRaises(HTTPError) as ctx:
            urlopen(target)
        self.assertEqual(ctx.exception.code, 403)

    def test_download_serves_outbox_file_with_nosniff(self):
        artifact = self.task_mgr.outbox_dir / "sample.html"
        artifact.write_text("<p>ok</p>", encoding="utf-8")
        req = Request(f"{self.base_url}/api/download?path={artifact}")
        with urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertIn("filename*=UTF-8''", resp.headers.get("Content-Disposition", ""))
            self.assertEqual(resp.read().decode("utf-8"), "<p>ok</p>")

    def test_upload_rejects_oversized_body(self):
        boundary = "BoundaryTooBig"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="big.pdf"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
            f"%PDF-1.4 padding padding padding\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        req = Request(
            f"{self.base_url}/api/upload",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with patch.object(LiteParseAppHandler, "max_upload_bytes", 16):
            with self.assertRaises(HTTPError) as ctx:
                urlopen(req)
        self.assertEqual(ctx.exception.code, 413)

    def test_reveal_endpoints(self):
        # Never let a test touch the real Finder: the project root here is a
        # TemporaryDirectory, so `open` would pop windows on /var/folders.
        with patch("src.web_app.reveal_in_finder", return_value=True) as opener:
            req1 = Request(f"{self.base_url}/api/reveal_outbox", data=b"", method="POST")
            with urlopen(req1) as resp:
                self.assertEqual(resp.status, 200)

            req2 = Request(f"{self.base_url}/api/reveal_inbox", data=b"", method="POST")
            with urlopen(req2) as resp:
                self.assertEqual(resp.status, 200)

        opener.assert_any_call(self.task_mgr.outbox_dir)
        opener.assert_any_call(self.task_mgr.inbox_dir)

    def test_reveal_helper_skips_missing_directory(self):
        missing = self.project_root / "deleted-after-test"
        with patch("src.web_app.subprocess.run") as run:
            self.assertFalse(reveal_in_finder(missing))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
