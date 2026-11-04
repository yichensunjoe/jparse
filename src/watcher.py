#!/usr/bin/env python3
"""Watch a project-local inbox and parse stable PDFs with LiteParse."""

import argparse
try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Dict, Optional, Tuple
from urllib.parse import unquote, urlsplit

try:
    from .html_renderer import render_markdown_file
    from .markdown_reflow import reflow_markdown_document
    from .scan_html_renderer import render_scanned_pdf
    from .table_repair import (
        find_suspicious_tables,
        normalize_table_cell_spacing,
        repair_markdown_tables,
    )
    from .translator import TranslationEngine, translate_document_file
except ImportError:
    from html_renderer import render_markdown_file
    from markdown_reflow import reflow_markdown_document
    from scan_html_renderer import render_scanned_pdf
    from table_repair import (
        find_suspicious_tables,
        normalize_table_cell_spacing,
        repair_markdown_tables,
    )
    from translator import TranslationEngine, translate_document_file


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config.json"


class ConfigError(RuntimeError):
    pass


class ParseError(RuntimeError):
    pass


def _project_path(root: Path, raw_value: str, field: str) -> Path:
    value = Path(raw_value).expanduser()
    resolved = (root / value).resolve() if not value.is_absolute() else value.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ConfigError("%s 必须位于项目目录内" % field) from exc
    return resolved


class Config:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.root = self.path.parent
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError("无法读取配置：%s" % exc) from exc

        self.inbox = _project_path(self.root, raw.get("inbox", "inbox"), "inbox")
        self.outbox = _project_path(self.root, raw.get("outbox", "outbox"), "outbox")
        self.processing = _project_path(
            self.root, raw.get("processing", "processing"), "processing"
        )
        self.processed = _project_path(
            self.root, raw.get("processed", "processed"), "processed"
        )
        self.failed = _project_path(self.root, raw.get("failed", "failed"), "failed")
        self.logs = _project_path(self.root, raw.get("logs", "logs"), "logs")

        self.poll_interval = float(raw.get("poll_interval_seconds", 2))
        self.settle_seconds = float(raw.get("settle_seconds", 5))
        self.output_format = str(raw.get("output_format", "markdown")).lower()
        self.ocr_mode = str(raw.get("ocr_mode", "auto")).lower()
        self.ocr_language = str(raw.get("ocr_language", "eng"))
        tessdata = raw.get("tessdata_path")
        self.tessdata_path = (
            _project_path(self.root, tessdata, "tessdata_path") if tessdata else None
        )
        self.minimum_text_characters = int(raw.get("minimum_text_characters", 60))
        self.num_workers = int(raw.get("num_workers", 2))
        self.max_pages = int(raw.get("max_pages", 1000))
        self.dpi = int(raw.get("dpi", 150))
        self.parse_timeout = int(raw.get("parse_timeout_seconds", 1800))
        self.required_lit_version = str(raw.get("required_lit_version", "")).strip()
        self.repair_tables = raw.get("repair_tables", True)
        self.keep_markdown = raw.get("keep_markdown", True)
        self.reflow_markdown = raw.get("reflow_markdown", True)
        self.scan_book_mode = raw.get("scan_book_mode", True)
        self.scan_book_min_pages = int(raw.get("scan_book_min_pages", 10))
        self.scan_book_dpi = int(raw.get("scan_book_dpi", 120))
        self.scan_book_jpeg_quality = int(raw.get("scan_book_jpeg_quality", 68))
        self.scan_book_ocr_text = raw.get("scan_book_ocr_text", True)

        self.pdfinfo_binary = shutil.which(str(raw.get("pdfinfo_binary", "pdfinfo")))
        self.pdftoppm_binary = shutil.which(str(raw.get("pdftoppm_binary", "pdftoppm")))
        self.tesseract_binary = shutil.which(
            str(raw.get("tesseract_binary", "tesseract"))
        )
        self.ocr_engine = str(raw.get("ocr_engine", "paddleocr")).lower()
        paddleocr_python = raw.get("paddleocr_python")
        if paddleocr_python:
            path_obj = Path(paddleocr_python).expanduser()
            if not path_obj.is_absolute():
                path_obj = self.root / path_obj
            self.paddleocr_python = os.path.abspath(str(path_obj))
        else:
            self.paddleocr_python = None
        self.paddleocr_workers = int(raw.get("paddleocr_workers", 16))

        lit_value = str(raw.get("lit_binary", "lit"))
        if "/" in lit_value:
            path_obj = Path(lit_value).expanduser()
            if not path_obj.is_absolute():
                path_obj = self.root / path_obj
            self.lit_binary = os.path.abspath(str(path_obj))
        else:
            self.lit_binary = shutil.which(lit_value) or lit_value

        self.upstream_extractor = str(raw.get("upstream_extractor", "opendataloader")).lower()

        if self.output_format not in {"html", "markdown", "text"}:
            raise ConfigError("output_format 仅支持 html、markdown 或 text")
        if self.ocr_mode not in {"auto", "always", "never"}:
            raise ConfigError("ocr_mode 仅支持 auto、always 或 never")
        if self.poll_interval <= 0 or self.settle_seconds < 0:
            raise ConfigError("轮询和稳定时间配置无效")
        if self.num_workers < 1 or self.max_pages < 1 or self.dpi < 72:
            raise ConfigError("LiteParse 参数配置无效")
        if not isinstance(self.repair_tables, bool):
            raise ConfigError("repair_tables 必须为 true 或 false")
        if not isinstance(self.keep_markdown, bool):
            raise ConfigError("keep_markdown 必须为 true 或 false")
        if not isinstance(self.reflow_markdown, bool):
            raise ConfigError("reflow_markdown 必须为 true 或 false")
        if not isinstance(self.scan_book_mode, bool):
            raise ConfigError("scan_book_mode 必须为 true 或 false")
        if not isinstance(self.scan_book_ocr_text, bool):
            raise ConfigError("scan_book_ocr_text 必须为 true 或 false")
        if self.scan_book_min_pages < 2:
            raise ConfigError("scan_book_min_pages 不得小于 2")
        if not 72 <= self.scan_book_dpi <= 200:
            raise ConfigError("scan_book_dpi 必须在 72 到 200 之间")
        if not 30 <= self.scan_book_jpeg_quality <= 95:
            raise ConfigError("scan_book_jpeg_quality 必须在 30 到 95 之间")
        if self.ocr_engine not in {"tesseract", "paddleocr"}:
            raise ConfigError("ocr_engine 仅支持 tesseract 或 paddleocr")
        if self.paddleocr_workers < 1:
            raise ConfigError("paddleocr_workers 不得小于 1")

        raw_translate = raw.get("translate_literature", False)
        if not isinstance(raw_translate, bool):
            raise ConfigError("translate_literature 必须为 true 或 false")
        self.translate_literature = raw_translate
        translation_model = raw.get("translation_model_dir", "assets/models/translation")
        self.translation_model_dir = (
            _project_path(self.root, translation_model, "translation_model_dir")
            if translation_model else None
        )
        self.translation_batch_size = int(raw.get("translation_batch_size", 32))
        self.translation_beam_size = int(raw.get("translation_beam_size", 4))
        raw_bilingual = raw.get("translation_bilingual", False)
        if not isinstance(raw_bilingual, bool):
            raise ConfigError("translation_bilingual 必须为 true 或 false")
        self.translation_bilingual = raw_bilingual
        if self.translation_batch_size < 1:
            raise ConfigError("translation_batch_size 不得小于 1")
        if self.translation_beam_size < 1:
            raise ConfigError("translation_beam_size 不得小于 1")

        self.dual_track_mode = str(raw.get("dual_track_mode", "disabled")).lower()
        if self.dual_track_mode not in {"disabled", "auto", "vector", "scanned"}:
            raise ConfigError("dual_track_mode 仅支持 disabled、auto、vector 或 scanned")
        self.pdf2zh_service = str(raw.get("pdf2zh_service", "bing")).lower()

        self.log_max_bytes = int(raw.get("log_max_bytes", 1024 * 1024))
        self.log_backup_count = int(raw.get("log_backup_count", 3))
        if not 64 * 1024 <= self.log_max_bytes <= 64 * 1024 * 1024:
            raise ConfigError("log_max_bytes 必须在 64KB 到 64MB 之间")
        if not 1 <= self.log_backup_count <= 20:
            raise ConfigError("log_backup_count 必须在 1 到 20 之间")

    @property
    def output_extension(self) -> str:
        return {"html": "html", "markdown": "md", "text": "txt"}[self.output_format]

    @property
    def parse_format(self) -> str:
        return "markdown" if self.output_format == "html" else self.output_format

    @property
    def parse_extension(self) -> str:
        return "md" if self.parse_format == "markdown" else "txt"

    @property
    def managed_directories(self):
        return (
            self.inbox,
            self.outbox,
            self.processing,
            self.processed,
            self.failed,
            self.logs,
        )


