from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.media import frame_times
from app.security import validate_video_url
from app.store import TaskStore


@pytest.mark.parametrize("url,platform", [
    ("https://www.youtube.com/watch?v=abc", "youtube"),
    ("https://v.douyin.com/abc/", "douyin"),
    ("https://www.bilibili.com/video/BV1234567890", "bilibili"),
    ("https://www.xiaohongshu.com/explore/abc", "xiaohongshu"),
])
def test_supported_urls(url, platform):
    assert validate_video_url(url)[0] == platform


@pytest.mark.parametrize("url", [
    "http://www.youtube.com/watch?v=abc",
    "https://youtube.com.evil.example/video",
    "https://127.0.0.1/video.mp4",
    "https://user:pass@youtube.com/video",
    "https://youtube.com:443/video",
    "https://youtube.com/redirect?url=http://127.0.0.1/",
])
def test_rejected_urls(url):
    with pytest.raises(ValueError):
        validate_video_url(url)


def test_frame_sampling_covers_long_video():
    times = frame_times(7200, max_frames=24, interval=90)
    assert len(times) == 24
    assert times[0] > 0
    assert times[-1] > 7000


@pytest.mark.parametrize("provider,key_name,vision,summary", [
    ("deepseek", "DEEPSEEK_API_KEY", "deepseek-flash", "deepseek-flash"),
    ("qwen", "DASHSCOPE_API_KEY", "qwen3-vl-plus", "qwen-plus"),
    ("kimi", "KIMI_API_KEY", "kimi-k2.6", "kimi-k2.6"),
])
def test_provider_presets(monkeypatch, provider, key_name, vision, summary):
    monkeypatch.setenv("AI_PROVIDER", provider)
    monkeypatch.delenv("ASR_PROVIDER", raising=False)
    monkeypatch.setenv(key_name, "selected-key")
    monkeypatch.setenv("OPENAI_API_KEY", "speech-key")
    settings = Settings.from_env()
    assert settings.api_key == "selected-key"
    assert settings.vision_model == vision
    assert settings.summary_model == summary
    assert settings.asr_provider == ("qwen" if provider == "qwen" else "openai")
    settings.validate_for_run()


def test_qwen_asr_sends_audio_to_chat_completions(tmp_path: Path, monkeypatch):
    from app import provider

    monkeypatch.setenv("AI_PROVIDER", "qwen")
    monkeypatch.delenv("ASR_PROVIDER", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    settings = Settings.from_env()
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio bytes")

    def fake_request(client, url, headers, **kwargs):
        assert url.endswith("/chat/completions")
        assert headers["Authorization"] == "Bearer test-key"
        assert kwargs["json"]["model"] == "qwen3-asr-flash"
        assert kwargs["json"]["messages"][0]["content"][0]["input_audio"]["data"].startswith(
            "data:audio/mpeg;base64,"
        )
        return {"choices": [{"message": {"content": "转写内容"}}]}

    monkeypatch.setattr(provider, "_request", fake_request)
    assert provider.transcribe(audio, settings) == "转写内容"


def test_task_store_recovers_running_tasks(tmp_path: Path):
    store = TaskStore(tmp_path / "tasks.db")
    task = store.create("https://youtu.be/abc", "youtube", "中文", "")
    store.update(task["id"], status="running", stage="转写", progress=60)
    pending = store.recover_pending()
    assert len(pending) == 1
    assert pending[0]["status"] == "queued"
    assert pending[0]["progress"] == 0


def test_api_task_lifecycle(tmp_path: Path, monkeypatch):
    from app import main

    settings = replace(Settings.from_env(), data_dir=tmp_path, api_key="test", transcription_key="test")

    def fake_analyze(url, platform, language, focus, folder, config, progress):
        progress("转写音频", 50)
        return {"title": "测试视频", "report": "语音所述：测试。", "platform": platform}

    monkeypatch.setattr(main, "analyze", fake_analyze)
    with TestClient(main.create_app(settings)) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.post("/api/tasks", json={"url": "https://127.0.0.1/video"}).status_code == 422
        response = client.post("/api/tasks", json={"url": "https://youtu.be/abc"})
        assert response.status_code == 202
        task_id = response.json()["id"]
        import time
        for _ in range(50):
            task = client.get(f"/api/tasks/{task_id}").json()
            if task["status"] == "completed":
                break
            time.sleep(0.02)
        assert task["result"]["report"] == "语音所述：测试。"
        assert client.get("/api/tasks").json()[0]["id"] == task_id


def test_audio_and_visual_pipeline(tmp_path: Path, monkeypatch):
    import subprocess

    from app import pipeline
    from app.media import Media, ffmpeg_exe

    source = tmp_path / "source.mp4"
    subprocess.run([
        ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=size=320x240:rate=5",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000",
        "-t", "2", "-c:v", "mpeg4", "-c:a", "aac", "-y", str(source),
    ], check=True)
    monkeypatch.setattr(pipeline, "download_video", lambda *_: Media(source, "演示", "作者", 2))
    monkeypatch.setattr(pipeline, "transcribe", lambda *_: "原话：数字是 42。")

    calls = []

    def fake_chat(messages, model, settings):
        calls.append(messages)
        if len(calls) == 1:
            return "语音：数字是 42。"
        if len(calls) == 2:
            assert any(part["type"] == "image_url" for part in messages[0]["content"])
            return "画面：显示图表。"
        assert "语音：数字是 42。" in messages[1]["content"]
        assert "画面：显示图表。" in messages[1]["content"]
        return "融合：数字 42 与图表。"

    monkeypatch.setattr(pipeline, "chat", fake_chat)
    settings = replace(Settings.from_env(), api_key="test", transcription_key="test")
    stages = []
    result = pipeline.analyze(
        "https://youtu.be/abc", "youtube", "中文", "数字", tmp_path / "run",
        settings, lambda stage, percent: stages.append((stage, percent)),
    )
    assert result["audio_segments"] == 1
    assert result["frames_analyzed"] == 1
    assert result["report"] == "融合：数字 42 与图表。"
    assert stages[-1] == ("完成", 100)
