"""Environment configuration with no implicit credential sharing or logging."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROVIDERS = {
    "openai": ("OpenAI", "https://api.openai.com/v1", "gpt-4.1-mini", "gpt-4.1-mini", "OPENAI_API_KEY"),
    "deepseek": ("DeepSeek", "https://api.deepseek.com", "deepseek-flash", "deepseek-flash", "DEEPSEEK_API_KEY"),
    "qwen": ("千问（阿里云百炼）", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3-vl-plus", "qwen-plus", "DASHSCOPE_API_KEY"),
    "kimi": ("Kimi（月之暗面）", "https://api.moonshot.cn/v1", "kimi-k2.6", "kimi-k2.6", "KIMI_API_KEY"),
}
ASR_PROVIDERS = {"openai", "qwen"}


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class Settings:
    ai_provider: str
    asr_provider: str
    api_key: str
    base_url: str
    transcription_key: str
    transcription_base_url: str
    transcription_model: str
    vision_model: str
    summary_model: str
    data_dir: Path
    max_video_minutes: int
    max_download_mb: int
    max_frames: int
    frame_interval_seconds: int
    max_concurrent_tasks: int
    cookies_file: Path | None

    @classmethod
    def from_env(cls) -> Settings:
        root = Path(os.getenv("DATA_DIR", "./data")).expanduser().resolve()
        ai_provider = os.getenv("AI_PROVIDER", "openai").strip().lower()
        if ai_provider not in PROVIDERS:
            raise ValueError(f"AI_PROVIDER 不支持 {ai_provider}；可选 openai、deepseek、qwen、kimi")
        asr_provider = os.getenv("ASR_PROVIDER", "qwen" if ai_provider == "qwen" else "openai").strip().lower()
        if asr_provider not in ASR_PROVIDERS:
            raise ValueError("ASR_PROVIDER 只支持 openai 或 qwen")
        _, default_url, vision_model, summary_model, key_name = PROVIDERS[ai_provider]
        base_url = os.getenv(f"{ai_provider.upper()}_BASE_URL", default_url).rstrip("/")
        asr_url = (
            os.getenv("TRANSCRIPTION_BASE_URL", "").rstrip("/") or
            (base_url if asr_provider == ai_provider else os.getenv(
                f"{asr_provider.upper()}_BASE_URL", PROVIDERS[asr_provider][1]
            ).rstrip("/"))
        )
        cookie = os.getenv("COOKIES_FILE", "").strip()
        return cls(
            ai_provider=ai_provider,
            asr_provider=asr_provider,
            api_key=os.getenv(key_name, "").strip(),
            base_url=base_url,
            transcription_key=os.getenv("TRANSCRIPTION_API_KEY", "").strip()
            or os.getenv(PROVIDERS[asr_provider][4], "").strip(),
            transcription_base_url=asr_url,
            transcription_model=os.getenv(
                "QWEN_ASR_MODEL" if asr_provider == "qwen" else "TRANSCRIPTION_MODEL",
                "qwen3-asr-flash" if asr_provider == "qwen" else "whisper-1",
            ),
            vision_model=os.getenv(
                "VISION_MODEL" if ai_provider == "openai" else f"{ai_provider.upper()}_VISION_MODEL", vision_model
            ),
            summary_model=os.getenv(
                "SUMMARY_MODEL" if ai_provider == "openai" else f"{ai_provider.upper()}_SUMMARY_MODEL", summary_model
            ),
            data_dir=root,
            max_video_minutes=_positive_int("MAX_VIDEO_MINUTES", 120),
            max_download_mb=_positive_int("MAX_DOWNLOAD_MB", 1024),
            max_frames=_positive_int("MAX_FRAMES", 24),
            frame_interval_seconds=_positive_int("FRAME_INTERVAL_SECONDS", 90),
            max_concurrent_tasks=_positive_int("MAX_CONCURRENT_TASKS", 2),
            cookies_file=Path(cookie).expanduser().resolve() if cookie else None,
        )

    def validate_for_run(self) -> None:
        if not self.api_key:
            raise ValueError(f"请先在 .env 中配置 {PROVIDERS[self.ai_provider][4]}")
        if not self.transcription_key:
            raise ValueError(f"请先在 .env 中配置 {PROVIDERS[self.asr_provider][4]}（语音转写）")
        if self.cookies_file and not self.cookies_file.is_file():
            raise ValueError("COOKIES_FILE 指向的文件不存在")
