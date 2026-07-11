from __future__ import annotations

import html
import mimetypes
import re
import urllib.parse
from pathlib import Path

from .collect import _fetch_bytes
from .models import Draft


def _extension(url: str, content_type: str) -> str:
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    extension = mimetypes.guess_extension(content_type.split(";")[0].strip().lower())
    return extension if extension in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else ".jpg"


def _svg_card(title: str, eyebrow: str) -> str:
    safe_title = html.escape(title[:90])
    safe_eyebrow = html.escape(eyebrow[:48])
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-label="{safe_title}">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#07142b"/><stop offset="0.52" stop-color="#0b4d63"/><stop offset="1" stop-color="#106b54"/></linearGradient></defs>
<rect width="1200" height="630" fill="url(#g)"/><circle cx="1040" cy="115" r="220" fill="#5eead4" fill-opacity=".12"/><circle cx="1040" cy="115" r="145" fill="none" stroke="#99f6e4" stroke-opacity=".28" stroke-width="2"/>
<text x="80" y="132" fill="#99f6e4" font-family="Arial, sans-serif" font-size="28" font-weight="700" letter-spacing="3">{safe_eyebrow}</text>
<foreignObject x="80" y="185" width="900" height="330"><div xmlns="http://www.w3.org/1999/xhtml" style="color:#f8fafc;font:700 54px/1.25 Arial,sans-serif;word-break:keep-all">{safe_title}</div></foreignObject>
<text x="80" y="558" fill="#cbd5e1" font-family="Arial, sans-serif" font-size="22">AI Engineering Daily Brief</text></svg>"""


def _public_url(base_url: str, date: str, filename: str) -> str:
    if base_url.strip():
        return f"{base_url.rstrip('/')}/{date}/{filename}"
    return f"assets/{date}/{filename}"


def create_image_assets(root: Path, draft: Draft, asset_base_url: str) -> dict[str, dict[str, str]]:
    """Save a hero and one visual per verified article for copy-ready HTML."""
    directory = root / "docs" / "tistory" / "assets" / draft.date
    directory.mkdir(parents=True, exist_ok=True)
    # A refresh can switch a remote image between png/jpg/svg fallback.  This
    # directory belongs entirely to the fixed daily draft, so stale variants
    # must go before writing the new canonical set.
    for stale_path in directory.iterdir():
        if stale_path.is_file() and (stale_path.name == "hero.svg" or stale_path.name.startswith("issue-")):
            stale_path.unlink()
    images: dict[str, dict[str, str]] = {}
    hero_name = "hero.svg"
    (directory / hero_name).write_text(_svg_card(draft.title, "AI · MODEL · OPEN SOURCE"), encoding="utf-8")
    images["hero"] = {"path": hero_name, "url": _public_url(asset_base_url, draft.date, hero_name), "kind": "generated-hero"}
    for index, source in enumerate(draft.source_items, start=1):
        key = source.id
        fallback_name = f"issue-{index}.svg"
        item: dict[str, str] = {"origin_url": source.image_url, "kind": "source-image"}
        if source.image_url.startswith(("https://", "http://")):
            try:
                raw, content_type = _fetch_bytes(source.image_url, "image/*,*/*", attempts=2)
                if len(raw) > 10_000_000:
                    raise ValueError("image exceeds 10 MB")
                filename = f"issue-{index}{_extension(source.image_url, content_type)}"
                (directory / filename).write_bytes(raw)
                item.update({"path": filename, "url": _public_url(asset_base_url, draft.date, filename)})
            except Exception:
                item["kind"] = "generated-fallback"
        if "url" not in item:
            (directory / fallback_name).write_text(_svg_card(source.title, source.topic), encoding="utf-8")
            item.update({"path": fallback_name, "url": _public_url(asset_base_url, draft.date, fallback_name)})
        images[key] = item
    return images
