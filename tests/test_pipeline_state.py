import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tistory_newsroom.assets import create_image_assets
from tistory_newsroom.generate import generate_demo
from tistory_newsroom.models import QualityReport, SourceItem
from tistory_newsroom.pipeline import (
    _existing_ready_draft,
    historical_url_keys,
    prune_expired_details,
    record_historical_url_keys,
    refresh_hero_image,
    run,
    source_health_warnings,
)
from tistory_newsroom.render import write_outputs


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class PipelineStateTest(unittest.TestCase):
    def test_history_uses_prior_selected_urls_but_not_current_day_or_unselected_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "data/runs/2026-07-10/collection.json", {
                "selected": [{
                    "canonical_key": "https://github.com/OpenAI/Example/",
                    "url": "https://news.example.com/announcement?utm_source=test",
                    "official_url": "https://github.com/OpenAI/Example/",
                    "listing_url": "https://news.hada.io/topic?id=1",
                }],
                "candidates": [{"url": "https://should-not-be-in-history.example.com"}],
            })
            write_json(root / "data/runs/2026-07-11/collection.json", {
                "selected": [{"url": "https://same-day.example.com"}],
            })

            keys = historical_url_keys(root, "2026-07-11")

            self.assertIn("https://github.com/openai/example", keys)
            self.assertIn("https://news.example.com/announcement", keys)
            # GeekNews identifies articles only by their id query parameter.
            # Collapsing it to /topic once excluded every future GeekNews
            # candidate after a single selection.
            self.assertIn("https://news.hada.io/topic?id=1", keys)
            self.assertNotIn("https://news.hada.io/topic", keys)
            self.assertNotIn("https://same-day.example.com", keys)
            self.assertNotIn("https://should-not-be-in-history.example.com", keys)

    def test_source_health_warnings_surface_outages_and_news_starved_days(self):
        community = SourceItem(
            id="repo", source="GitHub 커뮤니티", topic="AI 모델링", title="owner/project",
            url="https://github.com/owner/project", published_at="", summary="프로젝트",
            verification={"community_source": "github"},
        )
        article = SourceItem(
            id="article", source="GeekNews", topic="생성형 AI", title="검증 기사",
            url="https://example.org/article", published_at="", summary="기사",
        )

        starved = source_health_warnings(["수집 실패: 요즘IT (HTTP Error 405)"], [community])
        self.assertEqual(len(starved), 2)
        self.assertIn("수집 경고: 수집 실패: 요즘IT (HTTP Error 405)", starved[0])
        self.assertIn("기사형 소스 0건", starved[1])

        healthy = source_health_warnings([], [community, article])
        self.assertEqual(healthy, [])

    def test_generation_failure_still_writes_a_blocked_quality_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "config/site.json", {
                "blog_name": "테스트", "author_name": "테스터", "contact_email": "writer@example.com",
                "blog_url": "https://example.tistory.com",
                "draft_assets_base_url": "https://example.github.io/repo/tistory/assets",
            })
            write_json(root / "config/sources.json", {"sources": [], "selection": {}})
            items = [
                SourceItem(
                    id=f"s{number}", source="GitHub 커뮤니티", topic="AI 모델링", title=f"owner/p{number}",
                    url=f"https://github.com/owner/p{number}", published_at="", summary="프로젝트",
                    official_url=f"https://github.com/owner/p{number}", canonical_key=f"https://github.com/owner/p{number}",
                    verification={"project_kind": "github", "community_source": "github"},
                )
                for number in range(1, 4)
            ]
            with patch("tistory_newsroom.pipeline.collect_candidates", return_value=(items, ["수집 실패: 요즘IT (HTTP 405)"])), \
                    patch("tistory_newsroom.pipeline.generate_with_gemini", side_effect=RuntimeError("Gemini 초안 생성 실패: 테스트")):
                with self.assertRaises(RuntimeError):
                    run(root=root, date="2026-07-11")

            report = json.loads((root / "data/runs/2026-07-11/quality-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "BLOCKED")
            self.assertIn("Gemini 초안 생성 실패: 테스트", report["errors"])
            self.assertTrue(any("기사형 소스 0건" in warning for warning in report["warnings"]))
            self.assertTrue(any("요즘IT" in warning for warning in report["warnings"]))

    def test_ready_daily_draft_is_reused_only_when_every_review_file_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            day = "2026-07-11"
            self.assertIsNone(_existing_ready_draft(root, day))

            write_json(root / f"data/runs/{day}/collection.json", {"selected": [{"url": "https://example.org/one"}]})
            write_json(root / f"data/runs/{day}/draft.json", {"source_items": [{"id": "one"}]})
            write_json(root / f"data/runs/{day}/quality-report.json", {
                "status": "READY_FOR_MANUAL_REVIEW",
                "warnings": ["manual check"],
            })
            output_dir = root / "docs/tistory"
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / f"{day}.html").write_text("<article>ready</article>", encoding="utf-8")
            write_json(output_dir / f"{day}.json", {"date": day})

            result = _existing_ready_draft(root, day)

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["status"], "READY_FOR_MANUAL_REVIEW")
            self.assertEqual(result["article_count"], 1)
            self.assertTrue(result["reused_existing_draft"])

            write_json(root / f"data/runs/{day}/quality-report.json", {"status": "BLOCKED"})
            self.assertIsNone(_existing_ready_draft(root, day))

    def test_compact_history_index_survives_pruning_of_old_collection_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = SourceItem(
                id="project", source="GitHub", topic="AI 모델링", title="owner/project",
                url="https://github.com/owner/project", published_at="", summary="공식 프로젝트입니다.",
                official_url="https://github.com/owner/project", canonical_key="https://github.com/owner/project",
            )
            record_historical_url_keys(root, "2026-07-10", [source])

            index = root / "data/history/seen-url-keys.json"
            self.assertTrue(index.exists())
            self.assertIn("https://github.com/owner/project", historical_url_keys(root, "2026-07-11"))
            self.assertNotIn("https://github.com/owner/project", historical_url_keys(root, "2026-07-10"))

    def test_no_op_does_not_reuse_a_draft_when_collection_audit_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            day = "2026-07-11"
            write_json(root / f"data/runs/{day}/draft.json", {"source_items": []})
            write_json(root / f"data/runs/{day}/quality-report.json", {"status": "READY_FOR_MANUAL_REVIEW"})
            output = root / "docs/tistory"
            output.mkdir(parents=True, exist_ok=True)
            (output / f"{day}.html").write_text("<article>ready</article>", encoding="utf-8")
            write_json(output / f"{day}.json", {"date": day})
            self.assertIsNone(_existing_ready_draft(root, day))

    def test_refresh_hero_image_upgrades_an_approved_draft_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            day = "2026-07-11"
            site = {
                "blog_name": "테스트", "author_name": "테스터", "contact_email": "writer@example.com",
                "blog_url": "https://example.tistory.com", "draft_assets_base_url": "https://example.github.io/repo/tistory/assets",
                "minimum_body_characters": 1400, "required_source_count": 3,
            }
            write_json(root / "config/site.json", site)
            sources = [
                SourceItem(
                    id=f"source-{number}", source="출처", topic="AI 모델링", title=f"AI 모델 이슈 {number}",
                    url=f"https://example.org/{number}", published_at="", summary="검증된 AI 모델 소식입니다.",
                    official_url="https://github.com/example/project" if number == 1 else "",
                    verification={"project_kind": "github", "project_name": "example/project"} if number == 1 else {},
                )
                for number in range(1, 4)
            ]
            draft = generate_demo(day, sources, site)
            draft.images = create_image_assets(root, draft, site["draft_assets_base_url"])
            draft.images["thumbnail"] = {"path": "thumbnail.png", "url": "https://example.github.io/thumbnail.png"}
            legacy_thumbnail = root / f"docs/tistory/assets/{day}/thumbnail.png"
            legacy_thumbnail.write_bytes(b"legacy thumbnail")
            report = QualityReport(
                status="READY_FOR_MANUAL_REVIEW", errors=[], warnings=[], checks={}, manual_review_required=True,
            )
            write_json(root / f"data/runs/{day}/draft.json", draft.to_dict())
            write_json(root / f"data/runs/{day}/quality-report.json", report.to_dict())
            write_outputs(root, draft, report, site)
            original_title = draft.title

            result = refresh_hero_image(root, day)

            refreshed = json.loads((root / f"data/runs/{day}/draft.json").read_text(encoding="utf-8"))
            self.assertEqual(result["hero"]["path"], "hero.png")
            self.assertEqual(refreshed["title"], original_title)
            self.assertEqual(refreshed["images"]["hero"]["path"], "hero.png")
            self.assertNotIn("thumbnail", refreshed["images"])
            self.assertTrue((root / f"docs/tistory/assets/{day}/hero.png").is_file())
            self.assertFalse((root / f"docs/tistory/assets/{day}/thumbnail.png").exists())
            article_html = (root / f"docs/tistory/{day}.html").read_text(encoding="utf-8")
            # 대표 이미지는 티스토리 썸네일 전용이라 본문에는 들어가지 않는다.
            self.assertNotIn("hero.png", article_html)
            self.assertNotIn("thumbnail.png", article_html)

    def test_pruning_removes_old_detail_artifacts_but_not_the_history_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_day, fresh_day, current_day = "2025-01-01", "2026-07-10", "2026-07-11"
            write_json(root / f"data/runs/{old_day}/collection.json", {"selected": []})
            write_json(root / f"data/runs/{fresh_day}/collection.json", {"selected": []})
            write_json(root / "data/history/seen-url-keys.json", {"entries": {"https://example.org/old": old_day}})
            for day in (old_day, fresh_day):
                write_json(root / f"docs/tistory/{day}.json", {"date": day})
                (root / f"docs/tistory/{day}.html").write_text("<article></article>", encoding="utf-8")
                asset_dir = root / f"docs/tistory/assets/{day}"
                asset_dir.mkdir(parents=True)
                (asset_dir / "hero.svg").write_text("asset", encoding="utf-8")

            removed = prune_expired_details(root, current_day, 180)

            self.assertTrue(removed)
            self.assertFalse((root / f"data/runs/{old_day}").exists())
            self.assertFalse((root / f"docs/tistory/{old_day}.json").exists())
            self.assertFalse((root / f"docs/tistory/assets/{old_day}").exists())
            self.assertTrue((root / f"data/runs/{fresh_day}").exists())
            self.assertTrue((root / "data/history/seen-url-keys.json").exists())
