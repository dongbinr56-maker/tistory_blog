import unittest
from unittest.mock import patch

from tistory_newsroom.collect import _fetch_headers, choose_diverse
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
