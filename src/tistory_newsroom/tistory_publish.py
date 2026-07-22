from __future__ import annotations

import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit


LOCAL_IMAGE_RE = re.compile(
    r"(<img\b[^>]*\bsrc\s*=\s*)([\"'])(?P<src>\./[^\"']+)(\2)",
    re.IGNORECASE,
)
PUBLISH_IMAGE_NAMES = ("cover.png", "body-1.png", "body-2.png")


def prepare_tistory_publish_html(
    input_html: Path,
    asset_dir: Path,
    asset_base_url: str,
    output_html: Path | None = None,
) -> dict[str, object]:
    """Copy three local article images to a hosted asset tree and write paste-ready HTML."""
    input_html = input_html.resolve()
    if not input_html.is_file():
        raise ValueError(f"HTML 파일을 찾을 수 없습니다: {input_html}")

    parsed_base = urlsplit(asset_base_url)
    if parsed_base.scheme != "https" or not parsed_base.netloc or parsed_base.query or parsed_base.fragment:
        raise ValueError("asset_base_url은 쿼리나 fragment가 없는 HTTPS 주소여야 합니다.")

    source_dir = input_html.parent
    html = input_html.read_text(encoding="utf-8")
    matches = list(LOCAL_IMAGE_RE.finditer(html))
    if len(matches) != 3:
        raise ValueError(f"로컬 이미지가 정확히 3개여야 합니다. 현재: {len(matches)}개")

    asset_dir = asset_dir.resolve()
    asset_dir.mkdir(parents=True, exist_ok=True)
    hosted_urls: list[str] = []

    for match, publish_name in zip(matches, PUBLISH_IMAGE_NAMES, strict=True):
        relative_path = match.group("src")[2:].replace("/", str(Path("/").anchor or "/"))
        source_image = (source_dir / relative_path).resolve()
        if not source_image.is_relative_to(source_dir) or not source_image.is_file():
            raise ValueError(f"HTML과 같은 폴더의 이미지를 찾을 수 없습니다: {match.group('src')}")
        if source_image.suffix.lower() != ".png":
            raise ValueError(f"최종 이미지 형식은 PNG여야 합니다: {source_image.name}")

        target_image = asset_dir / publish_name
        shutil.copy2(source_image, target_image)
        hosted_urls.append(f"{asset_base_url.rstrip('/')}/{publish_name}")

    index = 0

    def replace_src(match: re.Match[str]) -> str:
        nonlocal index
        url = hosted_urls[index]
        index += 1
        return f"{match.group(1)}{match.group(2)}{url}{match.group(4)}"

    publish_html = LOCAL_IMAGE_RE.sub(replace_src, html)
    if LOCAL_IMAGE_RE.search(publish_html):
        raise ValueError("발행본에 로컬 이미지 경로가 남았습니다.")

    output_html = (output_html or input_html.with_name(f"{input_html.stem}-tistory-paste.html")).resolve()
    if output_html == input_html:
        raise ValueError("로컬 미리보기 원본과 발행본은 다른 파일이어야 합니다.")
    output_html.write_text(publish_html, encoding="utf-8")

    return {
        "local_preview_html": str(input_html),
        "tistory_paste_html": str(output_html),
        "asset_dir": str(asset_dir),
        "image_urls": hosted_urls,
    }
