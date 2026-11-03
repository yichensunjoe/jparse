# 本项目踩坑记录（REUSE_AND_PITFALL_LOG）

本项目专属的踩坑/可复用经验明细。总项目库 `/Users/joe/ai/reasonix/REUSE_AND_PITFALL_LOG.md` 为全局汇总。

规则：执行任务前先读本文件；任务完成后**双写**——先追加本文件，再同步追加总库（见 AGENTS.md）。

## 2026-11-02 · 矢量论文内嵌位图图例的原位翻译与重绘（P052-LiteParse-PDF自动识别）

- 场景：用户反馈在处理学术论文（如 MDPI、Springer、IEEE）时，正文虽是矢量文字并已被翻译，但论文内的流程图、网络结构图（如 Figure 1 代理模型流程、Figure 2 神经网络结构）中的英文文字依然未翻译。
- 根因：这些图由作者在外部绘图工具制成后以位图（PNG/Image XObject 带 SMask 透明通道）形式贴入论文中，PDF 文字流中文字对象为 0。此前的 `figure_overlay` 属于矢量图层引擎（只处理矢量路径与文字），为保护位图画质跳过了纯位图。
- 做法：新增 `src/bitmap_figure_translator.py`，构建位图图例原位翻译管道：
  ① 提取带 SMask 透明通道的高清位图并于白底合成；
  ② 本地 PaddleOCR 1:1 像素空间精确检测（禁用 UVDoc/orientation 避免坐标扭曲，置信度达 0.98~1.00）；
  ③ 门禁机制：自动跳过数学公式与变量（$x_1, x_2, y_1$, formulas），跳过无文字纯照片与散点图；
  ④ 智能多行聚合与核能领域词典适配（如 `core input parameters` -> `堆芯输入参数`，`NN model` -> `NN 模型`）；
  ⑤ 容器边界底色采样与原位平滑擦除；
  ⑥ 思源黑体抗锯齿重绘，自动提取并匹配原图字体颜色（输入层橙色、隐藏层蓝色、输出层绿色）；
  ⑦ PyMuPDF `replace_image(xref)` 直接在 PDF 内原位无缝替换图片对象，外部排版与图题完全不变。
- 验证：Figure 1、Figure 2 全部精准翻译重绘，全量 293/293 单测全绿，端到端替换生成 PDF 并实机比对验证。
- 适用：学术论文与技术白皮书中以栅格位图（PNG/JPEG）形式内嵌的流程图、框图、架构图原位翻译与本土化重绘。


## 2026-11-02 · 模式收口与极简降噪：隐藏模式选择与投递区翻译选项（P052-LiteParse-PDF自动识别）

- 场景：用户反馈顶栏/设置中的模式切换（智能双轨/高清扫描/现代矢量/原位双层）及投递卡片上的翻译引擎选择/隐私说明造成过多视觉干扰与解释成本，要求彻底隐藏模式选择并让投递面板回归原始极简状态。
- 做法：① 移除 `LightHeaderView` 顶栏的 `pipelineSwitcher` 与更多模式菜单，顶栏仅保留品牌与状态操作；② 移除 `LightDropZoneView` 空态 Hero 与紧凑条上的 `TranslationServicePicker` 与 `TranslationServiceNotice`，主卡片仅保留核心 CTA（选取文献 / 导入目录 / 拖拽提示）；③ 移除 `SettingsView` 中的“识别模式”Picker，翻译引擎统一收进偏好设置（⌘,）按需配置，代码中将默认路由锁死为 `.auto`；④ Web UI（`src/web_app.py`）将“智能路由策略”下拉框替换为隐藏域 `<input type="hidden" id="pipelineMode" value="auto">`，保持 `/api/upload` 协议兼容。
- 踩坑：投递面板移除选择器后，紧凑条恢复为单行 `HStack` 布局，高度更紧凑；隐藏模式与翻译选择不影响后台默认能力，默认依旧走智能双轨与 Bing 神经翻译。
- 验证：Swift 重新编译零警告（2.4M），真机截图确认 Hero 与顶栏恢复纯白极简；`tests/test_macos_ui.py`、Tier3/Tier4、287/287 单元测试全绿。
- 适用：专业工具大众化收口时，将底层技术分支（如多种排版/抽取策略）与高阶配置（翻译服务）下沉到偏好设置，主视窗只保留极简投递动作。

## 2026-11-02 · 原生设置窗口：输出目录、主题令牌与后端重放（P052-LiteParse-PDF自动识别）

- 场景：桌面端需要把“基本设置”收进原生设置窗口，其中最关键的输出文件夹必须真正影响后续任务，而不能只改 UI 文案。
- 做法：新增 `AppSettings`（UserDefaults）与 `Settings` scene；用 `NSOpenPanel` 选目录，`BackendManager` 通过 `POST /api/settings` 同步到 `ConversionTaskManager.outbox_dir`，后端先创建目录并写探针再发布；主题改为 4 个强调色 × 3 个画布底色，`LightTheme` 从 `static let` 改为计算属性，并用 `themeRevision` + `.id()` 强制主视图重新取值。
- 踩坑：① `LightTheme` 的静态 `let` 会在启动时冻结颜色，设置改变后只有设置窗口变色；必须改成读取 `AppSettings` 的计算属性，并在根视图用 revision 重建。② `Settings` scene 必须是顶层 scene，`.commands` 要挂在 `WindowGroup` 上；误把 `.commands` 接在 `Settings` 后面虽然能编译，但工作台菜单的归属会漂移。③ 输出目录只存 App 端不够：后端重启会回到默认 `outbox`，所以每次连上/重连都要按当前 UserDefaults 重放；后端还需做真实写入探测，避免接受只读目录。④ 这是 Studio 任务级设置，后台 watcher 仍读 `config.json`，文档必须写明。
- 验证：Swift 零警告 2.7M；`286/286` 单测（22.94s）；Tier4 8/8；真实原位 HTML 解析 149K；8765 设置 API 200、自定义目录下载 200、文件路径 400、恢复默认 200；设置窗口从菜单打开后窗口列表出现「通用」。
- 适用：桌面 App 的“偏好设置”必须同时做本地持久化、后端重放和真实能力校验；主题切换要把设计令牌改成可观察状态，而不是只换一个局部颜色。

## 2026-10-30 · 工程减负：先引用核查，再删缓存/生成物/重复归档（P052-LiteParse-PDF自动识别）

- 场景：1.26G 中大部分是用户原件和交付物，不能按目录名直接清；需要证明删除项不被运行时/测试引用。
- 做法：`rg` 搜索 `src`/`tests`/Swift/文档引用；只删 `.pytest_cache`、`.ruff_cache`、`__pycache__`、`.DS_Store`、旧 `audit_screenshots/`、4 个未跟踪测试输出、`work/acceptance_preview`；对 `processed`/`outbox` 的 ≥1MB 文件做 SHA-256 分组，删除 5 组字节级重复件，保留规范名/被任务文档引用的那份。
- 踩坑：① “测试产物”与“用户原件”必须分开，`processed/`/`outbox/`/`assets/models` 不动；② tracked `tests/artifacts` 与 `work/ui_review` 不属于缓存，保留证据；③ 有引用的 `熔盐堆…-保真版.pdf` 不能删，改删无引用的同哈希基名副本。
- 验证：283/283（19.86s）、Tier4 8/8、8765=200；体积 1.26G→902M（约 391MB）；无代码/管线变更。
- 适用：工作区减负先按“运行引用/测试引用/历史证据/用户数据”四层分流，重复大文件用哈希证明后再删。

## 2026-11-02 · 桌面文件工作台：阶段进度与隔离 UI 验证（P052-LiteParse-PDF自动识别）

- 场景：服务端只上报 10/30/100 阶段值，界面把 30% 当精确进度；本地 App 还固定连接现有 8765 服务。
- 做法：UI 显示不定进度和阶段说明；通过独立端口、模拟响应和合成任务核对空态/失败/成果，不替换现有 App 或服务。导入时快照模式与服务，模式请求值单独映射，保留既有偏好值。
- 踩坑：空列表分支也需要显示上传和错误；只在前端删除完成记录会被轮询重新带回；文件本地识别不代表翻译文字不上网，说明必须放到服务选择旁。全量单测还可能条件性读取现有 PDF，运行前应核对测试内容。
- 验证：Swift 原生状态测试 3 次通过、287/287 项单测、合成 PDF 真实 LiteParse 闭环；截图 `work/ui_review/ux-20261102-review/`。
- 适用：本地文件处理客户端 + 后台轮询 + 可选在线服务。

## 2026-10-30 · 顶栏/空状态品牌标记与 AppIcon 统一（P052-LiteParse-PDF自动识别）

- 现象：换完 AppIcon 后，顶栏 26pt 和空状态 68pt 仍是旧的蓝色圆角方块 + 白色文档 SF Symbol，界面与 Dock 图标像两个产品。
- 做法：在 `LightTheme` 新增 `LiteParseMark` 矢量视图：深墨蓝圆角底、约 39%×52% 的暖白纸页、右上折角、页尾青色光标和四角火花；顶栏 26pt、空状态 68pt 共用。小于 40pt 时文本行从三行减为两行，保留轮廓和光标；拖拽条仍用 SF Symbol，功能符号不参与品牌化。
- 踩坑：① 不要用 `Image("AppIcon")` 依赖 `.icns` 资源加载，图标资源在 Bundle 里不等于 SwiftUI 可直接取用；画同源矢量更稳。② 26pt 下若照搬 1024 图标的细节，纸页会缩成白块；需按尺寸减少行数、给线条最小 0.55–0.7pt 下限。③ 纸页占卡片比例要按图标实际 39%×52%，而不是凭感觉用 34%×46%，否则大尺寸品牌标记会显得空。
- 验证：Swift 零警告 2.0M；顶栏/空状态/1008/900 两档实机截图；`283/283` 单测（25.16s）。截图 `work/ui_review/ui-brandmark-final.png`、`ui-brandmark-compact.png`、`ui-brandmark-before-after.jpg`。
- 适用：App 图标更新后，界面内的品牌标记应与 Dock/Finder 图标同源；尺寸差异用简化细节处理，不要把功能图标也强行换成品牌符号。

## 2026-10-30 · App 图标从居中厚文档改为折角纸页 + 解析火花（P052-LiteParse-PDF自动识别）

- 现象：旧图标是蓝色渐变底 + 居中白文档 + 四条粗横线，轮廓方正、重心居中，像通用文档模板；用户觉得“笨拙”。
- 做法：`generate_icon.py` 重写为 2048 超采样：深墨蓝圆角底（左上冷光/右下青回光），暖白纸页逆时针倾斜 8°，右上折角露出青色纸背，三条细墨线 + 页尾青色光标，折角旁四角星火花。导出 1024 icns 及 16–512 全套尺寸。
- 踩坑：① 旧版文档圆角过大、横线过粗，缩小后只剩一块白卡片；新版收窄纸页、圆角 26、线宽 9，16px 仍有斜向轮廓。② 纸页投影必须跟纸页一起旋转，否则会出现“纸在飘、影子没动”。③ 火花先画柔光层再叠星形，否则小尺寸下只是硬点；透明角必须保留，不能把圆角底铺满画布。
- 验证：`sips` 取 icns 1024 PNG，角落 alpha=0；16/32/64/128/512/1024 目视走查；App bundle 图标用 `NSWorkspace` 复核；Swift 零警告 2.0M，283/283 单测（21.37s）。截图 `work/ui_review/icon-final-1024.png`、`icon-before-after.png`。
- 适用：macOS App 图标；需要摆脱“白文档 + 蓝底”模板感时，用倾斜、折角、单一彩色焦点建立轮廓记忆点。

## 2026-10-30 · 顶栏四模式平铺收为“当前模式 + 更多模式”（P052-LiteParse-PDF自动识别）

- 需求：四个模式项常驻顶栏太像参数面板；只保留默认“智能双轨”，其余收进“更多模式”菜单，但四项都要可切换。
- 做法：`LightHeaderView` 左侧显示当前模式（图标 + 短名 + 墨蓝选中片），右侧 `Menu` 内用 `Picker(.inline)` 列出 `PipelineMode.allCases`，原生勾选当前项；默认只显示“智能双轨”，选择其他模式后左侧同步更新。移除原 `ForEach` 与 `matchedGeometryEffect`。
- 踩坑：`Menu` 在 `.borderlessButton` 样式下已自带下拉指示器；再手放 `chevron.down` 会与系统指示器争位置，实测出现左侧箭头、右侧消失，去掉自定义箭头后系统箭头正常落在右侧。互斥选项用 `Picker(.inline)` 才有原生勾选态，手写 Button + checkmark 容易在菜单里错位。
- 验证：菜单展开四项且当前项勾选；切到“高清扫描”顶栏同步、再切回“智能双轨”均实测；Swift 零警告 1.8M；283/283 单测（22.20s）；1008/900 截图。
- 适用：macOS SwiftUI 工具顶栏参数收口；默认项覆盖多数场景、其余模式低频但需保留时，用“当前值 + 更多”替代平铺分段控件。

## 2026-10-30 · 桌面端配色从“冷白 + 系统蓝”收敛为“暖纸 + 墨蓝”（P052-LiteParse-PDF自动识别）

- 现象/需求：顶部分段控件仍是系统默认的深灰轨道 + 纯白滑块，整窗冷白 + #0071E3 高亮蓝，和“学术文档工作台”的纸张/校样语义脱节；用户要求参考 oil-ui 继续优化配色。
- 方向：把界面当成一张承托白纸的工作台——画布 #F3F1EB 暖纸色，内容卡保持纯白，文字用带蓝 undertone 的墨色 #1D2630，唯一主色收深为墨蓝 #1F5F8A；状态色去荧光（绿 #3D7A58、青 #2A737A、琥珀 #955F28、红 #B0444A）。
- 做法：颜色集中到 `LightTheme`；分段控件轨道 #E5E2DA、选中底为 18% 墨蓝冷调片、选中文字/图标 #174B6D 并加 0.26 蓝色发丝描边；画布改暖纸竖向渐变，雾光从紫改为青；主按钮/进度条/图标统一 #2C76A0→#1C4F74 窄渐变；PDF 交付图标由红色改墨蓝，红色只留给错误。
- 踩坑：① 不能只把强调色调深——外层表面也要有冷暖关系，否则仍像系统默认；② 选中态文字在浅轨道上必须重新算对比度，本轮确保 ≥4.5:1；③ 青色状态字在 8% 同色底上原 #2E7C84 只有 4.39:1，收深到 #2A737A 才过线；④ 白字主按钮的渐变顶端 #2C76A0 才稳过 4.5:1；⑤ 非错误语义不要用红色，否则 PDF 图标会像失败；⑥ `regularMaterial` 顶/底栏实际比画布更深，`textMuted` 在其上只有 4.3:1，footer 改用 `textSecondary` 才过线。
- 验证：Swift 零警告构建 1.7M；283/283 单测通过（23.14s）；1008×736 与 900×700 实机截图通过；任务卡用 `ImageRenderer` 复核完成态、交付行、状态胶囊；PDF 识别/翻译管线未改。截图 `work/ui_review/ui-color-before-after.jpg`、`ui-color-control-before-after.jpg`、`ui-color-after-final.png`、`ui-color-compact-final.png`、`ui-color-task-card.png`。
- 适用：macOS 原生 SwiftUI 工具类应用的配色收敛；尤其适合“白纸内容 + 系统蓝控件”显得像默认模板时。

## 2026-10-30 · pdf2zh 合并列表页重建 + 下划线语义回贴（P052-LiteParse-PDF自动识别）

- 现象：DOE 第 2 页（文件 p5）译文的 a/b/c/d/1)/2)/3) 全部挤成一段，后续行没有悬挂缩进；原页下划线按旧坐标保留，横穿未排好的中文。看起来像“线没删干净”，实际是段落结构丢失。
- 根因：pdf2zh 的布局阶段按文本类合并相邻行，同属正文的多个列表项被并为一个段落；它只保留行级基线/类，不保留源块的列表边界、首行缩进和续行缩进，所以单纯删线或微调坐标无法恢复对应关系。
- 做法：新增 `src/text_layout_repair.py`。只对满足门限的页面启用：译文页至少 2 个 `\x00` 段落标记、源页至少 2 个真实列表标记、源页无图片/大面积填充/过多长横线。从源页提取标题、每项首行 x、续行 x、基线和下划线语义；从当前译文提取段落文本；用 SourceHanSerif 子集重写译文页，擦掉旧正文和旧内联线，再按源语义在中文首句下画线。双语只改译文页。
- 踩坑：① 不能把所有细线都当正文下划线——脚注线、表格线、彩色链接线必须保留；② 不能无条件重排——含图/表的页面会破坏坐标，p26（仅 bullet、无节标题）与 p27（译文无 NUL 段落标记）仍应跳过；③ 不能重新翻译，否则译文术语会漂移；④ 中文行高与源英文行高不同，必须按“段首对齐源基线、段内自然行距”处理，不能强行逐行拉伸。
- 验证：DOE p5 恢复 7 个独立段（a/b/c/d/1)/2)/3)），519 汉字、无 `\x00`；6 条内联下划线落在对应中文术语下，另保留 1 条脚注线（共 7 条 drawings）；双语 idx9 同步，idx8 原文保持英文。p9 Figure 1 的 16 组中文标签、p11 表格 482 汉字、p13 584 汉字均无回归。283/283 单测全绿（23.46s，复跑）；单语 28 页 1.08 MB、双语 56 页 1.27 MB。截图 `work/ui_review/current-mono-p5.png`、`current-dual-p5.png`、`source-p5.png`。
- 适用场景：pdf2zh 输出中“多个列表项被合并、缩进丢失、旧下划线穿字”的矢量页；不适用于扫描件、表格页、图片页和没有稳定列表标记的段落。

