import datetime as dt
import unittest
from unittest.mock import patch

from tistory_newsroom.collect import (
    ListingCandidate,
    _extract_geeknews_original,
    _fetch_bytes,
    _find_official_url,
    _hackernews_listings,
    _topics,
    _verify_listing,
)

KST = dt.timezone(dt.timedelta(hours=9))


class TopicRelevanceTest(unittest.TestCase):
    def test_short_ascii_terms_require_token_boundaries(self):
        self.assertEqual(_topics("Sidedock provides a side-project platform", ""), [])
        self.assertIn("개발 도구", _topics("VS Code IDE plugin for reviews", ""))
        self.assertIn("생성형 AI", _topics("LLM 서비스 운영 비용을 줄이는 방법", ""))

    def test_a_bare_github_link_is_not_relevance(self):
        self.assertEqual(_topics("Shell script obfuscation tool", "https://github.com/owner/repo"), [])
        self.assertEqual(_topics("A tool mentioning github and 깃허브 only", ""), [])


class OfficialUrlTest(unittest.TestCase):
    def test_skips_assets_and_reserved_paths_and_normalizes_to_the_repo(self):
        page = (
            '<img src="https://github.com/fluidicon.png">'
            '<a href="https://github.com/features/actions">features</a>'
            '<a href="https://github.com/owner/repo/issues/5">repo</a>'
        )
        self.assertEqual(_find_official_url(page), "https://github.com/owner/repo")

    def test_returns_empty_when_only_page_noise_exists(self):
        page = '<img src="https://github.com/fluidicon.png"> <a href="https://github.com/pricing">pricing</a>'
        self.assertEqual(_find_official_url(page), "")

    def test_huggingface_dataset_and_model_paths(self):
        self.assertEqual(
            _find_official_url("https://huggingface.co/datasets/org/name/tree/main"),
            "https://huggingface.co/datasets/org/name",
        )
        self.assertEqual(
            _find_official_url("본문 링크: https://huggingface.co/org/model-name 참고"),
            "https://huggingface.co/org/model-name",
        )
        self.assertEqual(_find_official_url("https://huggingface.co/docs/hub/index"), "")


class GeekNewsOriginalTest(unittest.TestCase):
    def test_reads_the_url_inside_the_shared_content_object(self):
        page = '{"sharedContent": {"url": "https:\\/\\/original.example.com\\/post", "title": "t"}}'
        self.assertEqual(
            _extract_geeknews_original(page, "https://news.hada.io/topic?id=1"),
            "https://original.example.com/post",
        )

    def test_does_not_cross_the_object_boundary_for_a_stray_url_key(self):
        page = (
            '{"sharedContent": {"title": "no url here"}, "tracker": {"url": "https://evil.example.com/x"}}'
            '<a href="https://original.example.com/post">원문</a>'
        )
        self.assertEqual(
            _extract_geeknews_original(page, "https://news.hada.io/topic?id=1"),
            "https://original.example.com/post",
        )


class HackerNewsTest(unittest.TestCase):
    def test_builds_candidates_and_skips_self_posts(self):
        hits = {"hits": [
            {"title": "I love LLMs, I hate hype", "url": "https://example.org/llm-post", "objectID": "111", "created_at": "2026-07-12T18:31:56Z", "points": 415},
            {"title": "Ask HN: Add flag for AI articles", "url": None, "objectID": "222", "created_at": "2026-07-13T01:24:20Z", "points": 606},
        ]}
        now = dt.datetime(2026, 7, 13, 7, 0, tzinfo=KST)
        with patch("tistory_newsroom.collect._api_json", return_value=hits) as api:
            listings = _hackernews_listings({"name": "Hacker News", "minimum_points": 100}, now, 24, 15)

        self.assertEqual(len(listings), 1)
        candidate = listings[0]
        self.assertEqual(candidate.article_url, "https://example.org/llm-post")
        self.assertEqual(candidate.listing_url, "https://news.ycombinator.com/item?id=111")
        self.assertTrue(candidate.introduced_at)
        endpoint = api.call_args[0][0]
        self.assertIn("points%3E%3D100", endpoint)

    def test_verification_uses_the_preset_article_and_the_surfacing_time(self):
        candidate = ListingCandidate(
            source="Hacker News",
            listing_url="https://news.ycombinator.com/item?id=111",
            listing_title="I love LLMs, I hate hype",
            article_url="https://example.org/llm-post",
            introduced_at="2026-07-13T06:00:00+09:00",
        )
        article_page = (
            '<html><head>'
            '<meta property="og:title" content="I love LLMs, I hate hype">'
            '<meta property="og:description" content="LLM 에이전트와 모델 추론 비용에 대한 글">'
            '<meta property="og:site_name" content="example.org">'
            '<meta property="article:published_time" content="2026-07-01T00:00:00Z">'
            "</head><body></body></html>"
        )
        now = dt.datetime(2026, 7, 13, 7, 0, tzinfo=KST)
        with patch("tistory_newsroom.collect._fetch_text", return_value=article_page) as fetch:
            item = _verify_listing(candidate, now, 24)

        self.assertIsNotNone(item)
        assert item is not None
        # HN 아이템 페이지는 가져오지 않고 원문만 확인한다.
        fetch.assert_called_once_with("https://example.org/llm-post")
        self.assertEqual(item.url, "https://example.org/llm-post")
        self.assertEqual(item.source, "example.org")
        self.assertEqual(item.listing_url, "https://news.ycombinator.com/item?id=111")
        # 원문 게시일(7/1)이 오래돼도 HN에 오늘 올라왔으면 24시간 창을 통과한다.
        self.assertEqual(item.introduced_at, "2026-07-13T06:00:00+09:00")


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str = "image/png") -> None:
        self._body = body
        self.headers = {"Content-Type": content_type}

    def read(self, limit: int = -1) -> bytes:
        return self._body if limit is None or limit < 0 else self._body[:limit]

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class FetchBytesTest(unittest.TestCase):
    def test_reads_one_byte_past_the_limit_so_callers_detect_truncation(self):
        with patch("tistory_newsroom.collect.urllib.request.urlopen", return_value=_FakeResponse(b"x" * 5000)):
            raw, content_type = _fetch_bytes("https://example.org/img.png", "image/*", attempts=1, max_bytes=1000)
        self.assertEqual(len(raw), 1001)
        self.assertEqual(content_type, "image/png")


if __name__ == "__main__":
    unittest.main()
