"""Path and URL helper utilities shared across runtime modules."""

from __future__ import annotations

import re

IMAGE_URL_RE = re.compile(
    r"!\[[^\]]*]\((?P<md>https?://[^)\s]+)\)|(?P<raw>https?://[^\s)]+)",
    re.IGNORECASE,
)


def looks_like_image_url(url: str) -> bool:
    """Return True when a URL likely points to an image resource."""
    lower = url.lower()
    return (
        any(lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"))
        or "githubusercontent.com" in lower
        or "/assets/" in lower
    )


def infer_image_extension(url: str, content_type: str) -> str:
    """Infer a safe file extension from URL suffix or response content type."""
    lower_url = url.lower()
    for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"):
        if lower_url.endswith(ext):
            return ext
    ct = content_type.lower()
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "gif" in ct:
        return ".gif"
    if "webp" in ct:
        return ".webp"
    if "bmp" in ct:
        return ".bmp"
    if "svg" in ct:
        return ".svg"
    return ".png"


def extract_image_urls_from_texts(texts: list[str]) -> list[str]:
    """Extract de-duplicated image URLs from markdown/plain text snippets."""
    urls: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for match in IMAGE_URL_RE.finditer(text):
            candidate = match.group("md") or match.group("raw")
            if not candidate:
                continue
            url = candidate.strip()
            if not looks_like_image_url(url):
                continue
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)
    return urls

