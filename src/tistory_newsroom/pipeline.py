from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import shutil
from typing import Any
import urllib.parse

from .assets import create_hero_image_asset, create_image_assets, create_thumbnail_image_asset
from .collect import choose_diverse, collect_candidates, collection_payload
from .config import ROOT, load_site_config, load_sources_config
from .generate import generate_demo, generate_with_gemini
from .models import Draft, QualityReport, SourceItem
from .quality import inspect_draft
from .render import build_site, write_outputs


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


def _selected_url_keys(item: dict[str, Any]) -> set[str]:
    return {
        key
        for field in ("canonical_key", "url", "official_url", "listing_url")
        if (key := _url_key(item.get(field)))
    }


def _history_index_path(root: Path) -> Path:
    return root / "data" / "history" / "seen-url-keys.json"


def _scan_history_entries(root: Path) -> dict[str, str]:
    """Build a compact URL index from legacy daily collection records."""
    runs_root = root / "data" / "runs"
    if not runs_root.exists():
        return {}
    entries: dict[str, str] = {}
    for collection_path in sorted(runs_root.glob("*/collection.json")):
        try:
            payload = json.loads(collection_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        selected = payload.get("selected")
        if not isinstance(selected, list):
            continue
        for item in selected:
            if isinstance(item, dict):
                for key in _selected_url_keys(item):
                    entries.setdefault(key, collection_path.parent.name)
    return entries


def _history_entries(root: Path) -> dict[str, str]:
    path = _history_index_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = payload.get("entries")
        if isinstance(entries, dict):
            return {_url_key(key): str(value) for key, value in entries.items() if _url_key(key)}
    except (OSError, json.JSONDecodeError):
        pass
    return _scan_history_entries(root)


def historical_url_keys(root: Path, day: str) -> set[str]:
    """Read selected URLs from a compact index, with a legacy-record fallback.

    Only selected articles count as published coverage.  This avoids starving the
    selection pool because a candidate was merely collected and then rejected.
    """
    return {key for key, first_seen_day in _history_entries(root).items() if first_seen_day != day}


def record_historical_url_keys(root: Path, day: str, selected: list[SourceItem]) -> None:
    """Persist every selected URL identity once so old drafts can be pruned safely."""
    entries = _history_entries(root)
    for source in selected:
        for key in _selected_url_keys(source.to_dict()):
            entries.setdefault(key, day)
    _write_json(_history_index_path(root), {
        "version": 1,
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "entries": dict(sorted(entries.items())),
    })


def _is_expired_daily_path(path: Path, cutoff: dt.date) -> bool:
    try:
        return dt.date.fromisoformat(path.name) < cutoff
    except ValueError:
        return False


def prune_expired_details(root: Path, day: str, retention_days: int) -> list[str]:
    """Keep review artifacts bounded without dropping the permanent URL index."""
    if retention_days <= 0:
        return []
    cutoff = dt.date.fromisoformat(day) - dt.timedelta(days=retention_days)
    removed: list[str] = []
    runs_root = root / "data" / "runs"
    if runs_root.exists():
        for run_dir in runs_root.iterdir():
            if run_dir.is_dir() and _is_expired_daily_path(run_dir, cutoff):
                shutil.rmtree(run_dir)
                removed.append(str(run_dir.relative_to(root)))
    tistory_root = root / "docs" / "tistory"
    if tistory_root.exists():
        for metadata_path in tistory_root.glob("????-??-??.json"):
            try:
                expired = dt.date.fromisoformat(metadata_path.stem) < cutoff
            except ValueError:
                expired = False
            if expired:
                html_path = metadata_path.with_suffix(".html")
                metadata_path.unlink()
                if html_path.exists():
                    html_path.unlink()
                removed.append(str(metadata_path.relative_to(root)))
        assets_root = tistory_root / "assets"
        if assets_root.exists():
            for asset_dir in assets_root.iterdir():
                if asset_dir.is_dir() and _is_expired_daily_path(asset_dir, cutoff):
                    shutil.rmtree(asset_dir)
                    removed.append(str(asset_dir.relative_to(root)))
    return removed


def _existing_ready_draft(root: Path, day: str) -> dict[str, Any] | None:
    """Return an existing complete daily draft so a rerun is a true no-op."""
    run_dir = root / "data" / "runs" / day
    draft_path = run_dir / "draft.json"
    collection_path = run_dir / "collection.json"
    report_path = run_dir / "quality-report.json"
    html_path = root / "docs" / "tistory" / f"{day}.html"
    metadata_path = root / "docs" / "tistory" / f"{day}.json"
    required = (collection_path, draft_path, report_path, html_path, metadata_path)
    if not all(path.is_file() for path in required):
        return None
    try:
        collection = json.loads(collection_path.read_text(encoding="utf-8"))
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if report.get("status") != "READY_FOR_MANUAL_REVIEW":
        return None
    if not isinstance(collection.get("selected"), list):
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


def _quality_report_from_dict(value: dict[str, Any]) -> QualityReport:
    return QualityReport(
        status=str(value.get("status") or "BLOCKED"),
        errors=[str(item) for item in value.get("errors", [])],
        warnings=[str(item) for item in value.get("warnings", [])],
        checks={str(key): bool(item) for key, item in dict(value.get("checks") or {}).items()},
        manual_review_required=bool(value.get("manual_review_required", True)),
    )


def refresh_hero_image(root: Path = ROOT, date: str | None = None) -> dict[str, Any]:
    """Refresh generated visuals of an approved draft without rewriting its article."""
    day = _day_or_today(date)
    run_dir = root / "data" / "runs" / day
    draft_path = run_dir / "draft.json"
    report_path = run_dir / "quality-report.json"
    if not draft_path.is_file() or not report_path.is_file():
        raise RuntimeError(f"{day} 초안의 이미지 갱신에 필요한 검토 기록이 없습니다.")
    try:
        raw_draft = json.loads(draft_path.read_text(encoding="utf-8"))
        raw_report = json.loads(report_path.read_text(encoding="utf-8"))
        source_items = [SourceItem.from_dict(item) for item in raw_draft["source_items"]]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{day} 초안 기록을 읽을 수 없습니다: {error}") from error
    report = _quality_report_from_dict(raw_report)
    if report.status != "READY_FOR_MANUAL_REVIEW":
        raise RuntimeError(f"{day} 초안은 검토 가능 상태가 아니어서 대표 이미지를 갱신하지 않았습니다.")
    draft = Draft.from_dict(raw_draft, source_items)
    site = load_site_config(root)
    asset_base_url = str(site.get("draft_assets_base_url", ""))
    draft.images["hero"] = create_hero_image_asset(root, draft, asset_base_url)
    draft.images["thumbnail"] = create_thumbnail_image_asset(root, draft, asset_base_url)
    _write_json(draft_path, draft.to_dict())
    write_outputs(root, draft, report, site)
    return {
        "date": day,
        "status": report.status,
        "hero": draft.images["hero"],
        "thumbnail": draft.images["thumbnail"],
        "output": str(root / "docs" / "tistory" / f"{day}.html"),
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
    record_historical_url_keys(root, day, selected)
    write_outputs(root, draft, report, site)
    retention_days = int(sources_config.get("selection", {}).get("detail_retention_days", 180))
    pruned_details = prune_expired_details(root, day, retention_days)
    if pruned_details:
        build_site(root, site)
    return {"date": day, "article_count": len(selected), "status": report.status, "output": str(root / "docs" / "tistory" / f"{day}.html"), "warnings": report.warnings, "pruned_details": pruned_details, "reused_existing_draft": False}
