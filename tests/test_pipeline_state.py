import json
import tempfile
import unittest
from pathlib import Path

from tistory_newsroom.pipeline import _existing_ready_draft, historical_url_keys


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
            self.assertIn("https://news.hada.io/topic", keys)
            self.assertNotIn("https://same-day.example.com", keys)
            self.assertNotIn("https://should-not-be-in-history.example.com", keys)

    def test_ready_daily_draft_is_reused_only_when_every_review_file_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            day = "2026-07-11"
            self.assertIsNone(_existing_ready_draft(root, day))

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
