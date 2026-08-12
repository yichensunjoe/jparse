#!/usr/bin/env python3
"""Deterministic, dependency-free Markdown-to-HTML document renderer."""

import base64
from datetime import datetime
import html as html_lib
import mimetypes
from pathlib import Path
import re
from typing import List, Optional, Tuple
from urllib.parse import unquote, urlsplit


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_UNORDERED_RE = re.compile(r"^\s*[-+*]\s+(.+)$")
_ORDERED_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$")
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*([^\s`]*)\s*$")
_HORIZONTAL_RE = re.compile(r"^\s{0,3}((\*\s*){3,}|(-\s*){3,}|(_\s*){3,})$")
_TABLE_DIVIDER_CELL_RE = re.compile(r"^:?-{3,}:?$")


def _strip_markdown(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[`*_~]", "", text)
    return text.strip()


def extract_title(markdown_text: str, fallback_title: str) -> Tuple[str, str]:
    lines = markdown_text.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            title = _strip_markdown(match.group(1)) or fallback_title
            del lines[index]
            return title, "\n".join(lines)
        break
    return fallback_title, markdown_text


class ImageEmbedder:
    """Resolve LiteParse image references and return offline data URIs."""

    def __init__(self, base_dir: Optional[Path], max_bytes: int = 25 * 1024 * 1024):
        self.base_dir = base_dir.resolve() if base_dir and base_dir.exists() else None
        self.max_bytes = max_bytes

    def data_uri(self, raw_url: str) -> Optional[str]:
        if not self.base_dir:
            return None
        parsed = urlsplit(raw_url.strip().strip("<>"))
        if parsed.scheme or parsed.netloc:
            return None
        relative = Path(unquote(parsed.path))
        candidates = [self.base_dir / relative, self.base_dir / relative.name]
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
                resolved.relative_to(self.base_dir)
            except (OSError, ValueError):
                continue
            if not resolved.is_file():
                continue
            size = resolved.stat().st_size
            if size > self.max_bytes:
                return None
            mime_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
            if not mime_type.startswith("image/"):
                return None
            encoded = base64.b64encode(resolved.read_bytes()).decode("ascii")
            return "data:%s;base64,%s" % (mime_type, encoded)
        return None


def _safe_link(raw_url: str) -> Optional[str]:
    value = raw_url.strip().strip("<>")
    parsed = urlsplit(value)
    if parsed.scheme.lower() in {"http", "https", "mailto"}:
        return value
    if not parsed.scheme and not parsed.netloc and value.startswith("#"):
        return value
    return None


def render_inline(text: str, image_embedder: Optional[ImageEmbedder] = None) -> str:
    placeholders: List[str] = []

    def stash(fragment: str) -> str:
        index = len(placeholders)
        placeholders.append(fragment)
        return "\ue000%d\ue001" % index

    def code_replacement(match):
        return stash("<code>%s</code>" % html_lib.escape(match.group(1), quote=False))

    text = re.sub(r"`([^`\n]+)`", code_replacement, text)

    def image_replacement(match):
        alt = match.group(1).strip() or "PDF 图片"
        raw_url = match.group(2)
        data_uri = image_embedder.data_uri(raw_url) if image_embedder else None
        if not data_uri:
            return stash(
                '<span class="image-missing">[图片：%s]</span>'
                % html_lib.escape(alt)
            )
        return stash(
            '<img class="document-image" src="%s" alt="%s" loading="lazy" decoding="async">'
            % (html_lib.escape(data_uri, quote=True), html_lib.escape(alt, quote=True))
        )

    text = re.sub(
        r"!\[([^\]]*)\]\(([^\s)]+)(?:\s+[\"'][^\"']*[\"'])?\)",
        image_replacement,
        text,
    )

    def link_replacement(match):
        label = html_lib.escape(match.group(1), quote=False)
        target = _safe_link(match.group(2))
        if not target:
            return stash(label)
        return stash(
            '<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>'
            % (html_lib.escape(target, quote=True), label)
        )

    text = re.sub(
        r"\[([^\]]+)\]\(([^\s)]+)(?:\s+[\"'][^\"']*[\"'])?\)",
        link_replacement,
        text,
    )

    rendered = html_lib.escape(text, quote=False)
    rendered = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"__(.+?)__", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"~~(.+?)~~", r"<del>\1</del>", rendered)
    rendered = re.sub(r"(?<!\w)\*([^*\n]+?)\*(?!\w)", r"<em>\1</em>", rendered)
    rendered = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"<em>\1</em>", rendered)
    for index, fragment in enumerate(placeholders):
        rendered = rendered.replace("\ue000%d\ue001" % index, fragment)
    return rendered


