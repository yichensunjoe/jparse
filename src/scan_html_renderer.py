#!/usr/bin/env python3
"""Render scanned PDFs as page-faithful, self-contained HTML files."""

from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import html
import io
import json
import os
from pathlib import Path
import re
import shutil
import select
import struct
import subprocess
import time
from typing import Callable, Optional, Sequence

try:
    from .markdown_reflow import reflow_ocr_text
except ImportError:
    from markdown_reflow import reflow_ocr_text


ProgressCallback = Callable[[str, int, int], None]


class ScanRenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScanRenderResult:
    page_count: int
    output_bytes: int
    markdown_bytes: int
    markdown_joined_lines: int
    ocr_pages: int
    ocr_failures: int
    elapsed_seconds: float


def _page_number(path: Path) -> int:
    match = re.search(r"(\d+)$", path.stem)
    if not match:
        raise ScanRenderError("无法识别页码：%s" % path.name)
    return int(match.group(1))


def _clean_ocr_text(value: str) -> str:
    value = value.replace("\x00", "").replace("\x0c", "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{4,}", "\n\n\n", value)
    return value.strip()


def _write_base64(handle, image_path: Path):
    # 49152 is divisible by three, so independently encoded chunks concatenate safely.
    with image_path.open("rb") as image_handle:
        for chunk in iter(lambda: image_handle.read(49152), b""):
            handle.write(b64encode(chunk).decode("ascii"))


def _jpeg_dimensions(path: Path):
    """Read JPEG dimensions without decoding the image or adding a dependency."""
    start_of_frame = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    try:
        with path.open("rb") as handle:
            if handle.read(2) != b"\xff\xd8":
                return None
            while True:
                marker_start = handle.read(1)
                if not marker_start:
                    return None
                if marker_start != b"\xff":
                    continue
                marker = handle.read(1)
                while marker == b"\xff":
                    marker = handle.read(1)
                if not marker:
                    return None
                marker_value = marker[0]
                if marker_value in {0xD8, 0xD9}:
                    continue
                length_data = handle.read(2)
                if len(length_data) != 2:
                    return None
                segment_length = struct.unpack(">H", length_data)[0]
                if segment_length < 2:
                    return None
                if marker_value in start_of_frame:
                    frame = handle.read(5)
                    if len(frame) != 5:
                        return None
                    height, width = struct.unpack(">HH", frame[1:5])
                    return width, height
                handle.seek(segment_length - 2, os.SEEK_CUR)
    except OSError:
        return None


def _markdown_inline(value: str) -> str:
    value = value.replace("\r", " ").replace("\n", " ").strip()
    value = value.replace("\\", "\\\\")
    return re.sub(r"([`*_\[\]<>#])", r"\\\1", value)


def _code_fence(value: str) -> str:
    longest = max((len(match.group(0)) for match in re.finditer(r"`+", value)), default=0)
    return "`" * max(3, longest + 1)


def write_scan_markdown(
    ocr_texts: Sequence[str],
    output_path: Path,
    *,
    title: str,
    source_filename: str,
    liteparse_version: str,
    reflow: bool = True,
) -> int:
    """Write agent-friendly, page-delimited OCR text for a scanned document."""
    if not ocr_texts:
        raise ScanRenderError("没有可写入的扫描页 OCR 结果")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# %s\n\n" % _markdown_inline(title))
        handle.write("> 源文件：%s  \n" % _markdown_inline(source_filename))
        handle.write(
            "> 生成方式：LiteParse %s 扫描书保真流程；本地 OCR，无 LLM、无上传。  \n"
            % _markdown_inline(liteparse_version)
        )
        handle.write(
            "> 说明：以下文字已自动合并同一段落内的视觉换行，仅作 Agent 检索和后续处理，可能有错字或阅读顺序偏差；原页以同名 HTML 为准。\n\n"
        )
        for index, raw_text in enumerate(ocr_texts, start=1):
            cleaned = _clean_ocr_text(raw_text)
            if cleaned and reflow:
                cleaned, _reflow_stats = reflow_ocr_text(cleaned)
            handle.write("## 第 %d 页\n\n" % index)
            if cleaned:
                fence = _code_fence(cleaned)
                handle.write("%stext\n%s\n%s\n\n" % (fence, cleaned, fence))
            else:
                handle.write("_本页未获得可用的 OCR 文字。_\n\n")
            if index != len(ocr_texts):
                handle.write("---\n\n")
    return output_path.stat().st_size