## 2026-10-30 · 矢量图内文字回贴 + 孤立下划线清理（P052-LiteParse-PDF自动识别）

- 现象：① pdf2zh 译文页在正文末尾留下两条横线（原为标题/内联短语下划线，文字被重排后线还在）；② Figure 1 的色块与图内标签仍是英文，只有图题和注释被译。
- 根因：pdf2zh 稳定后端把 `figure` 与 `table` 一起放进 `vcls`，整块图内文字不进入翻译；版面重排只移动/替换文字，不删除原矢量下划线。
- 做法：`src/figure_overlay.py` 用 OpenDataLoader 找图题上方的色块/单元格，按包含关系聚合标签；Bing 翻译；`add_redact_annot(fill=False)` + `graphics=NONE` 只擦字，按原色/原字号/原框回写；SourceHanSans 动态子集；双语按页序只改译文页。`src/pdf_cleanup.py` 只清“源文本相交 + 译文无邻近文字”的细黑横线，跳过表格页、彩色链接下划线和脚注线。
- 踩坑：不能把所有细横线都当孤立线；第 2/4 页有彩色超链接下划线，表格页脚注线也应保留。判断条件必须同时看源文本与译文邻近文字；字体宽度要用实际 `fitz.Font.text_length` 而不是 1em 估算，否则 `insert_htmlbox` 会把“协议/协”再折一次。
- 验证：DOE p5 清 2 条（p2/p4 彩色线、p13–15 表注线均保留）；p9 Figure 1 的 16 组标签全部回贴，色块/边框/列宽不变；275/275 单测全绿（21.4s）；单语 28 页、双语 56 页，p11 表格 482 汉字、p13 584 汉字。
- 边界：扫描件位图内的表格/图内文字仍需 OCR 覆字；旋转页跳过。

## 2026-10-30 · 表格原位回贴：OpenDataLoader bbox + 红字擦除 + 字体子集（P052-LiteParse-PDF自动识别）

- 目标：矢量 PDF 表格要翻译，且必须落在原格子、保持原网格/列宽/底纹，不能像段落重排。
- 原生核查：pdf2zh 稳定后端 `vcls` 含 `table`，表格不译；BabelDOC 0.2.33 有实验性 `--translate-table-text`（RapidOCR），本机 numpy 2.5 下 OCR 子进程报错、表格仍英文，不可用。用户记得的“实测”更可能是 Markdown/HTML 表格翻译（`translate_table` / ASME HTML 重建），不是 PDF 原位表格。
- 做法：`src/table_overlay.py` 用 OpenDataLoader 的 cell bbox/rowspan/colspan；Bing 逐格翻译；`add_redact_annot(fill=False)` + `apply_redactions(graphics=NONE)` 只擦字不擦线；按原字号用 SourceHanSerif 回写；表注按“页底 + 小字号 + 数字开头”一并译。双语的译文页按 `2*i+offset` 回贴，原文页不动。
- 踩坑：PyMuPDF `doc.subset_fonts()` 在该 pdf2zh 双语 PDF 上直接 segfault（`pdf_subset_fonts2`）。改为 fontTools 按实际用字动态子集（约 80 KB/字重），不调用 `subset_fonts()`；文件 0.8/1.0 MB，字形与间距正常。
- 验证：DOE 28 页、6 个表格、123 个单元格全部回贴；p11 0→473 汉字，双语 p22 同步、p21 保持英文；单测 264/264（18.5s）。截图 `work/ui_review/table-before-after-p11.png`。
- 边界：扫描件“图片化表格”仍只译题注；旋转页暂跳过；表格文本若被 OpenDataLoader 截断（跨页单元格），回贴也忠实于截断源。

## 2026-10-30 · 表格未译定因：pdf2zh 把 table 列入 vcls 直接跳过（P052-LiteParse-PDF自动识别）

- 现象：矢量文献正文已译，但 Table 1 整页/整表仍是英文，容易被误判为引擎没工作。
- 核查：`pdf2zh 1.9.11` 同一条命令，第 10 页 3.2s 产出 587 汉字；第 11 页（Table 1）3.1s、0 汉字、48,050 拉丁字符。扫描流 `hd_scan_renderer` 第 1 页 2.8s、561 汉字，OpenDataLoader 0.42s、Chrome 正常。
- 根因：pdf2zh `high_level.py` 的 `vcls = ["abandon","figure","table","isolate_formula","formula_caption"]`，表格框被掩蔽，不进入擦除/翻译；扫描流仅结构化表逐格译，图片化表只译题注。
- 结论：不要直接改 `vcls`（表格会按段落重排、丢网格）。正解是独立“表格回贴层”：OpenDataLoader 取 cell+bbox → 逐格翻译 → fitz 擦原字 → 按格宽降字号回写。
- 适用：PDF 表格翻译、pdf2zh 二次开发、双引擎排障。

## 2026-10-30 · 渐变怎么加才不显乱：只给“光”和“细线”上色（P052-LiteParse-PDF自动识别）

- 结论：大面只用 3–5% 透明度、大半径的蓝/紫柔光，再叠同色相窄渐变（主按钮 #0A84FF→#0066CC、进度条蓝→靛）；渐变只出现在图标、主按钮、进度条、发丝线、卡片悬浮反射，文字保持纯黑。
- 踩坑：中文 26pt 标题整段渐变会显“落地页廉价感”，已回退纯色；按钮 hover 不要整体换渐变（会跳），改叠 10% 白色蒙层；大光斑饱和度超过 6% 就开始“花”。
- 适用：Apple 风浅色界面的“高级感渐变”。

## 2026-10-30 · 从“高饱和炫技”转向 Apple 审美的可复用配方（P052-LiteParse-PDF自动识别）

- 做法：① 画布 #F5F5F7 + 纯白卡片 + `black 7.5%` 发丝线 + 极轻阴影；② 全站只留一个品牌蓝 #0071E3，彩色只给状态；③ `hiddenTitleBar` 下内容 `ignoresSafeArea(.top)`、左侧留 78pt，品牌与红绿灯同排；④ 无任务用居中 Hero（26pt 标题 + 双胶囊 CTA），有任务切轻量投递条 + 列表；⑤ 内容列统一 940pt 居中，分区标题与卡片同宽；⑥ 胶囊按钮：实心蓝主操作、白底描边次操作；⑦ App 图标重绘为蓝底白文档。
- 踩坑：`.regularMaterial` 跟随系统深色会变黑，与写死浅色画布冲突，要么做完整动态色板、要么 `NSRequiresAquaSystemAppearance=true` 锁定浅色；排队任务给 0% 进度条会被误读为“卡住”；`matchedGeometry` 滑块动画会让滚动条抽动，列表动画必须只跟 id 集合。
- 适用：SwiftUI 桌面工具做“Apple 产品页”观感时的取舍。

## 2026-10-30 · SwiftUI 桌面端收尾：窄窗自适应、整窗拖拽与状态真实化（P052-LiteParse-PDF自动识别）

- 场景：桌面端 UI 重构后的可用性收口。
- 做法：
  1. **窄窗自适应**：用 `onGeometryChange` 量顶栏宽度，<1080px 切紧凑态（图标胶囊 + 短状态 + “成果目录”），并把可缩放文字 `.lineLimit(1).fixedSize()`；否则 900px 最小窗口下分段控件会竖排换行。
  2. **整窗投递**：根视图挂 `.dropDestination` + 全窗高亮遮罩（`allowsHitTesting(false)`），内层投放区保留自己的高亮，拖到卡片/标题/空白都能收。
  3. **状态不能写死**：胶囊文案改为 `BackendConnectionStatus.shortLabel`，否则后端未启动也显示“就绪”。
  4. **`accessibilityReduceMotion`**：脉冲、呼吸、漂浮全部降级为静态；图标按钮补 `.help` 与 `.accessibilityLabel`；`textMuted` 加深到 ≥4.5:1。
- 踩坑：`LinearGradient` 不能直接 `.opacity()`；`onGeometryChange(for:of:action:)` 要在 macOS 15+ 才可用（本项目基准 macOS 26）。
- 适用场景：SwiftUI 桌面应用的响应式顶栏与拖放体验。

## 2026-10-30 · 每秒轮询 + ScrollView 级 spring 动画 = 右侧滚动条反复抽动（P052-LiteParse-PDF自动识别）

- 现象：重构后用户看到右侧滚动条持续反复滑动/抽动。
- 根因：两层叠加——① `refreshTasks()` 每秒把解码结果无条件赋给 `@Published tasks`，即使内容完全相同也触发整棵列表重渲染；② 把 `.animation(.spring, value: manager.tasks)` 挂在了 `ScrollView` 上，容器尺寸每次重算都被弹簧动画带动，滚动条滑块因此反复滑动。
- 做法：① 发布前做等值判断 `if fetchedTasks != self.tasks`；② 动画下沉到列表容器，并把 key 换成稳定的 `tasks.map(\.id)`；③ `LazyVStack` 改非惰性 `VStack`（任务上限 200），消除轮询时的可见区重算。
- 验证：滚动后连续抓 4 帧（1s 间隔），对窗口最右 40px 滚动条区域做像素差，**变更像素 = 0**；全帧差异仅来自预期的脉冲动画。
- 踩坑：SwiftUI 里“动画打在滚动容器上”比“不动画”更糟——它会把滚动偏移、指示器尺寸一并纳入动画事务。
- 适用场景：SwiftUI 列表 + 定时轮询的数据面板。

## 2026-10-30 · SwiftUI 浅色工作台“更饱和 + 更丝滑”的四个抓手（P052-LiteParse-PDF自动识别）

- 场景：用户要求把原本偏灰的浅色界面做得更饱和、动效更跟手。
- 结论与做法：
  1. **饱和度不等于加深**：画布用蓝/紫/青三色低透明度大半径光斑叠渐变底，卡片保持纯白，发丝线从黑 6% 改为“品牌蓝 10%”，整体就“有颜色”但不脏。
  2. **丝滑的关键是 matchedGeometryEffect**：分段控件的白色滑块用 `matchedGeometryEffect` + `spring(response:0.34,dampingFraction:0.76)`，比淡入淡出高级一个量级。
  3. **悬浮必须“抬升 + 描边 + 阴影”三件套**：只改背景色看不出层次；渐变描边用 `strokeBorder(AnyShapeStyle(brandGradient))`，阴影同时变大变蓝。
  4. **状态要动但要克制**：进度条用 spring 追进度 + 发光，状态图标用扩散光环（1.6s repeatForever），不要旋转整个图标，否则抢戏。
- 踩坑点：① SF Symbol `textformat` 在中文环境会被本地化成“格式”字样，分段控件要用不随语言变化的符号（本例改 `text.alignleft`）；② `LinearGradient` 没有 `.opacity()`，需要透明度包一层或转 `AnyShapeStyle`，否则编译不过；③ macOS 14+ 的 `onChange(of:perform:)` 已弃用，改双参闭包可消警告。
- 适用场景：SwiftUI 浅色生产力应用的渐进式视觉升级。

## 2026-10-30 · 矢量管线验收：pdf2zh 不翻译表格，页码孤字符会被误译（P052-LiteParse-PDF自动识别）

- 场景：`DOE-STD-1271-2025.pdf`（28 页，矢量，含跨 4 页的大表）端到端验收。
- 结果：59 秒交付 mono 28 页 / dual 56 页、10,718 汉字；manifest/归档/原子发布均正常。
- 发现的问题：① **pdf2zh 矢量流对表格只保留原文不翻译**——Table 1 整页（p11–12 及 p13–14 表内文字）保持英文，正文已译；② 罗马页码 `i` 被译成“我”，属孤字符误译。
- 结论与做法：验收不能只看“产物存在 + 总字数”，要**逐页统计汉字/英文词比**，否则整页未译会被平均掉；表格密集型文档若要求全文中文，应走 OpenDataLoader + 表格翻译的 HD 管线，或增加“表格页回填”后处理。
- 适用场景：所有基于 pdf2zh 的矢量 PDF 翻译验收。

## 2026-10-30 · 本地 Web 工作台安全加固 + 双轨状态机重构：四个可复用模式（P052-LiteParse-PDF自动识别）

- 场景：按评审结论一次性修完 P0-2..5、全部 P1 与 P2 漂移，260/260 单测通过，并做了真实页面冲烟。
- 结论与做法：
  1. **本地 HTTP 服务的同源防护三件套**：`Host` 白名单（只认监听的 loopback 地址与端口）+ 写操作 `Origin` 校验 + CSP `script-src 'nonce-…'`。做法要点：把页面里所有内联 `onclick/onchange` 改成 `addEventListener`，否则 nonce CSP 会把按钮全部杀死；每次渲染生成新 nonce 并同步写进响应头。
  2. **投递即认领消除双写者竞争**：web 工作台上传后直接原子落到 `processing/<stem>.pdf`（占位 + `.tmp` 替换），而不是先写 `inbox/` 再等 watcher 来抢；watcher 只在启动时扫一次 `processing/`，天然互斥。配合“产物名纳入发号”，同名不同文档自动 `-2`。
  3. **用 manifest 替代“产物存在即完成”**：交付全部写入 `outbox/.<stem>.manifest.json`（源文件 sha256 + 产物清单），下次启动按哈希比对；无 manifest 的残留 mono/dual 视为半交付并清理。这同时解决了“同名不同文档被静默跳过”与“mono 先落盘、dual 缺失却判成功”。
  4. **路径沙箱只用 `Path.relative_to`**，不用字符串前缀；下载只开放 `outbox`，并补 `X-Content-Type-Options: nosniff` 与 RFC5987 文件名。
- 踩坑点：① CSP 加 nonce 前必须先清掉所有内联事件属性，否则功能静默失效（页面看着正常、按钮全不动）；② 测试断言“文件在 inbox”会把“投递即认领”误判为回归，需改为等待终态后校验归档字节；③ `with_suffix(".pdf.tmp")` 生成的是同名非隐藏文件，崩溃后清理逻辑接不住，临时名必须显式加前导点。
- 适用场景：任何“本地 HTTP 工作台 + 文件投递目录 + 多产物交付”的离线工具。

## 2026-10-30 · 一个动作两条执行路径：桌面端点一次按钮弹两个 Finder 窗口（P052-LiteParse-PDF自动识别）

- 场景：Swift 桌面端的「打开产物目录」按钮，点一次弹出两个 Finder 窗口。
- 根因：`BackendManager.revealOutbox()` 先 POST `/api/reveal_outbox`（后端 `subprocess.run(["open", dir])`），紧接着又用 `NSWorkspace.shared.open()` 本地开一次——同一意图写了两条执行路径，两条都生效。
- 做法：两条路径只保留一条。改为共用私有 `revealDirectory(at:)`：先 `createDirectory(withIntermediateDirectories: true)`、再 `fileExists` 门禁、最后只调一次 `NSWorkspace.open`；服务端 `/api/reveal_*` 端点保留给 Web UI，不再从桌面端调用。重编译后用 `strings | grep -c 'api/reveal'` = 0 验证 HTTP 调用确实已从二进制移除。
- 踩坑点：**“接口 + 本地回退”写成并联而不是串联**，是双开类 bug 的高发模式；要么只留一条，要么做幂等去重。验证时优先检查产物内部特征（符号/字符串/请求次数），比看 UI 可靠。
- 适用场景：任何同时具备本地能力与后端 API 的 macOS/Electron 桌面工具。

## 2026-10-30 · 单元测试真跑 `open`：每跑一次单测就弹 2 个 Finder 窗口（P052-LiteParse-PDF自动识别）

- 场景：用户反馈「每次你操作的时候都会自动给我拉起来几个文件夹」，截图显示 Finder 停在 `$TMPDIR`，满屏 `TemporaryDirectory.*`。
- 根因：`tests/test_web_app.py::test_reveal_endpoints` 用真实 HTTP 请求打了 `/api/reveal_outbox` 与 `/api/reveal_inbox`，端点内是 `subprocess.run(["open", dir])`；测试的 `project_root` 恰好是 `tempfile.TemporaryDirectory`，于是每次跑测弹 2 个窗口，测试结束目录被删后 Finder 落到 `$TMPDIR` 形成残留列表。
- 做法：① 把副作用收进模块级 `reveal_in_finder(path)`，先 `is_dir()` 门禁、`OSError` 容错，不存在就返回 False；② 端点改成调用它并回传 `revealed`；③ 测试 `patch("src.web_app.reveal_in_finder")` 并断言入参，新增「目录不存在时不得调用 open」回归；④ 全量 249/249 通过。
- 踩坑点：**测试要验证「点击后打开目录」这类行为，验证的是“是否以正确参数调了打开器”，不是“真的把 Finder 拉起来”**。副作用函数必须可注入；另外任何 `open`/`osascript`/`NSWorkspace` 都要加存在性门禁，否则删目录后 Finder 会回退到父目录，看起来像“残留垃圾堆”。
- 适用场景：所有带「在 Finder 中显示 / 打开文件」功能的桌面工具与其测试套件。

