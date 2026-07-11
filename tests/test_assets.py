import tempfile
import unittest
from pathlib import Path

from tistory_newsroom.assets import create_image_assets
from tistory_newsroom.generate import generate_demo
from tistory_newsroom.models import SourceItem


class AssetTest(unittest.TestCase):
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
            self.assertTrue((Path(directory) / "docs/tistory/assets/2026-07-11/hero.svg").exists())
            self.assertTrue(images["item-1"]["url"].startswith("https://example.github.io/"))
