import unittest
from unittest.mock import patch

from tistory_newsroom.collect import _canonical, _fetch_headers, choose_diverse, identifying_query
from tistory_newsroom.models import SourceItem


def item(number: int, project_kind: str = "", community: bool = False) -> SourceItem:
    return SourceItem(
        id=f"item-{number}",
        source=f"출처-{number}",
        topic="생성형 AI, AI 모델링",
        title=f"AI 모델 검증 기사 {number}",
        url=f"https://example.org/{number}",
        published_at="2026-07-11T07:00:00+09:00",
        summary="모델 추론과 배포, 평가 조건을 확인하는 기사입니다.",
        official_url=f"https://{project_kind}.example.org/project" if project_kind else "",
        canonical_key=f"project-{number}",
        verification={"project_kind": project_kind, **({"community_source": project_kind} if community else {})} if project_kind else {},
    )


class UrlKeyTest(unittest.TestCase):
    def test_canonical_key_keeps_the_identifying_id_but_drops_tracking_params(self):
        self.assertEqual(
            _canonical("https://news.hada.io/topic?id=31363", ""),
            "https://news.hada.io/topic?id=31363",
        )
        self.assertEqual(
            _canonical("https://news.hada.io/topic?id=31363&utm_source=rss#comments", ""),
            "https://news.hada.io/topic?id=31363",
        )
        self.assertEqual(
            _canonical("https://news.example.com/post?utm_source=x&utm_medium=y", ""),
            "https://news.example.com/post",
        )

    def test_two_geeknews_articles_keep_distinct_keys(self):
        first = _canonical("https://news.hada.io/topic?id=1", "")
        second = _canonical("https://news.hada.io/topic?id=2", "")
        self.assertNotEqual(first, second)

    def test_identifying_query_only_keeps_id(self):
        self.assertEqual(identifying_query("id=31363&utm_source=rss"), "id=31363")
        self.assertEqual(identifying_query("utm_source=rss"), "")
        self.assertEqual(identifying_query(""), "")


class SelectionTest(unittest.TestCase):
    def test_github_api_uses_the_optional_action_token_but_other_hosts_do_not(self):
        with patch.dict("os.environ", {"GH_API_TOKEN": "test-token"}, clear=False):
            github_headers = _fetch_headers("https://api.github.com/repos/owner/project", "application/json")
            web_headers = _fetch_headers("https://github.com/owner/project", "text/html")
        self.assertEqual(github_headers["Authorization"], "Bearer test-token")
        self.assertNotIn("Authorization", web_headers)

    def test_requires_one_github_or_huggingface_community_project(self):
        selected = choose_diverse([item(1), item(2)], 3, [])
        self.assertEqual(selected, [])

    def test_fills_three_slots_from_editorial_and_community_sources(self):
        selected = choose_diverse([item(1, "github", community=True), item(2), item(3)], 3, [])
        self.assertEqual(len(selected), 3)
        self.assertEqual(selected[0].verification["project_kind"], "github")
        self.assertEqual(selected[0].verification["community_source"], "github")

    def test_a_day_rich_in_articles_earns_a_fourth_slot(self):
        selected = choose_diverse([item(1, "github", community=True), item(2), item(3), item(4), item(5)], 3, [])
        self.assertEqual(len(selected), 4)
        self.assertEqual(sum(bool(chosen.verification.get("community_source")) for chosen in selected), 1)

    def test_excludes_a_previously_selected_official_project_url(self):
        prior_project = item(1, "github", community=True)
        replacement_project = item(2, "huggingface", community=True)
        selected = choose_diverse(
            [prior_project, replacement_project, item(3), item(4)],
            3,
            [],
            {prior_project.official_url},
        )
        self.assertNotIn(prior_project, selected)
        self.assertIn(replacement_project, selected)
        self.assertEqual(len(selected), 3)
