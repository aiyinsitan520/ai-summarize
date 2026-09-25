"""Download bounded media and extract timestamped audio and images."""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
import yt_dlp

from .config import Settings


@dataclass(frozen=True)
class Media:
    path: Path
    title: str
    uploader: str
    duration: float


class MediaError(RuntimeError):
    pass


def ffmpeg_exe() -> str:
    """The bundled binary works even when FFmpeg is absent from system PATH."""
    configured = Path(os.getenv("FFMPEG_BIN_DIR", "")) / "ffmpeg"
    if os.getenv("FFMPEG_BIN_DIR") and configured.is_file():
        return str(configured)
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run_ffmpeg(args: list[str], timeout: int = 180) -> None:
    try:
        done = subprocess.run(
            [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaError("FFmpeg 处理失败或超时") from exc
    if done.returncode:
        raise MediaError(f"FFmpeg 处理失败：{done.stderr[-350:]}")


def _has_stream(path: Path, kind: str) -> bool:
    try:
        done = subprocess.run(
            [ffmpeg_exe(), "-hide_banner", "-i", str(path)],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaError("无法读取视频媒体流") from exc
    if "Input #" not in done.stderr:
        raise MediaError("下载文件不是可读取的视频媒体")
    return f" {kind}:" in done.stderr


def download_video(url: str, folder: Path, settings: Settings) -> Media:
    folder.mkdir(parents=True, exist_ok=True)
    size_limit = settings.max_download_mb * 1024 * 1024

    def on_progress(status: dict) -> None:
        if status.get("downloaded_bytes", 0) > size_limit:
            raise MediaError("视频超过最大下载体积")

    options = {
        "format": "best[height<=720]/best",
        "outtmpl": str(folder / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "max_filesize": size_limit,
        "progress_hooks": [on_progress],
        "merge_output_format": "mp4",
        "socket_timeout": 30,
        "retries": 2,
        "fragment_retries": 2,
        "ignoreerrors": False,
    }
    # Separate streams need both system FFmpeg and FFprobe for yt-dlp merging.
    bin_dir = os.getenv("FFMPEG_BIN_DIR", "")
    search_path = bin_dir + os.pathsep + os.environ.get("PATH", "") if bin_dir else None
    full_ffmpeg = shutil.which("ffmpeg", path=search_path) and shutil.which(
        "ffprobe", path=search_path
    )
    if full_ffmpeg:
        options["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        if bin_dir:
            options["ffmpeg_location"] = bin_dir
    node = os.getenv("JS_RUNTIME_NODE") or shutil.which("node")
    if node:
        options["js_runtimes"] = {"node": {"path": node}}
    if settings.cookies_file:
        options["cookiefile"] = str(settings.cookies_file)
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            if not isinstance(info, dict) or info.get("entries"):
                raise MediaError("只支持单个视频，不支持播放列表")
            duration = info.get("duration")
            if (
                isinstance(duration, bool)
                or not isinstance(duration, (float, int))
                or not math.isfinite(duration)
                or duration <= 0
            ):
                raise MediaError("无法确认视频时长，未开始下载")
            if duration > settings.max_video_minutes * 60:
                raise MediaError(f"视频超过 {settings.max_video_minutes} 分钟限制")
            filesize = info.get("filesize") or info.get("filesize_approx")
            if isinstance(filesize, (int, float)) and filesize > size_limit:
                raise MediaError("视频超过最大下载体积")
            ydl.extract_info(url, download=True)
    except MediaError:
        raise
    except yt_dlp.utils.DownloadError as exc:
        raise MediaError("视频下载失败。请检查链接、平台访问权限或 cookies。") from exc
    candidates = [
        file for file in folder.glob("source.*")
        if file.is_file() and file.suffix not in {".part", ".json", ".ytdl"}
    ]
    if len(candidates) != 1:
        raise MediaError("下载未产生可用视频文件")
    media = candidates[0]
    if media.stat().st_size > size_limit:
        raise MediaError("视频超过最大下载体积")
    return Media(
        path=media,
        title=str(info.get("title") or "未命名视频")[:300],
        uploader=str(info.get("uploader") or info.get("channel") or "未知作者")[:200],
        duration=float(duration),
    )


def extract_audio_chunks(media: Media, folder: Path, chunk_seconds: int = 600) -> list[tuple[int, Path]]:
    """Use compact MP3 chunks to stay under common transcription upload limits."""
    if not _has_stream(media.path, "Audio"):
        return []
    folder.mkdir(parents=True, exist_ok=True)
    chunks: list[tuple[int, Path]] = []
    for start in range(0, math.ceil(media.duration), chunk_seconds):
        output = folder / f"audio-{start:06d}.mp3"
        _run_ffmpeg([
            "-ss", str(start), "-i", str(media.path), "-t", str(chunk_seconds),
            "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
            "-b:a", "48k", str(output),
        ], timeout=180)
        if output.is_file() and output.stat().st_size > 0:
            chunks.append((start, output))
    return chunks


def frame_times(duration: float, max_frames: int, interval: int) -> list[float]:
    count = min(max_frames, max(1, math.ceil(duration / interval)))
    return [round((index + 0.5) * duration / count, 2) for index in range(count)]


def extract_frames(media: Media, folder: Path, settings: Settings) -> list[tuple[float, Path]]:
    if not _has_stream(media.path, "Video"):
        return []
    folder.mkdir(parents=True, exist_ok=True)
    frames: list[tuple[float, Path]] = []
    for index, second in enumerate(
        frame_times(media.duration, settings.max_frames, settings.frame_interval_seconds)
    ):
        output = folder / f"frame-{index:03d}.jpg"
        try:
            _run_ffmpeg([
                "-ss", str(second), "-i", str(media.path), "-frames:v", "1",
                "-vf", "scale='min(1024,iw)':-2", "-q:v", "5", str(output),
            ], timeout=90)
        except MediaError:
            continue  # An audio-only source has no frames.
        if output.is_file() and output.stat().st_size > 0:
            frames.append((second, output))
    if not frames:
        raise MediaError("无法从视频中提取画面")
    return frames
