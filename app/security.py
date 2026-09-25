"""Bound ingestion to known public video platforms."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

PLATFORM_HOSTS = {
    "youtube": ("youtube.com", "youtu.be"),
    "douyin": ("douyin.com", "iesdouyin.com"),
    "tiktok": ("tiktok.com",),
    "bilibili": ("bilibili.com", "b23.tv"),
    "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
}


def validate_video_url(value: str) -> tuple[str, str]:
    """Return a platform and HTTPS URL after exact domain-boundary checks.

    A deliberately narrow host list prevents arbitrary internal URL fetches through
    yt-dlp's generic extractor. Add new platform domains only after review.
    """
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("视频链接无效或过长")
    url = value.strip()
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
        port = parts.port
    except ValueError as exc:
        raise ValueError("视频链接格式无效") from exc
    if parts.scheme != "https" or not host or parts.username or parts.password or port:
        raise ValueError("请使用支持平台的 HTTPS 视频链接，不含端口或用户名")
    if parts.fragment:
        raise ValueError("视频链接不能包含片段标记")
    for platform, domains in PLATFORM_HOSTS.items():
        if any(host == domain or host.endswith("." + domain) for domain in domains):
            if not _video_path(platform, host, parts.path, parts.query):
                raise ValueError("请提供该平台的单个视频页面链接")
            return platform, url
    raise ValueError("目前支持 YouTube、抖音、TikTok、Bilibili 和小红书视频链接")


def _video_path(platform: str, host: str, path: str, query: str) -> bool:
    """Do not hand arbitrary platform pages to yt-dlp's generic extractor."""
    component = r"[A-Za-z0-9_-]+"
    if platform == "youtube":
        if host == "youtu.be":
            return re.fullmatch(rf"/{component}/?", path) is not None
        return (
            path == "/watch" and bool(parse_qs(query).get("v"))
        ) or re.fullmatch(rf"/(shorts|live|embed)/{component}/?", path) is not None
    if platform == "douyin":
        if host == "v.douyin.com":
            return re.fullmatch(rf"/{component}/?", path) is not None
        return re.fullmatch(r"/(video|note)/[0-9]+/?", path) is not None or (
            host.endswith("iesdouyin.com")
            and re.fullmatch(r"/share/video/[0-9]+/?", path) is not None
        )
    if platform == "tiktok":
        if host in {"vm.tiktok.com", "vt.tiktok.com"}:
            return re.fullmatch(rf"/{component}/?", path) is not None
        return re.fullmatch(r"/@[^/]+/video/[0-9]+/?", path) is not None
    if platform == "bilibili":
        if host == "b23.tv":
            return re.fullmatch(rf"/{component}/?", path) is not None
        return re.fullmatch(r"/video/(BV[A-Za-z0-9]{10}|av[0-9]+)/?", path) is not None
    if host == "xhslink.com":
        return re.fullmatch(rf"/{component}/?", path) is not None
    return re.fullmatch(rf"/(explore|discovery/item)/{component}/?", path) is not None
