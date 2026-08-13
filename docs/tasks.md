# P052-LiteParse-PDF自动识别 — 任务清单

## 已完成

- [x] PDF 投递箱、稳定等待和后台进程管理。
- [x] HTML + Markdown 双输出与原子发布。
- [x] 普通文字层、短扫描 OCR、长篇扫描书保真三条路由。
- [x] 安全 HTML 渲染、图片内嵌和 Markdown 相对资源。
- [x] 软换行重排与保守表格坐标修复。
- [x] 成功/失败归档和有上限日志。

## 每次修改后的验证

- [ ] 运行 `python3 -m unittest discover -s tests -v`。
- [ ] 用无敏感信息的小 PDF 做一次完整投递闭环。
- [ ] 检查 HTML 离线显示、Markdown 资源路径与原 PDF 归档。
- [ ] 若改 OCR/扫描路由，至少复验一份对应类型样本。
- [ ] 若改后台管理，验证 start/status/stop 且无孤儿进程。

## 后续候选

- [ ] 增加一键环境自检，明确报告 LiteParse/Poppler/Tesseract 与语言数据状态。
- [ ] 将历史大样本验收拆成小而稳定的回归夹具。
- [ ] 为处理队列和磁盘空间增加可观测性，但保持本地离线边界。