def _split_table_row(line: str) -> List[str]:
    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|") and not value.endswith(r"\|"):
        value = value[:-1]
    cells = re.split(r"(?<!\\)\|", value)
    return [cell.replace(r"\|", "|").strip() for cell in cells]


def _table_alignments(line: str) -> Optional[List[str]]:
    cells = _split_table_row(line)
    if not cells or not all(_TABLE_DIVIDER_CELL_RE.match(cell.replace(" ", "")) for cell in cells):
        return None
    alignments = []
    for cell in cells:
        compact = cell.replace(" ", "")
        if compact.startswith(":") and compact.endswith(":"):
            alignments.append("center")
        elif compact.endswith(":"):
            alignments.append("right")
        else:
            alignments.append("left")
    return alignments


def _starts_block(lines: List[str], index: int) -> bool:
    line = lines[index]
    if not line.strip():
        return True
    if _HEADING_RE.match(line) or _FENCE_RE.match(line) or _HORIZONTAL_RE.match(line):
        return True
    if line.lstrip().startswith(">") or _UNORDERED_RE.match(line) or _ORDERED_RE.match(line):
        return True
    return index + 1 < len(lines) and "|" in line and _table_alignments(lines[index + 1]) is not None


def markdown_to_html(markdown_text: str, image_base_dir: Optional[Path] = None) -> str:
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    embedder = ImageEmbedder(image_base_dir)
    output: List[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        fence = _FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            language = re.sub(r"[^A-Za-z0-9_+-]", "", fence.group(2))
            index += 1
            code_lines = []
            while index < len(lines) and not re.match(r"^\s*%s\s*$" % re.escape(marker[0:3]), lines[index]):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            language_class = ' class="language-%s"' % language if language else ""
            output.append(
                "<pre><code%s>%s</code></pre>"
                % (language_class, html_lib.escape("\n".join(code_lines), quote=False))
            )
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            output.append(
                "<h%d>%s</h%d>"
                % (level, render_inline(heading.group(2), embedder), level)
            )
            index += 1
            continue

        if _HORIZONTAL_RE.match(line):
            output.append("<hr>")
            index += 1
            continue

        if index + 1 < len(lines) and "|" in line:
            alignments = _table_alignments(lines[index + 1])
            if alignments is not None:
                headers = _split_table_row(line)
                index += 2
                rows = []
                while index < len(lines) and "|" in lines[index] and lines[index].strip():
                    rows.append(_split_table_row(lines[index]))
                    index += 1
                output.append('<div class="table-wrap"><table><thead><tr>')
                for column, header in enumerate(headers):
                    alignment = alignments[column] if column < len(alignments) else "left"
                    output.append(
                        '<th style="text-align:%s">%s</th>'
                        % (alignment, render_inline(header, embedder))
                    )
                output.append("</tr></thead><tbody>")
                for row in rows:
                    output.append("<tr>")
                    for column in range(max(len(headers), len(row))):
                        value = row[column] if column < len(row) else ""
                        alignment = alignments[column] if column < len(alignments) else "left"
                        output.append(
                            '<td style="text-align:%s">%s</td>'
                            % (alignment, render_inline(value, embedder))
                        )
                    output.append("</tr>")
                output.append("</tbody></table></div>")
                continue

        if line.lstrip().startswith(">"):
            quote_lines = []
            while index < len(lines) and lines[index].lstrip().startswith(">"):
                quote_lines.append(lines[index].lstrip()[1:].lstrip())
                index += 1
            output.append(
                "<blockquote><p>%s</p></blockquote>"
                % "<br>".join(render_inline(item, embedder) for item in quote_lines)
            )
            continue

        unordered = _UNORDERED_RE.match(line)
        ordered = _ORDERED_RE.match(line)
        if unordered or ordered:
            list_tag = "ul" if unordered else "ol"
            pattern = _UNORDERED_RE if unordered else _ORDERED_RE
            items = []
            while index < len(lines):
                match = pattern.match(lines[index])
                if not match:
                    break
                value = match.group(1)
                task = re.match(r"^\[([ xX])\]\s+(.+)$", value)
                if task:
                    checked = " checked" if task.group(1).lower() == "x" else ""
                    value = '<input type="checkbox" disabled%s> %s' % (
                        checked,
                        render_inline(task.group(2), embedder),
                    )
                else:
                    value = render_inline(value, embedder)
                items.append("<li>%s</li>" % value)
                index += 1
            output.append("<%s>%s</%s>" % (list_tag, "".join(items), list_tag))
            continue

        paragraph_lines = [line.strip()]
        index += 1
        while index < len(lines) and not _starts_block(lines, index):
            paragraph_lines.append(lines[index].strip())
            index += 1
        paragraph = " ".join(part for part in paragraph_lines if part)
        output.append("<p>%s</p>" % render_inline(paragraph, embedder))

    return "\n".join(output)


_DOCUMENT_CSS = r"""
:root {
  color-scheme: light;
  --canvas: #eef2f6;
  --paper: #ffffff;
  --ink: #182230;
  --muted: #607086;
  --line: #d9e1ea;
  --soft: #f5f8fb;
  --accent: #245ea8;
  --accent-soft: #e8f1fb;
  --shadow: 0 24px 70px rgba(24, 34, 48, 0.13);
}
* { box-sizing: border-box; }
html { background: var(--canvas); scroll-behavior: smooth; }
body {
  margin: 0;
  color: var(--ink);
  background:
    radial-gradient(circle at 9% 4%, rgba(36, 94, 168, 0.10), transparent 28rem),
    var(--canvas);
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
  font-size: 17px;
  line-height: 1.82;
  -webkit-font-smoothing: antialiased;
}
.page {
  width: min(100% - 40px, 1020px);
  margin: 44px auto;
  background: var(--paper);
  border: 1px solid rgba(217, 225, 234, 0.9);
  border-radius: 22px;
  box-shadow: var(--shadow);
  overflow: hidden;
}
.document-header {
  padding: clamp(38px, 7vw, 76px) clamp(28px, 8vw, 86px) clamp(32px, 5vw, 54px);
  color: white;
  background:
    linear-gradient(120deg, rgba(255,255,255,0.08), transparent 46%),
    linear-gradient(135deg, #17385f 0%, #245ea8 62%, #2e74c7 100%);
  position: relative;
}
.document-header::after {
  content: "";
  position: absolute;
  right: -70px;
  bottom: -95px;
  width: 260px;
  height: 260px;
  border: 1px solid rgba(255,255,255,0.2);
  border-radius: 50%;
  box-shadow: 0 0 0 36px rgba(255,255,255,0.05), 0 0 0 74px rgba(255,255,255,0.035);
}
.eyebrow {
  margin: 0 0 16px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  opacity: 0.76;
}
.document-header h1 {
  max-width: 820px;
  margin: 0;
  color: #ffffff;
  font-size: clamp(30px, 5vw, 52px);
  line-height: 1.25;
  letter-spacing: -0.025em;
  text-wrap: balance;
  position: relative;
  z-index: 1;
}
.metadata {
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  margin-top: 26px;
  position: relative;
  z-index: 1;
}
.metadata span {
  padding: 6px 11px;
  border: 1px solid rgba(255,255,255,0.23);
  border-radius: 999px;
  background: rgba(255,255,255,0.09);
  font-size: 12px;
  line-height: 1.4;
}
article { padding: clamp(34px, 7vw, 76px) clamp(28px, 8vw, 86px); }
article > *:first-child { margin-top: 0; }
article > *:last-child { margin-bottom: 0; }
h1, h2, h3, h4, h5, h6 {
  color: #132238;
  line-height: 1.35;
  letter-spacing: -0.018em;
  scroll-margin-top: 24px;
}
h1 { margin: 2.1em 0 0.75em; font-size: 2.15em; }
h2 {
  margin: 2.2em 0 0.85em;
  padding-bottom: 0.42em;
  border-bottom: 2px solid var(--accent-soft);
  font-size: 1.65em;
}
h3 { margin: 1.8em 0 0.65em; font-size: 1.3em; color: var(--accent); }
h4, h5, h6 { margin: 1.6em 0 0.6em; font-size: 1.08em; }
p { margin: 0.9em 0 1.15em; }
a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 3px; }
a:hover { color: #164780; }
strong { color: #101c2b; }
hr { margin: 2.6em 0; border: 0; border-top: 1px solid var(--line); }
ul, ol { margin: 1em 0 1.35em; padding-left: 1.55em; }
li { padding-left: 0.24em; margin: 0.38em 0; }
li::marker { color: var(--accent); font-weight: 700; }
blockquote {
  margin: 1.7em 0;
  padding: 1em 1.3em 1em 1.5em;
  border-left: 4px solid var(--accent);
  border-radius: 0 12px 12px 0;
  color: #33475f;
  background: var(--accent-soft);
}
blockquote p { margin: 0; }
code {
  padding: 0.16em 0.38em;
  border: 1px solid #dce4ee;
  border-radius: 5px;
  background: var(--soft);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.88em;
}
pre {
  margin: 1.6em 0;
  padding: 1.25em 1.4em;
  overflow-x: auto;
  border: 1px solid #273b53;
  border-radius: 12px;
  color: #eaf2fb;
  background: #152538;
  line-height: 1.58;
}
pre code { padding: 0; border: 0; color: inherit; background: transparent; }
.table-wrap {
  margin: 1.7em 0 2em;
  overflow-x: auto;
  border: 1px solid var(--line);
  border-radius: 13px;
}
table { width: 100%; border-collapse: collapse; font-size: 0.94em; line-height: 1.55; }
th, td { min-width: 112px; padding: 12px 15px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: #18314f; background: var(--accent-soft); font-weight: 700; }
tbody tr:nth-child(even) { background: #fafbfd; }
tbody tr:last-child td { border-bottom: 0; }
.document-image {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 1.6em auto;
  border: 1px solid var(--line);
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(24, 34, 48, 0.10);
}
.image-missing { color: var(--muted); font-style: italic; }
.document-footer {
  padding: 22px clamp(28px, 8vw, 86px) 26px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  background: var(--soft);
  font-size: 12px;
}
input[type="checkbox"] { accent-color: var(--accent); }
@media (max-width: 640px) {
  body { font-size: 16px; }
  .page { width: 100%; margin: 0; border: 0; border-radius: 0; box-shadow: none; }
  .document-header, article { padding-left: 22px; padding-right: 22px; }
  th, td { min-width: 96px; padding: 10px 12px; }
}
@media print {
  @page { margin: 16mm; }
  html, body { background: white; }
  body { font-size: 11pt; }
  .page { width: 100%; margin: 0; border: 0; border-radius: 0; box-shadow: none; }
  .document-header { padding: 26px 30px; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  article { padding: 30px; }
  a { color: inherit; }
  .table-wrap { overflow: visible; }
  pre { white-space: pre-wrap; }
  h1, h2, h3, table, blockquote, .document-image { break-inside: avoid; }
}
"""


def render_markdown_document(
    markdown_text: str,
    fallback_title: str,
    source_filename: str,
    liteparse_version: str = "2.4.0",
    image_base_dir: Optional[Path] = None,
) -> str:
    title, body = extract_title(markdown_text, fallback_title)
    content = markdown_to_html(body, image_base_dir=image_base_dir)
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    escaped_title = html_lib.escape(title)
    escaped_source = html_lib.escape(source_filename)
    escaped_version = html_lib.escape(liteparse_version or "2.4.0")
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="generator" content="LiteParse %s + deterministic local HTML renderer">
  <title>%s</title>
  <style>%s</style>
</head>
<body>
  <main class="page">
    <header class="document-header">
      <p class="eyebrow">LiteParse 本地文档</p>
      <h1>%s</h1>
      <div class="metadata">
        <span>源文件：%s</span>
        <span>LiteParse %s</span>
        <span>本机离线 · 无 LLM</span>
      </div>
    </header>
    <article>%s</article>
    <footer class="document-footer">生成时间：%s · 内容未经模型改写或摘要</footer>
  </main>
</body>
</html>
""" % (
        escaped_version,
        escaped_title,
        _DOCUMENT_CSS,
        escaped_title,
        escaped_source,
        escaped_version,
        content,
        html_lib.escape(generated_at),
    )


def render_markdown_file(
    markdown_path: Path,
    output_path: Path,
    fallback_title: str,
    source_filename: str,
    liteparse_version: str = "2.4.0",
    image_base_dir: Optional[Path] = None,
):
    markdown_text = markdown_path.read_text(encoding="utf-8", errors="replace")
    rendered = render_markdown_document(
        markdown_text,
        fallback_title=fallback_title,
        source_filename=source_filename,
        liteparse_version=liteparse_version,
        image_base_dir=image_base_dir,
    )
    output_path.write_text(rendered, encoding="utf-8")
