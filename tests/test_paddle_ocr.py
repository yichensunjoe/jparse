"""Unit tests for the PaddleOCR worker integration in the scan renderer."""

import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.scan_html_renderer import (
    _read_worker_streams,
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

    def test_config_preserves_venv_symlink(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        fake_venv_bin = root / "venv" / "bin"
        fake_venv_bin.mkdir(parents=True)
        symlink_python = fake_venv_bin / "python"
        symlink_python.symlink_to("/usr/bin/python3")

        config_path = root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "ocr_engine": "paddleocr",
                    "paddleocr_python": str(symlink_python),
                }
            ),
            encoding="utf-8",
        )
        config = Config(config_path)
        self.assertEqual(str(symlink_python), config.paddleocr_python)

    def test_config_rejects_unknown_engine(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        config_path = root / "config.json"
        config_path.write_text('{"ocr_engine": "magic"}', encoding="utf-8")
        with self.assertRaises(ConfigError):
            Config(config_path)


class PaddleOcrStreamMultiplexingTests(unittest.TestCase):
    def _safe_cleanup(self, proc):
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        for stream in (proc.stdout, proc.stderr, proc.stdin):
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass

    def test_multiplexed_streams_avoid_deadlock_on_large_output(self):
        script0 = "import time, sys; time.sleep(0.05); sys.stdout.write('w0\\n'); sys.stdout.flush()"
        script1 = "import sys; sys.stdout.write('A' * 131072 + '\\n'); sys.stdout.flush()"

        p0 = subprocess.Popen([sys.executable, "-c", script0], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p1 = subprocess.Popen([sys.executable, "-c", script1], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self._safe_cleanup, p0)
        self.addCleanup(self._safe_cleanup, p1)

        outputs = _read_worker_streams([p0, p1], timeout_seconds=5)
        p0.wait(timeout=5)
        p1.wait(timeout=5)

        self.assertEqual("w0\n", outputs[p0][0])
        self.assertEqual("A" * 131072 + "\n", outputs[p1][0])

    def test_multiplexed_streams_handles_partial_timeout(self):
        script0 = "import sys; sys.stdout.write('done\\n'); sys.stdout.flush()"
        script1 = "import time; time.sleep(5)"

        p0 = subprocess.Popen([sys.executable, "-c", script0], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p1 = subprocess.Popen([sys.executable, "-c", script1], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self._safe_cleanup, p0)
        self.addCleanup(self._safe_cleanup, p1)

        outputs = _read_worker_streams([p0, p1], timeout_seconds=1)
        p0.wait(timeout=5)
        p1.kill()
        p1.wait(timeout=5)

        self.assertEqual("done\n", outputs[p0][0])
        self.assertIsInstance(outputs[p1], TimeoutError)

    def test_multiplexed_streams_fallback_on_non_file_streams(self):
        proc0 = FakeProc(['{"index": 0, "ok": true, "text": "synthetic"}'])
        outputs = _read_worker_streams([proc0], timeout_seconds=5)
        self.assertIn("synthetic", outputs[proc0][0])

    def test_multiplexed_streams_avoid_deadlock_on_large_stderr(self):
        script0 = "import sys; sys.stderr.write('E' * 131072 + '\\n'); sys.stdout.write('out0\\n'); sys.stderr.flush(); sys.stdout.flush()"
        script1 = "import sys; sys.stdout.write('out1\\n'); sys.stdout.flush()"

        p0 = subprocess.Popen([sys.executable, "-c", script0], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p1 = subprocess.Popen([sys.executable, "-c", script1], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self._safe_cleanup, p0)
        self.addCleanup(self._safe_cleanup, p1)

        outputs = _read_worker_streams([p0, p1], timeout_seconds=5)
        p0.wait(timeout=5)
        p1.wait(timeout=5)

        self.assertEqual("out0\n", outputs[p0][0])
        self.assertEqual("E" * 131072 + "\n", outputs[p0][1])
        self.assertEqual("out1\n", outputs[p1][0])

    def test_multiplexed_streams_aborted_read_returns_error_not_partial_data(self):
        script0 = "import time; time.sleep(5)"
        p0 = subprocess.Popen([sys.executable, "-c", script0], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self._safe_cleanup, p0)

        # Mock select.select to raise OSError (simulating abnormal OS pipe error or interruption)
        with patch("src.scan_html_renderer.select.select", side_effect=OSError("pipe error")):
            outputs = _read_worker_streams([p0], timeout_seconds=10)

        self.assertIsInstance(outputs[p0], RuntimeError)
        self.assertIn("异常中断", str(outputs[p0]))

    def test_run_paddle_ocr_reaps_zombie_processes_on_worker_timeout(self):
        directory, pages = make_pages(2)
        self.addCleanup(directory.cleanup)

        spawned_procs = []
        original_popen = subprocess.Popen

        def fake_popen(*args, **kwargs):
            p = original_popen(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            spawned_procs.append(p)
            return p

        with patch("src.scan_html_renderer.subprocess.Popen", side_effect=fake_popen):
            texts, failures = _run_paddle_ocr(
                pages,
                paddleocr_python=sys.executable,
                workers=2,
                timeout_seconds=1,
                progress=None,
            )

        self.assertEqual(2, failures)
        self.assertEqual(["", ""], texts)
        self.assertEqual(2, len(spawned_procs))
        for p in spawned_procs:
            self.assertIsNotNone(p.returncode)
            res = subprocess.run(["ps", "-o", "stat", "-p", str(p.pid)], capture_output=True, text=True)
            self.assertNotIn("Z", res.stdout)


if __name__ == "__main__":
    unittest.main()