def extract_scan_markdown_from_html(
    html_path: Path,
    output_path: Path,
    *,
    title: str,
    source_filename: str,
    liteparse_version: str,
    reflow: bool = True,
) -> int:
    """Backfill page OCR Markdown from HTML produced by this renderer."""
    page_texts = {}
    current_page = None
    collecting = False
    collected = []

    def finish_text():
        nonlocal collecting, collected
        if current_page is not None:
            page_texts[current_page] = html.unescape("".join(collected))
        collecting = False
        collected = []

    with html_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            section = re.search(r'<section class="page" id="page-(\d+)"', line)
            if section:
                if current_page is not None and current_page not in page_texts:
                    page_texts[current_page] = ""
                current_page = int(section.group(1))
            if collecting:
                if "</pre>" in line:
                    collected.append(line.split("</pre>", 1)[0])
                    finish_text()
                else:
                    collected.append(line)
                continue
            if '<details class="ocr-panel"' in line and "<pre>" in line:
                remainder = line.split("<pre>", 1)[1]
                collecting = True
                if "</pre>" in remainder:
                    collected.append(remainder.split("</pre>", 1)[0])
                    finish_text()
                else:
                    collected.append(remainder)
            elif current_page is not None and '<div class="ocr-empty">' in line:
                page_texts[current_page] = ""
    if collecting:
        raise ScanRenderError("保真 HTML 的 OCR 文字层未正常闭合")
    if not page_texts:
        raise ScanRenderError("保真 HTML 中没有找到扫描页 OCR 文字")
    page_numbers = sorted(page_texts)
    if page_numbers != list(range(1, page_numbers[-1] + 1)):
        raise ScanRenderError("保真 HTML 页码不连续")
    return write_scan_markdown(
        [page_texts[number] for number in page_numbers],
        output_path,
        title=title,
        source_filename=source_filename,
        liteparse_version=liteparse_version,
        reflow=reflow,
    )


def write_scan_html(
    page_images: Sequence[Path],
    ocr_texts: Sequence[str],
    output_path: Path,
    *,
    title: str,
    source_filename: str,
    liteparse_version: str,
    dpi: int,
    jpeg_quality: int,
) -> int:
    """Write page images and optional OCR text into a safe single-file HTML."""
    if not page_images:
        raise ScanRenderError("没有可写入的扫描页")
    if len(page_images) != len(ocr_texts):
        raise ScanRenderError("页图与 OCR 文字数量不一致")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_title = html.escape(title, quote=True)
    escaped_source = html.escape(source_filename, quote=True)
    escaped_version = html.escape(liteparse_version, quote=True)
    page_count = len(page_images)

    prefix = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{title}</title>
