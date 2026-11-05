"""LiteParse Interactive Web Application with Folder Drag-and-Drop and Dual-Track Processing.

Uses standard Python HTTP server (zero external dependencies) and modern HTML5 Web API.
Supports recursive folder drops, real-time conversion progress, and macOS Finder integration.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.router import probe_pdf_document_type, route_and_process_pdf
from src.runtime_paths import identity_matches, local_urlopen, mark_active_runtime
from src.watcher import acquire_lock, release_lock

logger = logging.getLogger("web_app")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class TaskStatus:
    QUEUED = "queued"
    PROBING = "probing"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ConversionTaskManager:
    """Thread-safe task manager with background processing queue."""

    def __init__(self, project_root: Path, max_workers: int = 1):
        self.project_root = Path(project_root).resolve()
        self.inbox_dir = self.project_root / "inbox"
        self.default_outbox_dir = self.project_root / "outbox"
        self.outbox_dir = self.default_outbox_dir
        self.processed_dir = self.project_root / "processed"
        self.failed_dir = self.project_root / "failed"
        # 工作台自己认领文件：投递即移入 processing/，与后台 watcher 的 inbox 扫描
        # 天然隔离，同一份 PDF 不会被两套管线同时处理。
        self.processing_dir = self.project_root / "processing"

        for d in [self.inbox_dir, self.outbox_dir, self.processed_dir, self.failed_dir, self.processing_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.tasks: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="LiteParseWorker")
        self._subscribers: List[threading.Event] = []
        self._inbox_observations: Dict[str, tuple] = {}
        self._reservation_locks: Dict[str, Any] = {}

    def scan_inbox_once(self, now: Optional[float] = None, settle_seconds: float = 5) -> None:
        """Claim only stable PDFs, atomically isolating them from other watchers."""
        runtime = os.environ.get("JPARSE_RUNTIME_ID")
        if runtime:
            try:
                if (self.project_root / ".active-runtime").read_text(encoding="utf-8") != runtime:
                    self._inbox_observations.clear()
                    return
            except OSError:
                self._inbox_observations.clear()
                return
        now = time.monotonic() if now is None else now
        visible = set()
        for source in sorted(self.inbox_dir.iterdir()):
            if source.name.startswith(".") or source.suffix.lower() != ".pdf" or source.is_symlink():
                continue
            try:
                stat = source.stat()
                if not source.is_file():
                    continue
            except OSError:
                continue
            key = str(source)
            visible.add(key)
            signature = (stat.st_size, stat.st_mtime_ns)
            previous = self._inbox_observations.get(key)
            if previous is None or previous[:2] != signature:
                self._inbox_observations[key] = (*signature, now)
                continue
            if now - previous[2] < settle_seconds:
                continue
            service = self.configured_service()
            stem = self.reserve_stem(source.stem)
            claimed = self.processing_dir / (stem + ".pdf")
            try:
                os.replace(str(source), str(claimed))
            except OSError as exc:
                claimed.unlink(missing_ok=True)
                self.release_reservation(stem)
                logger.warning("无法认领投递箱文件 %s: %s", source.name, exc)
            else:
                if claimed.is_symlink():
                    destination = self._unique_path(self.failed_dir, claimed.name)
                    os.replace(str(claimed), str(destination))
                    self.release_reservation(stem)
                    logger.warning("已拒绝投递箱符号链接: %s", source.name)
                else:
                    self.add_file(claimed, source.name, options={"service": service})
            self._inbox_observations.pop(key, None)
        for key in set(self._inbox_observations) - visible:
            self._inbox_observations.pop(key, None)

    def configured_service(self) -> str:
        """Read the explicitly selected default translation service."""
        config_path = self.project_root / "config.json"
        if not config_path.is_file():
            config_path = _PROJECT_ROOT / "config.json"
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError("配置不是对象")
            service = config.get("pdf2zh_service", "bing")
            if not isinstance(service, str) or not service.strip():
                raise ValueError("翻译服务不能为空")
            return service.strip()
        except (OSError, ValueError) as exc:
            raise RuntimeError("无法读取翻译配置: %s" % exc) from exc

    def set_translation_service(self, service: str) -> None:
        if not isinstance(service, str) or service not in {"bing", "google"}:
            raise ValueError("翻译服务仅支持 bing 或 google")
        target = self.project_root / "config.json"
        source = target if target.exists() else _PROJECT_ROOT / "config.json"
        with self._lock:
            try:
                config = json.loads(source.read_text(encoding="utf-8"))
                if not isinstance(config, dict):
                    raise ValueError("配置不是对象")
                config["pdf2zh_service"] = service
                stage = self.project_root / (".config-%d-%d.tmp" % (os.getpid(), time.time_ns()))
                try:
                    stage.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    os.replace(str(stage), str(target))
                finally:
                    stage.unlink(missing_ok=True)
            except (OSError, ValueError) as exc:
                raise ValueError("无法保存翻译配置：%s" % exc) from exc

    def watch_inbox(self) -> None:
        while True:
            try:
                self.recover_interrupted()
                self.scan_inbox_once()
            except Exception:
                logger.exception("扫描投递箱失败")
            time.sleep(2)

    def set_outbox_dir(self, raw_path: str) -> Path:
        """Switch the output directory for future tasks.

        The path comes from the desktop app's native folder picker, so it may
        legitimately live outside the project. Validate it as a real, writable
        directory before publishing the change to the task manager.
        """
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("输出文件夹不能为空")

        try:
            candidate = Path(raw_path).expanduser()
            if not candidate.is_absolute():
                candidate = self.project_root / candidate
            candidate = candidate.resolve()
        except (OSError, ValueError) as exc:
            raise ValueError("输出文件夹路径无效：%s" % exc) from exc

        if candidate.exists() and not candidate.is_dir():
            raise ValueError("输出路径不是文件夹")

        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / (".liteparse-write-probe-%s-%s" % (os.getpid(), time.time_ns()))
            probe.write_text("", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise ValueError("输出文件夹不可写：%s" % exc) from exc

        self.outbox_dir = candidate
        return candidate

    def _stem_free(self, stem: str) -> bool:
        """True when no existing input or deliverable already uses this stem."""
        occupied = [
            self.processing_dir / (stem + ".pdf"),
            self.processed_dir / (stem + ".pdf"),
            self.failed_dir / (stem + ".pdf"),
            self.outbox_dir / (stem + ".html"),
            self.outbox_dir / (stem + ".md"),
            self.outbox_dir / (stem + "-中文精译版.pdf"),
            self.outbox_dir / (stem + "-双语对照版.pdf"),
            self.outbox_dir / (stem + ".mono.pdf"),
            self.outbox_dir / (stem + ".原位双层版.html"),
        ]
        return not any(path.exists() for path in occupied)

    def reserve_stem(self, original_stem: str) -> str:
        """Reserve a collision-free stem under processing/ so peers skip it too."""
        with self._lock:
            base = original_stem or "document"
            stem = base
            index = 2
            while True:
                handle = None
                if self._stem_free(stem):
                    lock_path = self.processing_dir / (".%s.lock" % stem)
                    if not lock_path.is_symlink():
                        handle = acquire_lock(lock_path)
                if handle is not None:
                    try:
                        (self.processing_dir / (stem + ".pdf")).touch(exist_ok=False)
                    except FileExistsError:
                        release_lock(handle)
                    else:
                        self._reservation_locks[stem] = handle
                        return stem
                stem = "%s-%d" % (base, index)
                index += 1

    def release_reservation(self, stem: str) -> None:
        with self._lock:
            handle = self._reservation_locks.pop(stem, None)
        release_lock(handle)

    def recover_interrupted(self) -> None:
        """Move abandoned, lock-protected claims to failed/; never take live jobs."""
        runtime = os.environ.get("JPARSE_RUNTIME_ID")
        if runtime:
            try:
                if (self.project_root / ".active-runtime").read_text(encoding="utf-8") != runtime:
                    return
            except OSError:
                return
        for source in self.processing_dir.glob("*.pdf"):
            if source.is_symlink():
                continue
            with self._lock:
                if source.stem in self._reservation_locks:
                    continue
            lock_path = self.processing_dir / (".%s.lock" % source.stem)
            if not lock_path.is_file() or lock_path.is_symlink():
                continue  # It may belong to an older independent watcher.
            handle = acquire_lock(lock_path)
            if handle is None:
                continue
            try:
                if source.is_file() and not source.is_symlink():
                    destination = self._unique_path(self.failed_dir, source.name)
                    os.replace(str(source), str(destination))
                    destination.with_suffix(".error.txt").write_text(
                        "处理被中断；原件已保留。请将 PDF 重新放入 inbox 后重试。\n", encoding="utf-8"
                    )
                    logger.warning("已保留中断任务的原件: %s", destination.name)
            finally:
                release_lock(handle)

    @staticmethod
    def _unique_path(directory: Path, filename: str) -> Path:
        candidate = directory / filename
        if not candidate.exists():
            return candidate
        source = Path(filename)
        index = 2
        while True:
            candidate = directory / ("%s-%d%s" % (source.stem, index, source.suffix))
            if not candidate.exists():
                return candidate
            index += 1

    def add_file(self, file_path: Path, relative_path: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Add a PDF file to the conversion task queue."""
        task_id = f"task_{int(time.time() * 1000)}_{len(self.tasks) + 1}"
        file_path = Path(file_path).resolve()
        task = {
            "id": task_id,
            "filename": file_path.name,
            "relative_path": relative_path or file_path.name,
            "file_size": file_path.stat().st_size if file_path.exists() else 0,
            "input_path": str(file_path),
            "status": TaskStatus.QUEUED,
            "doc_type": "unknown",
            "progress": 0,
            "output_files": [],
            "error": None,
            "created_at": datetime.now().strftime("%H:%M:%S"),
            "duration": 0.0,
            "options": options or {},
        }
        with self._lock:
            self.tasks.insert(0, task)
            del self.tasks[200:]
        self._notify_subscribers()
        try:
            self._executor.submit(self._run_task, task_id, file_path.stem)
        except Exception:
            self.release_reservation(file_path.stem)
            raise
        return task

    def get_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.tasks)

    def _update_task(self, task_id: str, **kwargs):
        with self._lock:
            for t in self.tasks:
                if t["id"] == task_id:
                    t.update(kwargs)
                    break
        self._notify_subscribers()

    def _run_task(self, task_id: str, reserved_stem: str):
        try:
            self._run_task_impl(task_id)
        finally:
            self.release_reservation(reserved_stem)

    def _run_task_impl(self, task_id: str):
        task = None
        with self._lock:
            for t in self.tasks:
                if t["id"] == task_id:
                    task = dict(t)
                    break
        if not task:
            return

        input_path = Path(task["input_path"])
        if not input_path.exists():
            self._update_task(task_id, status=TaskStatus.FAILED, error="文件不存在")
            return

        start_time = time.time()
        try:
            # 1. Probing phase
            self._update_task(task_id, status=TaskStatus.PROBING, progress=10)
            doc_type = probe_pdf_document_type(input_path)
            self._update_task(task_id, doc_type=doc_type, status=TaskStatus.PROCESSING, progress=30)

            # 2. Conversion phase
            opts = task.get("options", {})
            p_mode = opts.get("pipeline_mode", "auto")
            config = {
                "force_pipeline": p_mode,
                "pdf2zh_service": opts.get("service", "bing"),
                "pdf2zh_threads": 4,
            }
            if p_mode == "insitu_legacy":
                config["force_pipeline"] = "insitu_legacy"
                config["upstream_extractor"] = "liteparse"
            else:
                config["force_pipeline"] = p_mode
                config["upstream_extractor"] = "opendataloader"
            output_paths = route_and_process_pdf(
                pdf_path=input_path,
                outbox_dir=self.outbox_dir,
                config=config,
            )

            # 3. Archive original file into processed/ (never overwrite an old one)
            if input_path.exists() and input_path.parent in (self.inbox_dir, self.processing_dir):
                dest_processed = self._unique_path(self.processed_dir, input_path.name)
                shutil.move(str(input_path), str(dest_processed))

            duration = round(time.time() - start_time, 2)
            out_info = [
                {
                    "name": p.name,
                    "path": str(p),
                    "size": p.stat().st_size if p.exists() else 0,
                    "is_pdf": p.suffix.lower() == ".pdf",
                    "is_html": p.suffix.lower() == ".html",
                }
                for p in output_paths
            ]
            self._update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                output_files=out_info,
                duration=duration,
            )
            logger.info("任务 %s 转换成功，用时 %.2fs，产物: %s", task_id, duration, [p.name for p in output_paths])

        except Exception as e:
            logger.exception("任务 %s 转换失败: %s", task_id, e)
            duration = round(time.time() - start_time, 2)
            # Move to failed/ (never overwrite an old one)
            if input_path.exists() and input_path.parent in (self.inbox_dir, self.processing_dir):
                try:
                    dest_failed = self._unique_path(self.failed_dir, input_path.name)
                    shutil.move(str(input_path), str(dest_failed))
                except Exception:
                    pass
            self._update_task(
                task_id,
                status=TaskStatus.FAILED,
                progress=100,
                error=str(e),
                duration=duration,
            )

    def _notify_subscribers(self):
        # We can implement SSE or simple polling
        pass


INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JParse 文档智能中枢 · 双轨极速转换平台</title>
    <style>
        :root {
            --bg: #0c0f17;
            --surface: #151a26;
            --surface-hover: #1c2333;
            --border: #263045;
            --accent: #3b82f6;
            --accent-glow: rgba(59, 130, 246, 0.25);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --badge-vector: #059669;
            --badge-scanned: #d97706;
            --success: #10b981;
            --danger: #ef4444;
            --font-stack: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Segoe UI", Roboto, sans-serif;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: var(--font-stack);
            background-color: var(--bg);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
            background-image: 
                radial-gradient(at 0% 0%, rgba(59, 130, 246, 0.08) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.06) 0px, transparent 50%);
        }

        header {
            border-bottom: 1px solid var(--border);
            padding: 18px 40px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            backdrop-filter: blur(16px);
            position: sticky;
            top: 0;
            z-index: 50;
            background: rgba(12, 15, 23, 0.85);
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .logo-icon {
            width: 36px;
            height: 36px;
            background: linear-gradient(135deg, #3b82f6, #06b6d4);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 18px;
            box-shadow: 0 4px 12px var(--accent-glow);
        }

        .brand-title {
            font-size: 18px;
            font-weight: 700;
            letter-spacing: -0.02em;
        }

        .brand-subtitle {
            font-size: 12px;
            color: var(--text-secondary);
            font-weight: 400;
        }

        .header-actions {
            display: flex;
            gap: 12px;
            align-items: center;
        }

        .btn {
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
        }

        .btn:hover {
            background: var(--surface-hover);
            border-color: #3b4d6b;
            transform: translateY(-1px);
        }

        .btn-primary {
            background: var(--accent);
            border-color: var(--accent);
            box-shadow: 0 4px 12px var(--accent-glow);
        }

        .btn-primary:hover {
            background: #2563eb;
            border-color: #2563eb;
        }

        main {
            flex: 1;
            max-width: 1180px;
            margin: 0 auto;
            width: 100%;
            padding: 36px 24px;
            display: flex;
            flex-direction: column;
            gap: 32px;
        }

        /* Drop Zone */
        .dropzone-container {
            position: relative;
        }

        .dropzone {
            border: 2px dashed #2f3b52;
            border-radius: 16px;
            padding: 48px 32px;
            text-align: center;
            background: rgba(21, 26, 38, 0.6);
            backdrop-filter: blur(8px);
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
            cursor: pointer;
            position: relative;
            overflow: hidden;
        }

        .dropzone:hover, .dropzone.dragover {
            border-color: var(--accent);
            background: rgba(59, 130, 246, 0.05);
            box-shadow: 0 8px 32px rgba(59, 130, 246, 0.15);
            transform: scale(1.005);
        }

        .dropzone.dragover::after {
            content: "释放立即开始识别与翻译";
            position: absolute;
            inset: 0;
            background: rgba(12, 15, 23, 0.92);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            font-weight: 600;
            color: var(--accent);
            z-index: 10;
        }

        .drop-icon {
            font-size: 42px;
            margin-bottom: 16px;
            display: inline-block;
            transition: transform 0.3s ease;
        }

        .dropzone:hover .drop-icon {
            transform: translateY(-4px) scale(1.1);
        }

        .drop-title {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 8px;
        }

        .drop-hint {
            font-size: 13px;
            color: var(--text-secondary);
            margin-bottom: 24px;
        }

        .drop-options {
            display: flex;
            justify-content: center;
            gap: 16px;
            flex-wrap: wrap;
        }

        /* Controls Toolbar */
        .toolbar-panel {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 16px;
        }

        .control-group {
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 13px;
            color: var(--text-secondary);
        }

        .select-input {
            background: var(--bg);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 13px;
            outline: none;
            cursor: pointer;
        }

        .select-input:focus {
            border-color: var(--accent);
        }

        /* Task List Section */
        .tasks-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }

        .tasks-title {
            font-size: 16px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .badge-count {
            background: var(--surface-hover);
            color: var(--accent);
            border: 1px solid var(--border);
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }

        .task-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .task-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 18px 20px;
            display: flex;
            flex-direction: column;
            gap: 14px;
            transition: border-color 0.2s ease;
        }

        .task-card:hover {
            border-color: #3b4d6b;
        }

        .task-main {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 16px;
        }

        .task-info {
            display: flex;
            flex-direction: column;
            gap: 6px;
            flex: 1;
            min-width: 0;
        }

        .task-name-row {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }

        .task-name {
            font-size: 15px;
            font-weight: 600;
            word-break: break-all;
        }

        .task-path {
            font-size: 12px;
            color: var(--text-muted);
            font-family: monospace;
        }

        .pill {
            font-size: 11px;
            font-weight: 600;
            padding: 3px 8px;
            border-radius: 6px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .pill-vector {
            background: rgba(5, 150, 105, 0.15);
            color: #34d399;
            border: 1px solid rgba(5, 150, 105, 0.3);
        }

        .pill-scanned {
            background: rgba(217, 119, 6, 0.15);
            color: #fbbf24;
            border: 1px solid rgba(217, 119, 6, 0.3);
        }

        .pill-queued {
            background: rgba(100, 116, 139, 0.15);
            color: #94a3b8;
            border: 1px solid rgba(100, 116, 139, 0.3);
        }

        .pill-completed {
            background: rgba(16, 185, 129, 0.15);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .pill-failed {
            background: rgba(239, 68, 68, 0.15);
            color: #ef4444;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }

        .task-progress-bar {
            height: 4px;
            background: #1e2638;
            border-radius: 2px;
            overflow: hidden;
            width: 100%;
        }

        .task-progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #3b82f6, #10b981);
            transition: width 0.4s ease;
        }

        .task-outputs {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            padding-top: 6px;
            border-top: 1px solid rgba(255, 255, 255, 0.04);
        }

        .output-btn {
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.25);
            color: #93c5fd;
            padding: 5px 12px;
            border-radius: 6px;
            font-size: 12px;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s ease;
        }

        .output-btn:hover {
            background: rgba(59, 130, 246, 0.2);
            color: #bfdbfe;
            border-color: #3b82f6;
        }

        .empty-placeholder {
            text-align: center;
            padding: 48px 24px;
            color: var(--text-muted);
            font-size: 14px;
            border: 1px dashed var(--border);
            border-radius: 12px;
        }

        footer {
            border-top: 1px solid var(--border);
            padding: 20px 40px;
            text-align: center;
            font-size: 12px;
            color: var(--text-muted);
            margin-top: auto;
        }

        /* Animations */
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .anim-pulse {
            animation: pulse 1.5s infinite ease-in-out;
        }
    </style>
</head>
<body>

    <header>
        <div class="brand">
            <div class="logo-icon">⚡️</div>
            <div>
                <div class="brand-title">JParse 交互式工作台</div>
                <div class="brand-subtitle">双轨智能版面路由器 · OpenDataLoader 顶尖抽取与出版级高清重构</div>
            </div>
        </div>
        <div class="header-actions">
            <button class="btn" id="btnRevealOutbox">📂 打开产物目录 (outbox)</button>
            <button class="btn" id="btnRevealInbox">📥 打开投递箱 (inbox)</button>
        </div>
    </header>

    <main>
        <!-- Drag & Drop Zone -->
        <div class="dropzone-container">
            <div class="dropzone" id="dropzone">
                <div class="drop-icon">📑</div>
                <div class="drop-title">拖入单个 PDF，或拖入包含多个 PDF 的整套文件夹</div>
                <div class="drop-hint">系统将递归解析所有 PDF，自动判别矢量学术论文与历史扫描件并启动最优管线</div>
                <div class="drop-options">
                    <button class="btn btn-primary" id="btnPickFile">
                        📄 选择 PDF 文件
                    </button>
                    <button class="btn" id="btnPickFolder">
                        📁 选择整个文件夹
                    </button>
                    <input type="file" id="fileInput" multiple accept=".pdf" style="display: none;">
                    <input type="file" id="folderInput" webkitdirectory directory multiple style="display: none;">
                </div>
            </div>
        </div>

        <!-- Strategy & Settings Toolbar -->
        <div class="toolbar-panel">
            <input type="hidden" id="pipelineMode" value="auto">
            <div class="control-group">
                <span>翻译引擎:</span>
                <select id="serviceEngine" class="select-input">
                    <option value="bing">Bing 神经网络翻译 (免费高速 · 已应用分块防截断补丁)</option>
                    <option value="google">Google 翻译 (全球通道)</option>
                </select>
            </div>
        </div>

        <!-- Task Conversion Queue -->
        <section>
            <div class="tasks-header">
                <div class="tasks-title">
                    <span>转换任务列表</span>
                    <span class="badge-count" id="taskCountBadge">0</span>
                </div>
                <button class="btn" id="btnRefreshTasks" style="font-size: 12px; padding: 4px 10px;">🔄 刷新状态</button>
            </div>

            <div id="taskList" class="task-list">
                <div class="empty-placeholder">暂无正在处理或已完成的任务，请将 PDF 或文件夹拖放至上方区域</div>
            </div>
        </section>
    </main>

    <footer>
        LiteParse 自动化文档识别与翻译工程 · 离线私有化部署 · 遵循确定性代码与原子落盘规范
    </footer>

    <script nonce="__CSP_NONCE__">
        const dropzone = document.getElementById('dropzone');
        let isUploading = false;

        function esc(value) {
            return String(value === undefined || value === null ? '' : value)
                .replace(/[&<>"']/g, (c) => ({
                    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
                }[c]));
        }

        // Drag & Drop Handlers
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('dragover');
        });

        dropzone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('dragover');
        });

        dropzone.addEventListener('drop', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('dragover');

            const items = e.dataTransfer.items;
            if (!items || items.length === 0) return;

            const filesToUpload = [];
            
            // Read all entries in a directory (handles Chromium/WebKit 100-entry batch limit)
            async function readAllEntries(dirReader) {
                const entries = [];
                let batch;
                do {
                    batch = await new Promise((resolve) => {
                        dirReader.readEntries((results) => resolve(results || []));
                    });
                    if (batch && batch.length > 0) {
                        entries.push(...batch);
                    }
                } while (batch && batch.length > 0);
                return entries;
            }

            // Recursive reader for entries
            async function traverseEntry(entry, path = "") {
                if (entry.isFile) {
                    if (entry.name.toLowerCase().endsWith('.pdf') && !entry.name.startsWith('.')) {
                        const file = await new Promise((resolve) => entry.file(resolve));
                        filesToUpload.push({
                            file: file,
                            relativePath: path ? `${path}/${file.name}` : file.name
                        });
                    }
                } else if (entry.isDirectory) {
                    const reader = entry.createReader();
                    const entries = await readAllEntries(reader);
                    for (const child of entries) {
                        await traverseEntry(child, path ? `${path}/${entry.name}` : entry.name);
                    }
                }
            }

            for (let i = 0; i < items.length; i++) {
                const item = items[i];
                if (item.webkitGetAsEntry) {
                    const entry = item.webkitGetAsEntry();
                    if (entry) await traverseEntry(entry);
                } else if (item.kind === 'file') {
                    const file = item.getAsFile();
                    if (file && file.name.toLowerCase().endsWith('.pdf')) {
                        filesToUpload.push({ file, relativePath: file.name });
                    }
                }
            }

            if (filesToUpload.length > 0) {
                await uploadBatch(filesToUpload);
            }
        });

        function handleFileInput(fileList) {
            if (!fileList || fileList.length === 0) return;
            const files = [];
            for (let i = 0; i < fileList.length; i++) {
                const f = fileList[i];
                if (f.name.toLowerCase().endsWith('.pdf') && !f.name.startsWith('.')) {
                    files.push({
                        file: f,
                        relativePath: f.webkitRelativePath || f.name
                    });
                }
            }
            if (files.length > 0) {
                uploadBatch(files);
            }
        }

        async function uploadBatch(items) {
            try { await serviceUpdate; } catch (err) { alert('无法保存翻译设置：' + err); return; }
            const pipelineMode = document.getElementById('pipelineMode').value;
            const service = document.getElementById('serviceEngine').value;
            const failures = [];

            for (const item of items) {
                const formData = new FormData();
                formData.append('file', item.file);
                formData.append('relativePath', item.relativePath);
                formData.append('pipelineMode', pipelineMode);
                formData.append('service', service);

                try {
                    const response = await fetch('/api/upload', {
                        method: 'POST',
                        body: formData
                    });
                    if (!response.ok) {
                        const details = await response.json().catch(() => ({}));
                        throw new Error(details.error || ('HTTP ' + response.status));
                    }
                } catch (err) {
                    console.error('上传失败:', err);
                    failures.push(item.file.name + '：' + err.message);
                }
            }
            if (failures.length) alert('以下文件未能添加：\\n' + failures.join('\\n'));
            refreshTasks();
        }

        const serviceSelect = document.getElementById('serviceEngine');
        let serviceUpdate = fetch('/api/settings').then(r => {
            if (!r.ok) throw new Error('读取配置失败');
            return r.json();
        }).then(data => { serviceSelect.value = data.pdf2zh_service; });
        serviceSelect.addEventListener('change', () => {
            const selected = serviceSelect.value;
            serviceUpdate = serviceUpdate.catch(() => {}).then(async () => {
                const response = await fetch('/api/settings', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({pdf2zh_service: selected})
                });
                if (!response.ok) throw new Error('保存翻译配置失败');
                serviceSelect.value = selected;
            });
        });

        async function refreshTasks() {
            try {
                const res = await fetch('/api/tasks');
                const tasks = await res.json();
                renderTasks(tasks);
            } catch (err) {
                console.error('获取任务失败:', err);
            }
        }

        function renderTasks(tasks) {
            const badge = document.getElementById('taskCountBadge');
            badge.innerText = tasks.length;

            const container = document.getElementById('taskList');
            if (tasks.length === 0) {
                container.innerHTML = '<div class="empty-placeholder">暂无正在处理或已完成的任务，请将 PDF 或文件夹拖放至上方区域</div>';
                return;
            }

            container.innerHTML = tasks.map(t => {
                let statusBadge = '';
                if (t.status === 'completed') {
                    statusBadge = '<span class="pill pill-completed">✓ 已完成</span>';
                } else if (t.status === 'failed') {
                    statusBadge = `<span class="pill pill-failed">✕ 失败: ${esc(t.error || '未知错误')}</span>`;
                } else if (t.status === 'probing') {
                    statusBadge = '<span class="pill pill-vector anim-pulse">🔍 判别版面中...</span>';
                } else if (t.status === 'processing') {
                    statusBadge = '<span class="pill pill-vector anim-pulse">⚡️ 翻译排版重构中...</span>';
                } else {
                    statusBadge = '<span class="pill pill-queued">⏱ 排队中</span>';
                }

                let docTypeBadge = '';
                if (t.doc_type === 'vector') {
                    docTypeBadge = '<span class="pill pill-vector">📘 现代矢量学术论文</span>';
                } else if (t.doc_type === 'scanned') {
                    docTypeBadge = '<span class="pill pill-scanned">📜 历史扫描文献</span>';
                }

                const outputsHtml = (t.output_files || []).map(out => {
                    const icon = out.is_pdf ? '📄' : (out.is_html ? '🌐' : '📝');
                    return `<a href="/api/download?path=${encodeURIComponent(out.path)}" target="_blank" class="output-btn">${icon} ${esc(out.name)}</a>`;
                }).join('');

                return `
                <div class="task-card">
                    <div class="task-main">
                        <div class="task-info">
                            <div class="task-name-row">
                                <span class="task-name">${esc(t.filename)}</span>
                                ${docTypeBadge}
                                ${statusBadge}
                            </div>
                            <div class="task-path">${esc(t.relative_path)} · ${(Number(t.file_size || 0) / 1024).toFixed(1)} KB ${t.duration ? `· 耗时 ${Number(t.duration)}s` : ''}</div>
                        </div>
                    </div>
                    <div class="task-progress-bar">
                        <div class="task-progress-fill" style="width: ${t.progress || (t.status === 'completed' ? 100 : 15)}%;"></div>
                    </div>
                    ${outputsHtml ? `<div class="task-outputs">${outputsHtml}</div>` : ''}
                </div>
                `;
            }).join('');
        }

        async function revealOutbox() {
            await fetch('/api/reveal_outbox', { method: 'POST' });
        }

        async function revealInbox() {
            await fetch('/api/reveal_inbox', { method: 'POST' });
        }

        // Wire up controls here instead of inline onclick handlers, so the page
        // can run under a nonce-based CSP that blocks inline script.
        document.getElementById('btnRevealOutbox').addEventListener('click', revealOutbox);
        document.getElementById('btnRevealInbox').addEventListener('click', revealInbox);
        document.getElementById('btnPickFile').addEventListener('click', () => {
            document.getElementById('fileInput').click();
        });
        document.getElementById('btnPickFolder').addEventListener('click', () => {
            document.getElementById('folderInput').click();
        });
        document.getElementById('btnRefreshTasks').addEventListener('click', refreshTasks);
        document.getElementById('fileInput').addEventListener('change', (e) => handleFileInput(e.target.files));
        document.getElementById('folderInput').addEventListener('change', (e) => handleFileInput(e.target.files));

        // Auto polling every 2 seconds
        setInterval(refreshTasks, 2000);
        refreshTasks();
    </script>