## 2026-10-30 · 本地 Web 工作台与双轨状态机的只读评审：五类可复用缺陷模式（P052-LiteParse-PDF自动识别）

- 场景：对 10.6k 行 `src/` + 3.1k 行 Swift 的全量只读评审，跑通 248/248 单测并实测加密 PDF 路径。
- 结论与做法（五类可复用缺陷模式）：
  1. **「仅监听 127.0.0.1」不等于安全**：`web_app` 无 Host / Origin 校验。任意网页可用 multipart POST 免预检地把文件写进 `inbox/`；DNS rebinding 后还能读到 `/api/tasks`、`/api/download`。做法：校验 Host 白名单 + 写操作校验同源 Origin，长跑服务再加启动 token。
  2. **前端 `innerHTML` 拼接服务端字符串 = 存储型 XSS**：PDF 文件名在 APFS 上可以含 `<` `>` 引号，原样拼进 `innerHTML` 就能执行；同理异常文本 `t.error`。做法：先 `escapeHTML()` 或改用 `textContent`，并补 CSP。
  3. **字符串前缀做路径沙箱是经典漏洞**：`str(p).startswith(str(root))` 会放过 `root-suffix/xxx`。做法：`Path.is_relative_to()`，并把可读目录收窄到 `outbox`。
  4. **「产物存在即视为已完成」的状态判断不可靠**：同名不同文档会被静默跳过（只归档 + 一条 warning）；多产物管线（mono 先落盘、dual 后落盘）中途失败或被杀进程后，残留的 mono 会让下一轮直接判成功。做法：交付完成后写 manifest（源文件 sha256 + 产物清单），以 manifest 而非文件名判完成。
  5. **配置校验写成死代码**：`bool(raw.get(k, False))` 后再 `isinstance(v, bool)`，转换在前导致校验恒真，字符串 `"false"` 会变成 `True`（此处会静默开启离线翻译重活）。做法：先取原值判类型，再赋值。
- 附加发现（记录备查）：默认 `dual_track_mode=auto` + `pdf2zh_service=bing` 会把正文文本发往第三方翻译，与 AGENTS.md「保持本地离线处理、不上传 PDF 内容」直接冲突——**合规红线必须落在默认配置层，不能只写在文档里**；README 宣称的 `log_max_bytes`/`log_backup_count` 无任何代码读取（硬编码 1MB×3）；归档用 `unlink()` 覆盖同名历史文件而 watcher 用 `unique_path`，同一项目两套归档语义。
- 踩坑点：单测全绿（248/248）与安全/状态机正确性无关——本次 5 项 P0 全部在测试盲区（无 Origin、无转义、无路径穿越、无同名冲突、无半交付断言）。
- 适用场景：任何「本地 HTTP 工作台 + 文件投递目录 + 多产物交付」的桌面工具。

## 2026-10-26 · 浅色极简桌面应用六处视觉精修与三级圆角统一（P052-LiteParse-PDF自动识别）

- 场景：用户确认 Raycast/Linear 浅色骨架方向后，需要进一步精修视觉层提升质感。
- 结论与做法：
  ① **品牌区呼吸感**：去掉副标题、版本号降灰、Logo 换文档图标，品牌区从"信息罗列"变为"一眼识别"。
  ② **投递区瘦身**：高度从 80pt 压至 60pt，去掉技术标签（"支持多层级目录递归"），增加蓝色呼吸动画（opacity 脉冲）暗示拖拽目标。
  ③ **任务卡片温度感**：状态图标从方形圆角矩形改为圆形；进度条从 RoundedRectangle 改为 Capsule 端头圆弧；交付按钮从实心蓝底改为 ghost 风格（透明底+蓝色文字），降低视觉噪音。
  ④ **空状态三叠文档插画**：用三个轻微旋转的 RoundedRectangle 模拟"一叠论文"，外框用虚线 dashed stroke 暗示拖拽目标。
  ⑤ **全局三级圆角统一**：`radiusCard=10 / radiusButton=8 / radiusBadge=6`，消除此前 12/7/6 三种不一致圆角。
- 踩坑点：
  1. **SwiftUI `StrokeStyle(dash:)` 必须与 `.stroke()` 搭配使用**，不能传给 `.overlay()` 的 `content` 参数。
  2. **品牌区不要堆副标题**：当 footer 已有隐私声明时，header 再加副标题会造成信息冗余，去掉反而更高级。
  3. **Ghost 按钮的关键是 opacity 层级**：背景 opacity 0.06 + 文字不透明 = 视觉存在感刚好够用，不争抢视线。
- 适用场景：Mac 原生浅色风生产力应用的渐进式精修。

## 2026-10-25 · 基于 Raycast/Linear 骨架与现代浅色风（Light Mode）重构原生学术重构桌面应用（P052-LiteParse-PDF自动识别）

- 场景：用户反馈此前的深色瑞士排版界面仍不满意，明确指示选择【骨架 A（Raycast / Linear 灵动极简工作台）+ 浅色风（Light Mode）】。
- 结论与做法：
  ① **彻底砍掉沉重侧栏，确立 Raycast / Linear 单窗体灵动架构**：
     - 摒弃写满技术参数的侧边栏，将全部视觉重心归还给文献本身；
     - 顶部采用 Raycast 风格的极简浮动分段选择器（`⚡️ 智能双轨`、`💎 扫描出版`、`📐 现代矢量`、`🌐 原位双层`），纯白浮动胶囊平滑滑动；
  ② **瓷面纯白高雅质感（Porcelain Light Mode）**：
     - 背景采用柔和的浅冷灰底色（`#f6f8fb`），主体卡片采用纯白（`#ffffff`）搭配 0.5px 发丝级细边框（`rgba(0,0,0,0.06)`）与 4px 柔和环境漫反射阴影；
     - 文字摒弃生硬纯黑，采用石墨青灰（`#171f2c`）作为主标题，次级信息使用板岩灰（`#66758a`），色彩温润高级；
  ③ **轻盈灵动投递区（Light Drop Zone）**：
     - 纯白浮动卡片配备柔和蓝色折射光晕（`#256be6`），鼠标拖拽悬停时自适应微缩并亮起电光蓝轮廓，操作提示简洁干练；
  ④ **平铺式纯白任务卡片与一键直达交付物**：
     - 单篇文献卡片清晰展示文件名、大小、耗时与分流徽标（`[ 现代矢量学术 ]` 柔和绿 / `[ 扫描专著高清 ]` 柔和琥珀金）；
     - 任务完成后平铺展开交付物列表（`[PDF] 中文精译版.pdf`、`[PDF] 双语对照版.pdf`），右侧配以醒目的电光蓝 `👁 打开` 与白底细边 `📂 定位` 按钮；
  ⑤ **极小体积交付与全量回归**：
     - 保持 100% 原生 Swift 编译，零第三方膨胀，打包后的 `LiteParse Studio.app` 仅 **1.1 MB**；
     - 全量 248/248 单元测试与端到端测试全绿通过（21.02s）。
- 踩坑点：
  1. **浅色风的质感核心在“漫反射阴影”与“灰阶阶梯”**：不要使用生硬的深色边框或纯黑文字，背景使用比纯白微暗一点的 `#f6f8fb`，卡片用纯白与 0.5px 发丝线抬升层级，才能达到顶级 Mac 原生应用的轻盈感。
- 适用场景：现代桌面端学术工具、高颜值生产力软件、轻量化极简工作台。

## 2026-10-25 · macOS GUI 环境变量缺失诱发 OpenDataLoader Java 桩命令报错排查与自动注入修复（P052-LiteParse-PDF自动识别）

- 场景：用户截图反馈桌面工作台中处理扫描文献时抛出红色报错：`Command '['java', '-Djava.awt.headless=true', ... 'opendataloader-pdf-cli.jar' ...] returned non-zero exit status 1`。
- 结论与做法：
  ① **定位根因：macOS GUI 环境隔离与系统空 Java 桩误判**：
     - 当从访达直接启动 macOS GUI 桌面应用时，系统不加载用户的终端配置（`.zshrc` / `.zprofile`），`PATH` 仅包含系统精简路径 `/usr/bin:/bin:/usr/sbin`；
     - 此时 `shutil.which("java")` 命中了系统自带的 `/usr/bin/java`，但该文件并非真实 JRE，而是一个空占位桩（Stub），执行时报错 `Unable to locate a Java Runtime` 并退出状态码 1；
     - 旧逻辑中存在匹配漏洞：`if ... or "runtime" in res.stderr.lower()` 误将错误信息中的 "Runtime" 判定为正常 Java 运行时，导致过早返回系统空桩，未去激活 Homebrew 安装的真实 OpenJDK；
  ② **严格 Java 验证门禁与多级候选自动注入 (`src/opendataloader_extractor.py`)**：
     - 将探测条件收紧为硬门禁：必须 `res.returncode == 0` 且明确排除 `"unable to locate a java runtime"`；
     - 建立系统级自动搜索序列（优先探测 `/opt/homebrew/opt/openjdk/bin/java` 与 `~/.local/bin/java`），一旦命中，自动将其目录强行注入当前 Python 进程及后续所有子进程的 `os.environ["PATH"]` 最前端，并同步配置 `JAVA_HOME`；
  ③ **Swift 桌面端环境主动穿透 (`BackendManager.swift`)**：
     - 在原生桌面端启动后端 Python 进程时，显式将 Homebrew 与局部环境路径（`/Users/joe/.local/bin:/opt/homebrew/bin:/opt/homebrew/opt/openjdk/bin`）注入 `proc.environment`，确保纯 GUI 点击启动下具备 100% 完备的运行时；
  ④ **端到端实证闭环**：
     - 重新测试扫描件切片样本，OpenDataLoader 毫秒级命中 OpenJDK 27，6 秒内完整交付 `中文精译版.pdf`、`双语对照版.pdf` 与 `原位双层版.html`；
     - 全量 248/248 单元测试全绿通过（20.88s）。
- 踩坑点：
  1. **macOS `/usr/bin/java` 是极其隐蔽的空占位桩**：切勿使用宽泛的字符串包含（如 `"runtime"` 或 `"java"`）来判断 Java 是否可用，因为系统提示 `Unable to locate a Java Runtime` 恰好包含这些词；必须且只能以 `returncode == 0` 作为唯一可用凭据。
  2. **macOS 桌面 GUI 进程不继承终端 shell 环境变量**：依赖外部 CLI 工具（如 `java`、`gs`、`tesseract` 等）的 Python 后台若由 GUI App 启动，必须在应用层或模块入口处主动补齐 PATH。
- 适用场景：macOS 原生应用拉起后端服务、Java/Python 跨语言工具链打包部署。

## 2026-10-25 · 基于 Oil UI 瑞士排版规范重构 macOS 原生学术重构桌面应用（P052-LiteParse-PDF自动识别）

- 场景：用户反馈初版界面过于厚重粗糙（“太丑了”）。排查诊断定位出根因在于陷入了“套娃式灰色大卡片堆叠”的模板病：巨型灰色投递区独占 60% 屏幕挤压了核心流水线，多层深灰卡片削弱了光感，圆角粗药丸导致视觉层级生硬扁平。根据 Oil UI 规范，用户选定【方向二：精密学术出版 · 典雅瑞士排版（Swiss Precision Publishing）】进行系统性重构。
- 结论与做法：
  ① **破除套娃卡片，确立 270pt 黄金分割不对称两栏架构**：
     - 左侧建立贯通上下的精细磨砂控制栏（集成管线选择、翻译引擎、术语库校对与安全指标），右侧为主工作台，结构稳定严谨；
  ② **极简精密投递光轨（Swiss Drop Rail）替代巨型占位框**：
     - 将原先沉重庞大的灰色占位卡收敛为 76pt 高度的高精度技术投递带（带细微技术虚线、支持无限制目录递归与单文件拖拽），释放 85% 视野给任务流水线；
  ③ **平铺式精密学术任务行（Swiss Task Row）**：
     - 采用瑞士排版直角微圆角（6px）、0.5px 发丝级细分割线与等宽数字（`.monospacedDigit()`），清晰展示任务进度、分流徽标（`[ 现代矢量学术 ]` / `[ 扫描出版高清 ]`）与交付产物（中文精译版、双语对照版、原位双层版），带一键“打开”与“定位”；
  ④ **进程管道缓冲死锁防范 (`BackendManager.swift`)**：
     - Swift `Process` 启动后台服务时，标准输出与错误流重定向至 `FileHandle.nullDevice`，彻底消除 64KB OS buffer 写满挂起隐患；
  ⑤ **极小体积交付与全量回归**：
     - Swift 原生二进制直接链接系统框架，打包生成的 `LiteParse Studio.app` 仅 **1.1 MB**，零 Electron/Chromium 冗余，双击立即可用；
     - 全量 248/248 单元测试与端到端测试全绿通过（20.72s）。
- 踩坑点：
  1. **SwiftUI `background(_:in:)` 必须传入实现 `ShapeStyle` 的类型**：若传入 `Group { if ... }` 会报编译错误；应在结构体内通过私有计算属性派生具体 `Color`。
  2. **Swift `Process` 重定向若不读取不可直接赋值空的 `Pipe()`**：不消费管道将导致子进程在写入 64KB 后写死锁挂起，重定向至 `FileHandle.nullDevice` 可彻底解决。
- 适用场景：原生学术桌面软件重构、高保真文献与图表翻译工作台、极小体积独立应用交付。

## 2026-10-25 · 扫描件高清出版级重构加固：页眉污染隔离、无结构表格图表化提取与核化工术语译后纠错（P052-LiteParse-PDF自动识别）

- 场景：在对纯图片/扫描件高清出版级重构进行严格对抗审查与像素级实测走查时，发现 5 处严重影响视觉与专业性的缺陷：①原图裁剪将原书页眉（`302 CHEMICAL PROCESSING [CHAP. 6`）错误截入插图顶部；②扫描表格因无矢量线被判定为 `is_table=False` 导致表头与数据退化为纵向破碎单行文本（如 Table 6-2 碎词堆叠）；③术语表仅在英文阶段替换，未能纠正机器翻译后的中文字词，导致出现 "毛毯材料"（bed blanket）与 "毒化效果" 等严重不符核化工常识的错译；④Chrome 打印样式遗留网页卡片式灰边框与阴影；⑤router 遗留旧式 HTML 回退后门、watcher 缺少对 HD PDF 交付产物的感知与临时文件清理、web_app 策略选项不一致。
- 结论与做法：
  ① **页眉警戒线与图区动态边界隔离 (`detect_figures_on_page`)**：
     - 设置 `header_guard = max(52.0, ph * 0.088)` 与底部 `ph * 0.92`，根除图书顶部 Running Header 与页码被错误裁剪进插图的问题；结合 PIL 差分算法收缩空白，截取区域纯净无污染；
  ② **无矢量线扫描表格自动识别与高清晰度整体图表化 (`detect_unstructured_tables_on_page`)**：
     - 识别 `TABLE \d+` 表题，自动提取连续标题行，向下探测数据区域并以 180 DPI 整体高保真裁剪；表题上方翻译，表格内部保持 100% 原始公式与数据精度，并跳过内部碎片块的段落输出；
  ③ **两阶段术语保护与核化工领域译后纠错 (`ScannedPDFTranslator`)**：
     - 增加译前章节标题正则快车道（`6-l . INTRODUCTION` -> `6-1. 引言`）；
     - 增加译后中文模式映射校正（`毛毯材料|毯区材料` -> `再生区材料`、`毒化效果` -> `中毒效应`、`两区反应堆` -> `双区反应堆`、`两区热增殖` -> `双区热中子增殖`、`两区钚生产者` -> `双区钚反应堆` 等），实现出版级专业领域表达；
  ④ **去卡片化与学术出版级排版对齐 (`generate_publication_html`)**：
     - 移除网页卡片式灰边框（`border: 1px solid #eaeaea`）与阴影（`box-shadow`），对齐 `pdf2zh` 纯白纸面无损矢量排版；中文精译版剥离英文全大写章节条，仅保留中文规范章名；
  ⑤ **全链路调度闭环 (`router.py`, `watcher.py`, `web_app.py`)**：
     - 清理 router 遗留的旧式 HTML 回退后门，Track B 默认完整交付中文精译版 PDF、双语对照版 PDF 与原位双层 HTML 三件套；
     - watcher 增加对高清 PDF 交付产物的感知与临时文件清理，web_app 明确区分出版级高清重构与历史双层 HTML；
     - 新增及优化单测，全量 248/248 单元测试全绿通过（18.27s）。
- 踩坑点：
  1. **扫描件图区绝对不能只靠文字块间距计算，必须有固定页眉/页脚几何门禁**：历史扫描图书顶部普遍有居中或靠外的章节名与页码，若上一文本块落在正文下方而直接取 `y=32`，必然将页眉整行截入插图顶部。
  2. **机器翻译术语库必须包含译后中文纠偏（Post-translation correction）**：通用翻译引擎（如 Bing）对未登录或上下文敏感词（如 nuclear blanket -> 毛毯）在英翻中时直接套用日常语义；在译文端进行确定性领域正则校正是确保专业出版级质量最有效的防线。