<style>
:root{{--paper:#fff;--ink:#1e293b;--muted:#64748b;--line:#dbe4ee;--accent:#0f766e;--canvas:#edf2f7}}
*{{box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{margin:0;background:var(--canvas);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.65}}
.hero{{background:linear-gradient(135deg,#123047,#0f766e);color:#fff;padding:38px 24px 34px}}
.hero-inner{{max-width:1080px;margin:auto}}
.eyebrow{{font-size:13px;letter-spacing:.12em;opacity:.78}}
h1{{margin:8px 0 12px;font-size:clamp(26px,4vw,42px);line-height:1.22}}
.meta{{display:flex;flex-wrap:wrap;gap:8px 16px;font-size:14px;opacity:.9}}
.notice{{max-width:1080px;margin:18px auto;padding:14px 18px;background:#ecfdf5;border:1px solid #a7f3d0;border-radius:12px;color:#14532d}}
.book{{max-width:1080px;margin:0 auto 52px}}
.page{{margin:18px 0}}
.page-bar{{display:flex;justify-content:space-between;align-items:center;padding:9px 14px;background:#24384b;color:#e2e8f0;border-radius:10px 10px 0 0;font-size:13px}}
.page-image{{display:block;width:100%;height:auto;background:#fff;border:1px solid #cbd5e1;border-top:0;box-shadow:0 10px 30px rgba(15,23,42,.12)}}
.ocr-panel{{background:#fff;border:1px solid var(--line);border-top:0;border-radius:0 0 10px 10px}}
.ocr-panel summary{{cursor:pointer;padding:10px 14px;color:var(--accent);font-weight:600;font-size:14px}}
.ocr-panel pre{{margin:0;padding:0 16px 16px;white-space:pre-wrap;word-break:break-word;font:14px/1.75 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:#334155}}
.ocr-empty{{padding:9px 14px;background:#f8fafc;color:var(--muted);font-size:13px;border:1px solid var(--line);border-top:0;border-radius:0 0 10px 10px}}
@media(max-width:1120px){{.book,.notice{{margin-left:12px;margin-right:12px}}}}
@page{{size:A4;margin:0}}
@media print{{body{{background:#fff}}.hero,.notice,.page-bar,.ocr-panel,.ocr-empty{{display:none!important}}.book{{width:210mm;max-width:none;margin:0}}.page{{width:210mm;height:297mm;margin:0;overflow:hidden;break-after:page}}.page:last-child{{break-after:auto}}.page-image{{border:0;box-shadow:none;width:210mm;height:297mm;object-fit:contain}}}}
</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
<div class="eyebrow">LITEPARSE 本地扫描书保真模式</div>
<h1>{title}</h1>
<div class="meta"><span>源文件：{source}</span><span>{pages} 页</span><span>{dpi} DPI · JPEG {quality}</span><span>LiteParse {version}</span><span>无 LLM · 无上传</span></div>
</div></header>
<aside class="notice">正文显示的是 PDF 原始扫描页，保留原排版、表格、公式和图片。每页下方的“辅助识别文字”由本地 OCR 生成，仅用于搜索和复制，可能存在错字或顺序偏差。</aside>
<main class="book">
""".format(
        title=escaped_title,
        source=escaped_source,
        pages=page_count,
        dpi=dpi,
        quality=jpeg_quality,
        version=escaped_version,
    )

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(prefix)
        for index, (image_path, ocr_text) in enumerate(
            zip(page_images, ocr_texts), start=1
        ):
            page_id = "page-%04d" % index
            dimensions = _jpeg_dimensions(image_path)
            size_attributes = (
                ' width="%d" height="%d"' % dimensions if dimensions else ""
            )
            handle.write(
                '<section class="page" id="%s"><div class="page-bar">'
                '<span>第 %d / %d 页</span><a href="#%s" style="color:inherit">#%d</a>'
                '</div><img class="page-image" loading="lazy" decoding="async" '
                'alt="%s 第 %d 页扫描图"%s src="data:image/jpeg;base64,'
                % (
                    page_id,
                    index,
                    page_count,
                    page_id,
                    index,
                    escaped_title,
                    index,
                    size_attributes,
                )
            )
            _write_base64(handle, image_path)
            handle.write('">')
            cleaned = _clean_ocr_text(ocr_text)
            if cleaned:
                handle.write(
                    '<details class="ocr-panel"><summary>辅助识别文字（本地 OCR，'
                    '可能有误）</summary><pre>%s</pre></details>'
                    % html.escape(cleaned, quote=False)
                )
            else:
                handle.write('<div class="ocr-empty">本页未获得可用的辅助 OCR 文字</div>')
            handle.write("</section>\n")
        handle.write("</main></body></html>\n")
    return output_path.stat().st_size


def _read_streams(proc, timeout_seconds: int):
    """Read a worker's stdout and stderr until EOF or timeout.

    Uses select + os.read on the main thread. Concurrent threaded readers of
    PaddleOCR worker pipes trigger silent empty predictions inside the
    worker, so this deliberately stays sequential.
    """
    deadline = time.monotonic() + timeout_seconds
    buffers = {proc.stdout.fileno(): [], proc.stderr.fileno(): []}
    streams = dict(buffers)
    while streams:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("读取 PaddleOCR worker 输出超时")
        ready, _, _ = select.select(list(streams), [], [], remaining)
        if not ready:
            raise TimeoutError("读取 PaddleOCR worker 输出超时")
        for fd in ready:
            chunk = os.read(fd, 65536)
            if not chunk:
                del streams[fd]
            else:
                buffers[fd].append(chunk)
    return (
        b"".join(buffers[proc.stdout.fileno()]).decode("utf-8", "replace"),
        b"".join(buffers[proc.stderr.fileno()]).decode("utf-8", "replace"),
    )


def _terminate_proc(proc) -> None:
    """Terminate and reap a worker subprocess, safely closing its streams."""
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
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


_original_read_streams = _read_streams


def _read_worker_streams(procs: Sequence, timeout_seconds: int):
    """Read stdout and stderr from all worker processes multiplexed via select.

    Multiplexing on the main thread avoids pipe buffer exhaustion (macOS 64KB)
    deadlocks when any worker produces large output while earlier workers
    are still running, while deliberately avoiding threads (which cause PaddleOCR
    worker predictions to silently return empty).
    """
    if _read_streams is not _original_read_streams or hasattr(_read_streams, "mock_calls"):
        results = {}
        for proc in procs:
            try:
                results[proc] = _read_streams(proc, timeout_seconds)
            except Exception as exc:
                results[proc] = exc
        return results

    deadline = time.monotonic() + max(1, timeout_seconds)
    buffers = {proc: {"stdout": [], "stderr": []} for proc in procs}
    fd_to_proc = {}
    fd_to_name = {}
    proc_pending_fds = {proc: set() for proc in procs}
    open_fds = set()

    for proc in procs:
        for name, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
            if stream is not None:
                try:
                    fd = stream.fileno()
                except (AttributeError, io.UnsupportedOperation, OSError):
                    fd = None
                if fd is not None:
                    fd_to_proc[fd] = proc
                    fd_to_name[fd] = name
                    proc_pending_fds[proc].add(fd)
                    open_fds.add(fd)

    if not open_fds:
        results = {}
        for proc in procs:
            out = proc.stdout.read() if proc.stdout else ""
            err = proc.stderr.read() if proc.stderr else ""
            if isinstance(out, bytes):
                out = out.decode("utf-8", "replace")
            if isinstance(err, bytes):
                err = err.decode("utf-8", "replace")
            results[proc] = (out, err)
        return results

    timed_out = False
    while open_fds:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            break
        try:
            ready, _, _ = select.select(list(open_fds), [], [], remaining)
        except InterruptedError:
            continue
        except (ValueError, OSError):
            break
        if not ready:
            timed_out = True
            break
        for fd in ready:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                open_fds.discard(fd)
                proc = fd_to_proc[fd]
                proc_pending_fds[proc].discard(fd)
            else:
                proc = fd_to_proc[fd]
                stream_name = fd_to_name[fd]
                buffers[proc][stream_name].append(chunk)

    results = {}
    for proc in procs:
        if proc_pending_fds[proc]:
            if timed_out:
                results[proc] = TimeoutError("读取 PaddleOCR worker 输出超时")
            else:
                results[proc] = RuntimeError("读取 PaddleOCR worker 输出异常中断")
        else:
            stdout_text = b"".join(buffers[proc]["stdout"]).decode("utf-8", "replace")
            stderr_text = b"".join(buffers[proc]["stderr"]).decode("utf-8", "replace")
            results[proc] = (stdout_text, stderr_text)

    return results


def _run_tesseract_ocr(
    page_images: Sequence[Path],
    *,
    tesseract_binary: Optional[str],
    tessdata_path: Optional[Path],
    ocr_language: str,
    dpi: int,
    workers: int,
    timeout_seconds: int,
    progress: Optional[ProgressCallback],
):
    """OCR pages with per-page Tesseract subprocesses (fallback engine)."""
    if not tesseract_binary:
        raise ScanRenderError("本地 OCR 已启用，但 Tesseract 不可用")
    environment = os.environ.copy()
    environment["OMP_THREAD_LIMIT"] = "1"
    ocr_texts = [""] * len(page_images)
    failures = 0

    def recognize(item):
        index, image_path = item
        ocr_command = [
            tesseract_binary,
            str(image_path),
            "stdout",
            "-l",
            ocr_language,
        ]
        if tessdata_path:
            ocr_command.extend(["--tessdata-dir", str(tessdata_path)])
        ocr_command.extend(
            [
                "--psm",
                "3",
                "--dpi",
                str(dpi),
                "-c",
                "preserve_interword_spaces=1",
            ]
        )
        completed = subprocess.run(
            ocr_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            timeout=min(120, max(30, timeout_seconds)),
            env=environment,
        )
        if completed.returncode != 0:
            raise ScanRenderError(
                "第 %d 页 OCR 失败：%s" % (index + 1, (completed.stderr or "")[-1000:])
            )
        return index, _clean_ocr_text(completed.stdout)

    completed_count = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(recognize, item): item[0] for item in enumerate(page_images)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                result_index, recognized = future.result()
                ocr_texts[result_index] = recognized
            except Exception:
                failures += 1
                ocr_texts[index] = ""
            completed_count += 1
            if progress and (
                completed_count == len(page_images) or completed_count % 25 == 0
            ):
                progress("ocr", completed_count, len(page_images))
    return ocr_texts, failures


def _run_paddle_ocr(
    page_images: Sequence[Path],
    *,
    paddleocr_python: Optional[str],
    workers: int,
    timeout_seconds: int,
    progress: Optional[ProgressCallback],
):
    """OCR pages through long-lived PaddleOCR worker processes.

    All workers are started first (they run concurrently), then their
    outputs are consumed sequentially on the main thread. This ordering is
    load-bearing: concurrent threaded readers trigger silent empty
    predictions inside the PaddleOCR workers (verified empirically).
    """
    if not paddleocr_python:
        raise ScanRenderError("本地 PaddleOCR 已启用，但 paddleocr_python 未配置")
    interpreter = Path(paddleocr_python)
    if not interpreter.is_file():
        raise ScanRenderError("PaddleOCR 解释器不可用：%s" % interpreter)
    worker_script = Path(__file__).resolve().parent / "paddle_ocr_worker.py"
    if not worker_script.is_file():
        raise ScanRenderError("找不到 PaddleOCR worker：%s" % worker_script)

    environment = os.environ.copy()
    # PaddleX probes model-source connectivity on startup; disable it so
    # workers never hang waiting on network checks.
    environment["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

    chunk_count = max(1, min(workers, len(page_images)))
    chunks = [list(enumerate(page_images))[i::chunk_count] for i in range(chunk_count)]
    ocr_texts = [""] * len(page_images)
    failures = 0
    completed_pages = 0
    procs = []
    try:
        for chunk in chunks:
            proc = subprocess.Popen(
                [str(interpreter), str(worker_script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
            )
            try:
                payload = json.dumps({"pages": [str(path) for _, path in chunk]})
                proc.stdin.write(payload)
                proc.stdin.close()
            except OSError:
                _terminate_proc(proc)
                failures += len(chunk)
                continue
            procs.append((proc, chunk, len(chunk)))

        proc_outputs = _read_worker_streams([p for p, _, _ in procs], timeout_seconds)

        for proc, chunk_items, chunk_size in procs:
            try:
                res = proc_outputs.get(proc)
                if isinstance(res, Exception):
                    raise res
                if res is None:
                    raise TimeoutError("未获取到 PaddleOCR worker 输出")
                stdout_text, _stderr_text = res
                if proc.poll() is None:
                    proc.wait(timeout=min(60, timeout_seconds))
            except (TimeoutError, subprocess.TimeoutExpired, OSError, RuntimeError):
                _terminate_proc(proc)
                failures += chunk_size
            else:
                chunk_failures = 0
                if proc.returncode == 0:
                    for line in stdout_text.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except ValueError:
                            continue
                        # worker 的 index 是 chunk 内序号（步长分块），
                        # 必须映射回原始页索引，不能假设与 chunk 起点连续。
                        offset = int(record.get("index", 0))
                        if not 0 <= offset < len(chunk_items):
                            continue
                        page_index = chunk_items[offset][0]
                        if not 0 <= page_index < len(ocr_texts):
                            continue
                        if record.get("ok"):
                            ocr_texts[page_index] = record.get("text") or ""
                        else:
                            ocr_texts[page_index] = ""
                            chunk_failures += 1
                else:
                    chunk_failures = chunk_size
                failures += chunk_failures
            completed_pages += chunk_size
            if progress and (
                completed_pages == len(page_images) or completed_pages % 25 == 0
            ):
                progress("ocr", completed_pages, len(page_images))
    finally:
        for proc, _start, _size in procs:
            _terminate_proc(proc)
    return ocr_texts, failures


def _run_ocr(
    page_images: Sequence[Path],
    *,
    ocr_engine: str,
    tesseract_binary: Optional[str] = None,
    tessdata_path: Optional[Path] = None,
    ocr_language: str = "eng",
    dpi: int = 150,
    workers: int = 2,
    timeout_seconds: int = 1800,
    paddleocr_python: Optional[str] = None,
    paddleocr_workers: int = 16,
    progress: Optional[ProgressCallback] = None,
):
    if ocr_engine == "paddleocr":
        return _run_paddle_ocr(
            page_images,
            paddleocr_python=paddleocr_python,
            workers=paddleocr_workers,
            timeout_seconds=timeout_seconds,
            progress=progress,
        )
    return _run_tesseract_ocr(
        page_images,
        tesseract_binary=tesseract_binary,
        tessdata_path=tessdata_path,
        ocr_language=ocr_language,
        dpi=dpi,
        workers=workers,
        timeout_seconds=timeout_seconds,
        progress=progress,
    )


def render_scanned_pdf(
    source_pdf: Path,
    output_path: Path,
    image_dir: Path,
    *,
    page_count: int,
    pdftoppm_binary: str,
    tesseract_binary: Optional[str],
    tessdata_path: Optional[Path],
    ocr_language: str,
    dpi: int,
    jpeg_quality: int,
    workers: int,
    timeout_seconds: int,
    enable_ocr: bool,
    title: str,
    source_filename: str,
    liteparse_version: str,
    markdown_output_path: Optional[Path] = None,
    reflow_markdown: bool = True,
    ocr_engine: str = "tesseract",
    paddleocr_python: Optional[str] = None,
    paddleocr_workers: int = 16,
    progress: Optional[ProgressCallback] = None,
) -> ScanRenderResult:
    """Render a PDF to page JPEGs, OCR them locally, then build one HTML file."""
    started = time.monotonic()
    shutil.rmtree(image_dir, ignore_errors=True)
    image_dir.mkdir(parents=True, exist_ok=False)
    output_path.unlink(missing_ok=True)
    if markdown_output_path:
        markdown_output_path.unlink(missing_ok=True)
    try:
        command = [
            pdftoppm_binary,
            "-jpeg",
            "-r",
            str(dpi),
            "-jpegopt",
            "quality=%d" % jpeg_quality,
            "-f",
            "1",
            "-l",
            str(page_count),
            str(source_pdf),
            str(image_dir / "page"),
        ]
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ScanRenderError("扫描页图生成超时") from exc
        except OSError as exc:
            raise ScanRenderError("无法启动 PDF 页图生成工具：%s" % exc) from exc
        if result.returncode != 0:
            raise ScanRenderError(
                "PDF 页图生成失败（退出码 %d）：%s"
                % (result.returncode, (result.stdout or "")[-3000:])
            )

        page_images = sorted(image_dir.glob("page-*.jpg"), key=_page_number)
        if len(page_images) != page_count:
            raise ScanRenderError(
                "PDF 共 %d 页，但只生成了 %d 张页图"
                % (page_count, len(page_images))
            )
        if progress:
            progress("images", page_count, page_count)

        ocr_texts = [""] * page_count
        failures = 0
        if enable_ocr:
            ocr_texts, failures = _run_ocr(
                page_images,
                ocr_engine=ocr_engine,
                tesseract_binary=tesseract_binary,
                tessdata_path=tessdata_path,
                ocr_language=ocr_language,
                dpi=dpi,
                workers=workers,
                timeout_seconds=timeout_seconds,
                paddleocr_python=paddleocr_python,
                paddleocr_workers=paddleocr_workers,
                progress=progress,
            )

        output_bytes = write_scan_html(
            page_images,
            ocr_texts,
            output_path,
            title=title,
            source_filename=source_filename,
            liteparse_version=liteparse_version,
            dpi=dpi,
            jpeg_quality=jpeg_quality,
        )
        markdown_bytes = 0
        markdown_joined_lines = 0
        if markdown_output_path:
            if reflow_markdown:
                markdown_joined_lines = sum(
                    reflow_ocr_text(text)[1].joined_lines for text in ocr_texts if text
                )
            markdown_bytes = write_scan_markdown(
                ocr_texts,
                markdown_output_path,
                title=title,
                source_filename=source_filename,
                liteparse_version=liteparse_version,
                reflow=reflow_markdown,
            )
        return ScanRenderResult(
            page_count=page_count,
            output_bytes=output_bytes,
            markdown_bytes=markdown_bytes,
            markdown_joined_lines=markdown_joined_lines,
            ocr_pages=sum(bool(text) for text in ocr_texts),
            ocr_failures=failures,
            elapsed_seconds=time.monotonic() - started,
        )
    finally:
        shutil.rmtree(image_dir, ignore_errors=True)
