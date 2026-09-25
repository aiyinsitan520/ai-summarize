# 给后续开发代理的工作说明

先阅读 [交接文档](docs/WORKBUDDY_HANDOFF.md) 与 README.md，再修改代码。

- 产品目标：用户使用自己的 API 密钥，对公开视频进行语音转写、抽帧理解与音画联合总结；报告须区分语音所述、画面可见和模型归纳，并明确抽帧与转写误差。
- 用户希望今后的代码变更同步到 GitHub 仓库。完成修改后运行相关检查，提交并推送改动；遵循当前任务的 PR、合并权限。不要只把代码留在本地。
- `.env`、`data/`、数据库、下载媒体和真实报告属于本机数据。程序可按需读取密钥用于 API 请求，但开发过程不要显示或输出密钥值；不要把真实密钥、用户数据或整段视频转写提交到仓库。
- DeepSeek 的 `deepseek-flash` 是 V4.1 Flash，当前官方 API 输入为文字和图片，不能作为语音转写服务。千问 `qwen3-asr-flash` 在本项目通过 Chat Completions 接收音频 Data URI。不要把兼容的聊天接口误认为兼容 `/audio/transcriptions`。
- 真实端到端验证目前只覆盖一条 Bilibili 视频；YouTube、抖音、TikTok、小红书和 Kimi 服务商预设仍需分别实测。不要把现有单次成功泛化为所有链接都可用。
- 保持本地服务默认只监听 `127.0.0.1`。任何让外部用户访问配置或任务数据的功能都必须先设计鉴权。

常用检查：`ruff check .`、`pytest -q`、`python -m compileall -q app`、`node --check app/static/app.js`。具体环境与已知问题见交接文档。
