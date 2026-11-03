# LiteParse PDF 自动识别

## Purpose

基于本机 LiteParse 2.4.0，实现一个 macOS 本地后台自动化：将 PDF 放入 `inbox/`，待文件写入稳定后自动识别，并在 `outbox/` 同时保留排好版的 HTML 与便于 Agent 处理的 Markdown。Markdown 会自动合并同一自然段内由 PDF/OCR 版面造成的软换行。全程不调用 LLM。

## 范围

- 仅处理 PDF。**识别、排版与 HTML/Markdown 生成全部在本机完成**；默认的翻译阶段（`dual_track_mode` 非 `disabled`）会把提取出的正文文本发往 `pdf2zh_service` 指定的翻译服务（默认 Bing），不会上传原始 PDF 文件。后台监控器需要完全离线时，把 `dual_track_mode` 设为 `"disabled"`。
- Studio 工作台不读取 `dual_track_mode` 的禁用设置，默认使用界面所选在线翻译服务。如需在 Studio 内使用本地翻译，应选择“原位双层”模式，并确保本地翻译模型可用。
- 同时支持带文字层 PDF 和需 OCR 的扫描 PDF。
- 支持提取 LiteParse 能识别的 PDF 内嵌位图，并用 Base64 直接嵌入 HTML。
- 对无文字层的长篇扫描书自动使用“原页保真 HTML”：每页扫描图作为正文，不让 OCR 改写排版、表格、图表或公式。
- 自动检测 LiteParse Markdown 中整列丢失的异常表格，并用同页文字坐标确定性重建单元格；不调用 LLM。
- 矢量 PDF 的表格单元格按 OpenDataLoader 单元格坐标原位回贴中文，保留表格线、底纹、列宽与行高；表注一并翻译。
- 矢量图（如授权流程图）的色块标签按原框回贴中文，保留色块、边框与列布局；同时清理 pdf2zh 重排后遗留的孤立标题下划线，不碰表格线、脚注线和彩色链接线。
- 使用已获“文稿”访问权的当前用户会话在后台运行；重启 Mac 后可双击项目内的启动入口。
- 成功后归档原 PDF，失败时保留原文件和错误说明。

## Status

已完成，后台监控正在运行。

“正在运行”是 2026-07-15 的最近一次已记录验收，不代表每次开机后的实时状态；当前状态应以“查看运行状态”入口或下方 `status` 命令为准。

## Stack

- Python 3 标准库：监控、原子发布、确定性 HTML 与 Markdown 重排。
- PyMuPDF（`fitz`）：版面探针、页图裁剪与双语 PDF 合成；版本见 [`requirements.txt`](requirements.txt)。
- fontTools：矢量表格/图内文字回贴时按实际用字裁 Source Han 字体，避免整字体嵌入。
- LiteParse `lit` CLI 与 OpenDataLoader-PDF（需要本机 Java）：文字层/OCR、结构、表格与坐标提取。
- Poppler 与 Tesseract（或 PaddleOCR venv）：长篇扫描书的原页保真和辅助 OCR 路由。
- Google Chrome（无头打印）与 `~/.local/venvs/pdf2zh`：出版级高清 PDF 与矢量论文原位翻译。
- macOS 用户会话后台进程：不注册系统级常驻服务。

> 任何一项外部依赖缺失时，对应路由会失败并写入 `failed/*.error.txt`，不会静默降级或上传内容。

## Quick Start

1. 把 PDF 放入 [`inbox/`](inbox/)。
2. 等待至少 5 秒，再等 LiteParse 完成识别。
3. 在 [`outbox/`](outbox/) 取得同名 `.html` 和 `.md`：HTML 用于保真阅读，Markdown 已做段落自动排版，可用于复制到翻译网页或交给其他 Agent 检索、分析和改写。
4. 成功后的原 PDF 会移入 [`processed/`](processed/)；失败的 PDF 会进入 [`failed/`](failed/)，并附带 `.error.txt` 说明。

非 PDF 文件会被忽略。同名文件不会覆盖旧结果，系统会自动添加 `-2`、`-3` 等后缀。

后续新投递 PDF 默认同时生成 `.html` 与 `.md`。普通 PDF 的 Markdown 保留 LiteParse 文本、表格修复结果和图片相对路径；图片保存在同名 `_assets/` 目录。扫描书 Markdown 按页保存本地 OCR 文字，不嵌入巨大页图。

## 桌面端设置

顶栏齿轮或应用菜单「设置…」（⌘,）打开设置窗口：

