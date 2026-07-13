import unittest

from tistory_newsroom.generate import generate_demo
from tistory_newsroom.models import SourceItem
from tistory_newsroom.quality import inspect_draft, names_source


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

    def test_repeated_analogies_block_draft(self):
        draft = generate_demo("2026-07-11", sources(), SITE)
        draft.sections[0].plain_explanation += " 마치 요리 레시피를 모아둔 웹사이트처럼 쓸 수 있습니다."
        draft.sections[1].plain_explanation += " 마치 부품을 조립해 로봇을 만드는 것처럼 구성합니다."
        report = inspect_draft(draft, SITE)
        self.assertEqual(report.status, "BLOCKED")
        self.assertFalse(report.checks["natural_editorial_voice"])

    def test_generic_conclusion_pattern_blocks_draft(self):
        draft = generate_demo("2026-07-11", sources(), SITE)
        draft.sections[0].why_it_matters += " 전체 품질을 향상시키는 데 기여합니다."
        draft.sections[1].why_it_matters += " 생태계 활성화에 기여합니다."
        report = inspect_draft(draft, SITE)
        self.assertEqual(report.status, "BLOCKED")
        self.assertFalse(report.checks["natural_editorial_voice"])

    def test_near_duplicate_impact_and_take_block_draft(self):
        draft = generate_demo("2026-07-11", sources(), SITE)
        duplicated = "데이터 수집 과정을 간소화하여 개발자가 모델 개발에 집중할 수 있게 돕습니다."
        draft.sections[0].why_it_matters = duplicated + " 영향은 배포 파이프라인 전체에 미칩니다."
        draft.sections[0].editorial_take = "도입 전에 확인할 점이 있습니다. " + duplicated + " 다만 청소 규칙과 요금제를 먼저 검토해야 하고, 대상 사이트의 약관도 살펴야 합니다. 소규모 실험으로 시작하는 편이 안전합니다."
        report = inspect_draft(draft, SITE)
        self.assertEqual(report.status, "BLOCKED")
        self.assertFalse(report.checks["natural_editorial_voice"])

    def test_intro_without_actual_projects_blocks_draft(self):
        draft = generate_demo("2026-07-11", sources(), SITE)
        draft.intro = "새로운 기술의 흐름을 정리합니다."
        report = inspect_draft(draft, SITE)
        self.assertEqual(report.status, "BLOCKED")
        self.assertFalse(report.checks["specific_intro"])

    def test_names_source_tolerates_the_www_prefix_and_case(self):
        self.assertTrue(names_source("thevccorner.com의 분석에 따르면 가치가 이동하고 있습니다.", "www.thevccorner.com"))
        self.assertTrue(names_source("WWW.Example.COM 보도에 따르면 서비스가 바뀝니다.", "www.example.com"))
        self.assertFalse(names_source("아무 귀속 없는 문장입니다.", "www.example.com"))

    def test_secondary_source_fact_summary_must_name_the_source(self):
        draft = generate_demo("2026-07-11", sources(), SITE)
        draft.sections[1].what_happened = "새 서비스가 규제 때문에 중단됐다가 재개됐습니다."
        report = inspect_draft(draft, SITE)
        self.assertEqual(report.status, "BLOCKED")
        self.assertFalse(report.checks["secondary_source_attribution"])

    def test_volatile_community_metrics_are_kept_out_of_the_body(self):
        draft = generate_demo("2026-07-11", sources(), SITE)
        draft.sections[0].what_happened += " GitHub 스타 22만 개를 기록했습니다."
        report = inspect_draft(draft, SITE)
        self.assertEqual(report.status, "BLOCKED")
        self.assertFalse(report.checks["no_volatile_community_metrics"])

    def test_placeholder_identity_blocks_production_draft(self):
        draft = generate_demo("2026-07-11", sources(), SITE)
        placeholder_site = {**SITE, "author_name": "작성자 이름", "contact_email": "hello@example.com", "blog_url": "https://example.tistory.com"}
        report = inspect_draft(draft, placeholder_site)
        self.assertEqual(report.status, "BLOCKED")
        self.assertFalse(report.checks["contact_configured"])
        self.assertFalse(report.checks["author_configured"])
        self.assertFalse(report.checks["blog_url_configured"])
