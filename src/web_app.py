"""LiteParse Interactive Web Application with Folder Drag-and-Drop and Dual-Track Processing.

Uses standard Python HTTP server (zero external dependencies) and modern HTML5 Web API.
Supports recursive folder drops, real-time conversion progress, and macOS Finder integration.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.router import probe_pdf_document_type, route_and_process_pdf

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
        self.outbox_dir = self.project_root / "outbox"
        self.processed_dir = self.project_root / "processed"
        self.failed_dir = self.project_root / "failed"

        for d in [self.inbox_dir, self.outbox_dir, self.processed_dir, self.failed_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.tasks: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="LiteParseWorker")
        self._subscribers: List[threading.Event] = []

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
        self._notify_subscribers()
        self._executor.submit(self._run_task, task_id)
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

    def _run_task(self, task_id: str):
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
            config = {
                "force_pipeline": opts.get("pipeline_mode", "auto"),
                "pdf2zh_service": opts.get("service", "bing"),
                "pdf2zh_threads": 4,
            }
            output_paths = route_and_process_pdf(
                pdf_path=input_path,
                outbox_dir=self.outbox_dir,
                config=config,
            )

            # 3. Archive original file into processed/
            dest_processed = self.processed_dir / input_path.name
            if input_path.exists() and input_path.parent == self.inbox_dir:
                if dest_processed.exists():
                    dest_processed.unlink()
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
            # Move to failed/ if in inbox
            if input_path.exists() and input_path.parent == self.inbox_dir:
                try:
                    dest_failed = self.failed_dir / input_path.name
                    if dest_failed.exists():
                        dest_failed.unlink()
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
    <title>LiteParse 文档智能中枢 · 双轨极速转换平台</title>
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
                <div class="brand-title">LiteParse 交互式工作台</div>
                <div class="brand-subtitle">双轨智能版面路由器 · 现代矢量与历史扫描一体化</div>
            </div>
        </div>
        <div class="header-actions">
            <button class="btn" onclick="revealOutbox()">📂 打开产物目录 (outbox)</button>
            <button class="btn" onclick="revealInbox()">📥 打开投递箱 (inbox)</button>
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
                    <button class="btn btn-primary" onclick="document.getElementById('fileInput').click()">
                        📄 选择 PDF 文件
                    </button>
                    <button class="btn" onclick="document.getElementById('folderInput').click()">
                        📁 选择整个文件夹
                    </button>
                    <input type="file" id="fileInput" multiple accept=".pdf" style="display: none;" onchange="handleFileInput(this.files)">
                    <input type="file" id="folderInput" webkitdirectory directory multiple style="display: none;" onchange="handleFileInput(this.files)">
                </div>
            </div>
        </div>

        <!-- Strategy & Settings Toolbar -->
        <div class="toolbar-panel">
            <div class="control-group">
                <span>智能路由策略:</span>
                <select id="pipelineMode" class="select-input">
                    <option value="auto">🤖 智能自动判别 (Auto Dual-Track 推荐)</option>
                    <option value="vector">📘 强制现代矢量论文流 (pdf2zh 无损擦除)</option>
                    <option value="scanned">📜 强制历史扫描文献流 (LiteParse 原位双层)</option>
                </select>
            </div>
            <div class="control-group">
                <span>翻译引擎:</span>
                <select id="serviceEngine" class="select-input">
                    <option value="bing">Bing 神经网络翻译 (免费高速 · 已应用分块防截断补丁)</option>
                    <option value="google">Google 翻译 (全球通道)</option>
                    <option value="offline">离线 CTranslate2 INT8 模型 (100% 局域离线)</option>
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
                <button class="btn" style="font-size: 12px; padding: 4px 10px;" onclick="refreshTasks()">🔄 刷新状态</button>
            </div>

            <div id="taskList" class="task-list">
                <div class="empty-placeholder">暂无正在处理或已完成的任务，请将 PDF 或文件夹拖放至上方区域</div>
            </div>
        </section>
    </main>

    <footer>
        LiteParse 自动化文档识别与翻译工程 · 离线私有化部署 · 遵循确定性代码与原子落盘规范
    </footer>

    <script>
        const dropzone = document.getElementById('dropzone');
        let isUploading = false;

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
                    const entries = await new Promise((resolve) => {
                        reader.readEntries((results) => resolve(results || []));
                    });
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
            const pipelineMode = document.getElementById('pipelineMode').value;
            const service = document.getElementById('serviceEngine').value;

            for (const item of items) {
                const formData = new FormData();
                formData.append('file', item.file);
                formData.append('relativePath', item.relativePath);
                formData.append('pipelineMode', pipelineMode);
                formData.append('service', service);

                try {
                    await fetch('/api/upload', {
                        method: 'POST',
                        body: formData
                    });
                } catch (err) {
                    console.error('上传失败:', err);
                }
            }
            refreshTasks();
        }

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
                    statusBadge = `<span class="pill pill-failed">✕ 失败: ${t.error || '未知错误'}</span>`;
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
                    return `<a href="/api/download?path=${encodeURIComponent(out.path)}" target="_blank" class="output-btn">${icon} ${out.name}</a>`;
                }).join('');

                return `
                <div class="task-card">
                    <div class="task-main">
                        <div class="task-info">
                            <div class="task-name-row">
                                <span class="task-name">${t.filename}</span>
                                ${docTypeBadge}
                                ${statusBadge}
                            </div>
                            <div class="task-path">${t.relative_path} · ${(t.file_size / 1024).toFixed(1)} KB ${t.duration ? `· 耗时 ${t.duration}s` : ''}</div>
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

        // Auto polling every 2 seconds
        setInterval(refreshTasks, 2000);
        refreshTasks();
    </script>
</body>
</html>
"""


