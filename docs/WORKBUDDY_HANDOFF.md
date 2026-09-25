# OmniVideo Insight · WorkBuddy 交接

更新：2026-09-25。目标仓库：<https://github.com/aiyinsitan520/ai-summarize>（原仓库名为 `-`，仓库 ID 未变）。本文概括了用户在前期对话中确认的目标、已实现功能、真实验证和下一步工作，不含密钥或完整视频内容。

## 用户目标与已确认选择

1. 从 [video-report-agent](https://github.com/imexlovery/video-report-agent) 的“下载视频 → 音频转写 → 报告”思路出发，支持 YouTube、抖音等平台的视频；除了语音，还要总结画面，并做音画证据融合。
2. 用户自己提供模型 API 密钥，在自己的电脑上运行服务并亲自体验。用户是 GitHub 新手，优先提供清晰的本地配置与可见的任务进度。
3. 模型服务商已加入 OpenAI、DeepSeek、千问和 Kimi。用户当前本机组合是 **DeepSeek 用于画面与总结，千问用于语音转写**。配置写在仓库根目录的 `.env`，该文件被 Git 忽略；不要同步或展示其内容。
4. 用户要求今后的代码改动同步到 GitHub。之前的 PR #1 和 PR #2 已合并；继续开发时保持仓库分支、PR 和本机代码一致。

## 已实现的流水线

| 阶段 | 位置 | 当前行为 |
| --- | --- | --- |
| 接口与任务 | `app/main.py`, `app/store.py` | FastAPI 创建/查询任务；SQLite 持久化，进度与错误状态；服务重启后重新排队未完成任务。 |
| URL 与下载 | `app/security.py`, `app/media.py` | 限定支持的平台域名，使用 yt-dlp 下载单个公开视频，并限制时长和体积。需要时以 FFmpeg/FFprobe 合并音画流。 |
| 音频 | `app/media.py`, `app/provider.py` | FFmpeg 转 16 kHz/48 kbps 单声道 MP3。OpenAI 使用 `/audio/transcriptions`，每段约 10 分钟；千问使用 Chat Completions 的 `input_audio` Data URI，每段约 4 分钟。 |
| 视觉与总结 | `app/pipeline.py`, `app/provider.py` | 均匀抽帧，每批 4 张调用视觉模型；音频分段整理；最终生成标记“语音所述 / 画面可见 / 综合归纳”的报告，提示冲突与待核验点。 |
| 网页 | `app/static/` | 输入视频链接、查看进度、历史和报告；可展开语音转写、下载报告与转写。页面不接收或显示 API 密钥。 |
| 配置 | `app/config.py`, `.env.example` | `AI_PROVIDER` 选画面与总结服务；`ASR_PROVIDER` 选语音转写服务；各服务商密钥、地址和模型名独立配置。 |

默认模型配置和具体变量以 `app/config.py`、`.env.example` 为准。DeepSeek 官方将 V4.1 Flash 暴露为 `deepseek-flash`，当前[模型列表](https://api-docs.deepseek.com/api/list-models/)的输入类型为 `text`、`image`，没有 `audio`；因此同一把 DeepSeek 密钥无法完成语音转写。千问转写请求格式见[阿里云官方 ASR 文档](https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference)。模型名和服务可用性会变化，升级前重新核对官方文档。

## 本机启动与配置

按 README 的依赖和启动步骤操作。常见配置组合：

```dotenv
AI_PROVIDER=deepseek
ASR_PROVIDER=qwen
DEEPSEEK_API_KEY=请在本机填写
DASHSCOPE_API_KEY=请在本机填写
```

上面的占位符是文档示例，不可直接用于运行；不要把真实值写进提交。修改 `.env` 后需要重启 Uvicorn，`GET /api/health` 只返回服务商名称与“是否已配置”的布尔值，不返回密钥。健康检查不能代替真实 API 验证。页面地址是 <http://127.0.0.1:8000/>，API 文档是 <http://127.0.0.1:8000/docs>。

Bilibili 等平台若提供分离的视频/音频流，需要 `ffmpeg` 与 `ffprobe` 同时可用。完整 YouTube 提取还需要 Node.js 20+。这些依赖通过 `PATH`、`FFMPEG_BIN_DIR`、`JS_RUNTIME_NODE` 配置；不要把某台电脑上的绝对路径写进仓库配置。

## 真实验证记录

2026-09-25 使用用户指定的公开 Bilibili 视频 <https://www.bilibili.com/video/BV1WD4y1r7FA?t=1.5> 做过一次端到端运行：

- 视频标题：`【高数】数列极限性质与证明|学渣救星！（知识篇）`；时长 1316.408 秒（约 22 分钟）。
- 使用千问 `qwen3-asr-flash` 转写 6 段音频，6 段都有文本；DeepSeek `deepseek-flash` 分析 15 张抽帧并完成分段整理与最终报告。
- 任务达到 `completed` / 100%，最终报告约 7200 字，包含语音、画面和综合归纳的标记，指出“保号性”里转写与板书的一个可能冲突。没有把完整转写或报告提交到仓库。
- 这是单条视频、单个本机环境的成功记录；尚未证明其他视频、账号区域、平台或服务商组合都成功。

## 已知限制与下一步建议

按优先级推进，并用真实可观察结果验证：

1. **更多平台实测**：分别用合法可访问的 YouTube 和抖音公开视频验证下载、时长识别、音画流合并、转写与报告；记录失败类型。当前只有 Bilibili 全流程实测。
2. **配置体验**：`.env` 编辑时曾把 `AI_PROVIDER` 恢复为 `openai`，造成已填密钥仍无法运行。可增加本机配置向导或更明确的服务商选择流程；严禁把密钥返回给浏览器或写进日志。
3. **报告阅读**：网页现以纯文本显示 Markdown，虽然可下载报告，但数学公式和长文阅读仍可改善。若渲染 Markdown，必须防止模型输出造成 HTML 注入。
4. **成本与恢复**：重启后未完成任务会从头重跑，可能重复计费。改进阶段缓存、幂等性、取消任务和费用上限前，保持这一限制在用户文档中醒目。
5. **结果准确性**：抽帧不覆盖每秒，ASR 可能误听数学符号。建立少量公开、可重复的评估视频，核查数字、公式、时间点和音画冲突提示。
6. **公开部署安全**：当前默认只监听本机；在加入远程访问、网页密钥输入或共享任务前，先设计鉴权、速率限制、密钥存储与用户数据隔离。

## 开发与同步检查

在不使用真实密钥的 CI/本机环境运行：

```bash
ruff check .
pytest -q
python -m compileall -q app
node --check app/static/app.js
git diff --check
```

真实 API 实测会产生费用，应选短视频和明确目的；不要在自动测试中调用付费模型。修改后提交并推送 GitHub，确认 PR 的 CI 状态以及本机代码是否对应远端提交。真实密钥、`data/`、数据库、媒体文件、完整转写与个人测试报告不进入仓库。
