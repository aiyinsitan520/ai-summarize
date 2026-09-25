"""Environment configuration with no implicit credential sharing or logging."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class Settings:
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
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        cookie = os.getenv("COOKIES_FILE", "").strip()
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            base_url=base_url,
            transcription_key=os.getenv("TRANSCRIPTION_API_KEY", "").strip()
            or os.getenv("OPENAI_API_KEY", "").strip(),
            transcription_base_url=os.getenv("TRANSCRIPTION_BASE_URL", "").rstrip("/")
            or base_url,
            transcription_model=os.getenv("TRANSCRIPTION_MODEL", "whisper-1"),
            vision_model=os.getenv("VISION_MODEL", "gpt-4.1-mini"),
            summary_model=os.getenv("SUMMARY_MODEL", "gpt-4.1-mini"),
            data_dir=root,
            max_video_minutes=_positive_int("MAX_VIDEO_MINUTES", 120),
            max_download_mb=_positive_int("MAX_DOWNLOAD_MB", 1024),
            max_frames=_positive_int("MAX_FRAMES", 24),
            frame_interval_seconds=_positive_int("FRAME_INTERVAL_SECONDS", 90),
            max_concurrent_tasks=_positive_int("MAX_CONCURRENT_TASKS", 2),
            cookies_file=Path(cookie).expanduser().resolve() if cookie else None,
        )

    def validate_for_run(self) -> None:
        if not self.api_key or not self.transcription_key:
            raise ValueError("请先在 .env 中配置 OPENAI_API_KEY（或单独配置转写 API 密钥）")
        if self.cookies_file and not self.cookies_file.is_file():
            raise ValueError("COOKIES_FILE 指向的文件不存在")