- 适用场景：历史扫描科技专著与古籍数字化翻译出版、复杂无矢量线表格高保真重构、高精度学术双语对照 PDF 生成。

## 2026-10-25 · 纯图片/扫描件出版级高清 PDF 渲染管线与原图隔离嵌入交付（P052-LiteParse-PDF自动识别）

- 场景：用户反馈纯图片/扫描件 PDF 仅输出原位双层 HTML 界面感较粗糙（"有点 low"），且翻译质量不及 pdf2zh，更缺少 pdf2zh 将原图嵌入译文并以高清矢量字体排版的出版级质感；要求将纯图片/扫描件识别后的输出全面升级为与 pdf2zh 一模一样的高清 PDF（交付单语精译版与双语对照版 PDF，隔离裁剪原图内嵌排版，支持 Bing / CTranslate2 双引擎与领域术语保护）。
- 结论与做法：
  ① **扫描版面原图智能锚定与高分辨率隔离裁剪 (`src/hd_scan_renderer.py`)**：
     - 构建基于图题锚点（`FIG. \d+`、`Figure \d+`）与非文字绘图边界的自动图区探测算法；
     - 调用 PyMuPDF (`fitz`) 以 180~200 DPI 超高采样率对原扫描图表进行无损像素抽取，结合 PIL `ImageChops` 差分算法自动裁切扫描边缘底色与噪点边框，生成高清晰度内嵌 Data URI 并与图题严格关联；
  ② **对齐 pdf2zh 出版级排版与单页/双页几何映射**：
     - 引入 Google Noto Serif CJK / Source Han Serif / Songti 学术排版标尺，设置 8.8pt 规范五号字、1.48 标准行距与 2em 首行缩进；
     - 采用学术经典三线表（Top/Bottom 1.5pt solid）与居中图题规范；
     - 提取原版图书物理几何尺寸（如 419pt x 594pt），设置 `@page { size: Wpt Hpt; margin: 20pt 24pt; }`，解决 HTML 打印因 min-height 虚高诱发的次页空白跳页问题，实现每页译文与母版扫描件 1:1 物理对齐；
  ③ **无头 Chrome 出版级矢量 PDF 打印与双语交替对照合成**：
     - 调用系统 Google Chrome (`--headless --disable-gpu --no-pdf-header-footer --print-to-pdf`)，将语义化 HTML 瞬间渲染为包含真实矢量字体与嵌入高清位图图表的出版级单语 PDF（`[stem]-中文精译版.pdf`）；
     - 构建 `create_dual_interleaved_pdf`，通过 PyMuPDF 将原始扫描页与高清翻译页按 1:1 奇偶交替合成双语对照 PDF（`[stem]-双语对照版.pdf`），读者在 PDF 阅读器开启双页翻页模式时左侧为原始扫描件、右侧为高清翻译件；
  ④ **双引擎神经翻译与核化工领域术语库保护**：
     - 接入 pdf2zh 环境内置的 BingTranslator（带会话 SID 缓存、智能分块防截断与 CJK 无缝拼接），并无缝支持离线 CTranslate2 INT8 模型作为离线备选回退；
     - 引入核工程与化工领域专用术语库保护（如 homogeneous reactor -> 均质反应堆、slurry -> 浆液、chemical processing -> 化学处理、poison effect -> 中毒效应）；
  ⑤ **路由器与 Web 桌面应用全链路贯通**：
     - 升级 `src/router.py`，使扫描件管线自动交付 `[stem]-中文精译版.pdf`、`[stem]-双语对照版.pdf` 与 `[stem].原位双层版.html`（三件套齐全）；
     - `src/web_app.py` 选项及徽标同步升级，新增 10 组回归单测，全量 244/244 单元测试全绿通过（18.56s），`FFR_chap06.pdf` 前 5 页端到端输出验证完全吻合出版级水准。
- 踩坑点：
  1. **HTML 打印中的 `@page` 与 `min-height` 冲突诱发虚假空白页**：在为自定义尺寸（419pt x 594pt）的页面生成 PDF 时，若在外层容器设置了接近整页高度的 `min-height`（如 542pt），哪怕内容仅有 100pt，只要加上内边距和 Chrome 内部浮点舍入差，就会被浏览器判定为高度溢出而插入分页符，进而与 CSS `page-break-after: always` 叠加产生一页有一页无的“隔页空白”；在排版分页容器中切忌使用硬编码 `min-height`，只需依靠自然内容流与 `.paper-page:not(:last-child) { page-break-after: always; }` 即可实现绝对精准的 1:1 分页。
  2. **扫描件图表必须独立高采样率裁剪与边框净化**：直接在 HTML 背景显示扫描底图会导致页面混杂油墨黑噪点且无法导出真实矢量 PDF；通过锚点探测独立裁剪图表并使用 PIL 滤除四周泛黄边框，既能使插图以 200 DPI 跃然纸上，又能使正文以 100% 矢量字体呈现，达到与数字原生论文完全一致的出版级品质。
- 适用场景：历史扫描文献数字化、科技期刊与学术专著高清翻译出版、原图自动提取与双语对照排版。

## 2026-10-25 · OpenDataLoader-PDF 审查加固与实证容错（PDFBox Type1 字体丢字修复、表格 Span 还原与全链路配置贯通）（P052-LiteParse-PDF自动识别）

- 场景：在对引入 `opendataloader-pdf` (2.5.15) 后的上游抽取与原位排版管线进行非橡皮图章的严格对抗审查与实测时，发现了 5 处严重甚至致命的隐性缺陷：在旧文献（如 `FFR_chap06.pdf`）中 Java PDFBox 底层字库映射缺陷致字母 'i' 被替换为空格断词诱发下游大面积神经翻译幻觉、表格跨行跨列 (rowspan/colspan) 在原位 HTML 中被硬编码剥离、表格单元格首尾空格导致翻译字典查表失效、表格空字段引发 `TypeError`、空图片列表导致整篇页面被 `zip` 静默丢弃，以及守护进程与 Web 应用未能透传用户配置的 upstream_extractor。
- 结论与做法：
  ① **Java PDFBox 历史 Type1 字体编码缺陷与 PyMuPDF 双向坐标校验还原 (`src/opendataloader_extractor.py`)**：
     - PDFBox 在解析部分老旧 PostScript/Type1 字体（如 `OPSUFont0`）时，未映射 glyphs 被粗暴降级为空格（如 `principal` 变 `pr nc pal`，`fluid` 变 `flu d`，`is the possibility` 变 ` s the poss b l ty`），导致下游 MarianMT 神经翻译模型发生灾难性错乱（如 `flu d` 被错译为“流感 d”，`po sons` 错译为“保生子”）；
     - 做法：在抽取阶段利用 PyMuPDF (`fitz`) 提取页面物理 word bboxes 并缓存；对 OpenDataLoader 产出的文本块做断词特征检测，当检测到碎词且字符数明显少于物理字词时，通过边界框包含度（Containment matching）自动取回 fitz 正确解码的单词进行无损原位修补，兼顾 OpenDataLoader 的版面拓扑与 PyMuPDF 的底层字符保真度。
  ② **表格语义结构与 HTML 跨行跨列（rowspan / colspan）完整还原 (`src/in_situ_renderer.py`)**：
     - 修复 `_parse_table_node` 中 `row span` / `col span` 在前端 HTML 生成时被丢失的问题，将实际跨度属性 `rowspan="..."` / `colspan="..."` 规范输出至 `<th>` 和 `<td>` 标签中；
     - 修复单元格首尾换行与空格导致的翻译查表失配问题（`clean_c = cell.get("text", "").strip()`），确保表格单元格 100% 汉化。
  ③ **防御表格 None/null 字段引发的类型异常与空图片静默截断 (`src/opendataloader_extractor.py`, `src/in_situ_renderer.py`)**：
     - 修复当 OpenDataLoader 返回 `{"row span": null}` 或 `{"number of rows": null}` 时执行 `int()` 导致的 `TypeError` 崩溃（改用 `int(d.get(k) or default)`）；
     - 修复 `render_insitu_html_document` 中使用 `zip(pages_data, page_data_uris, translated_pages)` 在 `page_data_uris` 为空或抽取指定子页码时发生的静默丢页缺陷，改为基于页码的安全索引匹配。
  ④ **全链路调度参数透传与回归单测闭环 (`src/watcher.py`, `src/web_app.py`, `src/router.py`)**：
     - Watcher 与 WebApp 统一显式透传 `upstream_extractor` 配置至路由器；
     - 新增 4 组专项回归测试，全量 234/234 单元测试全绿（19.07s），`FFR_chap06.pdf` 全真校验词汇 100% 正确恢复。
- 踩坑点：
  1. **第三方重型工具底层并非完美，跨引擎交叉校验才是终极解**：OpenDataLoader 具有卓越的版面与阅读顺序识别能力，但其底层的 Java PDFBox 字体解码器对历史旧字体（如无 Unicode CMap 的自定义 Type1 字体）容错性显著弱于 C 写的 MuPDF。不能盲信单一引擎，提取层将 OpenDataLoader 的版面/Bbox/AST 拓扑与 PyMuPDF 的 glyph 映射双向交叉校验，既有拓扑精度又有字符保真。
  2. **原位排版中的表格渲染必须保留 HTML span 属性**：若在翻译重构阶段只替换 `<td>{text}</td>` 而丢弃 `rowspan` 和 `colspan`，复杂的学术三线表与合并单元格表头会发生严重列错位变形。
- 适用场景：学术文献多格式复杂排版重构、历史扫描/打字机文献字体乱码清洗、高可靠离线翻译排版流水线。

## 2026-10-25 · OpenDataLoader-PDF 顶尖抽取引擎深度接入与原位双语重构无缝结合（P052-LiteParse-PDF自动识别）

- 场景：用户希望升级替换旧有 LiteParse 引擎，引入顶尖开源文档抽取引擎 `opendataloader-pdf` 作为上游抽取核心，将其卓越的版面解析能力（XY-Cut++ 智能阅读顺序拓扑排序、边界框物理坐标定位、表格结构化还原与行/列跨度感知、数学公式/LaTeX 特征识别）与项目既有的离线原位双语重构排版引擎无缝结合。
- 结论与做法：
  ① **Java 运行时探测与自动化环境注入 (`ensure_java_environment`)**：
     - `opendataloader-pdf` 底层采用基于 PDFBox/AWT 的预编译 Java JAR 架构；macOS Apple Silicon 默认自带的 `/usr/bin/java` 为系统存根，执行会报错 `Unable to locate a Java Runtime`；
     - 探测并锁定 Homebrew OpenJDK 27（`/opt/homebrew/opt/openjdk/bin/java`），在 `~/.local/bin/java` 建立软链接，并在 Python 层面实现自动多级探测、环境 `PATH` 前置注入与 `JAVA_HOME` 自动配置，确保任何环境即插即用；
  ② **上游抽取适配器模块建设 (`src/opendataloader_extractor.py`)**：
     - 构建 `opendataloader_extractor.py`，调用 `opendataloader_pdf.convert` 采用 `--reading-order xycut` 与 `--table-method cluster` 双算法；
     - 攻克 PDF 左下角原点至 Web/HTML 左上角原点坐标系统投影映射（`x = x1`, `y = page_h - y2`, `w = x2 - x1`, `h = y2 - y1`），实测与物理点阵 100% 吻合；
     - 实现递归 AST 展平器（`_traverse_raw_elements`），无缝保留 XY-Cut++ 拓扑阅读流，彻底杜绝历史扫描件标题误入正文、页底脚注被吞噬、多栏交错折行等人工规则难题；
     - 支持表格行/列/跨度解析（`_parse_table_node`），输出 GFM Markdown 表格与语义化 HTML `<table>`；
     - 支持数学字体（`CambriaMath`、`MathItal`、`CMMI` 等）及 Unicode 数学物理符号公式识别与免转译保护；
  ③ **原位双层布局引擎无缝接入 (`src/in_situ_renderer.py`)**：
     - `process_pdf_to_insitu_html` 默认将上游引擎升级为 `opendataloader`，保留 `liteparse` 平滑回退机制；
     - 对提取出的结构化元素直接按 XY-Cut++ 注入排版流；表格块渲染为独立的响应式原位 HTML 容器（`.table-block`），公式块赋予专用数学字体与标记（`.formula-block`），悬停统一显示 `data-en` 原文浮层；
     - 纵向层叠流算法（`layout_page_blocks`）无缝兼容表格真实高度约束，消除段落碰撞；
  ④ **路由调度与桌面应用全面升级 (`src/router.py`, `src/web_app.py`, `config.json`)**：
     - 路由器新增 `opendataloader` 策略分流与默认配置；
     - 桌面端 Web 应用新增 `⚡️ OpenDataLoader 原位双语重构` 专属路由模式，徽标与副标题同步升级；
     - 新增 12 组针对性单元与集成测试（`tests/test_opendataloader_extractor.py`），全量 230/230 单元测试全绿通过（18.1s），并在 39 页真实扫描技术文献上通过全流程端到端重构验证（产出 19.6MB 原位可编辑 HTML）。
- 踩坑点：
  1. **macOS 系统自带 `/usr/bin/java` 存根陷阱**：macOS 系统目录下的 `/usr/bin/java` 只是一个代理分发存根，在未全局安装 macOS JDK pkg 时即使执行 `which java` 返回有效路径，运行时仍会报错退出；对 Java 依赖的探测不能仅靠 `shutil.which`，必须真实执行 `-version` 校验其退出码与输出，若不可用需自动向 PATH 注入 Homebrew OpenJDK 真实二进制路径。
  2. **PDF 规范笛卡尔坐标系向 Web 屏幕坐标系的 Y 轴翻转计算**：PDF 内部遵循 PostScript 几何坐标系，原点位于页面左下角，Y 向上递增；而 HTML/CSS 绝对定位遵循屏幕几何坐标系，原点位于左上角，Y 向下递增。直接将 PDF 的 `y1` 当作 CSS `top` 会导致整页内容被彻底垂直镜像颠倒；必须严格使用 `top = page_height - y_max`，`bottom = page_height - y_min`，`height = y_max - y_min`。
  3. **分页提取时总页数与实际抽取页集合的解耦**：当向 `opendataloader-pdf` 传入 `--pages 1-2` 时，返回的全局元数据字典中 `"number of pages"` 依然是母版 PDF 的全量物理总页数（例如 39），而实际抽取结果仅存在于 `kids` 节点中包含的对应页。构建页面数据字典时必须按 `kids` 实际捕获的页面集合（`pages_seen`）进行初始化，否则会生成大量虚假的空页面对象。
- 适用场景：顶尖 PDF 版面结构分析、XY-Cut++ 复杂栏目阅读顺序重构、学术论文公式/表格精准识别与双语翻译排版。

## 2026-10-25 · 原位排版仿 pdf2zh 动态字号行距缩放、纵向层叠防碰撞与页底脚注保护（P052-LiteParse-PDF自动识别）

- 场景：用户使用应用审阅 `FFR_chap06.pdf` 原位双层 HTML 产物，反馈发现多处段落垂直重叠（第 1 页正文侵入页底脚注、第 6/24/33 页连续段落重叠，尤其是第 39 页参考文献第 18 条译文占 3 行直接叠印到第 19 条原位起始线，进而引发 19~23 条全篇级联碰撞）；要求模仿 `pdf2zh` 排版机制彻底修复重叠问题，并重新生成后由视觉走查核验。
- 结论与做法：
  ① **原位绝对定位与字号行距硬下界双重缺陷根因定位**：
     - `in_situ_renderer.py` 中每个文本块均被赋予 `position: absolute; top: {top_pct}%` 绝对坐标；
     - `compute_block_typography` 中强制设置了 `min line_height = 1.60` 和正文统一 11.0pt，当英文段落或参考文献（母版仅 7.8~8.5pt）翻译为中文后，行距与字号被无条件撑大 1.4~2.4 倍，导致文本框高度大幅溢出；
     - 紧接着的下一块依然被硬钉死在母版原始 Y 坐标，前一块的尾部与后一块的头部必然发生垂直交叉叠印；参考文献多条目密集排列时，叠印逐级传导形成严重连锁灾难；
  ② **借鉴 pdf2zh 构建动态字号行距缩放拟合机制 (`estimate_rendered_lines` & `compute_block_typography`)**：
     - 构建分词级 CJK/英文词元折行估算器（`estimate_rendered_lines`）：针对大写英文字母（0.72em）、数字（0.60em）、全角中文及标点（1.02em）、letter-spacing（0.02em）及 CSS 内边距（4px）进行精确词元折行模拟，解决之前纯字符累加未计入英文单词整体换行 slack 导致的行数低估；
     - 初始基准行距设为 1.40（对齐 pdf2zh 规范），严格将行距上限控制在 1.48，禁止虚高撑开至 1.70（避免估计行数存在微弱方差时单行直接膨胀 24px 引发下游雪崩）；
     - 当预测高度超过容器时，优先以 0.05 为步长动态压低 `line_height` 至 1.10；若仍超出容器高度，字号优雅梯度递减至 `min_fs`（7.5~8.5pt），确保长密段落和参考文献紧凑适配容器高度；
  ③ **同栏纵向动态层叠流与防碰撞约束 (`layout_page_blocks`)**：
     - 构建页面分栏与水平重叠流检测算法（水平重叠 > 35% 或宽度跨栏），严格判定同栏前后关联块；
     - 实施层叠非重叠约束：`block[i].top >= block[i-1].bottom + min_gap`（`min_gap = 4.0pt`），估算高度加入 2.5pt 边距冗余缓冲，前块若微幅延展，后块自动向下推移，从几何拓扑上阻断任何垂直碰撞；
  ④ **页底脚注硬边界防护与正文避让**：
     - 识别 Y > 78% 且含 `*` 或 `contribution from` 的页底脚注，严格锚定其在页底的独立安全保留区；
     - 计算同栏正文最大允许高度 `col_max_bottom = footnote_top - 8.0pt`，正文块逼近脚注时自动执行二次深度自适应压缩，杜绝正文向下侵入脚注；修复脚注碰撞循环中局部变量泄漏问题；
  ⑤ **标题与小节号版式量化收敛 (`quantize_typography`)**：
     - 强化章节大标题识别正则（`^(PART|CHAPTER)\s+` 及居中全大写副标题），使第 1 页 `CHAPTER 6` 与 `CHEMICAL PROCESSING*` 恢复 12.5pt 加粗；
     - 优先判定连字符小节号（如 `6-1. INTRODUCTION`），赋予规范 11.0pt 半加粗（weight 600），防止被通配规则降级为花名册字体；
  ⑥ **端到端全量 39 页重新生成与无头 Chrome 真实 DOM 逐页视觉质检**：
     - 重新生成 `outbox/FFR_chap06.原位双层版.html`；
     - 通过 Playwright 驱动真实 Google Chrome 引擎，遍历全书 39 页全部 316 个文本块的真实 DOM `getBoundingClientRect()`，**真实 DOM 几何碰撞数绝对归零（0 Collisions）**；
     - 截取全量关键页（第 1、6、17、24、33、36、38、39 页）高清截图，逐页视觉走查确认第 1 页正文与页底脚注间隔达 156.5px，第 38-39 页参考文献 1~23 逐项清晰离散排布；全量 218/218 单元测试全绿通过。
