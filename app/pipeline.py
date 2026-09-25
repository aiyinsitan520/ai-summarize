"""Audio and frame analysis with a source-grounded combined report."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .config import Settings
from .media import download_video, extract_audio_chunks, extract_frames
from .provider import chat, image_part, transcribe

Progress = Callable[[str, int], None]


def timestamp(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 3600:02d}:{(whole // 60) % 60:02d}:{whole % 60:02d}"


def analyze(
    url: str,
    platform: str,
    language: str,
    focus: str,
    folder: Path,
    settings: Settings,
    progress: Progress,
) -> dict:
    settings.validate_for_run()
    progress("下载视频", 5)
    media = download_video(url, folder, settings)
    progress("提取音频与画面", 20)
    chunk_seconds = 240 if settings.asr_provider == "qwen" else 600
    audio = extract_audio_chunks(media, folder / "audio", chunk_seconds=chunk_seconds)
    frames = extract_frames(media, folder / "frames", settings)
    if not audio and not frames:
        raise ValueError("视频没有可分析的音轨或画面")

    transcripts: list[dict] = []
    audio_notes: list[str] = []
    for index, (second, path) in enumerate(audio):
        progress(f"转写音频 {index + 1}/{len(audio)}", 30 + int(25 * index / len(audio)))
        content = transcribe(path, settings)
        transcripts.append({"start": timestamp(second), "text": content})
        if content:
            note = chat(
                [
                    {"role": "system", "content": (
                        "你是严谨的视频转写整理员。只根据所给转写归纳，不补充外部事实。"
                        "保留关键条件、数字、说话者归属和不确定性；不要把推断写成原话。"
                        "用简明中文要点列出，并标记本段起始时间。"
                    )},
                    {"role": "user", "content": f"起始时间：{timestamp(second)}\n转写：\n{content}"},
                ],
                settings.summary_model,
                settings,
            )
            audio_notes.append(f"[{timestamp(second)} 起，约 {chunk_seconds // 60} 分钟]\n{note}")

    visual_notes: list[str] = []
    for start in range(0, len(frames), 4):
        batch = frames[start:start + 4]
        progress(f"理解画面 {min(start + 4, len(frames))}/{len(frames)}", 55 + int(25 * start / len(frames)))
        parts = [{"type": "text", "text": (
            "按顺序观察下面的时间点画面。只记可见信息、文字、图表和场景变化。"
            "对看不清的文字明确说看不清；不要推断未展示的情节。"
            "这些是稀疏抽帧，不能代表中间所有画面。\n"
            + "\n".join(f"图 {i + 1}: {timestamp(second)}" for i, (second, _) in enumerate(batch))
        )}]
        for _, path in batch:
            parts.append(image_part(path))
        visual_notes.append(chat(
            [{"role": "user", "content": parts}], settings.vision_model, settings
        ))

    progress("融合音画报告", 85)
    source = (
        f"平台：{platform}\n标题：{media.title}\n作者：{media.uploader}\n"
        f"链接：{url}\n时长：{timestamp(media.duration)}\n"
        f"输出语言：{language}\n用户关注点：{focus or '无'}\n\n"
        f"音频整理（片段时间是近似范围，不代表逐句时间戳）：\n"
        + ("\n\n".join(audio_notes) if audio_notes else "无可用语音")
        + "\n\n抽帧画面观察（稀疏采样）：\n"
        + ("\n\n".join(visual_notes) if visual_notes else "无可用画面")
    )
    report = chat(
        [
            {"role": "system", "content": (
                "你是视频音画联合分析员。仅依据用户提供的转写整理和抽帧观察生成 Markdown 报告。"
                "必须分别标明‘语音所述’、‘画面可见’和‘综合归纳’的证据来源。"
                "指出音画冲突及无法核实的说法；没有冲突时无需虚构。"
                "时间戳只能引用已有片段或抽帧时间，不能编造精确逐句时间。"
                "抽帧并不覆盖每一秒，避免断言未采样的画面。"
                "报告包含：核心结论、按主题或时间的详细要点、音画互证/冲突、待核验信息。"
                "如果某一种模态缺失，说明该限制，不要编造其内容。"
            )},
            {"role": "user", "content": source},
        ],
        settings.summary_model,
        settings,
    )
    progress("完成", 100)
    return {
        "title": media.title,
        "uploader": media.uploader,
        "duration_seconds": media.duration,
        "platform": platform,
        "source_url": url,
        "audio_segments": len(audio),
        "frames_analyzed": len(frames),
        "transcript": transcripts,
        "report": report,
    }
