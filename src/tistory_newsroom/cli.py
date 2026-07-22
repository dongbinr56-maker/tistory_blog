from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .config import ROOT, load_local_env, load_site_config
from .pipeline import refresh_hero_image, run
from .render import build_site
from .tistory_publish import prepare_tistory_publish_html


def _write_step_summary(result: dict[str, Any]) -> None:
    """Surface run warnings in the GitHub Actions summary.

    Source outages (yozm 405, GeekNews exclusion) previously hid behind
    successful runs; the summary is where a maintainer actually looks.
    """
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_path:
        return
    lines = [f"## Daily draft: {result.get('date', '')} — {result.get('status', '')}", ""]
    warnings = [str(item) for item in result.get("warnings") or []]
    if warnings:
        lines.append("### 경고")
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("경고 없음")
    with Path(summary_path).open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main() -> None:
    load_local_env(ROOT)
    parser = argparse.ArgumentParser(description="Review-first daily Tistory newsroom")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="collect, draft, quality-check and render")
    run_parser.add_argument("--date", help="YYYY-MM-DD; defaults to today in Asia/Seoul")
    run_parser.add_argument("--demo", action="store_true", help="use bundled samples without calling Gemini")
    run_parser.add_argument("--refresh", action="store_true", help="regenerate and overwrite the fixed draft for the selected date")
    hero_parser = commands.add_parser("refresh-hero", help="regenerate the Tistory thumbnail hero image for an approved draft")
    hero_parser.add_argument("--date", help="YYYY-MM-DD; defaults to today in Asia/Seoul")
    commands.add_parser("build-site", help="rebuild the GitHub Pages copy/review UI")
    publish_parser = commands.add_parser("prepare-publish", help="write Tistory paste-ready HTML with hosted HTTPS images")
    publish_parser.add_argument("--html", required=True, type=Path, help="local-preview HTML containing exactly three ./ PNG paths")
    publish_parser.add_argument("--asset-dir", required=True, type=Path, help="GitHub Pages asset output directory")
    publish_parser.add_argument("--asset-base-url", required=True, help="public HTTPS URL matching --asset-dir")
    publish_parser.add_argument("--output", type=Path, help="paste-ready HTML output path")
    args = parser.parse_args()
    if args.command == "run":
        result = run(date=args.date, demo=args.demo, refresh=args.refresh)
        _write_step_summary(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "refresh-hero":
        print(json.dumps(refresh_hero_image(date=args.date), ensure_ascii=False, indent=2))
    elif args.command == "build-site":
        build_site(ROOT, load_site_config(ROOT))
        print("docs/index.html 과 docs/adsense-checklist.html을 생성했습니다.")
    else:
        result = prepare_tistory_publish_html(args.html, args.asset_dir, args.asset_base_url, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
