import unittest

from tistory_newsroom.generate import _distinct_title_candidates, _publication_title, make_rewrite_prompt
from tistory_newsroom.models import SourceItem


class GeneratePromptTest(unittest.TestCase):
    def test_rewrite_prompt_includes_the_triggered_reasons(self):
        source = SourceItem(
            id="ecc",
            source="GitHub",
            topic="AI 에이전트",
            title="affaan-m/ECC",
            url="https://github.com/affaan-m/ECC",
            published_at="2026-07-11T07:00:00+09:00",
            summary="AI 에이전트 하네스 프로젝트",
            official_url="https://github.com/affaan-m/ECC",
            verification={"project_name": "affaan-m/ECC"},
        )
        prompt = make_rewrite_prompt("2026-07-11", [source], {"intro": "", "sections": []}, ["도입부가 일반적입니다."])
        self.assertIn("도입부가 일반적입니다.", prompt)
        self.assertIn("ECC", prompt)

    def test_uses_a_valid_title_candidate_when_the_selected_title_is_too_long(self):
        selected = _publication_title({
            "title": "AI 에이전트 성능과 복잡한 운영 환경, 배포 보안, 규제 이슈, 서비스 안정성, 모델 활용 전략까지 모두 한 번에 설명하는 지나치게 긴 제목입니다",
            "title_candidates": ["ECC와 HimitsuShell: AI 배포에서 먼저 볼 두 가지"],
        })
        self.assertEqual(selected, "ECC와 HimitsuShell: AI 배포에서 먼저 볼 두 가지")
        self.assertLessEqual(len(selected), 75)

    def test_fills_duplicate_title_candidates_with_verified_project_variants(self):
        sources = [
            SourceItem(
                id="first", source="GitHub", topic="AI 모델링", title="owner/first-project",
                url="https://github.com/owner/first-project", published_at="", summary="공식 프로젝트입니다.",
                official_url="https://github.com/owner/first-project", verification={"project_name": "owner/first-project"},
            ),
            SourceItem(
                id="second", source="GitHub", topic="AI 에이전트", title="owner/second-project",
                url="https://github.com/owner/second-project", published_at="", summary="공식 프로젝트입니다.",
                official_url="https://github.com/owner/second-project", verification={"project_name": "owner/second-project"},
            ),
        ]

        candidates = _distinct_title_candidates({
            "title": "owner/first-project와 AI 에이전트 개발 흐름",
            "title_candidates": ["중복 후보", "중복 후보", "중복 후보"],
        }, sources)

        self.assertEqual(len(candidates), 3)
        self.assertEqual(len({candidate.casefold() for candidate in candidates}), 3)
        self.assertIn("owner/first-project", candidates[0])
