from __future__ import annotations

import re

from .models import Draft, QualityReport
from .style import generic_editorial_markers, generic_pattern_reasons, mentioned_projects, section_overlap_reasons

BLOCKED_TERMS = (
    "성인", "음란", "도박", "마약", "총기", "폭력 선동", "혐오",
)
CLICK_INDUCEMENT = (
    "광고를 클릭", "광고 클릭", "클릭해서 응원", "click ads",
)
UNNATURAL_TECH_MARKERS = (
    "해당 없음",
    "공개 자료에서 확인하지 못함",
    "{'모델'",
    '"모델"',
)
COMMUNITY_METRIC_MARKERS = (
    "GitHub 스타", "깃허브 스타", "Hugging Face 다운로드", "허깅페이스 다운로드", "다운로드 수", "좋아요 수",
)
EVIDENCE_MODES = {"hands_on", "source_analysis"}
EXECUTION_STATUSES = {"performed", "partial", "not_performed"}
TEMPLATE_HEADINGS = {
    "이번 변화의 요점",
    "쉽게 풀어 보면",
    "실무에서 달라지는 점",
    "먼저 볼 지점",
    "확인해 볼 것",
}
# Shared with the generation rewrite loop so a shortfall is repaired before
# the gate blocks the day over a few missing characters.
SECTION_MINIMUM_LENGTHS = (
    ("plain_explanation", 90),
    ("why_it_matters", 60),
    ("editorial_take", 130),
    ("reader_action", 45),
)


def names_source(text: str, source_name: str) -> bool:
    """Check that prose credits the medium, tolerating a www. prefix.

    Gemini wrote "thevccorner.com의 분석에 따르면" for the source
    "www.thevccorner.com" — correct attribution that an exact substring
    match rejected.
    """
    lowered = text.lower()
    name = source_name.strip().lower()
    trimmed = name.removeprefix("www.")
    return any(candidate and candidate in lowered for candidate in {name, trimmed})


def _body_text(draft: Draft) -> str:
    pieces = [draft.intro, draft.closing]
    for section in draft.sections:
        pieces.extend((section.headline, section.what_happened, section.plain_explanation, section.why_it_matters, section.editorial_take, section.reader_action))
    return " ".join(pieces)