- 踩坑点：
  1. **折行行数估算必须考虑单词级排版特性（Word-break Slack）**：纯字符累加会忽略长英文单词/化学式不能在行尾任意断开而整词折行所浪费的行尾空白，导致长密技术文本被低估 1 行；而一旦低估 1 行且设置了过度膨胀的行距（如 1.70），在浏览器渲染时瞬间膨胀 20+px，轻易吞噬微小间距并撞上下游块。
  2. **原位排版不能把所有元素“绝对钉死”**：原位双层排版的初衷是对齐原位，但译文体积与原文天然存在波动。正确的解法是“基准原位 + 同栏动态层叠（Cascade Push）+ 动态字号行距收敛（Dynamic Typography Fitting）”，既保留原位视差对齐，又彻底消除重叠。
  3. **学术参考文献不能盲目套用正文字号标尺**：学术书籍/期刊中的参考文献通常为 7.5~8.5pt 的微型字体，若一刀切强制升级为 11.0pt 正文字号，单条参考文献体积直接翻倍，直接在致密列表中诱发多米诺骨牌式的级联重叠；必须识别参考文献条目（`^(\[\d+\]|\d+[\.\:])\s+[A-Z]`）并将其量化区间独立收敛在 8.5~9.5pt。
- 适用场景：原位双层 PDF/HTML 渲染、科技文献翻译排版、富文本多段落自适应防重叠引擎、自动化视觉回归测试。

## 2026-10-24 · pdf2zh 斜体小节标题公式误判根因排查、多层级文件夹拖拽防碰撞与边界强化交付（P052-LiteParse-PDF自动识别）

- 场景：在完成长段落截断修复后，深入逐页核对 `EN13_MDPI_HybridChannel_2025-双语对照版.pdf` 发现第 3 章全部 5 个二级小节标题（3.1~3.5）依然全篇保留英文未被翻译；同时排查可交互桌面应用在多层级文件夹拖拽下的批处理边界。
- 结论与做法：
  ① **学术期刊正文斜体被误判为公式变量的根因定位**：
     - `pdf2zh/converter.py` 的公式字体判定规则 `vflag` 中，默认正则包含了宽泛的 `.*Ital`；
     - 现代学术期刊（如 MDPI、Springer、IEEE）标准排版中，二级标题（如 `3.1. Axial Profiles...`、`3.2. Effect of...`）统一采用正文字体斜体（如 `PalatinoLinotype-Italic`）；
     - `vflag` 将整句每一个普通英文字母全量判定为数学公式，将整段标题打包放入 `{v0}` 公式组；
     - 在翻译工作流 `worker(s)` 中，针对纯公式段落 `re.match(r"^\{v\d+\}$", s)` 执行静默跳过原样返回，导致小节标题 100% 漏译；
  ② **公式字体白名单收敛与安全注入 (`src/pdf2zh_patch.py` & `src/vector_pdf_renderer.py`)**：
     - 在 `pdf2zh_patch.py` 中增加 `patch_pdf2zh_converter_file`，将过度宽泛的 `.*Ital` 修正为仅匹配专用数学斜体 `.*MathItal`；
     - 在 `vector_pdf_renderer.py` 中显式向 `pdf2zh` 传入安全公式字体白名单参数 `-f`，彻底解锁 MDPI/IEEE 二级斜体标题翻译；
     - 重新生成全量 21 页论文，第 3 章 5 个二级标题 100% 汉化（`3.1. 体积温度和速度的轴向分布`、`3.2. 热侧质量流量的影响`、`3.3. 热侧入口温度的影响`、`3.4. 冷侧质量流量的影响`、`3.5. 不同热阻比的讨论`），全篇中文字数达 11,052 字；
  ③ **交互式应用多层文件夹拖拽边界加固 (`src/web_app.py`)**：
     - **Web API 100条批次截断修复**：HTML5 `FileSystemDirectoryReader.readEntries()` 在 WebKit/Chromium 中单次仅返回最多 100 项，实现 `readAllEntries` 循环读取直至空数组，防止百篇以上大型文献库丢失；
     - **同名文件防覆盖排队**：针对文件夹拖拽中子目录同名文件（如 `dir1/paper.pdf` 与 `dir2/paper.pdf`），引入动态递增安全重命名机制，避免后台任务冲突与覆盖；
     - **MIME Multipart 严格解包与非 PDF 拦截**：采用正则精准提取 `boundary` 参数，去除非协议 CRLF，禁止 `rstrip` 侵蚀二进制 PDF 尾部，并在网关层对非 PDF 文件立即拦截。
- 踩坑点：
  1. **公式字体判定中的“贪婪包含”陷阱**：将包含 `Ital` 的所有字体均视为公式，忽视了西方学术排版规范中斜体是极其常用的正文强调与小节标题样式。对字体的数学属性判定必须限定于专用数学字族（如 `Math`, `Sym`, `CMMI`, `MSAM`）或结合字符本身的数学 Unicode 区间。
  2. **HTML5 目录读取器的分批协议陷阱**：`readEntries()` 不是一次性返回全部文件，而是分页返回（批次上限通常为 100）。若仅调一次 `readEntries()`，任何超过 100 个文件的文件夹拖放都会被静默丢弃剩余文件。
- 适用场景：学术论文版面识别、公式/代码过滤算法、浏览器端目录递归批量拖拽上传、本地轻量 HTTP 服务器开发。

## 2026-10-24 · pdf2zh 长段落暴力截断根因排查、多分块保真注入与文件夹拖放交互应用全流程交付（P052-LiteParse-PDF自动识别）

- 场景：用户发现双语对照版论文（如 `EN13_MDPI_HybridChannel_2025-双语对照版.pdf`）存在严重译文残缺（摘要第 5 行后截断、引言长段后半截丢失、第 20-21 页参考文献只翻译到前 5 条和前 24 条后续全部失踪）；要求定位根因彻底修复，并将整个系统包装为支持单 PDF 或整套文件夹拖拽直接转换的可交互桌面应用，选定案例由视觉 agent 逐章质检验收通过后交付并推送到远端。
- 结论与做法：
  ① **长段落暴力截断与 SQLite 缓存污染根因定位**：
     - 逐页文本审计与底层跟踪定位到 `pdf2zh/translator.py` 中 `BingTranslator.do_translate` 存在硬编码截断：`text = text[:1000] # bing translate max length`；
     - 针对学术论文中普遍超过 1000 字符的长段落（摘要通常 1500~2000 字、参考文献单页 2500~4500 字），该逻辑将 1000 字符之后的内容全部无情扔弃；
     - 且 `TranslationCache`（`~/.cache/pdf2zh/cache.v1.db`）将截断后的残缺译文与完整原文键值强行绑定，导致后续重跑持续命中残缺缓存；
  ② **智能自适应多粒度分块器与 CJK 缝合算法 (`src/pdf2zh_patch.py`)**：
     - 构建 `split_into_chunks`：严格保护公式占位符（`{v\d+}`）不被切断，按标点边界（`.?!;\n`）与列表序号自适应拆分，单块阈值收敛至 800 字符安全裕度；
     - 构建 `smart_join_translated`：针对中文字符标点实现无损自然缝合（中文句号/感叹号直接拼接，英文保持空格），杜绝排版断裂；
     - 实现 `clean_truncated_cache`：从 SQLite 缓存库中精准剔除历史 >800 字符的截断残缺缓存行；
     - 在 `src/vector_pdf_renderer.py` 中引入环境幂等自动打补丁机制，确保 CLI 与 Python 调用均自动生效；
     - 实测 `EN13` 案例全篇中文字符由 ~7,000 字跃升至 10,978 字（+56.8%），摘要、正文与 38 项参考文献 100% 完整交付；
  ③ **极速纯原生交互式应用交付 (`src/web_app.py` + `打开交互应用.command`)**：
     - 遵循 AGENTS.md 约束，基于 Python 标准库 `ThreadingHTTPServer` 实现零第三方依赖本地 Web 服务（极速冷启动 <100ms）；
     - 前端采用现代 Apple 人机界面交互设计，基于 HTML5 `webkitGetAsEntry` API 实现支持单 PDF、多文件以及**整套嵌套文件夹直接拖拽递归深度解析**；
     - 集成实时任务进度队列、双轨自动识别状态徽标、原件自动归档 `processed/`、成果原子落盘 `outbox/` 及“在访达中定位”快捷调用；
     - 提供双击即可启动的 macOS 原生执行脚本 `打开交互应用.command`；
  ④ **逐章视觉质检验收与测试回归**：
     - 逐章走查 21 页单语精译版与 42 页双语对照版，出具详细视觉走查报告（Section 8），评定裁决为 `PASS (出版级通过)`；
     - 新增 `test_pdf2zh_patch.py` 与 `test_web_app.py` 单元测试，全量 205/205 单元测试全绿通过（15.2s）。
- 踩坑点：
  1. **第三方翻译 API 的未报错截断陷阱**：Bing 翻译 web 接口单次请求超过 1000 字符会返回 HTTP 400，上游开源作者为了省事简单采用了 `text[:1000]` 硬截断，导致长文本不仅被斩断而且完全不报错；对于文本重排与翻译流水线，长文本必须按语法标点做确定性安全分块，且分块器必须具备公式占位符守卫，严禁粗暴按固定字符数切分。
  2. **带状态缓存的副作用污染**：修复翻译截断逻辑后，若未清理历史 SQLite 缓存库，系统仍会通过原文本哈希命中旧有的截断译文并直接返回，造成“代码改了却没生效”的假象；对缓存型基础设施进行算法升级时，必须配套缓存数据版本校验与异常数据清理。
- 适用场景：学术论文翻译排版、大模型/翻译 API 长度受限长文本安全拆分、文件及嵌套文件夹拖拽交互桌面应用开发。

## 2026-10-24 · 双轨智能版面路由器与 pdf2zh 矢量学术文献管线深度集成（P052-LiteParse-PDF自动识别）

- 场景：用户提议将开源优秀的 `pdf2zh` 工具集成到本项目中以处理现代矢量学术论文，实现“鱼和熊掌兼得”；并要求派出视觉 QA subagent 执行客观、独立的视觉走查与验收。
- 结论与做法：
  ① **pdf2zh 隔离环境部署与关键依赖断裂修复**：在用户独立虚拟环境 `~/.local/venvs/pdf2zh` 部署 Python 3.12 虚拟环境并安装 `pdf2zh` (v1.9.11)；修复了两个上游突发破坏性升级：1) `tencentcloud-sdk-python-tmt` v3.1.129 移除 `TextTranslateRequest`，锁定降级至 `3.0.1478`；2) `bitstring` v5.0.0 移除 `BitStream`，锁定 `bitstring<5` (`4.4.0`)，确保 PyMuPDF、BabelDOC、RapidOCR 等底层依赖稳定可控；
  ② **跨文献类别底层机理实测（双轨分流的必然性）**：
     - *现代矢量学术论文 (`EN01_MDPI_PCHE_Review_2025.pdf`)*：`pdf2zh` 依托 PyMuPDF Redaction 抹除 PDF 原生矢量文本对象，直接在原位置注入中文字体，生成近乎母版出版级的双语/单语矢量 PDF，保留完美的公式下标（$CO_2$）与双栏非对称刊物版面；
     - *历史打字机扫描文献 (`ORNL-TM-0733 Rev 3`)*：`pdf2zh` 遭遇致命滑铁卢。因历史文献字符固化在光栅背景位图（Raster Bitmap）上，矢量 Redaction 无法抹除像素，导致中文字符直接“黑印黑”打在打字机墨迹上方，整页沦为无法阅读的墨坨（第 2 页法律声明全糊、第 11 页 70 项人员名单严重粘连叠印并放大 OCR 油墨乱码）；
     - 这一客观机理实测确立了“现代矢量论文走 pdf2zh 矢量流，历史扫描文献走 LiteParse 原位双层解耦流”的必然性；
  ③ **智能路由器 (`src/router.py`) 与双轨管线实现**：
     - 实现 `probe_pdf_document_type`：检测首 3 页光栅全页底图占比（$>75\%$）、OCR 专用字体（`GlyphLessFont` / `Type3` / `Tesseract`）及原生文本流密度（字数 $>250$、字体数 $\ge 3$），实现对仓库各类 PDF 100% 准确判别；
     - 实现 `route_and_process_pdf` 与 `vector_pdf_renderer.py`，支持原子输出至 `outbox/`、自动归档与临时文件清理；
     - 在 `config.json` 与 `src/watcher.py` 中引入 `dual_track_mode: "auto"` 与 `pdf2zh_service: "bing"`，保持 100% 向后兼容；
  ④ **自主 Visual QA Inspector Subagent 视觉验收**：
     - 派发专属视觉质检 subagent（`visual_qa_inspector`），对两流 7 份目标图像执行了包括碰撞、底色纯净度、字号收敛、公式符号保真的像素级走查，出具了详细的 `VISUAL_QA_REPORT.md`，给出明确的 `PASS` 最终裁决（矢量论文加权 99.2 分，原位双层 HTML 96.8 分，盲用 pdf2zh 仅 12.5 分）；
  ⑤ **全量测试与回归**：新增 7 项路由与 Watcher 集成单测，全网 194/194 单测全绿通过（14.9s）。
- 踩坑点：
  1. **PyMuPDF Redaction 无法抹除光栅位图中的字迹**：矢量 Redaction 只能擦除 PDF 内部的矢量文本流指令（Text Streams），对扫描件像素图片里的字迹无能为力。扫描件必须采用前底层解耦、动态透光度的原位双层架构（如 LiteParse In-situ HTML）才能根治“黑印黑”。
  2. **Python 传递依赖“幽灵破坏” (Ghost Breaking Changes)**：即使锁定了直接工具包版本（如 `pdf2zh==1.9.11`），其传递依赖（如 `tencentcloud-sdk-python-tmt`、`bitstring`）一旦发布主版本破坏（v5.0），就会导致整个虚拟环境崩溃；在生产部署中必须对上游传递依赖的关键 C/Python 库进行版本上界约束。
- 适用场景：学术论文翻译、历史扫描档案数字化、多格式混合 PDF 自动分流架构、跨管线自动化视觉 QA。

