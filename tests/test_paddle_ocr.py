"""Unit tests for the PaddleOCR worker integration in the scan renderer."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.scan_html_renderer import (
    _run_ocr,
    _run_paddle_ocr,
)
from src.watcher import Config, ConfigError


class FakeProc:
    def __init__(self, lines, returncode=0, stderr_text=""):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("\n".join(lines) + ("\n" if lines else ""))
        self.stderr = io.StringIO(stderr_text)
        self.returncode = returncode
        self.stdin_was_closed = False

    def close(self):
        self.stdin_was_closed = True

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


def make_pages(count=3):
    directory = tempfile.TemporaryDirectory()
    root = Path(directory.name)
    pages = []
    for index in range(count):
        path = root / ("page-%03d.jpg" % (index + 1))
        path.write_bytes(b"\xff\xd8fake\xff\xd9")
        pages.append(path)
    return directory, pages


class PaddleOcrRendererTests(unittest.TestCase):
    def test_run_paddle_ocr_assembles_page_texts_and_counts_failures(self):
        directory, pages = make_pages(3)
        self.addCleanup(directory.cleanup)
        lines = [
            json.dumps({"index": 0, "ok": True, "text": "第一页文字"}),
            json.dumps({"index": 1, "ok": False, "error": "boom"}),
            json.dumps({"index": 2, "ok": True, "text": "line1\nline2"}),
        ]
        with patch("src.scan_html_renderer.subprocess.Popen", return_value=FakeProc(lines)), patch(
            "src.scan_html_renderer._read_streams",
            return_value=("\n".join(lines), ""),
        ):
            texts, failures = _run_paddle_ocr(
                pages,
                paddleocr_python="/usr/bin/python3",
                workers=1,
                timeout_seconds=60,
                progress=None,
            )
        self.assertEqual(["第一页文字", "", "line1\nline2"], texts)
        self.assertEqual(1, failures)

    def test_run_paddle_ocr_crashed_worker_counts_all_pages_failed(self):
        directory, pages = make_pages(2)
        self.addCleanup(directory.cleanup)
        with patch(
            "src.scan_html_renderer.subprocess.Popen",
            return_value=FakeProc([], returncode=3),
        ), patch("src.scan_html_renderer._read_streams", return_value=("", "")):
            texts, failures = _run_paddle_ocr(
                pages,
                paddleocr_python="/usr/bin/python3",
                workers=1,
                timeout_seconds=60,
                progress=None,
            )
        self.assertEqual(["", ""], texts)
        self.assertEqual(2, failures)

    def test_run_paddle_ocr_strided_chunk_mapping(self):
        # 步长分块（workers>1）时 worker 的 index 是 chunk 内序号，
        # 必须映射回原始页索引；此测试防回归（曾因 chunk_start+index 覆盖错误页）。
        directory, pages = make_pages(4)
        self.addCleanup(directory.cleanup)
        chunk0_lines = [
            json.dumps({"index": 0, "ok": True, "text": "页0"}),
            json.dumps({"index": 1, "ok": True, "text": "页2"}),
        ]
        chunk1_lines = [
            json.dumps({"index": 0, "ok": True, "text": "页1"}),
            json.dumps({"index": 1, "ok": True, "text": "页3"}),
        ]
        with patch(
            "src.scan_html_renderer.subprocess.Popen",
            side_effect=[FakeProc(chunk0_lines), FakeProc(chunk1_lines)],
        ), patch(
            "src.scan_html_renderer._read_streams",
            side_effect=[
                ("\n".join(chunk0_lines), ""),
                ("\n".join(chunk1_lines), ""),
            ],
        ):
            texts, failures = _run_paddle_ocr(
                pages,
                paddleocr_python="/usr/bin/python3",
                workers=2,
                timeout_seconds=60,
                progress=None,
            )
        self.assertEqual(["页0", "页1", "页2", "页3"], texts)
        self.assertEqual(0, failures)

    def test_run_paddle_ocr_rejects_missing_interpreter(self):
        directory, pages = make_pages(1)
        self.addCleanup(directory.cleanup)
        with self.assertRaises(Exception) as context:
            _run_paddle_ocr(
                pages,
                paddleocr_python="/nonexistent/python",
                workers=1,
                timeout_seconds=60,
                progress=None,
            )
        self.assertIn("PaddleOCR 解释器不可用", str(context.exception))

    def test_run_ocr_dispatches_paddle_engine(self):
        directory, pages = make_pages(1)
        self.addCleanup(directory.cleanup)
        with patch(
            "src.scan_html_renderer._run_paddle_ocr", return_value=(["ok"], 0)
        ) as paddle, patch(
            "src.scan_html_renderer._run_tesseract_ocr", return_value=(["t"], 0)
        ) as tess:
            texts, failures = _run_ocr(
                pages, ocr_engine="paddleocr", paddleocr_python="/usr/bin/python3"
            )
        paddle.assert_called_once()
        tess.assert_not_called()
        self.assertEqual(["ok"], texts)

    def test_run_ocr_dispatches_tesseract_engine(self):
        directory, pages = make_pages(1)
        self.addCleanup(directory.cleanup)
        with patch(
            "src.scan_html_renderer._run_paddle_ocr", return_value=(["p"], 0)
        ) as paddle, patch(
            "src.scan_html_renderer._run_tesseract_ocr", return_value=(["t"], 0)
        ) as tess:
            texts, failures = _run_ocr(pages, ocr_engine="tesseract")
        paddle.assert_not_called()
        tess.assert_called_once()
        self.assertEqual(["t"], texts)

    def test_paddle_worker_receives_pages_and_env_guard(self):
        directory, pages = make_pages(2)
        self.addCleanup(directory.cleanup)
        captured = {}

        class RecordingProc(FakeProc):
            def __init__(self, *args, **kwargs):
                super().__init__(
                    [
                        json.dumps({"index": 0, "ok": True, "text": "a"}),
                        json.dumps({"index": 1, "ok": True, "text": "b"}),
                    ]
                )
                captured["args"] = args[0]
                captured["env"] = kwargs["env"]

        with patch("src.scan_html_renderer.subprocess.Popen", RecordingProc), patch(
            "src.scan_html_renderer._read_streams",
            return_value=(
                '{"index": 0, "ok": true, "text": "a"}\n{"index": 1, "ok": true, "text": "b"}',
                "",
            ),
        ):
            _run_paddle_ocr(
                pages,
                paddleocr_python="/usr/bin/python3",
                workers=1,
                timeout_seconds=60,
                progress=None,
            )
        self.assertEqual(["/usr/bin/python3"], captured["args"][:1])
        self.assertTrue(
            str(captured["args"][1]).endswith("paddle_ocr_worker.py")
        )
        self.assertEqual(
            "True", captured["env"].get("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK")
        )


class PaddleOcrConfigTests(unittest.TestCase):
    def test_config_accepts_paddleocr_engine(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        config_path = root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "ocr_engine": "paddleocr",
                    "paddleocr_python": "/usr/bin/python3",
                    "paddleocr_workers": 8,
                }
            ),
            encoding="utf-8",
        )
        config = Config(config_path)
        self.assertEqual("paddleocr", config.ocr_engine)
        self.assertEqual("/usr/bin/python3", config.paddleocr_python)
        self.assertEqual(8, config.paddleocr_workers)

    def test_config_rejects_unknown_engine(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        config_path = root / "config.json"
        config_path.write_text('{"ocr_engine": "magic"}', encoding="utf-8")
        with self.assertRaises(ConfigError):
            Config(config_path)


if __name__ == "__main__":
    unittest.main()
