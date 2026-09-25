"""Minimal OpenAI-compatible speech and multimodal chat client."""

from __future__ import annotations

import base64
from pathlib import Path

import httpx

from .config import Settings


class ProviderError(RuntimeError):
    pass


def _request(client: httpx.Client, url: str, headers: dict, **kwargs) -> dict:
    try:
        response = client.post(url, headers=headers, **kwargs)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        raise ProviderError(
            f"模型 API 返回 HTTP {exc.response.status_code}，请检查密钥、模型、余额和接口地址"
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError("模型 API 请求失败或响应不是 JSON") from exc
    if not isinstance(data, dict):
        raise ProviderError("模型 API 返回了无效结果")
    return data


def transcribe(path: Path, settings: Settings) -> str:
    headers = {"Authorization": f"Bearer {settings.transcription_key}"}
    with httpx.Client(timeout=300) as client, path.open("rb") as audio:
        data = _request(
            client,
            settings.transcription_base_url + "/audio/transcriptions",
            headers,
            data={"model": settings.transcription_model, "response_format": "json"},
            files={"file": (path.name, audio, "audio/mpeg")},
        )
    text = data.get("text")
    if not isinstance(text, str):
        raise ProviderError("转写 API 未返回 text 字段")
    return text.strip()


def chat(messages: list[dict], model: str, settings: Settings) -> str:
    headers = {"Authorization": f"Bearer {settings.api_key}"}
    with httpx.Client(timeout=300) as client:
        data = _request(
            client,
            settings.base_url + "/chat/completions",
            headers,
            json={"model": model, "messages": messages},
        )
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("对话 API 未返回可读内容") from exc
    if isinstance(content, list):
        content = "\n".join(
            item.get("text", "") for item in content if isinstance(item, dict)
        )
    if not isinstance(content, str) or not content.strip():
        raise ProviderError("对话 API 返回空内容")
    return content.strip()


def image_part(path: Path) -> dict:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "low"}}