## 2026-10-24 · 名单条目粗放正则反噬法律声明前言合并（“顾头不顾尾”冲突根因与全字词长门禁双赢规整）（P052-LiteParse-PDF自动识别）
- 场景：用户反馈“为什么总是会顾头不顾尾？这一处的重叠问题我记得之前已经改过一次了，难道不能一举两得嘛？”（附图：第 2 页法律声明 LEGAL NOTICE 中引言句 `Commission:` 与下属条款 `A. 就本报告所载资料...` 再次垂直交叉叠印）。
- 结论与做法：
  ① **“顾头不顾尾”冲突根因排查**：上一轮为了保护第 11 页 70 项人员分发名单不被拼接为伪段落，引入了名单条目判定 `is_roster_entry`；其中的正则 `^(\d+...|[A-Za-z0-9]{1,4}[\.\,])\s+([A-Z][\.\,]\s*)*[A-Z][a-z]+` 由于末尾未锚定字符串结尾且无词数限制，导致第 2 页法律条款 `A. Makes any warranty or representation...`（长达 13 词、306pt 宽的法律正文条款）因为以 `A. Makes` 开头，被错误判定为“人员名单条目”！进而在段落合并判定中触发名单条目隔离门禁，粗暴切断了以冒号 `:` 结尾的前言与条款 A 的合并，导致前言在中文折行后垂直侵入条款 A 的空间，造成重叠复发；
  ② **词数/字符长度硬门禁与严格边界锚定（两全其美）**：人员分发表的原子条目本质是短文本（如 `35. P. R. Kasten`、`Lo, R. E. MacPherson`、`Blumberg`、`Central Research Library (CRL)`），其词数必 $\le 5$ 且总长度必 $\le 45$ 字符；而法律条款正文动辄数十词、上百字符；在 `is_roster_entry` 头部增加 `len(words) > 5 or len(txt) > 45` 硬短路拦截，并为所有正则补充字符串末尾锚定 `$`，严格限制单姓氏 `^[A-Z][a-z]{4,}$`（排除如 `Safety Limits` 等双词短语），实现：
     - 第 2 页法律条款 A 判定为 `False`，冒号续行机制 100% 触发，前言与 Clause A、B 完美凝聚为单一 118pt 高完整声明块，第 2 页碰撞绝对归零；
     - 第 11 页 70 项人员与机构分发名单 100% 判定为 `True`，保持离散独立单行，两栏平齐对齐无任何粘连，第 11 页碰撞同样绝对归零；
  ③ **孤立单字母扫描噪点过滤与标题装饰符微清洗**：在 `is_clean_ocr_item` 中增加孤立微型单字母滤除规则（`len == 1 and not num_or_sec and w < 12.0`），彻底清除第 2 页右侧 OCR 噪点 `L`（`w=9.3pt` 虚假文本块）及全篇扫描尘埃；在预清洗中净化打字机装饰线 `- LEGAL NOTICE = -~ S` -> `LEGAL NOTICE`，规范译为“法定声明”；
  ④ **自动化验证与端到端交付**：编写包含 15 个边界样例的针对性单元测试 `TestInSituRosterAndLegalNoticeIsolation`，全量 187/187 单测全绿；端到端重新生成，第 2 页（0 碰撞）与第 11 页（0 碰撞）同时达标，无任何代码回退或此消彼长。
- 踩坑点：
  1. 正则表达式用于语义/版面实体识别（如“人名名单” vs “法律正文”）时，若只匹配前缀（如 `^[A-Z]\.\s+[A-Z][a-z]+`）而缺少全文本长度与词数门禁（`len(words) <= 5 and len(txt) <= 45`），极易把带有字母编号的正文条款（`A. Makes...`、`B. Assumes...`）误判为人名（如 `A. Makes`），导致正文逻辑被名单逻辑误杀。
  2. 规则扩展与异常修复必须在跨页全量回归中审视相互影响：在为一个复杂页面（如第 11 页名单）打补丁时，必须验证前面已修复页面（如第 2 页法律声明）的关键测试用例，将边界条件用参数（字数、宽度、结尾锚定）区分清晰，实现确定性兼得。
- 适用场景：原位双层 PDF/HTML 渲染、段落聚合与离散列表冲突裁决、历史打字机 OCR 条款与人名消歧。

## 2026-10-24 · 双栏名单误并伪段落乱排、孤立数字切句诱发条约幻觉与罗马数字章节误杀人名（P052-LiteParse-PDF自动识别）
- 场景：用户审阅原位 HTML 发现“怎么这里又乱了”（红框圈出第 11 页人员分发表 Internal Distribution）：
  ① 左侧人名名单中相邻人员被互相贪婪合并为两行/三行伪段落（`Affel` 与 `Anderson` 合并、`Baes` 与 `Bettis` 合并等），导致折行溢出并在垂直方向错乱叠印；
  ② 右侧名单爆发大面积联合国公约幻觉乱码（如 `35.`、`42.`、`56.`、`59.` 被翻成“经济、社会、文化权利”、“第 36 条：”等）；
  ③ 字体字号极度混乱：`L. Crowley`、`L. Culler`、`L. Hudson`、`63. Gale Young` 呈现 12.5pt 粗体大字，合并块呈现 11.0pt，单行呈现 9.5pt，跳跃突兀；
  ④ 底部机构名称（CRL、DRS、LRD）与人名区域堆叠挤压。
- 结论与做法：
  ① **回溯段落合并误杀离散名单的根因与原子条目硬隔离**：上一轮为了合并第 3 页并排公告框引入了 `reversed(paras[-8:])` 与 `is_both_left/is_both_right`。但在第 11 页双栏分发表中，自然正文续行规则（`is_same_col and v_gap <= 12.5 and w > 50`）将两两相邻的人名当成自然段落盲目拼接！重构实现 `is_roster_entry`，针对人名缩写（`R. G. Affel`）、序号项（`35. P. R. Kasten`）、单姓氏（`Blumberg`）和机构缩写（`(CRL)`）建立名单原子条目硬隔离门禁——除非行尾为破折号/逗号/悬挂缩进，否则绝不跨行合并；正文自然续行严格增加宽行门禁（`w >= 105pt` 且词数 $\ge 4$），彻底杜绝名单被吞并；
  ② **孤立数字切句诱发 NMT 条约条款幻觉根除**：查明右侧名单出现“经济、社会、文化权利”与“第 36 条”的根因：`split_sentences` 遇到 `35. P. R. Kasten` 时，句号后带空格大写字母的正则粗暴将 `35.` 剥离为独立单句。MarianMT 神经翻译模型在联合国/公约双语语料中将孤立的条约编号 `35.` 解码为联合国《经济、社会及文化权利国际公约》第 35 条！在分句器中加入 `len(buffer) == 1` 守卫：句首的孤立数字/编号前缀绝不切断，与后续正文一体送译，幻觉错译 100% 清零；
  ③ **罗马数字首字母与章节大标题误杀人名修复**：定位到 `quantize_typography` 中章节正则 `r"^(\d+\.|\b[IVXLCDM]+\b\.?)\s+[A-Za-z]{3,}"` 中罗马数字 `L` 误伤了首字母为 `L.` 的人名（`L. Crowley`、`L. Culler`、`L. Hudson`）以及条目号 `63. Gale Young`，将其打上 12.5pt 粗体；重构章节正则为全大写单词 `[A-Z\s]{3,}` 并排除人名缩写格式，名单条目统一赋予 9.5pt；
  ④ **装订打孔杂点清除与历史 OCR 打字机序号清洗**：清洗 `100 < x < 155` 打孔区域单字符杂点（`N`、`W`、`O`、`O~`）；在预翻译中将历史打字机序号 `Lo.` 归位 `40.`、`L1.` 归位 `41.`、`L,` 归位 `44.`、`k5,` 归位 `45.`、`4.` 归位 `46.`、`5k,` 归位 `54.`、`61l.` 归位 `61.`，序号 35~63 完全严格连续；
  ⑤ **全量验证交付**：全量 184/184 单测全绿，纯原生端到端重新生成；第 11 页 70 个块左右两栏每行水平高度绝对精准齐平，字号 100% 统一为 9.5pt，公约乱码与重叠全部归零。
- 踩坑点：
  1. 窗口多段回溯（`reversed(paras[-N:])`）是一把双刃剑：在多栏正文段落中可以缝合交替行，但若没有名单原子行守卫，会把多栏离散列表（人名、器件表、物料清单）当成环绕正文强行吞并，导致整版错乱。
  2. NMT 翻译模型训练语料中充斥联合国决议与法律条约，绝不能将句首的编号（如 `35.`、`42.`）单独切句喂给模型，否则会极大概率解码出《公约》等严重幻觉条目。
  3. 罗马数字章节检测（`[IVXLCDM]`）中 `L`（50）、`C`（100）、`M`（1000）、`D`（500）、`I`（1）、`V`（5）、`X`（10）恰好全是常见英文人名的首字母（如 L. Crowley），章节判断必须强行断言后续单词全部大写（`[A-Z\s]{3,}`），严禁对混合大小写人名开放。
- 适用场景：原位双层 PDF/HTML 渲染、多栏人员分发表与列表排版、NMT 句子级分词与公约幻觉抑制。

## 2026-10-24 · 历史双栏打字机文献文本块撕裂穿透、跨栏交错合并穿刺与异常字符宽度裁剪（P052-LiteParse-PDF自动识别）
- 场景：用户审阅原位 HTML 发现“你看这些也重叠了”（附图）：
  ① 第 2 页底部法律声明（Legal Notice）中引言句 `Commission:` 与下属条款 `A. Makes any warranty...` 垂直层叠交叉；
  ② 第 3 页顶部左右两框（Notice 框与 Legal Notice 框）被粉碎撕裂为 12 个单行碎片，纵横碰撞交织，且 NMT 产生严重幻觉错译（“倒数，他杀了他..。”、“原生的计数。它必须保存预知信息”、“里数”）；
  ③ 第 3 页底部摘要（Abstract）与替代注记（Supersession Note）互相缠绕穿透；
  ④ 第 6 页与第 8 页条款编号（如 4.9 与 4.10）出现文字叠印与撕裂。
- 结论与做法：
  ① **列表引言冒号续行放宽与垂直重叠根除**：定位到第 2 页引言句以 `:` 结尾，未包含在旧规则 `last_txt.endswith((",", "-", " and", " or"))` 中，导致被 `is_new_item`（`A. `）硬性阻断，从而拆分为两个垂直 Y 轴重合的块；在定界符中增加 `:` 后，引言与 A、B 条款自然凝聚为完整 13 行单段，第 2 页碰撞归零；
  ② **跨栏交替行回溯匹配机制 (`reversed(paras[-8:])`)**：定位到第 3 页顶部双框被撕裂成 12 碎片的深层根因：旧段落合并 `merge_smart_paragraphs` 仅比对当前行与最后一个段落末行 `paras[-1][-1]`；但在左右并排双栏版面中，按 Y 轴排序后左右两栏文本行垂直交替出现，导致 `paras[-1][-1]` 永远来自对侧栏，合并判定 100% 失败；重构算法向前回溯最多 8 个未闭合段落，配合双栏水平隔离检测（左框 `x+w <= 0.58*pw`、右框 `x >= 0.55*pw`），成功将左框聚合为 1 标题 + 1 正文，右框聚合为 1 标题 + 1 正文；
  ③ **打字机同物理行横向重叠守卫与基线漂移阻断**：在 `cluster_page_text_items` 中增加水平重叠守卫：若新 item 与行内已有 item 重叠超过 2.0pt，绝对禁止划归同一物理行，彻底消除打字机微漂移导致的上下行塌陷；装订孔噪点（`x < 45.0 and len <= 4`）滤除消除了“里数”幻觉源头；
  ④ **打字机负间隙容差与替代注记硬隔离**：`should_merge_blocks` 针对打字机重叠边框将垂直间隙下限放宽至 `-16.0pt`，使密集打字机段落顺利连通；针对摘要底部的 `This document supersedes...` 注入硬性阻断屏障，避免正文与注记缠绕；
  ⑤ **微缩胶片 OCR 损坏字宽截断与条款编号纠偏**：定位到第 8 页微缩胶片 OCR 存在损坏的字体变换矩阵（单个 `ol 2.9` 报 493.2pt 虚假宽度），在聚类前对 `width / len > 18.0` 进行合理字宽截断；在 `clean_historical_ocr_text` 中将逗号切分的 `4,10` 纠正为标准条款号 `4.10`；
  ⑥ **端到端原生交付**：纯确定性算法原生重新生成 12.32s 交付，第 2~11 页全书正文碰撞 100% 清零，184/184 单测全绿。
- 踩坑点：
  1. 并排双栏或左右分栏的文献绝不能用单纯的单向线性追加合并（`paras[-1][-1]`），因为在垂直排序下两栏行交替出现会 100% 阻断段落聚拢；必须使用窗口回溯多段匹配或分栏分区聚合。
  2. 历史打字机微缩胶片扫描件的 OCR 文本层常常包含损坏的字符几何信息（如宽度数百点），在做行聚类和包围盒计算时必须按字体大小进行合理上限截断（clamp），否则会导致行宽失真并污染碰撞检测。
  3. 引言句常以英文冒号 `:` 引入下级子条款（A.、B.、1. 等），合并逻辑若只拦截逗号和连词，会硬生生将引言与子条款劈开导致排版垂直撞车。
- 适用场景：原位双层 PDF/HTML 渲染、多栏与并排框段落聚合、打字机微缩胶片 OCR 修复。

## 2026-10-24 · 星号带注条款字号跳变根因定位、脚注正则过滤加固与横向 Tab 制表符间距自适应（P052-LiteParse-PDF自动识别）
- 场景：用户审阅原位 HTML 第 4 页时发现“还是会有字体跟其他字体不一样的，为什么？”（截图中 1.3、1.4、1.5、1.6、1.7、1.9 均为 11.0pt，唯独红框圈出的 1.8 节呈现较小的 9.5pt，字号跳跃突兀）。
- 结论与做法：
  ① **带星条款被误杀为脚注的根因查明**：旧字号量化规则使用 `txt.startswith(("*", "†", "‡"))` 粗暴判定脚注。但打字机正文中 1.8 节（`1.8 System Test at Elevated Pressure*`）与 6.3 节标题带有指向页底注脚的上标星号 `*`，OCR 识别将其排在前列（`* 1.8`），导致该条款被直接误杀为“脚注”，字号被错误打落为 9.5pt（而相邻正文条款为 11.0pt）；且单行名单规则误杀了章级标题（如 `5. 辐射`）；
  ② **章节条款前置判定与真脚注双重守卫**：重构 `quantize_typography` 执行流水线：
     - **第一优先级判定章节主标题**：`r"^(\d+\.|\b[IVXLCDM]+\b\.?)\s+[A-Za-z\u4e00-\u9fa5]{3,}"` 赋予 `12.5pt` 粗体；
     - **第二优先级锁定条款编号**：`r"^(\*+\s*)?(\d+(\.\d+)+)\s+"`，无论标题是否带星号或前置星号，绝对强制统一赋予 **`11.0pt`** 标准正文字号；
     - **脚注双重门禁**：仅当垂直坐标处于页面底部（`by > page_h * 0.78`）、长度大于 20 且非条款编号时，才允许分类为脚注（9.5pt）；
  ③ **打字机水平制表符（Tab Stop）间隙放宽**：第 5 页 `2.8` 章节号与 `Instrumentation` 标题之间存在 47.25pt 的物理 Tab 间隙，原行聚类 `column_h_gap=35pt` 将其切为两块；增加条款编号后自适应水平间距（`max_gap=55.0pt`），彻底将 `2.8 仪器 —— ...` 聚拢为完整单段；
  ④ **温度单位断句与星号排版归位**：修复 `split_sentences` 将 `1210°F.` 误判为单字母缩写导致 1.4 节漏译后半句的缺陷（1.4 节两句完整译出）；将 `* 1.8 标题` 归位为标准 `1.8 标题*`；
  ⑤ **全量验证交付**：原生重新生成 14.27s 交付，第 4 页所有条款 1.3~1.9 字号 100% 绝对统一为 11.0pt，184/184 单测全绿。
- 踩坑点：
  1. 含有上标或注释星号的章节编号（如 `* 1.8`、`* 6.3`）绝不能仅以 `startswith("*")` 判定为脚注，必须前置检查是否存在章节编号模式；真正的脚注必须结合页面几何垂直位置（`by > 0.78 * page_h`）综合判定。
  2. 英文单字母缩写过滤器（`\b[A-Za-z]\.$`）会误伤物理温度单位（`°F.`、`°C.`），导致以此结尾的句子无法触发分句切分并引发后续 NMT 截断丢句。
- 适用场景：原位双层 PDF/HTML 渲染、科技文献排版美化、打字机断行与脚注聚合。

## 2026-10-24 · 视觉占地面积自适应对齐：排版字号调大、自适应行距与多句段落截断根治（P052-LiteParse-PDF自动识别）
- 场景：用户审阅原位 HTML 发现中文由于信息密度高，字符数量仅为英文的 50%~60%，在 9.5pt 字号与 1.25 紧凑行距下仅占据原英文文本框约 35%~40% 的高度（如 4.5 节英文 8 行而中文缩在顶部 4 行，底部留下一大片空白），视觉稀疏扁平；用户要求“翻译的字体字号稍微大一些，行距稍微大一些，尽量占地和原文占地一致，让其看的饱满一些”。走查同时发现 4.6 节被漏掉了第二句、4.5 节出现温度译为“湿度”与丢失单位。
- 结论与做法：
  ① **字号阶梯稳健放大与饱满标尺**：将标准正文/规程条款统一基准由 9.5pt 安全上调至 11.0pt（标准中文五号字标尺），主章节标题升至 12.5pt（粗体），封面大标题升至 15.5pt，脚注 9.5pt，密集单行名单（如第 11 页）保持 9.5pt 防止折行溢出；
  ② **段落自适应行距动态回填 (`compute_block_typography`)**：构建基于字符数、段落宽度与原始英文外框高度的自适应行距估算模型：$L_h = \min(2.15, \max(1.60, \frac{bh}{N_{lines} \times F}))$，多行段落自动应用 1.60~2.15 倍行距与 0.035em 字间距；4.5 节等大段落占地高度由原来的 34% 跃升至 86%，原位占地饱满舒展且与原文几何边框高度贴合，各段落首行严格对其原始基准线；
  ③ **段落多句并行分词防截断重构**：定位到 4.6 节丢失后半句的根因是整段直接传给 MarianMT 触发了解码截断；重构流水线在聚类后以 `split_sentences` 拆分为独立单句进入批处理（259 句仅耗时 8.22s），译后再依自然标点还原整段，彻底消除多句段落丢句漏洞；
  ④ **规程术语精准映射补充**：补充 4.6 高压泄漏试验、-2 psig 负压保持、70 scfd / 280 scfd 标准流量单位、温度修正与燃料盐排盐罐等规程专用表达，破折号统一为中文双破折号 `——`；
  ⑤ **全量验证交付**：原生端到端 15.38s 重新生成交付，4.5/4.6/4.7 排版饱满大气、原位占地严格贴合，184/184 单测全绿。