- **通用**：选择输出文件夹（可位于项目外）、识别模式、翻译服务与清空已完成任务。输出文件夹只影响 Studio 新任务；原 PDF 仍归档到项目的 `processed/`。后台 watcher 与命令行走 `config.json` 的 `outbox`。
- **外观**：选择墨蓝/松绿/紫檀/岩灰强调色，以及暖纸/雾灰/米白画布底色；主题、输出路径和默认策略会持久化。
- 输出路径由本地 `127.0.0.1:8765` 的后台接口切换；目录必须存在且可写，非法路径不会生效。

## 可双击的入口

- [`打开PDF投递箱.command`](打开PDF投递箱.command)
- [`打开识别结果.command`](打开识别结果.command)
- [`查看运行状态.command`](查看运行状态.command)
- [`启动自动识别.command`](启动自动识别.command)
- [`停止自动识别.command`](停止自动识别.command)

当前后台进程会持续运行。重启 Mac 或退出登录后，双击“启动自动识别”即可恢复。

## Commands

```bash
# 查看、启动和停止后台监控
python3 -m src.manage status
python3 -m src.manage start
python3 -m src.manage stop

# 前台运行，便于查看即时错误
python3 -m src.watcher

# 离线单元测试；不会读取 inbox/processed 中的用户 PDF
python3 -m unittest discover -s tests -v
```

项目无独立 `build` 或 `lint` 命令；完整端到端验收需要向 `inbox/` 投递一份无敏感信息的小 PDF。

## 默认处理策略

- 每 2 秒检查一次投递箱，只处理连续稳定 5 秒的 PDF，防止读到尚未复制完的文件。
- 先使用 `--no-ocr` 快速读取文字层；统计时排除 Markdown 代码围栏、图片引用和 HTML 标签，避免把结构标记误当正文。
- 有文字层的 PDF 继续使用 LiteParse Markdown 重排版 HTML；无文字层且页数达到门槛的扫描书自动转入原页保真 HTML。
- 保真模式使用本地 Poppler 将每页生成 JPEG，Base64 内嵌到一个 HTML；本地 Tesseract `chi_sim+eng` 文字只放在每页下方的折叠“辅助识别文字”中，不参与可见排版。
- 同一次解析结果同时生成 HTML 和 Markdown，不为第二种格式重复调用 LiteParse。
- 默认启用 `reflow_markdown: true`：合并正文连续行，并在“上一行足够长、末尾没有句末标点、下一行不是新结构”时修复 PDF 常见的伪空白段落。
- 标题、带句末标点的真实段落边界、列表起点、表格行、图片、引用、代码围栏、公式、分页线和扫描书页码边界不会被跨结构合并；英文大写记录起点也按新条目保留。
- 中文行与中文行直接续接；英文单词之间补一个空格；行末连字符保留且不额外插空格。该过程是固定规则，不做语义改写、纠错或补字。
- LiteParse 以 Markdown 作为临时中间格式，同时使用 `image-mode=embed` 提取内嵌位图。
- 对表格单元格内的中文断词伪空格做局部清理；中英文之间的必要空格保持不变。
- 仅当表格出现整列为空等强异常信号时，才额外读取对应页的 LiteParse JSON 坐标；表头、行锚点和原有单元格通过一致性校验后才替换原表格。
- Python 标准库渲染器将标题、段落、列表、表格、引用、代码和链接转换为 HTML，并加入响应式与打印 CSS。
- 提取出的图片被编码为 `data:image/...;base64` 写入 HTML，因此 HTML 本身仍是无外部依赖的单文件。
- 为了让 Markdown 也能引用提取图片，其所需图片会集中保存在 `<文件名>_assets/`，Markdown 使用可移动的相对路径。
- 原始 HTML 会被转义，`javascript:` 等危险链接不会进入最终 HTML。
- 单份 PDF 默认最多 1000 页，解析超时为 30 分钟，OCR 并发数为 2。
- 输出先写临时文件，成功后再原子移入 `outbox/`，避免用到半成品。
- 运行日志在 `logs/watcher.log`，每份最大 1 MB，保留 3 份备份。

参数可在 [`config.json`](config.json) 中调整。

## Notes

