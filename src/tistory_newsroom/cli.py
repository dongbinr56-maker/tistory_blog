from __future__ import annotations

import argparse
import json

from .config import ROOT, load_local_env, load_site_config
from .pipeline import run
from .render import build_site


def main() -> None:
    load_local_env(ROOT)
    parser = argparse.ArgumentParser(description="Review-first daily Tistory newsroom")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="collect, draft, quality-check and render")
    run_parser.add_argument("--date", help="YYYY-MM-DD; defaults to today in Asia/Seoul")
    run_parser.add_argument("--demo", action="store_true", help="use bundled samples without calling Gemini")
    run_parser.add_argument("--refresh", action="store_true", help="regenerate and overwrite the fixed draft for the selected date")
    commands.add_parser("build-site", help="rebuild the GitHub Pages copy/review UI")
    args = parser.parse_args()
    if args.command == "run":
        print(json.dumps(run(date=args.date, demo=args.demo, refresh=args.refresh), ensure_ascii=False, indent=2))
    else:
        build_site(ROOT, load_site_config(ROOT))
        print("docs/index.html 과 docs/adsense-checklist.html을 생성했습니다.")
