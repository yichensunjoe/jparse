# 本地轻量离线翻译模型 (assets/models)

本目录内置完全本地离线运行的机器翻译模型与分词词表，用于将 LiteParse 识别生成的英文科技文献 Markdown 自动翻译为高质量中文 Markdown 与单文件 HTML。

## 默认模型：Opus-MT (en-zh, CTranslate2 INT8)
- 框架：CTranslate2 (C++ 极速推理，无后台守护进程，零外部服务)
- 语言方向：English -> 简体中文
- 参数体积：~150MB (INT8 量化)
- 内存占用：< 200MB（在 8GB / 16GB 内存的普通办公机或 Mac 上顺畅无感运行）
- 推理速度：单核 > 100 句/秒，整篇数十页标准/论文约 10~20 秒完成
- 文件清单：
  - `translation/model.bin`: CTranslate2 权值二进制
  - `translation/shared_vocabulary.json`: 共享词表映射
  - `translation/source.spm`: 英文 SentencePiece 分词模型
  - `translation/target.spm`: 中文 SentencePiece 分词模型
  - `translation/config.json`: 模型结构配置

## 离线安全承诺
本引擎所有计算均在本地 CPU / Metal 完成，严禁并将代码层面杜绝向任何公网或云端发送文档内容。