- 踩坑点：
  1. MarianMT 作为单句训练的神经机器翻译模型，若直接喂入包含多个英文句号的长段落，极易在第一句结束处提前终止解码（EOS），导致第二句乃至全段后半部分凭空蒸发；长段落必须前置 `split_sentences`。
  2. 扩充行距时必须设置动态上下限（1.60~2.15），绝不能无限放大，否则单句短段落会被拉扯得支离破碎；同时字间距 `letter-spacing: 0.035em` 能防止中文在大行距下显得字符松散。
- 适用场景：原位双层 PDF/HTML 渲染、跨语种排版密度自适应对齐、科技规程段落饱满美化。

## 2026-10-24 · 视觉质检走查断句撕裂根因、小节号误杀修复与核规程术语对齐（P052-LiteParse-PDF自动识别）
- 场景：用户审阅原位 HTML 发现多处句子未能延续整句翻译（如 4.16、5.3、1.5、2.6、4.13、6.4 等从数值或换行处被切成两段分别翻译，造成“至少是冷却水流”等残缺碎片），要求派出视觉质检员打开两栏分屏模式（split-mode）对全书 11 页逐页对照审计，自检断句与排版缺陷，并由底层流水线原生修复，严禁手工修改 HTML。
- 结论与做法：
  ① **全量视觉对照与断句根因定位**：派出视觉质检员比对 11 页 225 个文本块，查出断句的核心根因是 `should_merge_blocks` 中 `is_new_item = r"^(\d+([\.\,\-]\d+)*[\.\,]?)"` 的正则贪婪匹配：末尾 `[\.\,]?` 存在可选问号，导致所有以数字/量词开头的换行续行（`15 gpm`, `12-month`, `28 psig`, `849-ft`, `45 psig`, `8.1 Mw`, `0.5%`）均被误判为“新编号列表项”而阻断合并；且前行末尾有句号（如缩写 `9 in.`）或介词时被硬编码阈值阻断；
  ② **严格定界符守卫与量词穿透保护**：重构 `is_new_item`，强制编号必须包含明确分隔符（`.`、`:`、`,`、`）`）并紧跟空格；新增量词/单位前缀白名单（`gpm`, `psig`, `Mw`, `ft`, `in.`, `month` 等），绝对豁免为正常数值续行而非编号项；新增未完成句式（dangling syntax）穿透合并（以介词、连词、比较级结尾的行强制合并）；
  ③ **小节序号误杀与右边缘噪点滤除**：定位到旧规则 `x < 150 and len(txt) <= 2` 误杀了全书所有单数字小节号（`5.`、`6.`、`3.`、`L.`）和行首短词（`is`、`be`、`of`），升级为保留有效序号与功能词白名单；针对第 6 页、第 8 页右侧扫描边缘噪点（`x > pw - 35` 的 `.`、`o`、`-`、`v`）进行精准过滤，彻底杜绝噪点充当楔子切裂 3.1 和脚注的问题；
  ④ **核工程规程术语与专有名词对齐规范**：构建原位规范映射表（`apply_in_situ_glossary`），纠正离线 NMT 爆发的严重术语错译（Scram 停堆而非螺旋藻、scram time 停堆落棒时间而非倾斜时间、Flux Trip Point 通量停堆整定值而非通航三重点、Surge Volume 缓冲容积而非蒸气流、Cell 舱室而非细胞/电池、Annulus 环形空间而非废墟/休眠水、AEC/ORO 原子能委员会/橡树岭办公室而非非洲经济中心/欧洲办事处、Ditto/Beall 迪托/比尔而非现状/铃）；
  ⑤ **全量验证交付**：原生端到端 15.64s 重新生成，12 处严重断句全部 100% 聚合连贯翻译，全文字号统一收敛，184/184 单测全绿。
- 踩坑点：
  1. 列表项检测正则绝对不能用 `[\.\,]?`，必须要求显式定界符且后跟空格，否则英文文献中极普遍的带数字换行续行（如 `15 gpm`）会瞬间腰斩整句。
  2. 边界杂点清洗切忌单凭坐标与长度一刀切，历史文献的顶层章节号（如 `5.`、`6.`）与行首短词在 OCR 中常为孤立单个 token，盲目过滤会导致全篇小节号失踪。
  3. 页面右边缘的微小杂点（如打孔边缘墨迹）若落入段落行之间，在按 y 排序合并时会横插在两行中间打断自然段落合并，必须前置清洗右边缘孤立噪点。
- 适用场景：原位双层 PDF/HTML 渲染、科技文献断行与句子聚合、核工程规程翻译质检。

## 2026-10-24 · 原位双层排版标题连字符断裂与字号层级离散统一收敛（P052-LiteParse-PDF自动识别）
- 场景：用户审阅原位 HTML 第 9 页时发现：
  ① 标题与正文横向撕裂重叠：5.1、5.3、5.4 等小节标题与正文之间因连字符破损或横向间距阈值偏小被切成两截，后续行合并时反向拉宽外框导致 5.3 出现文字叠印；脚注 `* This` 孤立断裂；
  ② 全文排版字号离散跳跃：OCR 字符框高度波动导致渲染层生成了 36 种杂乱字号（8.0~15.12pt），同一小节内标题 12.6pt 与正文 9.5pt 突兀反差，视觉杂乱（用户明确要求字号统一且严禁手工修改 HTML）。
- 结论与做法：
  ① **标点符号安全保留与横向间隙自适应放宽**：取消对破折号 `-` 与星号 `*` 的误杀过滤（仅过滤边框装订孔微小杂点）；将 `column_h_gap` 由 24pt 安全放宽至 60pt（远低于双栏页面 160pt+ 栏间隙），将单行垂直容差安全放宽至 8.5pt，彻底将 `5.1/5.3/5.4 标题 - 正文` 以及 `* 脚注` 汇聚为完整连续行；
  ② **小节序号强制分块保护**：在段落合并规则中加入 `^\d+(\.\d+)+\s+` 硬阻断守卫，无论上一行是否以逗号结尾，新小节序号绝不与前文串块；
  ③ **四阶确定性统一字号标尺 (`quantize_typography`)**：彻底废弃浮点字号与字符高度乘积，引入统一排版标尺：正文/条款/名单统一 9.5pt（占比 98.6%），主章节标题 11.0pt（粗体），封面大标题 13.5pt，脚注统一 8.5pt；全文字号种类由 36 种收敛为 3 种基准；
  ④ **全量验证**：全量 184/184 单测全绿，端到端重新原生生成 15.69s 交付；第 9 页碰撞数归零、叠印彻底消除、字号全局统一。
- 踩坑点：
  1. 标点清洗逻辑绝不能以 `txt in ["-", "*"]` 粗暴拦截，打字机正文小节破折号常以孤立 token 存在，过滤后会人为造出大空隙导致整行切裂。
  2. OCR 引擎识别的字号是基于每个字符的高斯包围盒，存在天然浮动（8~12pt），必须在渲染层用阶梯量化（quantization）归一到固定设计标尺，切忌直接乘以系数。
  3. 历史文献常有将句末句号识别为逗号的 OCR 瑕疵，段落合并时若仅看上一行逗号就判定续行，容易将后续以序号开头的新节误并入上一段，需对小节编号设立绝对前置门禁。
- 适用场景：原位双层 PDF/HTML 渲染、科技文献排版美化、打字机断行与脚注聚合。

## 2026-10-24 · 原位双层排版多栏名单与历史OCR垂直噪点根因排查与算法收敛（P052-LiteParse-PDF自动识别）
- 场景：在针对 ORNL 历史打字机扫描件第 11 页（内部人员分发表 Internal Distribution）进行原位双层 HTML 生成时，出现严重文字重叠、双栏名单错位以及左边缘垂直乱码穿透现象（用户明确要求排查原生生成乱的根因，严禁手工篡改 HTML，要求原生算法收敛）。
- 结论与做法：
  ① **穿透性垂直 OCR 噪点过滤**：定位到老旧 PDF 中两处穿透性伪字符块（高度达 253.3pt 与 69.7pt，长宽比分别达 26.3 与 8.2 的垂直折痕/装订孔噪点 `fi]?:fi:fi?d?>...` 与 `HOEnEHOYG`），因其高度巨大导致单行垂直容差被放大到 114pt 并水平吞并相邻人名，生成覆盖 32% 页面的巨型重叠块。实现 `is_clean_ocr_item`，对 $h > 45$ 且 $w < 15$ 的窄长噪点及左边缘打孔噪点精准过滤；并在聚类中将垂直容差硬截断至 6.0pt，杜绝容差膨胀；
  ② **跨栏交错合并阻断与原子行保护**：双栏名单因 y 坐标接近，原算法按 y 排序时左右栏交替出现，贪婪段落合并误将右栏条目当成左栏续行合并，且将多行独立人名吞并为伪段落。实现 `should_merge_blocks`，引入严格水平对齐度校验（同栏判断或悬挂缩进）与列表原子行保护（包含数字范围 `49-50.`、`72-86,`、打字机错字 `Lo.`、`k5.`、部门缩写 `(DRS)`、`(LRD)` 均不得跨行合并），彻底杜绝跨栏与名单合并；
  ③ **双栏非右对齐收敛与悬挂缩进合并**：修正原本 $x > 0.65 \times page\_w$ 误判为 `right` 对齐的缺陷，双栏排版统一保持自然 `left` 对齐；对结尾为逗号/连接词的条目（如 97-98 条第二行）支持悬挂缩进安全合并；
  ④ **紧凑单行行高与防折行保护**：为单行人名应用 `white-space: nowrap; line-height: 1.25;` 并钳制字号为 $\min(font, 9.2pt)$，彻底杜绝中文字体行高溢出导致的垂直碰撞（Page 11 左右两栏碰撞数归零）；
  ⑤ **全量验证**：全量 184/184 单测全绿，端到端重新原生生成 15.57s 交付，第 11 页 70 个块坐标严丝合缝，零重叠零乱码。
- 踩坑点：
  1. 历史扫描件的隐式 OCR 层常残留长条垂直黑线或打孔伪字符，其异常 height 会彻底击穿基于 `line_h` 比例计算的行聚类容差，必须前置设置长宽比过滤器与行容差上限截断。
  2. 页面中并列多栏排版切忌直接全局按 `(y, x)` 排序后做垂直段落合并，否则左右栏交错时极易跨栏拉郎配；合并前必须强校验两行横向重叠度与列边界。
  3. 不能将页面右半区的文本块简单当成 `text-align: right`，右栏通常也是左对齐。
  4. 打字机密集单倍行距（行距仅 10~11pt）在转为中文字体渲染时，行高和字号稍有膨胀就会碰撞，单行列表必须加 `white-space: nowrap` 与字号自适应限制。
- 适用场景：原位双层 PDF/HTML 渲染、多栏科技文献排版重构、历史老旧扫描件 OCR 噪点滤除。