</body>
</html>
"""


def reveal_in_finder(directory: Path) -> bool:
    """Open a directory in file manager (Finder / Explorer / xdg-open) only when it really exists.

    Module-level on purpose: tests patch this, because calling the real `open`
    on a throw-away TemporaryDirectory pops file manager windows on every test run.
    """
    target = Path(directory)
    if not target.is_dir():
        return False
    try:
        if sys.platform == "win32":
            os.startfile(str(target))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=False)
        else:
            subprocess.run(["xdg-open", str(target)], check=False)
    except OSError:
        return False
    return True


class LiteParseAppHandler(SimpleHTTPRequestHandler):
    """HTTP Request Handler for LiteParse interactive application.

    Only 127.0.0.1 is bound, but that alone does not stop other web pages from
    posting to this server (multipart POST needs no preflight) or a DNS-rebound
    page from reading it. Every request is therefore checked against the
    listener's own host, and every mutation additionally against Origin.
    """

    task_manager: ConversionTaskManager = None
    max_upload_bytes = 1024 * 1024 * 1024  # 1 GB

    def log_message(self, format, *args):
        # pythonw.exe has no stderr. The default HTTP handler writes to it
        # before sending a response and otherwise drops every connection.
        message = (format % args).translate(self._control_char_table)
        logger.info("%s - %s", self.address_string(), message)

    def _allowed_origins(self):
        port = self.server.server_address[1]
        return {
            "http://127.0.0.1:%d" % port,
            "http://localhost:%d" % port,
            "http://[::1]:%d" % port,
        }

    def _host_allowed(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        allowed = {origin.split("://", 1)[1] for origin in self._allowed_origins()}
        return host in allowed

    def _origin_allowed(self) -> bool:
        origin = (self.headers.get("Origin") or "").strip().rstrip("/").lower()
        if not origin:
            return True  # 非浏览器客户端（curl / 桌面端）没有 Origin
        return origin in self._allowed_origins()

    def do_GET(self):
        if not self._host_allowed():
            self.send_error(403, "Forbidden host")
            return
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            nonce = secrets.token_urlsafe(16)
            content = INDEX_HTML.replace("__CSP_NONCE__", nonce).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'nonce-%s'; style-src 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'self'; form-action 'self'; "
                "base-uri 'none'; frame-ancestors 'none'" % nonce,
            )
            self.end_headers()
            self.wfile.write(content)
            return

        if path == "/api/settings":
            try:
                configured_service = self.task_manager.configured_service()
            except RuntimeError as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
                return
            self._send_json(
                {
                    "outbox_dir": str(self.task_manager.outbox_dir),
                    "default_outbox_dir": str(self.task_manager.default_outbox_dir),
                    "pdf2zh_service": configured_service,
                }
            )
            return

        if path == "/api/tasks":
            tasks = self.task_manager.get_tasks()
            data = json.dumps(tasks, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/identity":
            self._send_json({"runtime_id": os.environ.get("JPARSE_RUNTIME_ID", ""),
                             "data_dir": str(self.task_manager.project_root)})
            return

        if path == "/api/download":
            query = parse_qs(parsed.query)
            file_path_str = query.get("path", [""])[0]
            if not file_path_str:
                self.send_error(400, "Missing path parameter")
                return
            outbox_root = self.task_manager.outbox_dir.resolve()
            try:
                target_path = Path(file_path_str).resolve()
                target_path.relative_to(outbox_root)
            except (OSError, ValueError):
                # 字符串前缀比较会放过 `outbox-backup/` 这类兄弟目录，必须用真实路径包含。
                self.send_error(403, "Access denied")
                return
            if not target_path.is_file() or target_path.name.startswith("."):
                self.send_error(404, "File not found")
                return

            mime, _ = mimetypes.guess_type(str(target_path))
            mime = mime or "application/octet-stream"
            file_size = target_path.stat().st_size
            quoted = quote(target_path.name, safe="")
            disposition = "inline" if target_path.suffix.lower() == ".pdf" else "attachment"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(file_size))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Disposition", "%s; filename*=UTF-8''%s" % (disposition, quoted))
            self.end_headers()

            with open(target_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        if not self._host_allowed():
            self.send_error(403, "Forbidden host")
            return
        if not self._origin_allowed():
            self.send_error(403, "Forbidden origin")
            return
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/reveal_outbox":
            self._send_json({"ok": True, "revealed": reveal_in_finder(self.task_manager.outbox_dir)})
            return

        if path == "/api/reveal_inbox":
            self._send_json({"ok": True, "revealed": reveal_in_finder(self.task_manager.inbox_dir)})
            return

        if path == "/api/settings":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(400, "Invalid Content-Length")
                return
            if content_length <= 0:
                self.send_error(400, "Empty body")
                return
            if content_length > 64 * 1024:
                self.send_error(413, "Settings payload too large")
                return

            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.send_error(400, "Expected a JSON object")
                return

            if not isinstance(payload, dict):
                self.send_error(400, "Expected a JSON object")
                return

            if "pdf2zh_service" in payload:
                if "outbox_dir" in payload:
                    self._send_json({"ok": False, "error": "请分别修改输出目录与翻译服务"}, status=400)
                    return
                try:
                    self.task_manager.set_translation_service(payload["pdf2zh_service"])
                except ValueError as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=400)
                    return
                self._send_json({"ok": True, "pdf2zh_service": self.task_manager.configured_service()})
                return

            try:
                target = self.task_manager.set_outbox_dir(payload.get("outbox_dir"))
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
                return

            self._send_json(
                {
                    "ok": True,
                    "outbox_dir": str(target),
                    "default_outbox_dir": str(self.task_manager.default_outbox_dir),
                }
            )
            return

        if path == "/api/upload":
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data"):
                self.send_error(400, "Expected multipart/form-data")
                return

            # Robust boundary parser (handles quotes and additional parameters like ; charset=utf-8)
            b_match = re.search(r'boundary=(?:"([^"]+)"|([^;\s]+))', content_type)
            if not b_match:
                self.send_error(400, "Missing boundary in multipart/form-data")
                return
            boundary = b_match.group(1) or b_match.group(2)
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(400, "Invalid Content-Length")
                return
            if content_length <= 0:
                self.send_error(400, "Empty body")
                return
            if content_length > self.max_upload_bytes:
                self.send_error(413, "Payload too large")
                return
            raw_data = self.rfile.read(content_length)

            parts = raw_data.split(f"--{boundary}".encode())
            file_bytes = None
            filename = None
            relative_path = ""
            pipeline_mode = "auto"
            service = None

            for part in parts:
                if not part or part == b"--\r\n" or part == b"--" or part.startswith(b"--"):
                    continue
                header_sep = part.find(b"\r\n\r\n")
                if header_sep == -1:
                    continue
                headers_raw = part[:header_sep].decode("utf-8", errors="ignore")
                # Remove exactly the single trailing multipart MIME CRLF delimiter, preserving binary PDF bytes
                body = part[header_sep + 4 :]
                if body.endswith(b"\r\n"):
                    body = body[:-2]
                elif body.endswith(b"\n"):
                    body = body[:-1]

                if 'name="file"' in headers_raw:
                    fn_match = re.search(r'filename="([^"]+)"', headers_raw)
                    if fn_match:
                        filename = fn_match.group(1)
                    file_bytes = body
                elif 'name="relativePath"' in headers_raw:
                    relative_path = body.decode("utf-8", errors="ignore").strip()
                elif 'name="pipelineMode"' in headers_raw:
                    pipeline_mode = body.decode("utf-8", errors="ignore").strip()
                elif 'name="service"' in headers_raw:
                    service = body.decode("utf-8", errors="ignore").strip()

            if not filename or file_bytes is None or len(file_bytes) == 0:
                self.send_error(400, "No file uploaded")
                return

            try:
                configured = self.task_manager.configured_service()
            except RuntimeError as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
                return
            if service and service != configured:
                self._send_json({"ok": False, "error": "翻译设置已更改，请重新选择服务后重试"}, status=409)
                return
            service = configured

            if not filename.lower().endswith(".pdf"):
                self.send_error(400, "Only PDF files supported")
                return

            # 先投递到 inbox 的隐藏文件，再原子认领到 processing；监控器忽略隐藏文件。
            safe_name = Path(filename).name
            if not safe_name or safe_name in {".", ".."}:
                self.send_error(400, "Invalid filename")
                return
            stem = self.task_manager.reserve_stem(Path(safe_name).stem)
            claimed = self.task_manager.processing_dir / (stem + ".pdf")
            tmp_save = self.task_manager.inbox_dir / (".%s.%s.pdf" % (stem, time.time_ns()))
            try:
                tmp_save.write_bytes(file_bytes)
                tmp_save.replace(claimed)
            except OSError:
                tmp_save.unlink(missing_ok=True)
                claimed.unlink(missing_ok=True)
                self.task_manager.release_reservation(stem)
                self.send_error(500, "Failed to store upload")
                return

            task = self.task_manager.add_file(
                file_path=claimed,
                relative_path=relative_path or safe_name,
                options={
                    "pipeline_mode": pipeline_mode,
                    "service": service,
                },
            )

            self._send_json({"ok": True, "task": task})
            return

        self.send_error(404, "Not Found")

    def _send_json(self, data: Dict[str, Any], status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def _instance_serving(port: int) -> bool:
    """True when a LiteParse workbench already answers on this loopback port."""
    try:
        endpoint = "/api/identity" if os.environ.get("JPARSE_RUNTIME_ID") else "/api/tasks"
        with local_urlopen("http://127.0.0.1:%d%s" % (port, endpoint), timeout=1.5) as response:
            return response.status == 200 and (not os.environ.get("JPARSE_RUNTIME_ID") or identity_matches(json.load(response)))
    except Exception:
        return False


def get_data_root() -> Path:
    """Keep portable-app user files outside the bundled, replaceable code."""
    configured = os.environ.get("JPARSE_DATA_DIR")
    return Path(configured).expanduser().resolve() if configured else _PROJECT_ROOT


def run_server(port: int = 8765, open_browser: bool = True):
    """Start the LiteParse Interactive Application server."""
    project_root = get_data_root()
    if os.environ.get("JPARSE_DATA_DIR"):
        log_dir = project_root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "desktop.log", maxBytes=1048576, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        config_path = project_root / "config.json"
        if not config_path.exists():
            shutil.copy2(_PROJECT_ROOT / "config.json", config_path)
    task_mgr = ConversionTaskManager(project_root=project_root)
    LiteParseAppHandler.task_manager = task_mgr

    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), LiteParseAppHandler)
    except OSError as exc:
        # 不再静默换端口：桌面端写死 8765，换了端口它只会永远“连接失败”。
        # 端口已被占用且确实是本应用，就直接复用那个实例。
        if _instance_serving(port):
            print("端口 %d 上已有 LiteParse 工作台实例在运行，直接复用。" % port)
            return
        print("无法监听 127.0.0.1:%d：%s" % (port, exc), file=sys.stderr)
        raise SystemExit(1)

    url = f"http://127.0.0.1:{port}"
    try:
        mark_active_runtime(port)
    except OSError:
        httpd.server_close()
        raise
    if os.environ.get("JPARSE_WATCH_INBOX") == "1":
        threading.Thread(target=task_mgr.watch_inbox, name="JParseInbox", daemon=True).start()
    print(f"🚀 LiteParse 交互式工作台已启动: {url}")
    print("📁 支持将单个 PDF 或整套文件夹拖拽至网页，直接识别并转换。")

    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            try:
                if sys.platform == "darwin":
                    subprocess.run(["open", url], check=False)
                elif sys.platform == "win32":
                    os.startfile(url)
            except Exception:
                pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止服务...")
        httpd.shutdown()


if __name__ == "__main__":
    port = 8765
    for arg in sys.argv[1:]:
        if arg.isdigit():
            port = int(arg)
    open_b = "--no-open" not in sys.argv and "--no-browser" not in sys.argv
    run_server(port=port, open_browser=open_b)
