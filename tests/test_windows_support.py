"""Unit tests for Windows platform compatibility and desktop launcher in JParse."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.desktop_app_windows import (
    find_windows_app_browser,
    is_backend_alive,
    launch_desktop_window,
)
from src.hd_scan_renderer import find_chrome_binary
from src.manage import open_folder, process_matches, stop
from src.pdf2zh_patch import patch_pdf2zh_converter_file, patch_pdf2zh_translator_file
from src.vector_pdf_renderer import get_pdf2zh_binary
from src.watcher import acquire_lock, release_lock
from src.web_app import reveal_in_finder


class TestWindowsCompatibility(unittest.TestCase):
    """Verify that all OS-sensitive modules operate safely under Windows (win32)."""

    def test_find_windows_app_browser(self):
        with patch("pathlib.Path.is_file", return_value=True):
            b_type, b_bin = find_windows_app_browser()
            self.assertIn(b_type, ("edge", "chrome", "browser"))

    def test_is_backend_alive_handles_connection_error(self):
        self.assertFalse(is_backend_alive(port=59999, timeout=0.1))

    @patch("subprocess.run")
    def test_launch_desktop_window_uses_app_mode(self, mock_run):
        with patch("src.desktop_app_windows.find_windows_app_browser", return_value=("edge", "C:\\Edge\\msedge.exe")):
            launch_desktop_window(port=8765)
            self.assertTrue(mock_run.called)
            cmd = mock_run.call_args[0][0]
            self.assertIn("--app=http://127.0.0.1:8765", cmd)
            self.assertIn("--window-size=1260,840", cmd)

    def test_manage_process_matches_win32(self):
        with patch("sys.platform", "win32"):
            with patch("os.kill"):
                with patch("subprocess.run") as mock_sub:
                    mock_sub.return_value = MagicMock(returncode=0, stdout='"python.exe","1234","Console"')
                    self.assertTrue(process_matches(1234))

    def test_manage_open_folder_win32(self):
        with patch("sys.platform", "win32"):
            with patch("os.startfile", create=True) as mock_startfile:
                open_folder("inbox")
                mock_startfile.assert_called_once()

    def test_manage_stop_handles_win32(self):
        with patch("sys.platform", "win32"):
            with patch("src.manage.current_pid", return_value=9999):
                with patch("os.kill") as mock_kill:
                    with patch("src.manage.process_matches", return_value=False):
                        with patch("pathlib.Path.unlink"):
                            stop()
                            mock_kill.assert_called_once()

    def test_web_app_reveal_in_finder_win32(self):
        with patch("sys.platform", "win32"):
            with patch("pathlib.Path.is_dir", return_value=True):
                with patch("os.startfile", create=True) as mock_startfile:
                    self.assertTrue(reveal_in_finder(Path("inbox")))
                    mock_startfile.assert_called_once()

    def test_hd_scan_find_chrome_binary_win32(self):
        with patch("sys.platform", "win32"):
            with patch("shutil.which", return_value=None):
                with patch("pathlib.Path.is_file", return_value=True):
                    bin_path = find_chrome_binary()
                    self.assertIsNotNone(bin_path)

    def test_get_pdf2zh_binary_win32(self):
        with patch("sys.platform", "win32"):
            with patch("shutil.which", return_value=None):
                with patch("pathlib.Path.is_file", return_value=True):
                    bin_path = get_pdf2zh_binary()
                    self.assertIsNotNone(bin_path)

    def test_watcher_locking_msvcrt_fallback(self):
        dummy_handle = MagicMock()
        mock_msvcrt = MagicMock()
        with patch("src.watcher.fcntl", None):
            with patch("src.watcher.msvcrt", mock_msvcrt):
                with patch("pathlib.Path.open", return_value=dummy_handle):
                    handle = acquire_lock(Path("test.lock"))
                    self.assertIsNotNone(handle)
                    mock_msvcrt.locking.assert_called_once()
                    release_lock(handle)
                    self.assertEqual(mock_msvcrt.locking.call_count, 2)

    def test_pdf2zh_patch_finds_windows_site_packages(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            conv_file = base / "Lib" / "site-packages" / "pdf2zh" / "converter.py"
            conv_file.parent.mkdir(parents=True, exist_ok=True)
            conv_file.write_text(
                "def vflag(font: str, char: str):\n"
                "    if re.match(\n"
                "        r\"(CM[^R]|MS.M|XY|MT|BL|RM|EU|LA|RS|LINE|LCIRCLE|TeX-|rsfs|txsy|wasy|stmary|.*Mono|.*Code|.*Ital|.*Sym|.*Math)\",\n"
                "        font,\n"
                "    ):\n"
                "        return True\n",
                encoding="utf-8"
            )

            # Patch should succeed on Windows Lib/site-packages structure
            self.assertTrue(patch_pdf2zh_converter_file(venv_dir=base))
            content = conv_file.read_text(encoding="utf-8")
            self.assertIn(".*MathItal", content)

    def test_batch_files_exist_and_readable(self):
        expected_batches = [
            "一键安装环境-Windows.bat",
            "install_windows.bat",
            "启动JParse桌面应用.bat",
            "启动JParse桌面应用(无黑框).vbs",
            "打开交互应用.bat",
            "启动自动识别.bat",
            "停止自动识别.bat",
            "查看运行状态.bat",
            "打开PDF投递箱.bat",
            "打开识别结果.bat",
            "翻译已识别文献.bat",
        ]
        root = Path(__file__).resolve().parent.parent
        for bf in expected_batches:
            p = root / bf
            self.assertTrue(p.is_file(), f"Missing Windows batch launcher: {bf}")
            self.assertGreater(p.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
