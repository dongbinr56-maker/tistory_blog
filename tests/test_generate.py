import unittest

from tistory_newsroom.generate import make_rewrite_prompt
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
