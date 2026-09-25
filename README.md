# OmniVideo Insight

> 后续开发者（包括 WorkBuddy）：先阅读 [项目交接文档](docs/WORKBUDDY_HANDOFF.md) 和 [AGENTS.md](AGENTS.md)。

用自己的 OpenAI 兼容 API 为 YouTube、抖音、TikTok、Bilibili 和小红书的**单个视频**生成音画联合总结。服务下载公开视频，把音频分段转写、均匀抽取画面，再分别整理证据并生成 Markdown 报告。任务和结果保存在 SQLite；临时媒体处理结束后删除。

## 原理与参考项目的关系

[video-report-agent](https://github.com/imexlovery/video-report-agent) 的核心流程是视频获取 → FFmpeg 提取媒体 → ASR → 组织报告。它的开源流水线主要面向 Bilibili，报告由 Coding Agent 和 Skill 根据转写生成。本项目沿用流水线思路，扩展了平台入口，直接调用你配置的 API，并增加了关键帧视觉理解与音画证据融合。没有逐帧看完整视频：报告中的画面结论只来自抽样帧，时间戳是片段或抽帧位置。需要登录、地区访问或反爬校验的视频可能需要 cookies，也可能无法获取。

```text
支持平台的视频链接
   │
   ├─ yt-dlp 获取视频和元数据 ── FFmpeg 均匀抽帧 ── 视觉模型 ─┐
   └─ FFmpeg 分段压缩音频 ── 转写 API ── 分段摘要 ──────────┤
                                                       └─ 融合报告
```

## 本地运行

需要 Python 3.11+。项目依赖 `imageio-ffmpeg` 自带 FFmpeg 用于音画提取；**Bilibili 等只提供分离音视频流的平台还需要 `ffmpeg` 和 `ffprobe` 同时可用**，才能合并下载。把它们加入 `PATH`，或设置 `FFMPEG_BIN_DIR` 为二者所在目录。完整 YouTube 支持还需要 Node.js 20+（或设置 `JS_RUNTIME_NODE` 指向其可执行文件）；`yt-dlp[default]` 会安装所需的 JS 组件。YouTube 的提取规则可能随平台变化，建议保持 `yt-dlp` 更新；某些站点需要浏览器 cookies。[依赖说明](https://github.com/yt-dlp/yt-dlp#dependencies)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
# 编辑 .env，选择服务商并填写对应密钥
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000>；API 文档位于 <http://127.0.0.1:8000/docs>。在 `.env` 中设置 `AI_PROVIDER` 为 `openai`、`deepseek`、`qwen` 或 `kimi`，并填写对应的 `OPENAI_API_KEY`、`DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY` 或 `KIMI_API_KEY`。页面会显示画面与总结、语音转写各自的配置状态。更换 `.env` 后需重启服务。

报告完成后可在页面展开语音转写，并分别下载 Markdown 报告和纯文本转写。任务结果也保存在本机 SQLite 数据库中。

语音转写单独由 `ASR_PROVIDER` 控制，只支持 `openai` 或 `qwen`。选择千问作为主服务商时，默认也用千问转写，只需一把百炼密钥；选择 DeepSeek 或 Kimi 时，另配 OpenAI 密钥用于转写，或设置 `ASR_PROVIDER=qwen` 并填写百炼密钥。千问使用 `qwen3-asr-flash` 的 Chat Completions 音频输入，音频会切成约 4 分钟一段；OpenAI 使用 `/audio/transcriptions`，约 10 分钟一段。可在 `.env.example` 查看接口地址和模型覆盖项。

示例：只用千问：

```dotenv
AI_PROVIDER=qwen
DASHSCOPE_API_KEY=你的百炼密钥
```

示例：DeepSeek 负责画面与总结，千问负责转写：

```dotenv
AI_PROVIDER=deepseek
ASR_PROVIDER=qwen
DEEPSEEK_API_KEY=你的DeepSeek密钥
DASHSCOPE_API_KEY=你的百炼密钥
```

`.env` 已加入 Git 忽略。不要把 API 密钥写在网页里。运行中会把音频与抽帧发送至配置的服务商；数据库仍会保存转写文本和最终报告。默认只监听本机地址；若要开放公网，需要自行配置鉴权、HTTPS 和访问限流。

### API 示例

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s -X POST http://127.0.0.1:8000/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=VIDEO_ID","language":"中文","focus":"关键观点与证据"}'
curl -s http://127.0.0.1:8000/api/tasks/TASK_ID
curl -s http://127.0.0.1:8000/api/tasks
```

任务状态为 `queued`、`running`、`completed` 或 `failed`。服务重启后，未完成任务自动重新排队并从头处理，因此中途已发出的 API 请求可能再次计费。

## Docker

```bash
cp .env.example .env
# 填写密钥
docker compose up --build
```

镜像包含 Node.js、FFmpeg 和 FFprobe。Compose 只将端口映射到 `127.0.0.1:8000`，使用 Docker 命名卷保存任务数据库。若需要 cookies，请在宿主机准备 Netscape 格式文件，挂载到容器并将 `COOKIES_FILE` 指向容器内路径。

## 限制与费用

- 默认最长 120 分钟、下载体积上限 1 GiB、最多 24 帧；OpenAI 音频约 10 分钟一段、千问音频约 4 分钟一段。通过 `.env` 调整其他限制。
- 抽帧可能遗漏快速变化的场景；音频片段起始时间不能当作逐句时间戳。
- 平台下载能力取决于公开访问、地区、登录状态和 `yt-dlp` 版本；对抖音等平台不保证每条链接都可用。
- 处理费用由你选择的 API 服务商收取，长视频会产生多次转写和视觉请求。
- 目前限制入口到列出的平台域名，避免任意内网地址被当作下载链接。要增加平台，请先审查新域名和其重定向行为。

## 开发验证

```bash
ruff check .
pytest -q
python -m compileall -q app
node --check app/static/app.js
```