## 2026-10-24 · 历史打字机扫描文献端到端翻译优化：BPE分词占位符变异防御、表格停用词幻觉阻断与伪代码解围栏（P052-LiteParse-PDF自动识别）
- 场景：在以真实 ORNL 历史打字机扫描文献（`ORNL-TM-0733REV3_MSRE_Design_Operations_Part_VI_Rev3.pdf`，熔盐堆实验装置运行安全限值规程）为标杆进行端到端全链路翻译质量优化时，基线测评得分仅 35.83/100，发现三大深层瓶颈：
  ① 伪代码围栏阻断：打字机排版由于大量行首缩进，OCR 引擎将其误识别为 Markdown 代码块（``` 或 4 空格缩进），导致 59.7% 的正文被判定为不可翻译代码块跳过，有效翻译覆盖率仅 ~40%；
  ② NMT 在孤立单元格停用词/复合介词下的解码发散与幻觉涌现：表格中碎片化单元格（如 `of the`、`in the`、`whenever`）送入 MarianMT 后，因缺失主谓谓词上下文触发严重发散（`of the` 生成 `排会会议和排会总会会排排联合国经费分摊比额表排排拉会的排排`，`of` 生成 `联年月日`）；
  ③ SentencePiece/BPE 分词器对长标记变异（mangling）破坏占位符还原：77 项熔盐堆专业术语采用 `XPH{num}X` 隔离，模型在分词与上下文结合时偶发将其变异为 `XPF{num}X`、`XPM{num}X`、`XPPH{num}X` 并在前后脱落游离 `X `，严格正则无法还原，致使 17 处术语残留为代码状乱码。
- 结论与做法：
  ① **智能代码分类器解围栏**：实现 `classify_code_block`，基于代码语法特征（def, import, {}, ;, return, #include）与自然语言统计特征（动词、介词、首字母大写、自然标点），精准将误标为代码块的历史打字机引文段落解围栏（unwrap）为正常自然段落进行端到端翻译，使实际翻译覆盖率跃升至 95.19%；
  ② **表格短语确定性映射与幻觉过滤器**：建立 `TABLE_STOPWORDS_MAP` 字典（32+ 条映射，含 `of the` -> `的`，`in the` -> `在` 等），在表格单元格级前置确定性短路映射，不送入 NMT；并在译后处理中加入针对幻觉模式（`排会[会议总会排拉]*`、`联[年月日联]{2,}`）的清洗过滤器，彻底消除表格对齐幻觉；
  ③ **容错占位符逆向还原**：放宽占位符逆向正则为 `rf"(?i)(?:\bX\s+)?(?:XP[A-Za-z]*?|Z){num}X?(?:\s+X\b)?"`，彻底容忍 BPE 分词导致的变异并将脱落的 `X ` 伴随符号一并抹除，使术语还原率达到 100%；
  ④ **历史打字机 OCR 错字与连字系统级启发式规整**：系统级集成 33+ 条无损 OCR 启发式修复规则（`4o`->`40`, `ts`->`is`, `L.k`->`4.4`, `1imits`->`limits`, `0.62yc/sec`->`0.62 μCi/sec`），并实现 GB/T 15834 盘古排版中英文空格规整；
  ⑤ **全量验证与标杆突破**：全套 184/184 单测全绿；五维客观基准评测（离线合规 100、OCR 清洗 100、结构覆盖 96.63、术语准确 76.67、表格通顺 100）综合得分达到 **93.33 / 100.00**（超过 90.0 验收门禁）。
- 踩坑点：
  1. NMT 占位符隔离送入 BPE/SentencePiece 分词器时，模型不一定会原样吐出大写字母组合，必须在还原正则中做容错前缀匹配与游离脱落字符清理。
  2. 表格中缺失主谓语的孤立介词或短语切忌直接喂给端到端 NMT，缺少句式约束极易诱发长串无意义叠词或联合国决议风格幻觉。
  3. 历史文献的扫描件排版往往带有固定缩进，必须通过代码语法与语言统计联合特征对代码块做真伪二次鉴别，绝不可盲目信任 OCR 引擎输出的代码围栏。
- 适用场景：历史扫描件/打字机文献 OCR 翻译重构、嵌入式 NMT 表格抗幻觉防护、专业技术术语高保真隔离流水线。

## 2026-10-24 · 离线翻译代码/公式缩进与排版保真、O(N^2)批处理缺陷消除与NMT结巴死循环防御（P052-LiteParse-PDF自动识别）
- 场景：在对方案二内置离线文献翻译引擎进行深度审查与端到端攻击测试中，发现前次实现存在多处致命结构破坏与性能隐患：
  ① **代码块与公式块结构破坏**：旧实现将代码块与多行公式逐行收集并在末尾执行 `"\n\n".join(b.strip())`，导致 Python 代码块的所有缩进丢失（引发 IndentationError）且每行代码间被插入双换行；
  ② **批量翻译 O(N^2) 重复计算与逐句 I/O**：`translate_sentences` 的 `translate_batch` 调用被误缩进在 `for` 循环内部，导致每新增一句都会将此前所有未缓存句子重复翻译，耗时随句数二次方爆炸；而在文档层级却逐句调用单个翻译，未利用多核 CPU 批处理能力；
  ③ **表格管道符与单字复读结巴**：表格拆分使用未考虑转义的 `split("|")`，导致包含 `\|` 的单元格列数破损；MarianMT 对 `Name`、`Formula`、`Status`、`Date` 等单字表头因无句子上下文触发 beam search 结巴循环（生成“公式公式公式”、“名称名称名称名称”）；且孤立图片行送入 NMT 会将占位符数字翻译成“零Z”；
  ④ **括号链接截断与标点误伤**：URL 含括号（如 `wiki/Flow_(mathematics)`）时正则截断破坏链接；`!\[` 被误作为中文感叹号转为全角 `！` 破坏图片语法；启动脚本硬编码 `/Users/joe` 用户名影响外部通用分发。
- 结论与做法：
  ① **代码与公式块原子保真**：将代码围栏（```）与独立公式块（$$）作为整体原子块提取，严禁逐行 strip 与额外插入空行，原始缩进与多行 LaTeX 矩阵 100% 字节级保真。
  ② **O(N) 真正批处理与全篇一次调度**：修正 `translate_sentences` 批处理缩进；在 `MarkdownDocumentTranslator` 引入文档级句子汇聚与批量并行推理，整篇文档仅需 1~2 次 batch 调度，吞吐提升 5~10 倍。
  ③ **转义管道符安全切分与结巴抑制**：表格切分改用 `re.split(r"(?<!\\)\|", line)`；CTranslate2 解码启用 `repetition_penalty=1.15, no_repeat_ngram_size=3` 并配合正则去重与默认表头词表；对纯占位符/无英文字符的行（如纯图片）短路跳过 NMT，彻底消除“零Z”幻觉。
  ④ **平衡括号匹配与安全保护**：URL 匹配支持嵌套与空括号；中文标点规整加入 `!(?!\[)` 负向前瞻保护图片语法；启动脚本消除硬编码路径，改用自适应环境嗅探。
  ⑤ **全量验证**：全套 65/65 单测全绿（新增 6 项深度测试），真实核工程双页学术 PDF 端到端识别与离线翻译（耗时仅 1.1s，无幻觉，成果物完备）。
- 踩坑点：
  1. 结构化 Markdown 翻译千万不能以「行」为单位收集拼接后全量 `strip()`，代码块必须原子包裹。
  2. NMT 批处理的循环层级必须与输入数组严格解耦，外层切 chunk，绝不能写在元素枚举循环内。
  3. MarianMT 对无句式上下文的短表头有天然的 n-gram 重复发散倾向，必须通过 decoder repetition penalty + post-process repeat reduction 双重夹紧。
  4. 纯技术符号/占位符行绝不可直接喂给翻译模型，必须前置检查是否有实际字母需要翻译，否则模型会强行脑补翻译占位符数字。
- 适用场景：科技文献中英本地离线翻译、技术 Markdown 语法保护、CTranslate2 嵌入式推理流水线。

## 2026-10-24 · 内置轻量离线翻译引擎（方案二）、NMT 结构占位符与位置编码超限防御（P052-LiteParse-PDF自动识别）
- 场景：用户需面向 8GB/16GB 普通办公机摆脱 Ollama 等外部守护进程，将离线科技文献翻译引擎内置到项目中，将 PDF 识别产出的 Markdown 自动翻译为高质量中文 Markdown 与单文件 HTML。实施中遇到三大坑点：
  ① 占位符隔离被 NMT 语法重写与 Python 3.12 `re.sub` 反斜杠转义报错：若使用常见占位符格式如 `__PH_0__`、`<<0>>`、`[[0]]`、`<0>`，神经网络翻译模型极易将下划线、尖括号、中括号错乱为 `_PH_0`、`<1]`、甚至触发循环重复输出异常；若在占位符还原时使用 `re.sub(pattern, f" {val} ", translated)`，当 `val` 中含有 LaTeX 反斜杠（如 `\le`、`\nabla`、`\text`）时，Python 3.12 的 `re.sub` 会将 `\l` 等作为模板转义报错 `re.error: bad escape \l`；且若在还原占位符之后才执行中文标点规整，会将 `![alt](url)` 前的感叹号误转为全角 `！` 破坏 Markdown 语法；
  ② NMT 模型位置编码上限 (512 tokens) 与超长无标点段落/目录切分：文献 PDF 经识别后常出现长达数千字符的无标点目录行（如 `List of Abbreviations ... 10 1 Introduction ...`）或连续长句，若仅按句号 `[.!?]` 断句，送入 CTranslate2 时单句 tokens 达 541，触发底层 C++ 报错 `RuntimeError: No position encodings are defined for positions >= 512, but got position 541` 导致崩溃；
  ③ 中英文混排下的正则单词边界（`\b`）失效：在术语强制替换（如 `shall` -> `应`）时，使用 `\bshall\b` 匹配中文环境中的词汇（如 `本设备shall安装`），因 Python 正则中汉字属于 `\w` 字符类，汉字与英文之间不存在 `\b` 边界，导致替换完全静默失效。
- 结论与做法：
  ① **安全占位符三阶隔离闭环**：采用全字母数字大写隔离标记（如 `XPH0X`, `XPH1X`），实测 MarianMT/CTranslate2 对其 100% 原样保留且不引入括号错配；占位符还原的 `re.sub` 中 replacement 必须使用可调用对象 `lambda m, v=val: f" {v} "`，彻底免疫反斜杠转义解析；执行顺序严格保持：占位符隔离 -> 批处理推理 -> 中文标点规整 -> 术语替换 -> 占位符还原，确保还原出的代码、公式与图片 Markdown 绝不受标点转换波及。
  ② **超长段二级拆分与硬截断双重守卫**：实现 `chunk_long_text`，对词数 > 50 的句子按冒号、分号、逗号以及连续省略号（`\.{2,}`）次级切分，超长段强制均分；并在分词后增加硬截断守卫：`toks = toks[:480] + ['</s>']`，双重锁死单句位置上限，杜绝任何超长文本导致的异常退出。
  ③ **中英混合边界正则**：使用兼容中英混排的边界模式：`rf"(?i)(?:\b|(?<=[\u4e00-\u9fa5])){re.escape(term)}(?:\b|(?=[\u4e00-\u9fa5]))"`，精准替换术语。
  ④ **免装内置与原子交付**：内置 CTranslate2 INT8 模型于 `assets/models/translation/`（<200MB 内存，>100 句/秒，零外部守护进程）；提供双击启动 `翻译已识别文献.command` 与命令行入口；`watcher.py` 联动自动发布；中间文件经 `.partial` 暂存与原子替换；全套 59/59 单测通过。
- 踩坑点：
  1. 保护技术符号（代码/公式/图片）送入 MT 模型时，切忌使用含下划线或各种括号的占位符（极易被 NMT mangling）；必须用全大写字母数字复合标记如 `XPH0X`。
  2. Python `re.sub` 的替换串如果包含不可控字符串（如用户输入的 LaTeX 公式含 `\`），绝不能直接传字符串，必须传 `lambda m: s`，否则必报 `bad escape`。
  3. 还原占位符必须放在中文标点全角转换之后，否则图片语法 `![alt]` 的 `!` 会被相邻中文转为全角 `！` 致使 Markdown 失效。
  4. Transformer 翻译模型几乎均有固定的最大位置编码（如 512），真实 PDF 极易产生长达数千字的无标点目录或表格行，必须在断句时做长度钳制与分词硬截断。
  5. Python 正则中汉字属于 `\w`，汉字紧挨字母时 `\b` 无法匹配，术语词边界匹配必须补上汉字后顾/前瞻断言。
- 适用场景：科技文献中英本地离线翻译、技术 Markdown 语法保护、CTranslate2 嵌入式推理流水线。

## 2026-10-23 · 多子进程管道 select 多路复用规避阻塞、僵尸进程回收与特殊字符文件名清理修复（P052-LiteParse-PDF自动识别）
- 场景：代码审查与深度排查发现四大隐患：
  ① `scan_html_renderer.py` 中并发启动多 PaddleOCR worker 时，主线程按 worker 顺序在 `for` 循环中串行读取管道输出。若后续 worker 输出超过 OS 管道缓冲区（macOS 64KB），worker 进程将永久阻塞在 stdout/stderr 写操作上，引发死锁；
  ② 子进程超时或异常被 `proc.kill()` 强杀后，若未调用 `proc.wait()` 回收，将在 Unix/macOS 内核进程表中沦为 `<defunct>` 僵尸进程；且管道流未显式关闭会泄露文件描述符；
  ③ `_read_worker_streams` 在流未读尽且发生非超时异常（如 select 中断或 EBADF）时，原本因 `timed_out` 为 False 而错误地将截断的不完整缓冲区当作成功返回；
  ④ `watcher.py` 清理失败任务的 `.partial` 临时文件时使用 `glob(".%s.*.partial" % source.stem)`，若文件名含 `[`、`]` 等 glob 元字符（如 `report[2026].pdf`），`glob` 将其误判为字符集，无法匹配清理；`assemble.py` 存在绝对路径硬编码。
- 结论与做法：
  ① **全双工 select 多路复用与错误隔离**：实现 `_read_worker_streams`，主线程用 `select.select` 同时监听所有活动 worker 的 stdout/stderr 文件描述符并以 `os.read(fd, 65536)` 及时排空缓冲区，彻底支持大 stderr 与大 stdout 混合并发；严格以 `proc_pending_fds` 是否排空判定完成状态，未读尽管道无论是否超时一律抛出 `TimeoutError` 或 `RuntimeError`，绝不静默返回半截数据。
  ② **僵尸进程与句柄安全回收**：引入 `_terminate_proc`，在强杀后显式调用 `proc.wait(timeout=5)` 并安全 close 全部流，彻底杜绝后台常驻服务中的 `<defunct>` 僵尸累积与管道句柄泄漏。
  ③ **异常捕获闭环**：`_run_paddle_ocr` 捕获异常拓宽至 `(TimeoutError, subprocess.TimeoutExpired, OSError, RuntimeError)`，确保 worker 管道级异常被按分块安全兜底隔离，不会穿透崩溃整篇文档。
  ④ **字面量前缀后缀匹配替代 glob**：清理 `.partial` 临时文件时改用 `iterdir()` 遍历并以 `name.startswith(f".{source.stem}.") and name.endswith(".partial")` 匹配，杜绝 glob/正则特殊字符解析歧义，且单测验证不误删其他任务临时文件。
  ⑤ **路径动态化与全量验证**：`assemble.py` 改用 `Path(__file__).resolve().parents[2]` 动态获取根目录；新增 128KB stdout/stderr 防死锁、僵尸进程回收、异常中断拦截与方括号文件名单测（39/39 单测全绿）；真实 3 页通知 PDF 端到端闭环验证通过。
- 踩坑点：
  1. 并发启动多个产生大文本输出的子进程时，不可按进程列表串行 `read()` 其管道，必须通过 `select/poll` 全局多路复用或即时异步排空，否则极易踩中 OS pipe buffer (64KB) 写死锁。
  2. Unix 下向子进程发 `SIGKILL`（`proc.kill()`）后，若父进程不执行 `wait()`/`waitpid()`，子进程必定残留为 `<defunct>` 僵尸进程；常驻守护进程必须始终配对 wait 回收。
  3. 多路复用流收集不能靠布尔标记简单推断成功，必须以流自身是否达到 EOF 为准，避免任何原因中断时返回残缺数据。
  4. 匹配以不可信输入（如用户投递文件名）作为模式的路径时，切忌直接拼接传给 `Path.glob()`，应使用字面量比较（`startswith`/`endswith`）或 `glob.escape()`。
- 适用场景：Python 多进程并行流水线管道通信、守护进程子进程生命周期管理、文件监控临时目录安全清理。

## 2026-09-14 · 85 页标准 PDF 全册中文精译 + 精美排版 HTML 的分块并行流水线（P052-LiteParse-PDF自动识别）
- 场景：用户要求把 outbox 中识别出的 ASME QME-1-2025 全册（3287 行 / 530 KB 文本）精准翻译并做成精美排版的单文件 HTML。
- 结论与做法：
  ① **规范前置**：先写统一术语表（GLOSSARY.md，约 200 条强制译法，含 shall=应/should=宜/may=可 与 OCR 修复约定）和 HTML 片段规范（HTML-SPEC.md，规定 section/h3/p.clause/表格/表单/公式/译注的 class 与 id 命名），再分块，保证 19 个并行代理产出风格一致。
  ② **分块与边界**：按篇/节切 19 块，每块给「源文件行号范围 + 产出路径 + 自检要求（条款号源/产出对比、无 markdown 残留、无未转义 <）」，提示词内预先列出该块已知 OCR 特征与处理方式。
  ③ **确定性拼装**：Python 脚本（assemble.py）按编号拼接 skeleton-head + parts + skeleton-tail，自动做全局一致性替换（如 压力泄放阀→泄压阀、抗震报告→抗震鉴定报告）、从 h2/h3 自动生成侧边目录（94 锚点）、标签开闭计数校验、临时文件 + 原子替换进 outbox。
  ④ **渲染验证**：file:// 无法被浏览器扩展打开，临时起 `python3 -m http.server 8777`（本地回环，用完即杀），实测封面、正文、矩阵表、引用标准表渲染并截图核对。
  ⑤ **HTML → A4 PDF 导出**：HTML 内补 `@media print`（`@page{size:A4;margin:…}`、颜色 `print-color-adjust:exact`、`break-before/page` 分页、隐藏导航、追加「打印版目录页」），用 Playwright `page.pdf(format='A4', print_background=True, prefer_css_page_size=True)` 离线导出 169 页 A4 PDF；无头 Chrome CLI 的 `--print-to-pdf` 也可用但会忽略 A4 页型且进程偶发不退（需自行清理）。
- 踩坑点：
  1. **跨块 section 开闭**：两个分块共用一个 `<section>`（QR-3、QDR-2、QV-2 三处）时，必须在提示词中显式规定「谁开、谁不收、谁补闭」，否则代理各自"标签平衡"却留下未闭合 section；拼装脚本必须做开/闭计数复核（本次靠脚本发现并修复 1 处）。
  2. 分块代理自检报告不可全信——必须主控统一复核（本次另发现并修正 1 处未闭合 section）。
  3. 含点号的 id（如 `tbl-qv-2.5.3-1`）作为锚点 href 正常，但浏览器 `querySelector` 会报无效选择器；校验脚本用 `getElementById`。
  4. OCR 版表格/公式必须先回看上下文再重建（引用标准表被拆成 4 段乱序列表、EES/阿伦尼乌斯/端部载荷公式为碎片），重建处逐条加「译注」标注依据，绝不编造。
  5. 分块自检正则要覆盖 `QDR-`（Q + 两字母）等编号形态，只写 `Q[DRPV]-` 会漏计一半条款。
- 适用场景：长篇标准/文献/手册的逐页精译、多代理并行内容生产、扫描件 OCR 结果的版面重排与校验。

## 2026-09-14 · Python 虚拟环境解释器路径调用 resolve() 导致 PaddleOCR 等依赖丢失与后台监控启动崩溃（P052-LiteParse-PDF自动识别）
- 场景：用户反馈投递 PDF 无法自动识别。检查发现后台监控未运行；手动启动时报健康检查失败：`PaddleOCR 环境不可用（无法导入 paddleocr）：ModuleNotFoundError: No module named 'paddleocr'`，导致监控进程启动后立即退出。
- 结论与做法：
  ① **虚拟环境 Symlink 解析陷阱**：在 `Config.__init__` 中对配置的 `paddleocr_python` 执行了 `str(Path(paddleocr_python).expanduser().resolve())`。在 Python venv 体系中，虚拟环境的 `bin/python` 是指向底层 base python 解释器的符号链接，Python 解释器启动时通过 `argv[0]` 探查同级或父级目录下的 `pyvenv.cfg` 以激活 venv 并加载 `site-packages`。使用 `.resolve()`（或 `os.path.realpath`）会将路径解析为真实的 base python 解释器（如 `/Users/joe/.local/share/agent-tools/bin/python3.12`），脱离了虚拟环境上下文，使得 venv 内安装的第三方库（如 `paddleocr`）全部无法被 import。
  ② **规范路径标准化方式**：将 `.resolve()` 替换为 `os.path.abspath(str(Path(paddleocr_python).expanduser()))`，既保留绝对路径规范化与 `~` 展开能力，又不会 dereference 符号链接，确保子进程调用时维持虚拟环境的激活状态。
  ③ **启动脚本错误阻断与留屏**：在 `启动自动识别.command` 中增加退出码判断，启动失败时不再仅仅 sleep 2 秒关闭终端，而是输出错误并暂停（`read -k 1`），避免终端闪退掩盖启动失败原因。
  ④ **补齐防回归单测**：在 `tests/test_paddle_ocr.py` 中新增虚拟环境符号链接解释器路径测试，确保 Config 解析符号链接解释器时绝对不调用 resolve 发生解引用。
  ⑤ **端到端验证闭环**：启动后台监控服务，投递 `inbox/ASME QME-1-2025-E.pdf`（121 页），自动识别与段落合并闭环跑通，耗时 ~1 秒输出 HTML 与 Markdown，原 PDF 正常归档至 `processed/`。
- 踩坑点：
  1. 调用虚拟环境中的 Python 解释器二进制时，切勿对其使用 `Path.resolve()` 或 `os.path.realpath()`，否则会穿透符号链接至系统/底层 Python，导致 `pyvenv.cfg` 丢失而无法加载 venv 库。
  2. macOS `.command` 双击脚本如果启动失败，默认无 pause 会立即关闭窗口，排查时应先用终端运行或在脚本中加入失败等待。
- 适用场景：Python 虚拟环境多解释器编排、跨进程 CLI 子解释器调用、后台监控服务自动化健康检查。

