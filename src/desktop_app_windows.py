"""Windows Native-Feel Desktop Application Runner for JParse.

Launches the JParse backend server and opens a dedicated, frameless
application window using Microsoft Edge or Google Chrome in --app mode,
providing a standalone native desktop experience on Windows without
requiring heavy runtimes.
"""

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
import socket
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
from src.runtime_paths import identity_matches, local_urlopen, mark_active_runtime, packaged_port
from src.watcher import acquire_lock, release_lock


def default_port() -> int:
    return packaged_port()


def port_available(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def saved_runtime_port() -> int | None:
    runtime = os.environ.get("JPARSE_RUNTIME_ID")
    data = os.environ.get("JPARSE_DATA_DIR")
    if not runtime or not data:
        return None
    try:
        value = int((Path(data) / (".port-" + runtime)).read_text(encoding="utf-8"))
        return value if 1 <= value <= 65535 else None
    except (OSError, ValueError):
        return None


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
    endpoint = "/api/identity" if os.environ.get("JPARSE_RUNTIME_ID") else "/api/tasks"
    url = f"http://127.0.0.1:{port}{endpoint}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JParse-DesktopApp/2.1.0"})
        with local_urlopen(req, timeout=timeout) as resp:
            return resp.status == 200 and (not os.environ.get("JPARSE_RUNTIME_ID") or identity_matches(json.load(resp)))
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
    port = default_port()
    explicit_port = False
    for arg in sys.argv[1:]:
        if arg.isdigit():
            port = int(arg)
            explicit_port = True

    if "--server-only" in sys.argv:
        from src.web_app import run_server
        run_server(port=port, open_browser=False)
        return

    runtime = os.environ.get("JPARSE_RUNTIME_ID")
    data = os.environ.get("JPARSE_DATA_DIR")
    handle = None
    selected = None
    try:
        if runtime and data:
            root = Path(data)
            root.mkdir(parents=True, exist_ok=True)
            deadline = time.monotonic() + 60
            while handle is None and time.monotonic() < deadline:
                handle = acquire_lock(root / (".launch-" + runtime + ".lock"))
                if handle is None:
                    time.sleep(0.2)
            if handle is None:
                raise RuntimeError("等待 JParse 后台启动超时。")

        saved = saved_runtime_port() if not explicit_port else None
        if saved is not None and is_backend_alive(saved):
            selected = saved
        else:
            attempts = 20 if runtime and not explicit_port else 1
            for offset in range(attempts):
                candidate = 20000 + ((port - 20000 + offset) % 40000) if attempts > 1 else port
                if not is_backend_alive(candidate):
                    if not port_available(candidate):
                        continue
                    try:
                        start_backend_server(candidate)
                    except RuntimeError:
                        if attempts > 1 and not port_available(candidate) and not is_backend_alive(candidate):
                            continue
                        raise
                selected = candidate
                break
        if selected is None:
            raise RuntimeError("无法找到可用端口启动 JParse。")
        mark_active_runtime(selected)
    finally:
        release_lock(handle)
    launch_desktop_window(selected)


if __name__ == "__main__":
    data_dir = os.environ.get("JPARSE_DATA_DIR")
    if data_dir:
        log_dir = Path(data_dir) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_handler = RotatingFileHandler(
            log_dir / "desktop-launcher.log", maxBytes=1048576, backupCount=3, encoding="utf-8"
        )
        log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(log_handler)
    try:
        main()
    except Exception as exc:
        logger.exception("JParse 启动失败")
        if sys.platform == "win32" and "--server-only" not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(exc), "JParse 启动失败", 0x10)
        raise
