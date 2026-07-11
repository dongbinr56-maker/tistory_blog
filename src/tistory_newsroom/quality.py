from __future__ import annotations

import re

from .models import Draft, QualityReport

BLOCKED_TERMS = (
    "성인", "음란", "도박", "마약", "총기", "폭력 선동", "혐오",
)
CLICK_INDUCEMENT = (
    "광고를 클릭", "광고 클릭", "클릭해서 응원", "click ads",
)


def _body_text(draft: Draft) -> str:
    pieces = [draft.intro, draft.closing, draft.editorial_disclosure]
    for section in draft.sections:
        pieces.extend((section.headline, section.what_happened, section.plain_explanation, section.why_it_matters, section.technical_details, section.editorial_take, section.reader_action, section.verification_notes))
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

    checks["article_count_disclosed"] = bool(re.search(r"기사가?\s*\d+건", draft.article_count_note))
    if not checks["article_count_disclosed"]:
        errors.append("오늘 기준을 충족한 기사 수를 본문에 명시해야 합니다.")

    checks["tag_count_and_uniqueness"] = 5 <= len(draft.tags) <= 10 and len({tag.lower() for tag in draft.tags}) == len(draft.tags)
    if not checks["tag_count_and_uniqueness"]:
        errors.append("태그는 중복 없이 5~10개여야 합니다.")

    minimum_sources = int(site.get("required_source_count", 3))
    checks["sufficient_sources"] = len(draft.source_items) >= minimum_sources and all(item.url.startswith(("https://", "http://")) for item in draft.source_items)
    if not checks["sufficient_sources"]:
        errors.append(f"신뢰 가능한 원문 링크를 가진 출처가 {minimum_sources}개 이상 필요합니다.")

    checks["all_sections_trace_to_source"] = bool(draft.sections) and all(section.source_ids and set(section.source_ids) <= source_ids for section in draft.sections) and linked_ids == source_ids
    if not checks["all_sections_trace_to_source"]:
        errors.append("각 이슈는 출처 ID와 1:1로 추적 가능해야 하며, 선택된 모든 출처를 다뤄야 합니다.")

    checks["plain_language_and_technical_depth"] = all(len(section.plain_explanation) >= 90 and len(section.technical_details) >= 150 and len(section.verification_notes) >= 30 for section in draft.sections)
    if not checks["plain_language_and_technical_depth"]:
        errors.append("각 이슈에는 일반인 설명, 확인된 기술 정보, 검증 메모가 충분히 있어야 합니다.")

    checks["original_value_added"] = all(len(section.editorial_take) >= 130 and len(section.why_it_matters) >= 90 and len(section.reader_action) >= 45 for section in draft.sections)
    if not checks["original_value_added"]:
        errors.append("각 이슈에는 충분한 영향 분석·독자적 해설·독자 행동 제안이 필요합니다.")

    minimum_body = int(site.get("minimum_body_characters", 1500))
    checks["substantive_body"] = len(body) >= minimum_body
    if not checks["substantive_body"]:
        errors.append(f"본문은 최소 {minimum_body}자여야 합니다. 현재 {len(body)}자입니다.")

    checks["github_or_huggingface_project_included"] = any(item.verification.get("project_kind") in {"github", "huggingface"} and item.official_url for item in draft.source_items)
    if not checks["github_or_huggingface_project_included"]:
        errors.append("GitHub 또는 Hugging Face 공식 프로젝트가 최소 1건 포함되어야 합니다.")

    checks["ai_disclosure"] = "AI" in draft.editorial_disclosure and ("검토" in draft.editorial_disclosure or "확인" in draft.editorial_disclosure)
    if not checks["ai_disclosure"]:
        errors.append("AI 활용 및 사람 검토 고지가 필요합니다.")

    lowered = body.lower()
    checks["no_click_inducement"] = not any(term in lowered for term in CLICK_INDUCEMENT)
    if not checks["no_click_inducement"]:
        errors.append("광고 클릭을 유도하는 표현은 사용할 수 없습니다.")

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
