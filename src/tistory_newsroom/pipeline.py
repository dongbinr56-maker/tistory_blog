from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

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


def run(root: Path = ROOT, date: str | None = None, demo: bool = False) -> dict[str, Any]:
    day = _day_or_today(date)
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
        selected = choose_diverse(
            candidates,
            int(selection.get("final_article_count", 3)),
            [str(item) for item in selection.get("excluded_title_terms", [])],
        )
    collection = collection_payload(day, candidates, selected, collector_errors)
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
    return {"date": day, "article_count": len(selected), "status": report.status, "output": str(root / "docs" / "tistory" / f"{day}.html"), "warnings": report.warnings}
