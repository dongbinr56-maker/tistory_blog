import unittest

from tistory_newsroom.collect import choose_diverse
from tistory_newsroom.models import SourceItem


def item(number: int, project_kind: str = "") -> SourceItem:
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
        verification={"project_kind": project_kind} if project_kind else {},
    )


class SelectionTest(unittest.TestCase):
    def test_requires_one_github_or_huggingface_project(self):
        selected = choose_diverse([item(1), item(2)], 3, [])
        self.assertEqual(selected, [])

    def test_keeps_project_and_does_not_pad_to_three(self):
        selected = choose_diverse([item(1, "github"), item(2)], 3, [])
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0].verification["project_kind"], "github")
