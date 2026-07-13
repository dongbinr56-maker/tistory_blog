from __future__ import annotations

import html
import io
import mimetypes
import re
import urllib.parse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a Korean-capable system font on macOS and GitHub's Ubuntu runner."""
    font_paths = (
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJKkr-Bold.otf",
        "/usr/share/fonts/truetype/noto/NotoSansKR-Bold.otf",
    )
    for path in font_paths:
        if Path(path).is_file():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default(size=size)


def _wrapped_lines(draw: ImageDraw.ImageDraw, title: str, font: ImageFont.ImageFont, width: int) -> list[str]:
    """Wrap Korean and English titles without clipping a long project name."""
    lines: list[str] = []
    current = ""
    for token in re.findall(r"\S+\s*", title.strip()):
        candidate = current + token
        if not current or draw.textlength(candidate, font=font) <= width:
            current = candidate
            continue
        lines.append(current.rstrip())
        current = token.lstrip()
        # A single unbroken token can still be wider than the card. Only then
        # fall back to character wrapping, keeping normal project names intact.
        while draw.textlength(current, font=font) > width:
            split_at = 1
            while split_at < len(current) and draw.textlength(current[:split_at + 1], font=font) <= width:
                split_at += 1
            lines.append(current[:split_at].rstrip())
            current = current[split_at:].lstrip()
    if current:
        lines.append(current.rstrip())
    return lines or ["AI Engineering Daily Brief"]


def _png_card(title: str, eyebrow: str) -> bytes:
    """Render the independent, text-inclusive hero card as a 1200×630 PNG."""
    width, height = 1200, 630
    image = Image.new("RGB", (width, height), "#07142b")
    draw = ImageDraw.Draw(image)
    start, end = (7, 20, 43), (16, 107, 84)
    for y in range(height):
        ratio = y / (height - 1)
        color = tuple(round(start[index] * (1 - ratio) + end[index] * ratio) for index in range(3))
        draw.line((0, y, width, y), fill=color)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.ellipse((820, -140, 1260, 300), fill=(94, 234, 212, 30))
    overlay_draw.ellipse((895, -65, 1185, 225), outline=(153, 246, 228, 70), width=3)
    image = Image.alpha_composite(image.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(image)
    eyebrow_font = _font(28)
    footer_font = _font(22)
    draw.text((80, 108), eyebrow[:48], font=eyebrow_font, fill="#99f6e4", stroke_width=0)

    text_width = 900
    title_font = _font(54)
    lines = _wrapped_lines(draw, title[:110], title_font, text_width)
    for size in (54, 50, 46, 42, 38):
        title_font = _font(size)
        lines = _wrapped_lines(draw, title[:110], title_font, text_width)
        if len(lines) <= 3:
            break
    if len(lines) > 3:
        lines = lines[:3]
        suffix = "…"
        while lines[-1] and draw.textlength(lines[-1] + suffix, font=title_font) > text_width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += suffix
    line_height = int(title_font.size * 1.28)
    title_height = line_height * len(lines)
    title_y = max(185, min(260, 360 - title_height // 2))
    for index, line in enumerate(lines):
        draw.text((80, title_y + index * line_height), line, font=title_font, fill="#f8fafc")
    draw.text((80, 548), "AI Engineering Daily Brief", font=footer_font, fill="#cbd5e1")

    result = io.BytesIO()
    image.convert("RGB").save(result, format="PNG", optimize=True)
    return result.getvalue()


def _public_url(base_url: str, date: str, filename: str) -> str:
    if base_url.strip():
        return f"{base_url.rstrip('/')}/{date}/{filename}"
    return f"assets/{date}/{filename}"


def create_hero_image_asset(root: Path, draft: Draft, asset_base_url: str) -> dict[str, str]:
    """Create only the title card so an existing reviewed draft can be upgraded safely."""
    directory = root / "docs" / "tistory" / "assets" / draft.date
    directory.mkdir(parents=True, exist_ok=True)
    for stale_path in (directory / "hero.svg", directory / "hero.png"):
        if stale_path.is_file():
            stale_path.unlink()
    hero_name = "hero.png"
    (directory / hero_name).write_bytes(_png_card(draft.title, "AI · MODEL · OPEN SOURCE"))
    return {"path": hero_name, "url": _public_url(asset_base_url, draft.date, hero_name), "kind": "generated-hero"}


def create_image_assets(root: Path, draft: Draft, asset_base_url: str) -> dict[str, dict[str, str]]:
    """Save a hero and one visual per verified article for copy-ready HTML."""
    directory = root / "docs" / "tistory" / "assets" / draft.date
    directory.mkdir(parents=True, exist_ok=True)
    # A refresh can switch a remote image between png/jpg/svg fallback.  This
    # directory belongs entirely to the fixed daily draft, so stale variants
    # must go before writing the new canonical set.
    for stale_path in directory.iterdir():
        if stale_path.is_file() and (stale_path.name in {"hero.svg", "hero.png", "thumbnail.png"} or stale_path.name.startswith("issue-")):
            stale_path.unlink()
    images: dict[str, dict[str, str]] = {}
    images["hero"] = create_hero_image_asset(root, draft, asset_base_url)
    for index, source in enumerate(draft.source_items, start=1):
        key = source.id
        fallback_name = f"issue-{index}.svg"
        item: dict[str, str] = {"origin_url": source.image_url, "kind": "source-image"}
        if source.image_url.startswith(("https://", "http://")):
            try:
                raw, content_type = _fetch_bytes(source.image_url, "image/*,*/*", attempts=2, max_bytes=10_000_000)
                if len(raw) > 10_000_000:
                    raise ValueError("image exceeds 10 MB")
                main_type = content_type.split(";")[0].strip().lower()
                url_suffix = Path(urllib.parse.urlparse(source.image_url).path).suffix.lower()
                if not main_type.startswith("image/") and url_suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                    # Hotlink-blocked hosts return an HTML error page with
                    # HTTP 200; saving it as issue-N.jpg published broken files.
                    raise ValueError(f"not an image response: {main_type or 'missing content-type'}")
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
