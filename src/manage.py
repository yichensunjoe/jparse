#!/usr/bin/env python3
"""Manage the detached watcher process without broad macOS disk permissions."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent.parent
WATCHER = ROOT / "src" / "watcher.py"
CONFIG = ROOT / "config.json"
LOGS = ROOT / "logs"
PID_FILE = LOGS / "watcher.pid"
BOOT_ERROR_LOG = LOGS / "watcher-startup.error.log"


def process_matches(pid):
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    result = subprocess.run(
        ["/bin/ps", "-p", str(pid), "-o", "command="],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.returncode == 0 and str(WATCHER) in result.stdout


def current_pid():
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if process_matches(pid):
        return pid
    PID_FILE.unlink(missing_ok=True)
    return None


def check_environment():
    result = subprocess.run(
        [sys.executable, str(WATCHER), "--config", str(CONFIG), "--check"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip())
    return result.stdout.strip()


def start():
    LOGS.mkdir(parents=True, exist_ok=True)
    pid = current_pid()
    if pid:
        print("自动识别已在运行（进程 %d）。" % pid)
        return

    check_message = check_environment()
    with BOOT_ERROR_LOG.open("w", encoding="utf-8") as error_handle:
        process = subprocess.Popen(
            [sys.executable, str(WATCHER), "--config", str(CONFIG)],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=error_handle,
            start_new_session=True,
            close_fds=True,
        )
    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    time.sleep(1)
    if process.poll() is not None:
        PID_FILE.unlink(missing_ok=True)
        detail = BOOT_ERROR_LOG.read_text(encoding="utf-8", errors="replace").strip()
        raise RuntimeError(detail or "后台进程启动后立即退出")

    print(check_message)
    print("自动识别已在后台启动（进程 %d）。" % process.pid)
    print("PDF 投递箱：%s" % (ROOT / "inbox"))
    print("识别结果：%s" % (ROOT / "outbox"))


def stop():
    pid = current_pid()
    if not pid:
        print("自动识别当前未运行。")
        return
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and process_matches(pid):
        time.sleep(0.2)
    if process_matches(pid):
        os.kill(pid, signal.SIGKILL)
    PID_FILE.unlink(missing_ok=True)
    print("自动识别已停止。")


def status():
    pid = current_pid()
    print("运行状态：%s" % ("正在运行（进程 %d）" % pid if pid else "未运行"))
    try:
        output_format = json.loads(CONFIG.read_text(encoding="utf-8")).get("output_format", "html")
    except (OSError, json.JSONDecodeError):
        output_format = "html"
    output_suffix = {"html": ".html", "markdown": ".md", "text": ".txt"}.get(output_format, ".html")
    for label, folder, suffix in (
        ("待处理", ROOT / "inbox", ".pdf"),
        ("已输出", ROOT / "outbox", output_suffix),
        ("失败", ROOT / "failed", ".pdf"),
    ):
        count = sum(
            1
            for item in folder.iterdir()
            if item.is_file() and item.suffix.lower() == suffix
        )
        print("%s：%d" % (label, count))
    log_path = LOGS / "watcher.log"
    if log_path.is_file():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
        if lines:
            print("\n最近记录：")
            print("\n".join(lines))


def open_folder(name):
    folder = ROOT / name
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.run(["/usr/bin/open", str(folder)], check=True)


def parse_args():
    parser = argparse.ArgumentParser(description="管理 LiteParse PDF 自动识别")
    parser.add_argument(
        "action",
        choices=("install", "start", "stop", "status", "uninstall", "open-inbox", "open-outbox"),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        if args.action in {"install", "start"}:
            start()
        elif args.action in {"stop", "uninstall"}:
            stop()
        elif args.action == "status":
            status()
        elif args.action == "open-inbox":
            open_folder("inbox")
        else:
            open_folder("outbox")
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print("操作失败：%s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