def inspect_draft(draft: Draft, site: dict[str, object]) -> QualityReport:
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, bool] = {}
    body = _body_text(draft)
    source_ids = {item.id for item in draft.source_items}
    linked_ids = {source_id for section in draft.sections for source_id in section.source_ids}

    checks["three_distinct_title_candidates"] = len(set(draft.title_candidates)) >= 3
    if not checks["three_distinct_title_candidates"]:
        errors.append("제목 후보는 서로 다른 3개 이상이어야 합니다.")

    checks["reasonable_title_length"] = 15 <= len(draft.title) <= 75
    if not checks["reasonable_title_length"]:
        errors.append("선택된 제목은 15~75자여야 합니다.")

    checks["tag_count_and_uniqueness"] = 5 <= len(draft.tags) <= 10 and len({tag.lower() for tag in draft.tags}) == len(draft.tags)
    if not checks["tag_count_and_uniqueness"]:
        errors.append("태그는 중복 없이 5~10개여야 합니다.")

    minimum_sources = int(site.get("required_source_count", 3))
    checks["sufficient_sources"] = len(draft.source_items) >= minimum_sources and all(item.url.startswith(("https://", "http://")) for item in draft.source_items)
    if not checks["sufficient_sources"]:
        warnings.append(f"출처 수 경고: 신뢰 가능한 원문 링크를 가진 출처가 권장치 {minimum_sources}개보다 적습니다.")

    checks["all_sections_trace_to_source"] = bool(draft.sections) and all(section.source_ids and set(section.source_ids) <= source_ids for section in draft.sections) and linked_ids == source_ids
    if not checks["all_sections_trace_to_source"]:
        errors.append("각 이슈는 출처 ID와 1:1로 추적 가능해야 하며, 선택된 모든 출처를 다뤄야 합니다.")

    source_by_id = {source.id: source for source in draft.source_items}
    secondary_sections = [
        section
        for section in draft.sections
        if section.source_ids and all(not source_by_id[source_id].official_url for source_id in section.source_ids if source_id in source_by_id)
    ]
    checks["secondary_source_attribution"] = all(
        "원문" in section.what_happened
        or any(names_source(section.what_happened, source_by_id[source_id].source) for source_id in section.source_ids if source_id in source_by_id)
        for section in secondary_sections
    )
    if not checks["secondary_source_attribution"]:
        errors.append("공식 출처가 없는 이슈의 사실 요약은 원문 매체에 귀속해 작성해야 합니다.")

    # why_it_matters stays short on purpose: forcing 90+ characters pushed the
    # model to restate editorial_take, which reads as padded machine text.
    minimums = dict(SECTION_MINIMUM_LENGTHS)
    checks["plain_language_and_engineering_value"] = all(
        len(section.plain_explanation) >= minimums["plain_explanation"]
        and len(section.why_it_matters) >= minimums["why_it_matters"]
        and len(section.editorial_take) >= minimums["editorial_take"]
        for section in draft.sections
    )
    if not checks["plain_language_and_engineering_value"]:
        errors.append("각 이슈에는 일반인 설명과 엔지니어 관점의 충분한 분석이 필요합니다.")

    checks["original_value_added"] = all(
        len(section.editorial_take) >= minimums["editorial_take"]
        and len(section.why_it_matters) >= minimums["why_it_matters"]
        and len(section.reader_action) >= minimums["reader_action"]
        for section in draft.sections
    )
    if not checks["original_value_added"]:
        errors.append("각 이슈에는 충분한 영향 분석·독자적 해설·독자 행동 제안이 필요합니다.")

    minimum_body = int(site.get("minimum_body_characters", 1500))
    checks["substantive_body"] = len(body) >= minimum_body
    if not checks["substantive_body"]:
        warnings.append(f"본문 길이 경고: 권장치 {minimum_body}자보다 짧습니다. 현재 {len(body)}자입니다.")

    checks["valid_evidence_mode"] = draft.evidence_mode in EVIDENCE_MODES
    if not checks["valid_evidence_mode"]:
        errors.append("검증 방식은 hands_on 또는 source_analysis여야 합니다.")

    checks["valid_execution_status"] = draft.execution_status in EXECUTION_STATUSES
    if not checks["valid_execution_status"]:
        errors.append("실행 여부는 performed, partial, not_performed 중 하나여야 합니다.")

    promises_hands_on = bool(re.search(r"(?:만들기|실습(?:하기)?|테스트(?:하기|해보기)?)\s*$", draft.title))
    checks["hands_on_promise_is_performed"] = not promises_hands_on or draft.execution_status != "not_performed"
    if not checks["hands_on_promise_is_performed"]:
        errors.append("제목에서 만들기·실습·테스트를 약속한 글은 실제 실행 없이 발행할 수 없습니다.")

    checks["hands_on_artifacts_present"] = (
        draft.evidence_mode != "hands_on"
        or draft.execution_status != "performed"
        or bool(draft.evidence_artifacts)
    )
    if not checks["hands_on_artifacts_present"]:
        errors.append("실사용 완료 글에는 스크린샷·출력·검증 메모 중 하나 이상의 증거 자료가 필요합니다.")

    checks["source_limitations_documented"] = (
        draft.evidence_mode != "source_analysis"
        or all(section.verification_notes.strip() for section in draft.sections)
    )
    if not checks["source_limitations_documented"]:
        errors.append("문서 기반 글은 각 출처에서 확인한 범위와 독립 검증하지 못한 한계를 기록해야 합니다.")

    used_template_headings = {section.headline.strip() for section in draft.sections} & TEMPLATE_HEADINGS
    checks["no_template_heading_scaffold"] = len(used_template_headings) < 3
    if not checks["no_template_heading_scaffold"]:
        errors.append("여러 글에서 반복되는 고정 소제목 템플릿 대신 주제에 맞는 소제목을 사용해야 합니다.")

    # Review is enforced by the workflow/report, rather than inserting an
    # automation disclaimer into the reader-facing article.
    checks["manual_review_required"] = True

    lowered = body.lower()
    checks["no_click_inducement"] = not any(term in lowered for term in CLICK_INDUCEMENT)
    if not checks["no_click_inducement"]:
        errors.append("광고 클릭을 유도하는 표현은 사용할 수 없습니다.")

    checks["no_empty_technical_inventory"] = not any(term in body for term in UNNATURAL_TECH_MARKERS)
    if not checks["no_empty_technical_inventory"]:
        errors.append("확인 불가 항목을 나열하는 기술 인벤토리 대신, 실제 확인한 내용만 자연스러운 문장으로 작성해야 합니다.")

    checks["no_volatile_community_metrics"] = not any(term.lower() in lowered for term in COMMUNITY_METRIC_MARKERS)
    if not checks["no_volatile_community_metrics"]:
        errors.append("변동 가능한 커뮤니티 수치는 본문이 아닌 검토 화면의 사실·수치 근거에서 확인해야 합니다.")

    # Style findings warn instead of block: every draft is human-reviewed
    # before publishing anyway, and killing a whole day over one extra
    # "~을 보여줍니다" wastes the run. The rewrite loop still tries to fix
    # these during generation; whatever survives lands here for the reviewer.
    style_problems = (
        generic_editorial_markers(body)
        + generic_pattern_reasons(body)
        + section_overlap_reasons((section.why_it_matters, section.editorial_take) for section in draft.sections)
    )
    checks["natural_editorial_voice"] = not style_problems
    if not checks["natural_editorial_voice"]:
        warnings.extend("문체 경고: " + problem for problem in style_problems)

    checks["specific_intro"] = len(mentioned_projects(draft.intro, draft.source_items)) >= 2
    if not checks["specific_intro"]:
        warnings.append("문체 경고: 도입부가 그날 다루는 실제 프로젝트·모델 이름을 두 개 미만으로 언급합니다. 발행 전에 도입부를 다듬어 주세요.")

    blocked = [term for term in BLOCKED_TERMS if term in body]
    checks["no_restricted_topic_signal"] = not blocked
    if blocked:
        errors.append("제한 가능성이 높은 주제 신호가 있어 수동 정책 검토가 필요합니다: " + ", ".join(blocked))

    checks["contact_configured"] = "@" in str(site.get("contact_email", "")) and "example.com" not in str(site.get("contact_email", ""))
    if not checks["contact_configured"]:
        errors.append("실제 문의 이메일을 config/site.json에 설정해야 합니다.")
    checks["author_configured"] = str(site.get("author_name", "")) not in {"", "작성자", "작성자 이름"}
    if not checks["author_configured"]:
        errors.append("실제 작성자 이름과 소개를 config/site.json에 설정해야 합니다.")
    blog_url = str(site.get("blog_url", ""))
    checks["blog_url_configured"] = blog_url.startswith(("https://", "http://")) and "example." not in blog_url
    if not checks["blog_url_configured"]:
        errors.append("실제 티스토리 블로그 주소를 config/site.json에 설정해야 합니다.")

    return QualityReport(
        status="READY_FOR_MANUAL_REVIEW" if not errors else "BLOCKED",
        errors=errors,
        warnings=warnings,
        checks=checks,
        manual_review_required=True,
    )
