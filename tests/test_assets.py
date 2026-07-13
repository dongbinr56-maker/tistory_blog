import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tistory_newsroom.assets import create_image_assets
from tistory_newsroom.generate import generate_demo
from tistory_newsroom.models import SourceItem


class AssetTest(unittest.TestCase):
    def _draft_with_remote_image(self):
        sources = [
            SourceItem(
                id="item", source="출처", topic="AI 모델링", title="모델 이슈",
                url="https://example.org/item", published_at="", summary="검증된 기사입니다.",
                image_url="https://cdn.example.org/hero-image",
            )
        ]
        return generate_demo("2026-07-11", sources, {"blog_name": "테스트", "author_name": "테스터"})

    def test_non_image_response_falls_back_to_the_generated_card(self):
        draft = self._draft_with_remote_image()
        with tempfile.TemporaryDirectory() as directory, \
                patch("tistory_newsroom.assets._fetch_bytes", return_value=(b"<html>hotlink blocked</html>", "text/html; charset=utf-8")):
            images = create_image_assets(Path(directory), draft, "")
            self.assertEqual(images["item"]["kind"], "generated-fallback")
            self.assertTrue(images["item"]["path"].endswith(".svg"))
            self.assertFalse((Path(directory) / "docs/tistory/assets/2026-07-11/issue-1.jpg").exists())

    def test_oversize_image_falls_back_to_the_generated_card(self):
        draft = self._draft_with_remote_image()
        with tempfile.TemporaryDirectory() as directory, \
                patch("tistory_newsroom.assets._fetch_bytes", return_value=(b"x" * 10_000_001, "image/png")):
            images = create_image_assets(Path(directory), draft, "")
            self.assertEqual(images["item"]["kind"], "generated-fallback")
            self.assertTrue(images["item"]["path"].endswith(".svg"))
    def test_creates_hero_and_one_fallback_per_article(self):
        sources = [
            SourceItem(
                id=f"item-{number}", source="출처", topic="AI 모델링", title=f"모델 이슈 {number}",
                url=f"https://example.org/{number}", published_at="", summary="모델 평가를 다루는 검증된 기사입니다.",
                official_url="https://github.com/test/project" if number == 1 else "",
                verification={"project_kind": "github"} if number == 1 else {},
            )
            for number in range(1, 4)
        ]
        site = {"blog_name": "테스트", "author_name": "테스터"}
        draft = generate_demo("2026-07-11", sources, site)
        with tempfile.TemporaryDirectory() as directory:
            images = create_image_assets(Path(directory), draft, "https://example.github.io/repo/tistory/assets")
            self.assertEqual(set(images), {"hero", "item-1", "item-2", "item-3"})
            hero_path = Path(directory) / "docs/tistory/assets/2026-07-11/hero.png"
            self.assertTrue(hero_path.exists())
            self.assertEqual(hero_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(images["hero"]["path"], "hero.png")
            self.assertTrue(images["item-1"]["url"].startswith("https://example.github.io/"))

    def test_refresh_removes_stale_daily_asset_variants(self):
        sources = [
            SourceItem(
                id="item", source="출처", topic="AI 모델링", title="모델 이슈",
                url="https://example.org/item", published_at="", summary="검증된 기사입니다.",
            )
        ]
        draft = generate_demo("2026-07-11", sources, {"blog_name": "테스트", "author_name": "테스터"})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "docs/tistory/assets/2026-07-11"
            assets.mkdir(parents=True)
            (assets / "issue-1.png").write_bytes(b"old")
            (assets / "hero.svg").write_text("old", encoding="utf-8")

            create_image_assets(root, draft, "https://example.github.io/repo/tistory/assets")

            self.assertFalse((assets / "issue-1.png").exists())
            self.assertTrue((assets / "issue-1.svg").exists())
            self.assertFalse((assets / "hero.svg").exists())
            self.assertTrue((assets / "hero.png").exists())
            self.assertFalse((assets / "thumbnail.png").exists())
