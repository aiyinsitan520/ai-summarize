# OmniVideo Insight

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
# 编辑 .env，至少填写 OPENAI_API_KEY 以及所用 API 支持的模型名称
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000>；API 文档位于 <http://127.0.0.1:8000/docs>。默认模型名适用于 OpenAI API；换用兼容服务时，请设置 `OPENAI_BASE_URL`、`TRANSCRIPTION_MODEL`、`VISION_MODEL` 和 `SUMMARY_MODEL`。语音接口需支持 `POST /audio/transcriptions`，视觉与总结接口需支持 `POST /chat/completions` 和图片输入。转写服务不同于主服务时，可单独设置 `TRANSCRIPTION_BASE_URL` 与 `TRANSCRIPTION_API_KEY`。

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

- 默认最长 120 分钟、下载体积上限 1 GiB、最多 24 帧、音频 10 分钟一段。通过 `.env` 调整。
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
