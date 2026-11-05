"""Windows Native-Feel Desktop Application Runner for JParse.

Launches the JParse backend server and opens a dedicated, frameless
application window using Microsoft Edge or Google Chrome in --app mode,
providing a standalone native desktop experience on Windows without
requiring heavy runtimes.
"""

import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser

logger = logging.getLogger("desktop_app_windows")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def find_windows_app_browser() -> tuple[str, str]:
    """Find a Chromium-based browser supporting --app mode (Edge or Chrome).

    Returns:
        (browser_type, executable_path_or_command)
    """
    # 1. Microsoft Edge (Built into Windows 10 & 11)
    edge_candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(shutil.which("msedge.exe") or shutil.which("msedge") or ""),
    ]
    for p in edge_candidates:
        if str(p) and p.is_file():
            return "edge", str(p)

    # 2. Google Chrome
    chrome_candidates = [
        Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path(shutil.which("chrome.exe") or shutil.which("chrome") or ""),
    ]
    for p in chrome_candidates:
        if str(p) and p.is_file():
            return "chrome", str(p)

    return "browser", ""


def is_backend_alive(port: int = 8765, timeout: float = 1.0) -> bool:
    """Check if JParse backend server is responding on 127.0.0.1:port."""
    url = f"http://127.0.0.1:{port}/api/tasks"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JParse-DesktopApp/2.1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_backend_server(port: int = 8765) -> subprocess.Popen:
    """Start JParse backend server in the background."""
    web_app_script = _PROJECT_ROOT / "src" / "web_app.py"
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)

    cmd = [sys.executable, str(web_app_script), str(port), "--no-browser"]
    logger.info("正在启动 JParse 后台服务: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=str(_PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )

    # First launch can load several native libraries on slower Windows PCs.
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if is_backend_alive(port, timeout=0.5):
            logger.info("JParse 后台服务已就绪 (127.0.0.1:%d)", port)
            return proc
        if proc.poll() is not None:
            raise RuntimeError("JParse 后台服务启动失败，请查看用户数据目录下的 logs/desktop.log。")
        time.sleep(0.2)

    proc.terminate()
    raise RuntimeError("JParse 后台服务启动超时，请查看用户数据目录下的 logs/desktop.log。")


def launch_desktop_window(port: int = 8765) -> None:
    """Open the native-feel application window or browser."""
    target_url = f"http://127.0.0.1:{port}"
    browser_type, browser_bin = find_windows_app_browser()

    if browser_bin:
        # Profile directory for app cookies/settings persistence
        local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".jparse")
        profile_dir = Path(local_app_data) / "JParse" / "AppProfile"
        profile_dir.mkdir(parents=True, exist_ok=True)

        app_cmd = [
            browser_bin,
            f"--app={target_url}",
            "--window-size=1260,840",
            f"--user-data-dir={str(profile_dir)}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        logger.info("以独立桌面窗口运行 (%s): %s", browser_type, " ".join(app_cmd))
        try:
            # Run the browser app process
            subprocess.run(app_cmd, check=False)
            return
        except Exception as e:
            logger.warning("无法以桌面应用模式启动: %s，回退至默认浏览器", e)

    # Fallback to standard default browser
    logger.info("在默认浏览器中打开 JParse: %s", target_url)
    try:
        webbrowser.open(target_url)
    except Exception as e:
        logger.error("打开浏览器失败: %s", e)


def main() -> None:
    port = 8765
    for arg in sys.argv[1:]:
        if arg.isdigit():
            port = int(arg)

    if "--server-only" in sys.argv:
        from src.web_app import run_server
        run_server(port=port, open_browser=False)
        return

    # 1. Check or start backend
    if not is_backend_alive(port):
        start_backend_server(port)

    # 2. Launch UI window
    launch_desktop_window(port)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.exception("JParse 启动失败")
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(exc), "JParse 启动失败", 0x10)
        raise
