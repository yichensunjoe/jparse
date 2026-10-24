"""Unit tests for LiteParse Interactive Web Application."""

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from src.web_app import ConversionTaskManager, LiteParseAppHandler, ThreadingHTTPServer


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

    def test_reveal_endpoints(self):
        req1 = Request(f"{self.base_url}/api/reveal_outbox", data=b"", method="POST")
        with urlopen(req1) as resp:
            self.assertEqual(resp.status, 200)

        req2 = Request(f"{self.base_url}/api/reveal_inbox", data=b"", method="POST")
        with urlopen(req2) as resp:
            self.assertEqual(resp.status, 200)


if __name__ == "__main__":
    unittest.main()
