from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any
import urllib.parse

from .assets import create_image_assets
from .collect import choose_diverse, collect_candidates, collection_payload
from .config import ROOT, load_site_config, load_sources_config
from .generate import generate_demo, generate_with_gemini
from .models import SourceItem
from .quality import inspect_draft
from .render import write_outputs


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _day_or_today(value: str | None) -> str:
    if value:
        return dt.date.fromisoformat(value).isoformat()
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()


def _url_key(value: object) -> str:
    """Normalize a URL in the same way as collected source canonical keys."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw.rstrip("/").lower()
    clean = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        query="",
        fragment="",
    )
    return urllib.parse.urlunparse(clean).rstrip("/").lower()


def historical_url_keys(root: Path, day: str) -> set[str]:
    """Read selected records from older daily runs without trusting raw listings.

    Only selected articles count as published coverage.  This avoids starving the
    selection pool because a candidate was merely collected and then rejected.
    """
    runs_root = root / "data" / "runs"
    if not runs_root.exists():
        return set()
    keys: set[str] = set()
    for collection_path in sorted(runs_root.glob("*/collection.json")):
        if collection_path.parent.name == day:
            continue
        try:
            payload = json.loads(collection_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        selected = payload.get("selected")
        if not isinstance(selected, list):
            continue
        for item in selected:
            if not isinstance(item, dict):
                continue
            for field in ("canonical_key", "url", "official_url", "listing_url"):
                key = _url_key(item.get(field))
                if key:
                    keys.add(key)
    return keys


def _existing_ready_draft(root: Path, day: str) -> dict[str, Any] | None:
    """Return an existing complete daily draft so a rerun is a true no-op."""
    run_dir = root / "data" / "runs" / day
    draft_path = run_dir / "draft.json"
    report_path = run_dir / "quality-report.json"
    html_path = root / "docs" / "tistory" / f"{day}.html"
    metadata_path = root / "docs" / "tistory" / f"{day}.json"
    required = (draft_path, report_path, html_path, metadata_path)
    if not all(path.is_file() for path in required):
        return None
    try:
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if report.get("status") != "READY_FOR_MANUAL_REVIEW":
        return None
    source_items = draft.get("source_items")
    if not isinstance(source_items, list):
        return None
    warnings = report.get("warnings")
    return {
        "date": day,
        "article_count": len(source_items),
        "status": "READY_FOR_MANUAL_REVIEW",
        "output": str(html_path),
        "warnings": warnings if isinstance(warnings, list) else [],
        "reused_existing_draft": True,
    }


def run(root: Path = ROOT, date: str | None = None, demo: bool = False, refresh: bool = False) -> dict[str, Any]:
    day = _day_or_today(date)
    if not demo and not refresh:
        existing = _existing_ready_draft(root, day)
        if existing:
            return existing
    site = load_site_config(root)
    # A demo must work immediately after cloning. Production requires the
    # actual identity, contact and blog address in config/site.json.
    if demo:
        site = {
            **site,
            "author_name": "데모 작성자",
            "contact_email": "demo@tistory-newsroom.local",
            "blog_url": "https://demo.tistory-newsroom.local",
            "draft_assets_base_url": "",
        }
    sources_config = load_sources_config(root)
    run_dir = root / "data" / "runs" / day
    if demo:
        raw = json.loads((root / "data" / "samples" / "news.json").read_text(encoding="utf-8"))
        selected = [SourceItem.from_dict(item) for item in raw]
        candidates, collector_errors = selected, []
    else:
        candidates, collector_errors = collect_candidates(sources_config)
        selection = sources_config.get("selection", {})
        history_keys = historical_url_keys(root, day)
        selected = choose_diverse(
            candidates,
            int(selection.get("final_article_count", 3)),
            [str(item) for item in selection.get("excluded_title_terms", [])],
            history_keys,
        )
    if demo:
        history_keys = set()
    historical_excluded_candidate_count = sum(
        bool({
            _url_key(value)
            for value in (item.canonical_key, item.url, item.official_url, item.listing_url)
            if value
        } & history_keys)
        for item in candidates
    )
    collection = collection_payload(
        day,
        candidates,
        selected,
        collector_errors,
        historical_url_key_count=len(history_keys),
        historically_excluded_candidate_count=historical_excluded_candidate_count,
    )
    _write_json(run_dir / "collection.json", collection)
    required_sources = int(site.get("required_source_count", 3))
    if len(selected) < required_sources:
        message = f"초안 생성 중단: 요즘IT·GeekNews 기사와 GitHub/Hugging Face 커뮤니티 프로젝트를 합쳐 검증 가능한 {required_sources}건을 만들지 못했습니다."
        _write_json(run_dir / "quality-report.json", {"status": "BLOCKED", "errors": [message], "collector_errors": collector_errors})
        raise RuntimeError(message)
    asset_base_url = str(site.get("draft_assets_base_url", ""))
    if not demo and (not asset_base_url.startswith("https://") or "YOUR_GITHUB_ID" in asset_base_url):
        message = "초안 생성 중단: 티스토리에서 표시할 이미지 주소인 draft_assets_base_url을 config/site.json에 실제 GitHub Pages 주소로 설정하세요."
        _write_json(run_dir / "quality-report.json", {"status": "BLOCKED", "errors": [message], "collector_errors": collector_errors})
        raise RuntimeError(message)
    draft = generate_demo(day, selected, site) if demo else generate_with_gemini(day, selected, site)
    draft.images = create_image_assets(root, draft, asset_base_url)
    _write_json(run_dir / "draft.json", draft.to_dict())
    report = inspect_draft(draft, site)
    _write_json(run_dir / "quality-report.json", report.to_dict())
    if report.status != "READY_FOR_MANUAL_REVIEW":
        raise RuntimeError("초안 품질 게이트가 차단했습니다: " + " / ".join(report.errors))
    write_outputs(root, draft, report, site)
    return {"date": day, "article_count": len(selected), "status": report.status, "output": str(root / "docs" / "tistory" / f"{day}.html"), "warnings": report.warnings, "reused_existing_draft": False}