class LiteParseAppHandler(SimpleHTTPRequestHandler):
    """HTTP Request Handler for LiteParse interactive application."""

    task_manager: ConversionTaskManager = None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            content = INDEX_HTML.encode("utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path == "/api/tasks":
            tasks = self.task_manager.get_tasks()
            data = json.dumps(tasks, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/download":
            query = parse_qs(parsed.query)
            file_path_str = query.get("path", [""])[0]
            if not file_path_str:
                self.send_error(400, "Missing path parameter")
                return
            target_path = Path(file_path_str).resolve()
            # Security sandbox check: must be in outbox or project root
            if not str(target_path).startswith(str(self.task_manager.project_root)):
                self.send_error(403, "Access denied")
                return
            if not target_path.exists() or not target_path.is_file():
                self.send_error(404, "File not found")
                return

            mime, _ = mimetypes.guess_type(str(target_path))
            mime = mime or "application/octet-stream"
            file_size = target_path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(file_size))
            if target_path.suffix.lower() == ".pdf":
                self.send_header("Content-Disposition", f'inline; filename="{target_path.name}"')
            else:
                self.send_header("Content-Disposition", f'attachment; filename="{target_path.name}"')
            self.end_headers()

            with open(target_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/reveal_outbox":
            try:
                subprocess.run(["open", str(self.task_manager.outbox_dir)])
            except Exception:
                pass
            self._send_json({"ok": True})
            return

        if path == "/api/reveal_inbox":
            try:
                subprocess.run(["open", str(self.task_manager.inbox_dir)])
            except Exception:
                pass
            self._send_json({"ok": True})
            return

        if path == "/api/upload":
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data"):
                self.send_error(400, "Expected multipart/form-data")
                return

            # Simple robust multipart parser for Python standard library
            boundary = content_type.split("boundary=")[-1].strip()
            content_length = int(self.headers.get("Content-Length", 0))
            raw_data = self.rfile.read(content_length)

            parts = raw_data.split(f"--{boundary}".encode())
            file_bytes = None
            filename = None
            relative_path = ""
            pipeline_mode = "auto"
            service = "bing"

            for part in parts:
                if not part or part == b"--\r\n" or part == b"--":
                    continue
                header_sep = part.find(b"\r\n\r\n")
                if header_sep == -1:
                    continue
                headers_raw = part[:header_sep].decode("utf-8", errors="ignore")
                body = part[header_sep + 4 :].rstrip(b"\r\n")

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

            if not filename or not file_bytes:
                self.send_error(400, "No file uploaded")
                return

            # Save uploaded file to inbox/
            safe_name = Path(filename).name
            save_path = self.task_manager.inbox_dir / safe_name
            # Atomic save
            tmp_save = self.task_manager.inbox_dir / f".{safe_name}.tmp"
            tmp_save.write_bytes(file_bytes)
            tmp_save.replace(save_path)

            task = self.task_manager.add_file(
                file_path=save_path,
                relative_path=relative_path or safe_name,
                options={
                    "pipeline_mode": pipeline_mode,
                    "service": service,
                },
            )

            self._send_json({"ok": True, "task": task})
            return

        self.send_error(404, "Not Found")

    def _send_json(self, data: Dict[str, Any]):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(port: int = 8765, open_browser: bool = True):
    """Start the LiteParse Interactive Application server."""
    project_root = Path(__file__).resolve().parent.parent
    task_mgr = ConversionTaskManager(project_root=project_root)
    LiteParseAppHandler.task_manager = task_mgr

    server_address = ("127.0.0.1", port)
    try:
        httpd = ThreadingHTTPServer(server_address, LiteParseAppHandler)
    except OSError:
        # Fallback to alternate port
        port = port + 1
        server_address = ("127.0.0.1", port)
        httpd = ThreadingHTTPServer(server_address, LiteParseAppHandler)

    url = f"http://127.0.0.1:{port}"
    print(f"🚀 LiteParse 交互式工作台已启动: {url}")
    print("📁 支持将单个 PDF 或整套文件夹拖拽至网页，直接识别并转换。")

    if open_browser:
        try:
            subprocess.run(["open", url])
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止服务...")
        httpd.shutdown()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    open_b = "--no-open" not in sys.argv
    run_server(port=port, open_browser=open_b)
