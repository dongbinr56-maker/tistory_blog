from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from typing import Any

from .models import Draft, SourceItem
from .quality import SECTION_MINIMUM_LENGTHS, names_source
from .style import (
    generic_editorial_markers,
    generic_pattern_reasons,
    mentioned_projects,
    project_aliases,
    section_overlap_reasons,
)

_FIELD_LABELS = {
    "plain_explanation": "일반인 설명(plain_explanation)",
    "why_it_matters": "영향 분석(why_it_matters)",
    "editorial_take": "작성자 판단(editorial_take)",
    "reader_action": "독자 행동 제안(reader_action)",
}


def _strip_json_fence(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s*```$", "", value).strip()


def make_prompt(date: str, sources: list[SourceItem], site: dict[str, Any]) -> str:
    source_payload = [item.to_dict() for item in sources]
    return f"""당신은 AI 엔지니어·ML 엔지니어·모델링 엔지니어를 위한 한국어 기술 블로그의 수석 편집자입니다. 아래 출처만 근거로 {date}의 티스토리 초안을 작성하세요.

가장 중요한 규칙:
- 글은 실제로 이 소식을 읽고 선별한 기술 블로그 편집자가 쓴 것처럼 작성합니다. 보도자료, AI 요약문, 강의안처럼 쓰지 말고, 첫 문장에서 오늘 이슈들을 함께 묶는 구체적인 관찰이나 판단을 제시합니다. "오늘의 초점은", "함께 살펴보겠습니다", "독자 여러분", "핵심적인", "중요한", "혁신", "실질적인 인사이트" 같은 상투어는 쓰지 않습니다.
- 문장을 일정한 길이·형식으로 반복하지 않습니다. 각 이슈마다 도입 방식과 문장 리듬을 다르게 하고, 모든 문단을 "~을 보여줍니다", "~에 기여합니다", "~가 중요합니다"로 끝내지 않습니다. 확인된 사실 다음에는 왜 그렇게 판단하는지 원인과 조건을 붙입니다.
- 독자는 AI를 처음 접하는 일반인부터 실무 AI 엔지니어까지다. plain_explanation에서는 일상어로 2~3문장 안에 풀어 씁니다. 비유("마치 ~처럼", "~와 같아서")는 글 전체를 통틀어 최대 한 번만 사용하고, 나머지 설명은 실제 동작과 사용 흐름으로 풀어냅니다.
- 원문을 복제·번역·문장 치환하지 말고, 사실을 짧게 요약한 뒤 독자에게 새로운 가치를 주는 분석을 작성합니다.
- 각 이슈에서 what_happened(확인된 사실), plain_explanation(일반인 설명), why_it_matters(영향), editorial_take(작성자 판단), reader_action(직접 해볼 점검)을 제공하되, 필드명 자체를 본문에서 되풀이하지 않습니다. why_it_matters는 이 사실이 실무 흐름에서 무엇을 바꾸는지 1~3문장으로 짧게 쓰고, editorial_take는 도입 전에 확인할 조건·한계·대안을 최소 하나 담은 작성자의 견해를 씁니다. 두 필드에 같은 내용이나 같은 문장을 반복하면 안 됩니다.
- 필드 최소 분량(공백 포함): plain_explanation 90자, why_it_matters 60자, editorial_take 130자, reader_action 45자. 분량을 채우려 수식어를 덧붙이지 말고 사실과 조건을 하나 더 담으세요.
- 마크다운 문법(백틱 `, 별표 강조, # 제목)을 어떤 필드에도 쓰지 않습니다. 프로젝트 이름은 기호 없이 그대로 씁니다.
- GitHub 스타·포크·Hugging Face 좋아요·다운로드 수, 사용량 한도, 성능 수치처럼 시점에 따라 달라지거나 오독되기 쉬운 숫자는 본문에 쓰지 않습니다. 이 값은 별도 검토 화면의 사실·수치 근거로만 남깁니다.
- official_url이 없는 항목은 2차 출처입니다. what_happened 첫 문장에서 반드시 해당 입력의 source 값을 표기 그대로 넣어 "요즘IT에 따르면"처럼 출처에 귀속하고(예: source가 "www.example.com"이면 "www.example.com"이라고 쓰기), 규제·법률·서비스 중단·회사 관계·인과관계는 입력 summary에 있어도 독립 사실처럼 단정하거나 확대 해석하지 않습니다.
- 표, JSON, 사전, 체크리스트 형태로 "모델: 해당 없음" 같은 빈 항목을 나열하지 않습니다. 모델과 직접 관련 없는 도구라면 그 도구가 해결하는 개발 문제와 사용 흐름만 설명합니다.
- 출처에 없는 숫자, 인용, 사건, 제품 기능을 지어내지 않습니다. 불확실하면 단정하지 않습니다.
- 선정적 제목, 광고 클릭 유도, 의료·법률·투자 조언, 타사 비방을 쓰지 않습니다.
- sections는 [입력 출처]의 항목마다 정확히 하나씩, 총 {len(sources)}개를 만듭니다. 어떤 출처도 빠뜨리거나 한 섹션에 합치지 않으며, 각 섹션의 source_ids에는 해당 입력의 id를 넣습니다.
- 제목 후보 3개는 문장 구조가 서로 다르게 만들되 과장·낚시를 피하고, 오늘 다루는 핵심 모델·프로젝트 이름을 자연스럽게 포함합니다. "[AI 뉴스룸]" 같은 고정 머리말·대괄호 접두사·날짜는 붙이지 않습니다. 태그는 5~8개, # 없이 작성하되 전날과 똑같은 조합이 되지 않게 그날 내용에서 뽑습니다.
- 전체 본문은 밀도 있게 쓰고, 각 editorial_take은 3문장 이상입니다. 뜬구름 잡는 생산성 조언, 억지로 모든 이슈를 AI 모델과 연결하는 설명, 일반론은 금지합니다.
- `editorial_disclosure`는 빈 문자열로 반환합니다. 이 값은 공개 본문에 표시하지 않는 내부 호환 필드입니다. AI 작성·검토 과정에 관한 문구나 변명은 본문, 도입, 마무리에 넣지 않습니다.

블로그: {site['blog_name']}
작성자: {site['author_name']}

반환 형식은 다른 문장 없이 JSON 하나입니다:
{{
  "date": "{date}",
  "title": "선택한 제목",
  "title_candidates": ["후보1", "후보2", "후보3"],
  "tags": ["태그"],
  "meta_description": "120~160자 설명",
  "intro": "2~3문단 도입",
  "sections": [{{
    "headline": "소제목",
    "source_ids": ["입력 id"],
    "what_happened": "사실 요약",
    "plain_explanation": "일반인도 이해할 쉬운 설명",
    "why_it_matters": "영향 분석",
    "editorial_take": "작성자 분석",
    "reader_action": "독자 행동 제안"
  }}],
  "closing": "마무리",
  "editorial_disclosure": ""
}}

[입력 출처]
{json.dumps(source_payload, ensure_ascii=False, indent=2)}
"""


def _draft_text(value: dict[str, Any]) -> str:
    sections = value.get("sections") if isinstance(value.get("sections"), list) else []
    section_text = [
        str(section.get(field) or "")
        for section in sections
        if isinstance(section, dict)
        for field in ("headline", "what_happened", "plain_explanation", "why_it_matters", "editorial_take", "reader_action")
    ]
    return " ".join([str(value.get("intro") or ""), str(value.get("closing") or ""), *section_text])


def make_rewrite_prompt(date: str, sources: list[SourceItem], draft: dict[str, Any], reasons: list[str]) -> str:
    """Ask for a factual rewrite when the first pass sounds like a generic digest."""
    source_payload = json.dumps([item.to_dict() for item in sources], ensure_ascii=False, indent=2)
    draft_payload = json.dumps(draft, ensure_ascii=False, indent=2)
    marker_payload = json.dumps(reasons, ensure_ascii=False)
    return f"""당신은 한국어 기술 블로그의 최종 편집자입니다. 아래 초안은 확인된 출처를 바탕으로 만들었지만, 너무 일반적인 AI 요약문처럼 들립니다. 사실과 source_ids를 보존하면서 전체 문장을 사람이 직접 읽고 쓴 기술 칼럼처럼 다시 써 주세요.

편집 원칙:
- 제목과 도입부는 "AI가 빠르게 발전한다" 같은 배경 설명으로 시작하지 않습니다. 세 개 항목을 관통하는 구체적인 긴장, 선택지, 또는 관찰로 바로 시작합니다. 도입부에는 아래 프로젝트 이름 가운데 둘 이상을 직접 넣습니다: {", ".join(project_aliases(sources)[:6])}.
- 출처에 없는 관계·수치·기능을 추가하지 않습니다. 특히 서로 무관한 회사·프로젝트를 연결하거나 추측을 사실처럼 쓰지 않습니다.
- 각 이슈에서 확인된 사실은 짧고 명확하게, 해석은 조건과 트레이드오프를 담아 씁니다. 막연한 생산성 향상, 혁신, 중요성, 기여 같은 결론으로 끝내지 않습니다.
- 비유("마치 ~처럼")는 글 전체에서 최대 한 번만 쓰고, 과장된 말투·강의안 말투·독자 호명은 피합니다. 문단을 "~에 기여합니다", "~할 수 있을 것입니다", "~을 보여줍니다"로 끝내지 않습니다.
- "AI 기술이 빠르게 발전", "오늘 살펴볼 소식", "독자 여러분", "함께 살펴보", "실질적인 인사이트", "가치를 창출", "다음 주에도"는 절대 쓰지 않습니다.
- why_it_matters와 editorial_take가 같은 내용을 반복하면 안 됩니다. 마크다운 문법(백틱 등)은 쓰지 않습니다.
- 필드 최소 분량(공백 포함)을 지킵니다: plain_explanation 90자, why_it_matters 60자, editorial_take 130자, reader_action 45자. 공식 페이지가 없는 2차 출처 이슈는 what_happened 첫 문장에 입력의 source 값을 표기 그대로 넣어 귀속을 유지합니다.
- `editorial_disclosure`는 빈 문자열로 둡니다. 공개 글 안에 작성 방식이나 검토 과정에 관한 언급을 넣지 않습니다.
- JSON 구조를 유지하고, [확인된 출처]의 모든 항목이 정확히 한 섹션씩 다뤄지게 합니다. 누락된 출처가 있으면 그 출처를 다루는 섹션을 새로 추가하고, 기존 섹션의 source_ids는 유지합니다. 다른 문장 없이 JSON 하나만 반환합니다.

날짜: {date}

[확인된 출처]
{source_payload}

[다시 편집할 초안]
{draft_payload}

[다시 편집해야 하는 이유]
{marker_payload}
"""


def _response_text(result: dict[str, Any]) -> str:
    """Extract the model text with a diagnosable error for each failure shape.

    Indexing result["candidates"][0]... raised a bare KeyError/IndexError on
    safety blocks, empty responses and truncation, so every failure looked
    identical after the retry loop.
    """
    candidates = result.get("candidates") or []
    if not candidates:
        feedback = result.get("promptFeedback") or {}
        raise ValueError(f"Gemini가 응답 후보를 반환하지 않았습니다 (blockReason: {feedback.get('blockReason') or 'unknown'})")
    candidate = candidates[0] or {}
    finish_reason = str(candidate.get("finishReason") or "")
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict))
    if not text.strip():
        raise ValueError(f"Gemini가 텍스트 없이 응답했습니다 (finishReason: {finish_reason or 'unknown'})")
    if finish_reason and finish_reason != "STOP":
        raise ValueError(f"Gemini 응답이 완결되지 않았습니다 (finishReason: {finish_reason})")
    return text


def _request_json(endpoint: str, api_key: str, prompt: str, temperature: float) -> dict[str, Any]:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            # Thinking tokens count against this cap on current Gemini models,
            # and a four-section Korean draft alone can pass 8k tokens — the
            # old 8192 cap truncated the JSON mid-response (MAX_TOKENS).
            "maxOutputTokens": 32768,
            "responseMimeType": "application/json",
        },
    }
    payload = json.dumps(body).encode("utf-8")
    # The key travels in a header, not the query string, so proxies, server
    # logs and error messages never see it.
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.loads(response.read().decode("utf-8"))
    parsed = json.loads(_strip_json_fence(_response_text(result)))
    if not isinstance(parsed, dict):
        raise ValueError("Gemini가 JSON 객체를 반환하지 않았습니다.")
    return parsed


def _section_field_pairs(draft: dict[str, Any]) -> list[tuple[str, str]]:
    sections = draft.get("sections") if isinstance(draft.get("sections"), list) else []
    return [
        (str(section.get("why_it_matters") or ""), str(section.get("editorial_take") or ""))
        for section in sections
        if isinstance(section, dict)
    ]


def _gate_repair_reasons(draft: dict[str, Any], sources: list[SourceItem]) -> list[str]:
    """Mirror the mechanical quality-gate checks so a rewrite fixes them first.

    Without this the gate blocked a whole day over a plain_explanation four
    characters short of the minimum — a defect the rewrite loop repairs
    trivially when told about it.
    """
    reasons: list[str] = []
    sections = draft.get("sections") if isinstance(draft.get("sections"), list) else []
    source_by_id = {source.id: source for source in sources}
    linked_ids = {
        str(source_id)
        for section in sections
        if isinstance(section, dict)
        for source_id in section.get("source_ids") or []
    }
    for source in sources:
        if source.id not in linked_ids:
            reasons.append(
                f"입력 출처 '{source.title}'(id: {source.id})가 어떤 섹션에도 연결되지 않았습니다. 이 출처를 다루는 섹션을 추가하고 source_ids에 id를 넣으세요."
            )
    tags = [str(tag).strip() for tag in draft.get("tags") or [] if str(tag).strip()]
    if not 5 <= len(set(tag.lower() for tag in tags)) <= 10:
        reasons.append(f"태그가 중복 없이 5~10개여야 하는데 현재 {len(tags)}개입니다.")
    for number, section in enumerate([item for item in sections if isinstance(item, dict)], start=1):
        for field, minimum in SECTION_MINIMUM_LENGTHS:
            length = len(str(section.get(field) or ""))
            if length < minimum:
                reasons.append(
                    f"{number}번째 이슈의 {_FIELD_LABELS.get(field, field)}이 {length}자로 짧습니다. 내용을 더 구체화해 {minimum}자 이상으로 쓰세요."
                )
        section_sources = [source_by_id[source_id] for source_id in section.get("source_ids") or [] if source_id in source_by_id]
        secondary = bool(section_sources) and all(not source.official_url for source in section_sources)
        what_happened = str(section.get("what_happened") or "")
        if secondary and "원문" not in what_happened and not any(names_source(what_happened, source.source) for source in section_sources):
            names = ", ".join(source.source for source in section_sources)
            reasons.append(
                f"{number}번째 이슈는 공식 페이지가 없는 2차 출처입니다. what_happened 첫 문장에 매체 이름({names})을 그대로 넣어 귀속하세요."
            )
    return reasons


def _rewrite_reasons(draft: dict[str, Any], sources: list[SourceItem]) -> list[str]:
    text = _draft_text(draft)
    reasons = (
        generic_editorial_markers(text)
        + generic_pattern_reasons(text)
        + section_overlap_reasons(_section_field_pairs(draft))
        + _gate_repair_reasons(draft, sources)
    )
    if len(mentioned_projects(str(draft.get("intro") or ""), sources)) < 2:
        reasons.append("도입부가 실제로 다루는 프로젝트 이름을 최소 두 개 직접 언급하지 않았습니다.")
    return reasons


def make_critic_prompt(draft: dict[str, Any]) -> str:
    draft_payload = json.dumps(
        {key: draft.get(key) for key in ("title", "intro", "sections", "closing")},
        ensure_ascii=False,
        indent=2,
    )
    return f"""당신은 한국어 기술 블로그의 외부 감수자입니다. 아래 초안이 사람 편집자가 직접 읽고 판단해 쓴 글로 읽히는지 엄격하게 평가하세요.

기계 생성 신호의 예: 모든 문단이 비슷한 길이와 리듬으로 반복됨, "~에 기여합니다"·"~할 수 있을 것입니다" 같은 결론 어미의 반복, 출처 없이 일반론으로 채운 문단, 비유 남용, 이슈마다 똑같은 문장 구조, 사실 대신 수식어가 많은 문장.

다른 문장 없이 JSON 하나만 반환합니다:
{{"reads_like_human_editor": true 또는 false, "problems": ["문제가 있는 문장과 이유를 구체적으로, 최대 5개"]}}

[평가할 초안]
{draft_payload}
"""


def _critic_reasons(endpoint: str, api_key: str, draft: dict[str, Any]) -> list[str]:
    """A semantic second net behind the pattern rules; never blocks the run by itself."""
    try:
        verdict = _request_json(endpoint, api_key, make_critic_prompt(draft), temperature=0.0)
    except Exception:
        return []
    if verdict.get("reads_like_human_editor", True):
        return []
    return [str(problem).strip() for problem in verdict.get("problems", []) if str(problem).strip()][:5]


def _issue_title_label(source: SourceItem, number: int) -> str:
    """Use a compact, recognizable project name in the fixed newsroom title."""
    raw = source.verification.get("project_name") or source.title
    label = raw.rsplit("/", 1)[-1].strip()
    label = re.sub(r"-(?:GGUF|quantized|instruct)$", "", label, flags=re.IGNORECASE)
    label = re.sub(r"\s+", " ", label).strip(" ,:|-–—")
    return label[:18].rstrip(" ,:|-–—") or f"AI 이슈 {number}"


def newsroom_title_candidates(sources: list[SourceItem]) -> list[str]:
    """Return three SEO-safe variants of the fixed newsroom title format."""
    labels: list[str] = []
    used: set[str] = set()
    for number, source in enumerate(sources[:3], start=1):
        label = _issue_title_label(source, number)
        key = label.casefold()
        if key in used:
            label = f"{label} {number}"
            key = label.casefold()
        labels.append(label)
        used.add(key)
    while len(labels) < 3:
        labels.append(f"AI 이슈 {len(labels) + 1}")
    first, second, third = labels[:3]
    return [
        f"[AI 뉴스룸] | {first}, {second}, {third}",
        f"[AI 뉴스룸] | {first}, {third}, {second}",
        f"[AI 뉴스룸] | {second}, {first}, {third}",
    ]


def merge_title_candidates(raw_draft: dict[str, Any], sources: list[SourceItem]) -> list[str]:
    """Prefer the model's daily titles; the fixed newsroom format is only a fallback.

    Publishing every post as "[AI 뉴스룸] | A, B, C" made the archive read as
    machine output, and the permuted candidates defeated the distinct-titles
    gate. The reviewer still gets one fixed-format option to choose from.
    """
    merged: list[str] = []
    seen: set[str] = set()

    def push(candidate: str) -> None:
        value = candidate.strip()
        if value and 15 <= len(value) <= 75 and value.casefold() not in seen:
            seen.add(value.casefold())
            merged.append(value)

    for candidate in [str(raw_draft.get("title") or ""), *(str(value) for value in raw_draft.get("title_candidates") or [])]:
        push(candidate)
    del merged[3:]
    fallbacks = newsroom_title_candidates(sources)
    push(fallbacks[0])
    for fallback in fallbacks[1:]:
        if len(merged) >= 3:
            break
        push(fallback)
    return merged


def generate_with_gemini(date: str, sources: list[SourceItem], site: dict[str, Any]) -> Draft:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 없습니다. .env.example과 README의 설정 절차를 확인하세요.")
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash").strip()
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    last_error: Exception | None = None
    for retry in range(3):
        try:
            raw_draft = _request_json(endpoint, api_key, make_prompt(date, sources, site), temperature=0.35)
            raw_draft["date"] = date
            raw_draft["model"] = model
            raw_draft["editorial_disclosure"] = ""
            for _ in range(2):
                reasons = _rewrite_reasons(raw_draft, sources)
                if not reasons:
                    # Pattern rules are cheap but literal; consult the model
                    # critic only once they pass, as a deeper reading.
                    reasons = _critic_reasons(endpoint, api_key, raw_draft)
                if not reasons:
                    break
                raw_draft = _request_json(endpoint, api_key, make_rewrite_prompt(date, sources, raw_draft, reasons), temperature=0.5)
                raw_draft["date"] = date
                raw_draft["model"] = model
                raw_draft["editorial_disclosure"] = ""
            raw_draft["title_candidates"] = merge_title_candidates(raw_draft, sources)
            raw_draft["title"] = raw_draft["title_candidates"][0]
            return Draft.from_dict(raw_draft, sources)
        except Exception as error:
            last_error = error
            if retry < 2:
                time.sleep(4 * (retry + 1))
    raise RuntimeError(f"Gemini 초안 생성 실패: {last_error}")


def generate_demo(date: str, sources: list[SourceItem], site: dict[str, Any]) -> Draft:
    """Deterministic local fixture: it tests rendering and policy gates without an API key."""
    sections = []
    for source in sources:
        project_name = source.verification.get("project_name") or source.title
        sections.append(
            {
                "headline": project_name,
                "source_ids": [source.id],
                "what_happened": (
                    f"{source.source}에서 {source.summary} 이번에 볼 만한 이유는 {project_name}이 실제 개발 흐름에서 어떤 병목을 건드리는지 가늠할 단서가 있기 때문입니다."
                ),
                "plain_explanation": (
                    "모델 하나를 잘 고르는 일과 그 모델을 업무에 쓸 수 있게 만드는 일은 다릅니다. "
                    "입력과 도구, 실패했을 때의 처리 방식까지 맞춰져야 결과가 반복 가능해집니다. 한 번 잘 나온 결과만으로는 충분하지 않습니다."
                ),
                "why_it_matters": (
                    "벤치마크 점수만으로는 운영에서의 차이를 설명하기 어렵습니다. 어떤 입력을 허용하는지, 어떤 도구를 연결하는지, 실패를 어디서 멈추는지가 "
                    "비용과 사용자 경험을 함께 바꿉니다. 그래서 도입 초기에 재현 가능한 평가 기준을 만드는 팀이 모델 교체도 더 차분하게 할 수 있습니다."
                ),
                "editorial_take": (
                    "도입 논의에서 먼저 고정할 것은 모델 이름이 아니라 인터페이스입니다. "
                    "입력 스키마, 프롬프트 버전, 도구 호출, 평가 샘플을 남겨야 모델을 바꾼 뒤 달라진 결과의 원인을 추적할 수 있습니다. "
                    "데모가 좋아 보인다고 바로 넓히기보다, 작은 대표 데이터셋에서 실패 사례까지 포함해 비교하는 편이 비용을 덜 치릅니다. "
                    "그 과정이 없으면 새 도구의 장점과 기존 시스템의 우연한 차이를 구분하기 어렵습니다."
                ),
                "reader_action": (
                    "이번 주 모델 호출 하나만 골라 입력 예시 20개와 기대 출력, 실패 기준을 적어 보세요. 새 후보는 같은 조건에서 비교해야 판단이 흔들리지 않습니다."
                ),
            }
        )
    aliases = project_aliases(sources)
    first = aliases[0] if aliases else "오늘의 프로젝트"
    second = aliases[1] if len(aliases) > 1 else "함께 살펴본 프로젝트"
    titles = [
        f"{first}부터 {second}까지, 오늘 확인한 개발 흐름",
        f"{first}와 {second}, 도입 전에 따져 볼 조건들",
        f"{first} 중심으로 본 오늘의 AI 프로젝트 점검",
    ]
    lead_projects = ", ".join(aliases[:2])
    raw = {
        "date": date,
        "title": titles[0],
        "title_candidates": titles,
        "tags": ["AI모델", "AI에이전트", "오픈소스AI", "GitHub", "HuggingFace", "ML엔지니어링"],
        "meta_description": f"{date}의 AI 모델·에이전트·오픈소스 프로젝트 {len(sources)}건을 일반인 설명과 엔지니어 검증 관점으로 정리했습니다.",
        "intro": (
            f"{lead_projects}는 쓰임새가 다르지만, 모델을 실제 환경에 넣을 때 생기는 주변부 문제를 건드립니다. "
            "에이전트의 실행 품질, 배포 스크립트의 경계, 그리고 새 도구를 평가하는 기준입니다.\n\n"
            "화제성만으로는 도입 이유가 되지 않습니다. 각 소식에서 실제로 확인할 수 있는 사실과, 팀에서 바로 점검할 질문을 나눠 정리했습니다."
        ),
        "sections": sections,
        "closing": (
            "새 프로젝트를 볼 때는 기능 목록보다 기존 흐름에서 무엇이 달라지는지 먼저 따져 보는 편이 낫습니다. "
            "오늘 언급한 항목 가운데 하나를 골라 작은 평가 세트에 적용해 보면, 화제와 적합성 사이의 거리가 금방 드러납니다."
        ),
        "editorial_disclosure": "",
        "model": "local-demo",
    }
    return Draft.from_dict(raw, sources)
