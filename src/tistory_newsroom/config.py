from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SITE = {
    "blog_name": "나의 IT 인사이트",
    "author_name": "작성자",
    "author_bio": "IT와 개발 이슈를 실무 관점에서 해설합니다.",
    "contact_email": "hello@example.com",
    "blog_url": "",
    "draft_assets_base_url": "",
    "default_category": "IT·개발",
    "language": "ko",
    "minimum_body_characters": 1400,
    "required_source_count": 1,
    "required_internal_link_note": "관련 기존 글이 있다면 내부 링크를 1개 이상 넣으세요.",
}


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_site_config(root: Path = ROOT) -> dict[str, Any]:
    configured = root / "config" / "site.json"
    example = root / "config" / "site.example.json"
    value = dict(DEFAULT_SITE)
    if configured.exists():
        value.update(read_json(configured))
    elif example.exists():
        value.update(read_json(example))
    return value


def load_sources_config(root: Path = ROOT) -> dict[str, Any]:
    return read_json(root / "config" / "sources.json")


def load_local_env(root: Path = ROOT) -> None:
    """Load a minimal .env file without adding a runtime dependency.

    Existing environment variables always win, so GitHub Actions secrets are
    never replaced by a local file.
    """
    path = root / ".env"
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name:
            os.environ.setdefault(name, value)
