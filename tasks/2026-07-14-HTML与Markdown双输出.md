# 2026-07-14 HTML 与 Markdown 双输出

## 目标

保留默认排版 HTML，同时保留 Markdown，便于后续交给其他 Agent 处理。

## 实现

- 新增 `keep_markdown: true`，HTML 模式下同时发布同名 `.md`。
- 普通 PDF 的 HTML 与 Markdown 复用同一次 LiteParse 结果，表格坐标修复和断词清理同时反映在两种输出中。
- Markdown 引用的 LiteParse 图片保存到同名 `_assets/` 目录，引用重写为可移动相对路径。
- 扫描书 Markdown 按 `## 第 N 页` 分隔本地 OCR 文字；页图仅保留在同名保真 HTML，避免 Markdown 体积过大。
- 同名检查同时覆盖 HTML、Markdown 和资源目录，不覆盖旧结果。
- 多输出发布中途失败时回收已发布的同批文件，原 PDF 仍按失败流程隔离。

## 存量回填

- 从现有保真 HTML 直接提取 513 页 OCR 辅助文字，生成 `熔盐堆科学技术导论-保真版.md`，约 915 KB，未重跑 OCR。
- 为已完成的英文专著回填约 1.9 MB Markdown 及 309 个引用图片。

## 验证

- 14 项单元测试通过，覆盖双输出、图片相对路径、扫描书 Markdown、动态代码围栏和同名保护。
- 真实 PDF 后台投递生成 `双输出验证.html`、`双输出验证.md` 与 1 个图片资源。
- Markdown 中图片相对路径可解析，缺失资源 0；两张四列表格表头与 HTML 一致。
- 后台监控进程保持 `PPID=1`，待处理 0，失败 0。
