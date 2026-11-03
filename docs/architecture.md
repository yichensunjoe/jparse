# P052-LiteParse-PDF自动识别 — 架构

## 数据流

```text
inbox/PDF
   │ 等待大小与时间稳定
   ▼
processing/临时工作区
   │
   ├─ 有文字层 ── LiteParse Markdown + 图片 ── HTML/Markdown
   ├─ 短扫描件 ── LiteParse OCR ───────────── HTML/Markdown
   └─ 长篇扫描书 ─ Poppler 页图 + Tesseract ─ 保真 HTML/辅助 Markdown
   │
   ├─ 成功：原子发布到 outbox/，原 PDF 移至 processed/
   └─ 失败：原 PDF 与错误说明移至 failed/
```

## 组件

- `src/watcher.py`：轮询、稳定性判断、路由、临时文件和归档编排。
- `src/manage.py`：用户会话后台进程的 start/stop/status 管理。
- `src/html_renderer.py`：普通 Markdown 的安全 HTML 渲染。
- `src/scan_html_renderer.py`：扫描书逐页保真 HTML。
- `src/markdown_reflow.py`：确定性软换行修复。
- `src/table_repair.py`：强异常信号触发的坐标表格修复。
- `src/table_overlay.py`：矢量 PDF 表格单元格按 OpenDataLoader bbox 原位回贴中文，保留网格与底纹。
- `src/figure_overlay.py`：矢量图内标签按色块/单元格聚合翻译，只擦文字、保留图形与配色。
- `src/pdf_cleanup.py`：清理 pdf2zh 重排后遗留的孤立标题/内联下划线，保护表格、脚注与彩色链接线。
- `src/text_layout_repair.py`：识别 pdf2zh 把多个列表项合并成一段的页面，按源 PDF 的基线、悬挂缩进和列表标记重排；只改译文页，并将原内联下划线贴回对应中文术语。
- `config.json`：路径、超时、页数、OCR 与日志限制。

## 关键不变量

1. 不读取尚未稳定的 PDF。
2. 输出未完成前不出现在 `outbox/` 的正式文件名下。
3. HTML 不执行来自 PDF 的原始 HTML 或危险链接。
4. OCR/重排只产生派生文本，不覆盖原 PDF；关键内容以原页为准。
5. 任一路由失败都保留可恢复的原文和错误说明。

## 运行边界

后台进程属于当前用户会话。重启或退出登录后是否运行必须通过 `python3 -m src.manage status` 实测；文档中的历史运行状态不是在线探针。
