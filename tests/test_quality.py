import unittest

from tistory_newsroom.generate import generate_demo
from tistory_newsroom.models import SourceItem
from tistory_newsroom.quality import inspect_draft


SITE = {
    "blog_name": "테스트 블로그",
    "author_name": "테스터",
    "contact_email": "writer@myblog.kr",
    "blog_url": "https://myblog.tistory.com",
    "minimum_body_characters": 1500,
    "required_source_count": 3,
}


def sources():
    return [
        SourceItem(
            id=f"source-{index}",
            source=f"출처 {index}",
            topic="개발",
            title=f"테스트 이슈 {index}",
            url=f"https://example.org/{index}",
            published_at="2026-07-11T07:00:00+09:00",
            summary="검증을 위한 원천 요약입니다. 팀의 판단 기준을 다루는 공개 자료입니다.",
            official_url="https://huggingface.co/test/model" if index == 1 else "",
            verification={"project_kind": "huggingface", "community_source": "huggingface", "project_name": "test/model", "license": "Apache-2.0"} if index == 1 else {},
        )
        for index in range(1, 4)
    ]


class QualityGateTest(unittest.TestCase):
    def test_demo_draft_passes_review_gate(self):
        draft = generate_demo("2026-07-11", sources(), SITE)
        report = inspect_draft(draft, SITE)
        self.assertEqual(report.status, "READY_FOR_MANUAL_REVIEW")
        self.assertTrue(report.manual_review_required)
        self.assertTrue(report.checks["manual_review_required"])
        self.assertEqual(draft.editorial_disclosure, "")

    def test_missing_source_trace_blocks_draft(self):
        draft = generate_demo("2026-07-11", sources(), SITE)
        draft.sections[0].source_ids = ["not-a-real-source"]
        report = inspect_draft(draft, SITE)
        self.assertEqual(report.status, "BLOCKED")
        self.assertFalse(report.checks["all_sections_trace_to_source"])

    def test_click_inducement_blocks_draft(self):
        draft = generate_demo("2026-07-11", sources(), SITE)
        draft.closing += " 광고를 클릭해서 응원해 주세요."
        report = inspect_draft(draft, SITE)
        self.assertEqual(report.status, "BLOCKED")
        self.assertFalse(report.checks["no_click_inducement"])

    def test_empty_technical_inventory_blocks_draft(self):
        draft = generate_demo("2026-07-11", sources(), SITE)
        draft.sections[0].why_it_matters += " 모델: 해당 없음"
        report = inspect_draft(draft, SITE)
        self.assertEqual(report.status, "BLOCKED")
        self.assertFalse(report.checks["no_empty_technical_inventory"])

    def test_generic_ai_summary_phrase_blocks_draft(self):
        draft = generate_demo("2026-07-11", sources(), SITE)
        draft.intro = "오늘 살펴본 소식들은 AI 엔지니어링이 단순히 모델을 만드는 일이 아님을 보여줍니다."
        report = inspect_draft(draft, SITE)
        self.assertEqual(report.status, "BLOCKED")
        self.assertFalse(report.checks["natural_editorial_voice"])

    def test_intro_without_actual_projects_blocks_draft(self):
        draft = generate_demo("2026-07-11", sources(), SITE)
        draft.intro = "새로운 기술의 흐름을 정리합니다."
        report = inspect_draft(draft, SITE)
        self.assertEqual(report.status, "BLOCKED")
        self.assertFalse(report.checks["specific_intro"])

    def test_placeholder_identity_blocks_production_draft(self):
        draft = generate_demo("2026-07-11", sources(), SITE)
        placeholder_site = {**SITE, "author_name": "작성자 이름", "contact_email": "hello@example.com", "blog_url": "https://example.tistory.com"}
        report = inspect_draft(draft, placeholder_site)
        self.assertEqual(report.status, "BLOCKED")
        self.assertFalse(report.checks["contact_configured"])
        self.assertFalse(report.checks["author_configured"])
        self.assertFalse(report.checks["blog_url_configured"])