def setup_logging(
    log_dir: Path, max_bytes: int = 1024 * 1024, backup_count: int = 3
) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("liteparse_pdf_watcher")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = RotatingFileHandler(
        log_dir / "watcher.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(handler)
    return logger


def health_check(config: Config) -> str:
    for directory in config.managed_directories:
        directory.mkdir(parents=True, exist_ok=True)

    version_output = ""
    if getattr(config, "upstream_extractor", "opendataloader") == "opendataloader":
        try:
            try:
                from .opendataloader_extractor import check_opendataloader_available
            except ImportError:
                from opendataloader_extractor import check_opendataloader_available
            od_ok, od_detail = check_opendataloader_available()
            if od_ok:
                version_output = f"OpenDataLoader: {od_detail}"
            elif not Path(config.lit_binary).is_file():
                raise ConfigError("OpenDataLoader-PDF 引擎不可用：%s" % od_detail)
        except ConfigError:
            raise
        except Exception:
            pass

    lit_path = Path(config.lit_binary)
    if lit_path.is_file() and os.access(str(lit_path), os.X_OK):
        try:
            result = subprocess.run(
                [config.lit_binary, "--version"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=10,
            )
            lit_ver = result.stdout.strip()
            if config.required_lit_version and config.required_lit_version not in lit_ver:
                raise ConfigError(
                    "LiteParse 版本不匹配，期望 %s，实际 %s"
                    % (config.required_lit_version, lit_ver)
                )
            version_output = f"{version_output}; LiteParse: {lit_ver}" if version_output else lit_ver
        except (OSError, subprocess.SubprocessError) as exc:
            if getattr(config, "upstream_extractor", "opendataloader") != "opendataloader":
                raise ConfigError("LiteParse 版本检查失败：%s" % exc) from exc
    elif getattr(config, "upstream_extractor", "opendataloader") != "opendataloader":
        raise ConfigError("LiteParse 可执行文件不可用：%s" % config.lit_binary)

    if not version_output:
        version_output = "upstream: opendataloader"

    if config.ocr_engine == "paddleocr":
        interpreter = (
            Path(config.paddleocr_python) if config.paddleocr_python else None
        )
        if config.ocr_mode != "never" and (
            not interpreter or not interpreter.is_file()
        ):
            raise ConfigError(
                "PaddleOCR 解释器不可用：%s" % config.paddleocr_python
            )
        try:
            probe = subprocess.run(
                [str(interpreter), "-c", "import paddleocr"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ConfigError("PaddleOCR 可用性检查失败：%s" % exc) from exc
        if probe.returncode != 0:
            raise ConfigError(
                "PaddleOCR 环境不可用（无法导入 paddleocr）：%s"
                % (probe.stdout or "")[-1000:]
            )
    elif config.ocr_mode != "never" and config.tessdata_path:
        for language in config.ocr_language.split("+"):
            language_file = config.tessdata_path / (language + ".traineddata")
            if not language_file.is_file():
                raise ConfigError("OCR 语言数据缺失：%s" % language_file)
    if config.scan_book_mode and config.output_format == "html":
        if not config.pdfinfo_binary:
            raise ConfigError("扫描书保真模式缺少 pdfinfo")
        if not config.pdftoppm_binary:
            raise ConfigError("扫描书保真模式缺少 pdftoppm")
        if (
            config.scan_book_ocr_text
            and config.ocr_mode != "never"
            and config.ocr_engine == "tesseract"
            and not config.tesseract_binary
        ):
            raise ConfigError("扫描书辅助文字层缺少 Tesseract")

    if config.translate_literature:
        engine = TranslationEngine(config.translation_model_dir)
        ok, reason = engine.is_available()
        if not ok:
            raise ConfigError(reason)

    return version_output


def text_score(path: Path) -> int:
    if not path.is_file():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    # Markdown 结构符号不是 PDF 内容。扫描页的空输出常只有
    # ```text / ``` 围栏，过去会把其中的语言标签“text”误算为正文。
    text = re.sub(r"(?m)^[ \t]{0,3}(?:`{3,}|~{3,})[^\n]*$", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^\n)]*\)", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    return sum(character.isalnum() for character in text)


def unique_path(directory: Path, filename: str) -> Path:
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


def remove_path(path: Optional[Path]):
    if not path or not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


_MARKDOWN_IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\((<[^>]+>|[^\s)]+)(?:\s+([\"'][^\"']*[\"']))?\)"
)


def stage_markdown_bundle(
    markdown_source: Path,
    image_dir: Optional[Path],
    staged_markdown: Path,
    staged_assets: Path,
    assets_dir_name: str,
    reflow: bool = True,
):
    """Stage Markdown and referenced LiteParse images for atomic publication."""
    staged_markdown.unlink(missing_ok=True)
    remove_path(staged_assets)
    markdown_text = markdown_source.read_text(encoding="utf-8", errors="replace")
    base_dir = image_dir.resolve() if image_dir and image_dir.is_dir() else None
    copied_assets = False

    def rewrite_image(match):
        nonlocal copied_assets
        if not base_dir:
            return match.group(0)
        raw_url = match.group(2).strip().strip("<>")
        parsed = urlsplit(raw_url)
        if parsed.scheme or parsed.netloc:
            return match.group(0)
        relative = Path(unquote(parsed.path))
        if relative.is_absolute():
            return match.group(0)
        candidates = (base_dir / relative, base_dir / relative.name)
        resolved = None
        target_relative = None
        for candidate in candidates:
            try:
                checked = candidate.resolve()
                checked.relative_to(base_dir)
            except (OSError, ValueError):
                continue
            if checked.is_file():
                resolved = checked
                target_relative = checked.relative_to(base_dir)
                break
        if not resolved or target_relative is None:
            return match.group(0)
        destination = staged_assets / target_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(resolved, destination)
        copied_assets = True
        target_url = "%s/%s" % (assets_dir_name, target_relative.as_posix())
        if any(character.isspace() for character in target_url):
            target_url = "<%s>" % target_url
        title = " " + match.group(3) if match.group(3) else ""
        return "![%s](%s%s)" % (match.group(1), target_url, title)

    rewritten = _MARKDOWN_IMAGE_RE.sub(rewrite_image, markdown_text)
    reflow_stats = None
    if reflow:
        rewritten, reflow_stats = reflow_markdown_document(rewritten)
    staged_markdown.write_text(rewritten, encoding="utf-8")
    if not copied_assets:
        remove_path(staged_assets)
    return copied_assets, reflow_stats


class Watcher:
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.stop_event = threading.Event()
        self.observations: Dict[str, Tuple[int, int, float]] = {}

    def request_stop(self, _signum=None, _frame=None):
        self.logger.info("收到停止请求")
        self.stop_event.set()

    def _stem_available(self, stem: str) -> bool:
        pdf_name = stem + ".pdf"
        output_name = stem + "." + self.config.output_extension
        occupied = [
            self.config.processing / pdf_name,
            self.config.processed / pdf_name,
            self.config.failed / pdf_name,
            self.config.outbox / output_name,
        ]
        if self.config.output_format == "html" and self.config.keep_markdown:
            occupied.extend(
                [
                    self.config.outbox / (stem + ".md"),
                    self.config.outbox / (stem + "_assets"),
                ]
            )
        if self.config.dual_track_mode != "disabled":
            # 双轨产物用固定文件名，必须纳入占号，否则同名不同文档会互相覆盖。
            occupied.extend(
                [
                    self.config.outbox / (stem + "-中文精译版.pdf"),
                    self.config.outbox / (stem + "-双语对照版.pdf"),
                    self.config.outbox / (stem + ".mono.pdf"),
                    self.config.outbox / (stem + ".原位双层版.html"),
                    self.config.outbox / (".%s.manifest.json" % stem),
                ]
            )
        return not any(path.exists() for path in occupied)

    def _reserve_stem(self, original_stem: str) -> str:
        if self._stem_available(original_stem):
            return original_stem
        index = 2
        while not self._stem_available("%s-%d" % (original_stem, index)):
            index += 1
        return "%s-%d" % (original_stem, index)

    def claim(self, source: Path) -> Optional[Path]:
        stem = self._reserve_stem(source.stem)
        claimed = self.config.processing / (stem + ".pdf")
        try:
            os.replace(str(source), str(claimed))
        except FileNotFoundError:
            return None
        self.logger.info("已接收 PDF：%s", claimed.name)
        return claimed

    def _lit_command(
        self,
        source: Path,
        output: Path,
        use_ocr: bool,
        image_dir: Optional[Path],
        parse_format: Optional[str] = None,
        target_pages=None,
    ):
        format_value = parse_format or self.config.parse_format
        command = [
            self.config.lit_binary,
            "parse",
            str(source),
            "--format",
            format_value,
            "--max-pages",
            str(self.config.max_pages),
            "--dpi",
            str(self.config.dpi),
            "--num-workers",
            str(self.config.num_workers),
            "--quiet",
            "--output",
            str(output),
        ]
        if target_pages:
            command.extend(["--target-pages", ",".join(str(page) for page in target_pages)])
        if format_value == "markdown" and self.config.output_format == "html" and image_dir:
            command.extend(["--image-mode", "embed", "--image-output-dir", str(image_dir)])
        else:
            command.extend(["--image-mode", "off"])
        if use_ocr:
            command.extend(["--ocr-language", self.config.ocr_language])
            if self.config.tessdata_path:
                command.extend(["--tessdata-path", str(self.config.tessdata_path)])
        else:
            command.append("--no-ocr")
        return command

    def _run_lit(
        self,
        source: Path,
        output: Path,
        use_ocr: bool,
        image_dir: Optional[Path],
        parse_format: Optional[str] = None,
        target_pages=None,
    ) -> Tuple[bool, str]:
        output.unlink(missing_ok=True)
        remove_path(image_dir)
        try:
            result = subprocess.run(
                self._lit_command(
                    source,
                    output,
                    use_ocr,
                    image_dir,
                    parse_format=parse_format,
                    target_pages=target_pages,
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                timeout=self.config.parse_timeout,
            )
        except subprocess.TimeoutExpired:
            return False, "LiteParse 超过 %d 秒未完成" % self.config.parse_timeout
        except OSError as exc:
            return False, "无法启动 LiteParse：%s" % exc
        detail = (result.stdout or "").strip()[-6000:]
        if result.returncode != 0:
            return False, "LiteParse 退出码 %d\n%s" % (result.returncode, detail)
        if not output.is_file():
            return False, "LiteParse 未生成输出文件\n%s" % detail
        return True, detail

    def _pdf_page_count(self, source: Path) -> int:
        if not self.config.pdfinfo_binary:
            raise ParseError("pdfinfo 不可用")
        try:
            result = subprocess.run(
                [self.config.pdfinfo_binary, str(source)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ParseError("无法读取 PDF 页数：%s" % exc) from exc
        if result.returncode != 0:
            raise ParseError(
                "无法读取 PDF 页数：%s" % (result.stdout or "")[-2000:]
            )
        match = re.search(r"(?m)^Pages:\s+(\d+)\s*$", result.stdout or "")
        if not match:
            raise ParseError("pdfinfo 未返回 PDF 页数")
        page_count = int(match.group(1))
        if page_count < 1:
            raise ParseError("PDF 页数无效")
        if page_count > self.config.max_pages:
            raise ParseError(
                "PDF 共 %d 页，超过配置上限 %d 页"
                % (page_count, self.config.max_pages)
            )
        return page_count

    def _scan_book_page_count(self, source: Path, no_ocr_score: int) -> int:
        if not (
            self.config.scan_book_mode
            and self.config.output_format == "html"
            and self.config.ocr_mode == "auto"
            and no_ocr_score < self.config.minimum_text_characters
        ):
            return 0
        try:
            page_count = self._pdf_page_count(source)
        except ParseError as exc:
            self.logger.warning("扫描书模式页数检查失败，改用常规 OCR：%s", exc)
            return 0
        return page_count if page_count >= self.config.scan_book_min_pages else 0

    def _parse(
        self, source: Path
    ) -> Tuple[Optional[Path], Optional[Path], bool, int]:
        extension = self.config.parse_extension
        base = self.config.processing / ("." + source.stem)
        no_ocr_output = Path(str(base) + ".noocr." + extension + ".partial")
        ocr_output = Path(str(base) + ".ocr." + extension + ".partial")
        no_ocr_images = Path(str(base) + ".noocr.images.partial") if self.config.output_format == "html" else None
        ocr_images = Path(str(base) + ".ocr.images.partial") if self.config.output_format == "html" else None

        if self.config.ocr_mode == "never":
            ok, detail = self._run_lit(source, no_ocr_output, use_ocr=False, image_dir=no_ocr_images)
            if not ok:
                raise ParseError(detail)
            selected = no_ocr_output
            selected_images = no_ocr_images
        elif self.config.ocr_mode == "always":
            ok, detail = self._run_lit(source, ocr_output, use_ocr=True, image_dir=ocr_images)
            if not ok:
                raise ParseError(detail)
            selected = ocr_output
            selected_images = ocr_images
        else:
            no_ocr_ok, no_ocr_detail = self._run_lit(
                source, no_ocr_output, use_ocr=False, image_dir=no_ocr_images
            )
            no_ocr_score = text_score(no_ocr_output) if no_ocr_ok else 0
            if no_ocr_ok and no_ocr_score >= self.config.minimum_text_characters:
                selected = no_ocr_output
                selected_images = no_ocr_images
                self.logger.info(
                    "快速文字层足够，跳过 OCR：%s（%d 个文字数字字符）",
                    source.name,
                    no_ocr_score,
                )
            else:
                scan_page_count = self._scan_book_page_count(source, no_ocr_score)
                if scan_page_count:
                    no_ocr_output.unlink(missing_ok=True)
                    ocr_output.unlink(missing_ok=True)
                    remove_path(no_ocr_images)
                    remove_path(ocr_images)
                    self.logger.info(
                        "检测到无文字层的扫描书，启用原页保真 HTML：%s（%d 页）",
                        source.name,
                        scan_page_count,
                    )
                    return None, None, False, scan_page_count
                self.logger.info("文字层不足，启用中英 OCR：%s", source.name)
                ocr_ok, ocr_detail = self._run_lit(
                    source, ocr_output, use_ocr=True, image_dir=ocr_images
                )
                ocr_score = text_score(ocr_output) if ocr_ok else 0
                if ocr_ok and ocr_score > 0 and ocr_score >= no_ocr_score:
                    selected = ocr_output
                    selected_images = ocr_images
                elif no_ocr_ok and no_ocr_score > 0:
                    selected = no_ocr_output
                    selected_images = no_ocr_images
                    if not ocr_ok:
                        self.logger.warning("OCR 失败，保留文字层结果：%s", ocr_detail)
                else:
                    detail = ocr_detail if not ocr_ok else "LiteParse 未提取到可用文字"
                    if not no_ocr_ok:
                        detail += "\n无 OCR 尝试：" + no_ocr_detail
                    raise ParseError(detail)

        if text_score(selected) == 0:
            raise ParseError("LiteParse 输出为空")
        other = ocr_output if selected == no_ocr_output else no_ocr_output
        other.unlink(missing_ok=True)
        other_images = ocr_images if selected == no_ocr_output else no_ocr_images
        remove_path(other_images)
        return selected, selected_images, selected == ocr_output, 0

    def _repair_suspicious_tables(self, source: Path, selected: Path, use_ocr: bool) -> int:
        if not self.config.repair_tables or self.config.parse_format != "markdown":
            return 0
        markdown_text = selected.read_text(encoding="utf-8", errors="replace")
        normalized_text, spacing_fixes = normalize_table_cell_spacing(markdown_text)
        issues = find_suspicious_tables(normalized_text)

        def save_working_text(value: str):
            if value == markdown_text:
                return
            repaired_output = Path(str(selected) + ".table-repaired.partial")
            repaired_output.write_text(value, encoding="utf-8")
            os.replace(str(repaired_output), str(selected))

        if not issues:
            save_working_text(normalized_text)
            if spacing_fixes:
                self.logger.info(
                    "已清理 %d 处表格断词空格：%s", spacing_fixes, source.name
                )
            return 0

        pages = sorted({issue.page_number for issue in issues})
        layout_output = self.config.processing / ("." + source.stem + ".layout.json.partial")
        try:
            ok, detail = self._run_lit(
                source,
                layout_output,
                use_ocr=use_ocr,
                image_dir=None,
                parse_format="json",
                target_pages=pages,
            )
            if not ok:
                save_working_text(normalized_text)
                self.logger.warning("表格坐标提取失败，保留原结果：%s", detail)
                return 0
            try:
                layout_json = json.loads(layout_output.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                save_working_text(normalized_text)
                self.logger.warning("表格坐标数据无效，保留原结果：%s", exc)
                return 0
            repaired_text, repaired_count = repair_markdown_tables(normalized_text, layout_json)
            save_working_text(repaired_text)
            if spacing_fixes:
                self.logger.info(
                    "已清理 %d 处表格断词空格：%s", spacing_fixes, source.name
                )
            if repaired_count:
                self.logger.info(
                    "已用 PDF 坐标修复 %d 个异常表格：%s",
                    repaired_count,
                    source.name,
                )
            if repaired_count < len(issues):
                self.logger.warning(
                    "发现 %d 个异常表格，其中 %d 个通过一致性校验并修复：%s",
                    len(issues),
                    repaired_count,
                    source.name,
                )
            return repaired_count
        finally:
            layout_output.unlink(missing_ok=True)

    def _publish(self, source: Path, selected: Path, image_dir: Optional[Path], output: Path):
        if self.config.output_format != "html":
            remove_path(image_dir)
            if self.config.output_format == "markdown" and self.config.reflow_markdown:
                reformatted = Path(str(selected) + ".reflowed.partial")
                markdown_text = selected.read_text(encoding="utf-8", errors="replace")
                markdown_text, stats = reflow_markdown_document(markdown_text)
                reformatted.write_text(markdown_text, encoding="utf-8")
                os.replace(str(reformatted), str(selected))
                if stats.joined_lines:
                    self.logger.info(
                        "已合并 %d 处 Markdown 段落换行：%s",
                        stats.joined_lines,
                        source.name,
                    )
            os.replace(str(selected), str(output))
            return
        rendered = self.config.processing / ("." + source.stem + ".rendered.html.partial")
        staged_markdown = self.config.processing / (
            "." + source.stem + ".published.md.partial"
        )
        staged_assets = self.config.processing / (
            "." + source.stem + ".markdown-assets.partial"
        )
        markdown_output = self.config.outbox / (source.stem + ".md")
        assets_dir_name = source.stem + "_assets"
        assets_output = self.config.outbox / assets_dir_name
        rendered.unlink(missing_ok=True)
        render_markdown_file(
            selected,
            rendered,
            fallback_title=source.stem,
            source_filename=source.name,
            liteparse_version=self.config.required_lit_version or "2.4.0",
            image_base_dir=image_dir,
        )
        has_assets = False
        reflow_stats = None
        if self.config.keep_markdown:
            if markdown_output.exists() or assets_output.exists():
                raise ParseError("Markdown 输出或资源目录已存在，拒绝覆盖")
            has_assets, reflow_stats = stage_markdown_bundle(
                selected,
                image_dir,
                staged_markdown,
                staged_assets,
                assets_dir_name,
                reflow=self.config.reflow_markdown,
            )
            if reflow_stats and reflow_stats.joined_lines:
                self.logger.info(
                    "已合并 %d 处 Markdown 段落换行：%s",
                    reflow_stats.joined_lines,
                    source.name,
                )

        published = []
        try:
            if has_assets:
                os.replace(str(staged_assets), str(assets_output))
                published.append(assets_output)
            if self.config.keep_markdown:
                os.replace(str(staged_markdown), str(markdown_output))
                published.append(markdown_output)
            os.replace(str(rendered), str(output))
            published.append(output)
        except Exception:
            for path in reversed(published):
                remove_path(path)
            raise
        selected.unlink(missing_ok=True)
        remove_path(image_dir)
        if self.config.translate_literature and self.config.keep_markdown:
            self._translate_output(source, markdown_output, assets_output if has_assets else None)

    def _publish_scanned(self, source: Path, output: Path, page_count: int):
        rendered = self.config.processing / (
            "." + source.stem + ".scan.rendered.html.partial"
        )
        page_images = self.config.processing / (
            "." + source.stem + ".scan.pages.partial"
        )
        staged_markdown = self.config.processing / (
            "." + source.stem + ".scan.md.partial"
        )
        markdown_output = self.config.outbox / (source.stem + ".md")
        if self.config.keep_markdown and markdown_output.exists():
            raise ParseError("Markdown 输出已存在，拒绝覆盖")

        def log_progress(stage: str, current: int, total: int):
            if stage == "images":
                self.logger.info("已生成 %d 张保真页图：%s", total, source.name)
            else:
                self.logger.info(
                    "扫描书辅助 OCR 进度：%d/%d 页：%s",
                    current,
                    total,
                    source.name,
                )

        result = render_scanned_pdf(
            source,
            rendered,
            page_images,
            page_count=page_count,
            pdftoppm_binary=self.config.pdftoppm_binary or "pdftoppm",
            tesseract_binary=self.config.tesseract_binary,
            tessdata_path=self.config.tessdata_path,
            ocr_language=self.config.ocr_language,
            dpi=self.config.scan_book_dpi,
            jpeg_quality=self.config.scan_book_jpeg_quality,
            workers=self.config.num_workers,
            timeout_seconds=self.config.parse_timeout,
            ocr_engine=self.config.ocr_engine,
            paddleocr_python=self.config.paddleocr_python,
            paddleocr_workers=self.config.paddleocr_workers,
            enable_ocr=(
                self.config.scan_book_ocr_text and self.config.ocr_mode != "never"
            ),
            title=source.stem,
            source_filename=source.name,
            liteparse_version=self.config.required_lit_version or "2.4.0",
            markdown_output_path=(
                staged_markdown if self.config.keep_markdown else None
            ),
            reflow_markdown=self.config.reflow_markdown,
            progress=log_progress,
        )
        published = []
        try:
            if self.config.keep_markdown:
                os.replace(str(staged_markdown), str(markdown_output))
                published.append(markdown_output)
            os.replace(str(rendered), str(output))
            published.append(output)
        except Exception:
            for path in reversed(published):
                remove_path(path)
            raise
        self.logger.info(
            "保真 HTML 已生成：%d 页，辅助 OCR %d 页，Markdown 合并换行 %d 处，HTML %.1f MB，Markdown %.1f MB，耗时 %.1f 秒",
            result.page_count,
            result.ocr_pages,
            result.markdown_joined_lines,
            result.output_bytes / (1024 * 1024),
            result.markdown_bytes / (1024 * 1024),
            result.elapsed_seconds,
        )
        if self.config.translate_literature and self.config.keep_markdown:
            self._translate_output(source, markdown_output, None)

    def _translate_output(
        self,
        source: Path,
        markdown_output: Path,
        image_dir: Optional[Path],
    ):
        if not self.config.translate_literature:
            return
        try:
            self.logger.info("开始本地科技文献离线翻译：%s", source.name)
            t0 = time.time()
            translate_document_file(
                source_md=markdown_output,
                model_dir=self.config.translation_model_dir,
                bilingual=self.config.translation_bilingual,
                image_base_dir=image_dir,
                batch_size=self.config.translation_batch_size,
                beam_size=self.config.translation_beam_size,
            )
            self.logger.info(
                "本地文献翻译完成（耗时 %.1f 秒）：%s",
                time.time() - t0,
                source.name,
            )
        except Exception as exc:
            self.logger.warning("本地文献翻译失败（不影响主成果物）：%s：%s", source.name, exc)

    def _archive_success(self, source: Path) -> Path:
        destination = unique_path(self.config.processed, source.name)
        os.replace(str(source), str(destination))
        return destination

    def _manifest_path(self, stem: str) -> Path:
        return self.config.outbox / (".%s.manifest.json" % stem)

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _write_manifest(self, source: Path, outputs) -> None:
        """Record what was actually delivered, so success is not inferred from
        the mere existence of a file that happened to survive a crash."""
        manifest = {
            "version": 1,
            "source_name": source.name,
            "source_sha256": self._file_sha256(source),
            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "outputs": [Path(p).name for p in outputs if p],
        }
        target = self._manifest_path(source.stem)
        staged = self.config.outbox / (".%s.manifest.json.tmp" % source.stem)
        try:
            staged.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(str(staged), str(target))
        except OSError as exc:
            self.logger.error("写入完成标记失败（产物已交付）：%s：%s", source.name, exc)
            staged.unlink(missing_ok=True)

    def _completed_by_manifest(self, source: Path) -> bool:
        try:
            manifest = json.loads(self._manifest_path(source.stem).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        recorded = manifest.get("source_sha256")
        if not recorded:
            return False
        try:
            return recorded == self._file_sha256(source)
        except OSError:
            return False

    def _clear_stale_deliverables(self, stem: str) -> None:
        """Remove half-delivered outputs left by a killed run (no manifest)."""
        stale = [
            self.config.outbox / (stem + "-中文精译版.pdf"),
            self.config.outbox / (stem + "-双语对照版.pdf"),
            self.config.outbox / (stem + ".mono.pdf"),
            self.config.outbox / (stem + ".原位双层版.html"),
        ]
        removed = [path for path in stale if path.exists()]
        for path in removed:
            remove_path(path)
        if removed:
            self.logger.warning(
                "清理上次未完成的半交付产物（无完成标记）：%s",
                ", ".join(path.name for path in removed),
            )

    def _archive_failure(self, source: Path, error: str) -> Path:
        destination = unique_path(self.config.failed, source.name)
        os.replace(str(source), str(destination))
        error_path = destination.with_suffix(".error.txt")
        error_path.write_text(
            "%s\n\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), error[:12000]),
            encoding="utf-8",
        )
        return destination

    def process(self, source: Path):
        output = self.config.outbox / (
            source.stem + "." + self.config.output_extension
        )
        if self.config.dual_track_mode != "disabled":
            if self._completed_by_manifest(source):
                archived = self._archive_success(source)
                self.logger.warning(
                    "检测到已完成双轨输出（完成标记校验一致），仅恢复归档：%s", archived.name
                )
                return
            self._clear_stale_deliverables(source.stem)
        else:
            if output.exists():
                archived = self._archive_success(source)
                self.logger.warning("检测到已完成输出，仅恢复归档：%s", archived.name)
                return

        if self.config.dual_track_mode != "disabled":
            try:
                from .router import route_and_process_pdf
            except ImportError:
                from router import route_and_process_pdf
            try:
                outputs = route_and_process_pdf(
                    pdf_path=source,
                    outbox_dir=self.config.outbox,
                    config={
                        "force_pipeline": self.config.dual_track_mode,
                        "pdf2zh_service": self.config.pdf2zh_service,
                        "upstream_extractor": getattr(self.config, "upstream_extractor", "opendataloader"),
                    },
                )
                self._write_manifest(source, outputs)
                archived = self._archive_success(source)
                output_names = ", ".join(p.name for p in outputs)
                self.logger.info("双轨智能识别完成：%s -> %s", archived.name, output_names)
                return
            except Exception as exc:
                self._cleanup_partials(source.stem)
                try:
                    failed = self._archive_failure(source, str(exc))
                    self.logger.error("双轨识别失败：%s：%s", failed.name, exc)
                except FileNotFoundError:
                    self.logger.error("双轨处理失败且原文件已不存在：%s", exc)
                return
        try:
            selected, image_dir, use_ocr, scan_page_count = self._parse(source)
            if scan_page_count:
                self._publish_scanned(source, output, scan_page_count)
            else:
                if selected is None:
                    raise ParseError("内部错误：未选中 LiteParse 输出")
                self._repair_suspicious_tables(source, selected, use_ocr)
                self._publish(source, selected, image_dir, output)
            archived = self._archive_success(source)
            output_names = output.name
            if self.config.output_format == "html" and self.config.keep_markdown:
                output_names += " + " + source.stem + ".md"
            self.logger.info("识别完成：%s -> %s", archived.name, output_names)
        except Exception as exc:
            self._cleanup_partials(source.stem)
            try:
                failed = self._archive_failure(source, str(exc))
                self.logger.error("识别失败：%s：%s", failed.name, exc)
            except FileNotFoundError:
                self.logger.error("处理失败且原文件已不存在：%s", exc)

    def _cleanup_partials(self, stem: str):
        prefix = ".%s." % stem
        try:
            for partial in self.config.processing.iterdir():
                if partial.name.startswith(prefix) and partial.name.endswith(".partial"):
                    remove_path(partial)
            for partial in self.config.outbox.iterdir():
                if partial.name.startswith(f".{stem}") and partial.name.endswith(".tmp"):
                    remove_path(partial)
        except OSError as exc:
            self.logger.warning("清理临时文件失败：%s", exc)

    def recover_processing(self):
        for source in sorted(self.config.processing.iterdir(), key=lambda path: path.name):
            if source.is_file() and source.suffix.lower() == ".pdf":
                self.logger.info("恢复上次未完成任务：%s", source.name)
                self.process(source)

    def scan_inbox(self, force: bool = False):
        now = time.monotonic()
        visible = set()
        candidates = sorted(self.config.inbox.iterdir(), key=lambda path: path.name)
        for source in candidates:
            if (
                not source.is_file()
                or source.name.startswith(".")
                or source.suffix.lower() != ".pdf"
            ):
                continue
            key = str(source)
            visible.add(key)
            try:
                stat = source.stat()
            except FileNotFoundError:
                continue
            previous = self.observations.get(key)
            signature = (stat.st_size, stat.st_mtime_ns)
            if force:
                stable = True
            elif previous is None or previous[:2] != signature:
                self.observations[key] = (signature[0], signature[1], now)
                stable = False
            else:
                stable = now - previous[2] >= self.config.settle_seconds
            if stable:
                claimed = self.claim(source)
                self.observations.pop(key, None)
                if claimed:
                    self.process(claimed)
        for key in set(self.observations) - visible:
            self.observations.pop(key, None)

    def run_once(self):
        self.recover_processing()
        self.scan_inbox(force=True)

    def run_forever(self):
        self.recover_processing()
        self.logger.info(
            "监控已启动：%s（稳定等待 %.1f 秒）",
            self.config.inbox,
            self.config.settle_seconds,
        )
        while not self.stop_event.is_set():
            try:
                self.scan_inbox()
            except Exception:
                self.logger.exception("扫描投递箱时出错")
            self.stop_event.wait(self.config.poll_interval)
        self.logger.info("监控已停止")


def acquire_lock(lock_path: Path):
    handle = lock_path.open("a+")
    if fcntl:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            handle.close()
            return None
    elif msvcrt:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def release_lock(lock_handle):
    if lock_handle is None:
        return
    try:
        if fcntl:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        elif msvcrt:
            lock_handle.seek(0)
            msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
    except Exception:
        pass
    finally:
        try:
            lock_handle.close()
        except Exception:
            pass


def parse_args():
    parser = argparse.ArgumentParser(description="LiteParse PDF 文件夹自动识别")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--once", action="store_true", help="立即处理当前文件后退出")
    parser.add_argument("--check", action="store_true", help="仅执行环境健康检查")
    parser.add_argument("--settle-seconds", type=float, help="临时覆盖稳定等待时间")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = Config(args.config)
        if args.settle_seconds is not None:
            if args.settle_seconds < 0:
                raise ConfigError("稳定等待时间不得为负数")
            config.settle_seconds = args.settle_seconds
        version = health_check(config)
    except ConfigError as exc:
        print("健康检查失败：%s" % exc, file=sys.stderr)
        return 2

    if args.check:
        print("健康检查通过：%s" % version)
        return 0

    logger = setup_logging(config.logs, config.log_max_bytes, config.log_backup_count)
    lock_handle = acquire_lock(config.logs / "watcher.lock")
    if lock_handle is None:
        logger.warning("已有一个监控进程在运行")
        return 3

    watcher = Watcher(config, logger)
    signal.signal(signal.SIGTERM, watcher.request_stop)
    signal.signal(signal.SIGINT, watcher.request_stop)
    try:
        if args.once:
            watcher.run_once()
        else:
            watcher.run_forever()
    finally:
        release_lock(lock_handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