- 识别、排版与单文件 HTML 生成在本机执行，不上传原始 PDF；默认开启的翻译阶段会把正文文本发往配置的翻译服务，详见「范围」。
- HTML 排版是固定规则与 CSS，没有 LLM 摘要、改写、纠错或内容判断。
- 已验证带文字层 PDF、短扫描 PDF 常规 OCR 和长篇扫描书保真输出三条路由。OCR 会受清晰度、字体与排版影响，因此保真模式中 OCR 只作辅助搜索与复制，原扫描页才是内容准绳。
- LiteParse 能提取照片、logo、印章等被 PDF 识别为内嵌位图的内容。纯矢量图形、复杂图表或整页扫描底图不一定会作为独立图片返回；长篇扫描书因此会改用每页整体成像的保真路由。
- 保真 HTML 为了离线单文件携带每页图像，体积会明显大于普通重排版 HTML；数百页扫描书需要数分钟处理。
- 扫描书 `.md` 是 OCR 文字层，适合 Agent 做检索与粗处理，但不能替代 HTML 中的原页图；关键表格、公式和数字仍应回看 HTML。
- 无 LLM 条件下无法百分之百判断所有异常空白究竟是排版换行还是作者有意分段，因此排版器采用保守信号；它优先保证标题、表格、代码、公式和分页可追溯，不跨扫描页拼接句子。
- 表格坐标修复采用保守策略；无法通过一致性校验的复杂合并单元格会保留 LiteParse 原结果并写入警告日志，不会猜测或调用模型补写。
- 密码保护 PDF 会失败并进入 `failed/`，当前不在配置中保存 PDF 密码。
- macOS 不允许未授权的 `launchd` 任务直接读取“文稿”内的项目。为了不复制项目到工作区外、也不给 Python 过宽的磁盘权限，本项目由已获文稿访问权的用户会话启动独立后台进程。

## Project Structure

- `inbox/`：PDF 投递箱。
- `outbox/`：HTML、Markdown 与 Markdown 图片资源。
- `processing/`：正在处理的临时区。
- `processed/`：成功处理后的原 PDF 归档。
- `failed/`：失败的 PDF 和错误说明。
- `src/`：监控器与管理脚本。
- `tests/`：测试和验证记录。
- `docs/`：使用与设计文档。
- `assets/`：项目资源。
- `logs/`：有上限的运行日志。
- `tasks/`：简短任务记录。

## Configuration

运行参数集中在 [`config.json`](config.json)，包括投递/处理/成功/失败/日志目录、稳定等待时间、轮询间隔、页数与超时上限、OCR 语言和并发数。相对路径按项目根解析。

- `reflow_markdown` 控制确定性段落重排。
- `scan_book_min_pages` 控制长篇无文字层 PDF 是否转入原页保真路由。
- `log_max_bytes`（64KB–64MB，默认 1MB）与 `log_backup_count`（1–20，默认 3）控制 `logs/watcher.log` 的轮转。
- `dual_track_mode` 为 `"disabled"` 时走纯本地单轨（HTML/Markdown）；`auto`/`vector`/`scanned` 会启用翻译并联网。
- 项目不需要 API Key，也不应把 PDF 密码写入配置。

迁移机器前应同时检查 `lit`、`pdftoppm`、`tesseract` 及语言数据是否可用；缺失时相关路由会失败，而不是自动上传或调用云端服务。

## 验证

```text
283 项单元测试通过（含安全边界、双轨状态机、上传/下载路径、图内文字与列表页重排回归）
DOE p5 列表页按源基线恢复 a/b/c/d/1)/2)/3) 悬挂缩进，6 条内联下划线贴回对应中文术语
LiteParse 真实文字层 PDF 验收通过
后台监控“投递 -> 等待 -> HTML 输出 -> 归档”验收通过
简体中文扫描 PDF OCR 路由验收通过
真实 PDF 内嵌印章提取与 Base64 HTML 嵌入验收通过
最终 HTML 视觉预览通过
真实四列表格 PDF 的“整列脱落 -> 坐标重建 -> 16 行完整 HTML”回归通过
扫描书封面、图表、示意图和正文代表页保真 HTML 视觉验收通过
保真 HTML 打印验证为 PDF 一页对应 HTML 一页
513 页《熔盐堆科学技术导论》后台端到端保真输出通过：513 页图 + 513 辅助 OCR 层，失败 0
真实 PDF 后台双输出验收通过：HTML + Markdown + 1 个可解析的相对路径图片资源，表格修复结果一致
Markdown 段落排版回归通过：普通文档与扫描 OCR 的单换行、伪空白行可确定性合并，结构计数和非空白文字保持一致，二次运行不再改动
10 页真实扫描样本后台验收通过：5.5 秒生成 HTML + Markdown，自动合并 136 处换行，失败 0
513 页《熔盐堆科学技术导论》存量 Markdown 补排版通过：513 页与非空白文字逐页一致，处理后稳定无二次变化
```
