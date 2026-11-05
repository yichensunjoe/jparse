"""Native client state checks against an isolated local server."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("swiftc"), "requires macOS and swiftc")
class TestMacOSUI(unittest.TestCase):
    def test_import_settings_errors_and_dismissed_tasks(self):
        uploads = []
        settings = {"pdf2zh_service": "bing"}
        tasks = [{
            "id": "completed-1", "filename": "paper.pdf", "relative_path": "paper.pdf",
            "file_size": 42, "input_path": "/tmp/paper.pdf", "status": "completed",
            "doc_type": "vector", "progress": 100, "output_files": [], "error": None,
            "created_at": "10:00:00", "duration": 1.0,
        }]

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/tasks":
                    self.respond(200, tasks)
                elif self.path == "/api/settings":
                    self.respond(200, settings)
                else:
                    self.send_error(404)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                if self.path == "/api/settings":
                    payload = json.loads(body)
                    if "pdf2zh_service" in payload:
                        if payload["pdf2zh_service"] == "google":
                            time.sleep(0.15)
                        settings["pdf2zh_service"] = payload["pdf2zh_service"]
                    self.respond(200, {"outbox_dir": "/tmp"})
                elif self.path == "/api/upload":
                    uploads.append(body)
                    self.respond(200 if len(uploads) == 1 else 400, {"ok": len(uploads) == 1})
                else:
                    self.send_error(404)

            def respond(self, status, payload):
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                binary = Path(temp) / "MacOSUIChecks"
                sources = [
                    "macos-app/Sources/Models/Models.swift",
                    "macos-app/Sources/Models/AppSettings.swift",
                    "macos-app/Sources/Views/LightTheme.swift",
                    "macos-app/Sources/Services/BackendManager.swift",
                    "tests/macos_ui_checks.swift",
                ]
                subprocess.run(
                    ["swiftc", "-parse-as-library", *[str(ROOT / source) for source in sources], "-o", str(binary)],
                    check=True, timeout=120,
                )
                import os
                env = dict(os.environ, LITEPARSE_TEST_PORT=str(server.server_address[1]))
                result = subprocess.run([str(binary)], env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("macOS UI model checks passed", result.stdout)
            self.assertEqual(len(uploads), 2)
            for upload in uploads:
                self.assertIn(b'name="pipelineMode"\r\n\r\nvector\r\n', upload)
                self.assertIn(b'name="service"\r\n\r\ngoogle\r\n', upload)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
