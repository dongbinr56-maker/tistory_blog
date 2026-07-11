from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any

from .models import Draft, SourceItem
from .style import generic_editorial_markers, mentioned_projects, project_aliases


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
- 독자는 AI를 처음 접하는 일반인부터 실무 AI 엔지니어까지다. plain_explanation에서는 일상어로 2~3문장 안에 풀어 쓰되, 억지 비유를 반복하지 않습니다. why_it_matters와 editorial_take에서는 모델·에이전트·배포·오픈소스 관점의 실무적 의미와 트레이드오프를 자연스러운 문장으로 설명합니다.
- 원문을 복제·번역·문장 치환하지 말고, 사실을 짧게 요약한 뒤 독자에게 새로운 가치를 주는 분석을 작성합니다.
- 각 이슈에서 what_happened(확인된 사실), plain_explanation(일반인 설명), why_it_matters(영향), editorial_take(엔지니어 관점), reader_action(직접 해볼 점검)을 제공하되, 필드명 자체를 본문에서 되풀이하지 않습니다. editorial_take에는 단순 칭찬 대신 도입 전에 확인할 조건·한계·대안을 최소 하나 포함합니다.
- 모델 구조·학습 데이터·라이선스·성능 수치·GitHub 스타 수·Hugging Face 다운로드 수는 입력 verification에 실제 값이 있을 때만 자연스러운 문장으로 인용합니다. 값이 없으면 그 항목을 언급하지 않습니다.
- 표, JSON, 사전, 체크리스트 형태로 "모델: 해당 없음" 같은 빈 항목을 나열하지 않습니다. 모델과 직접 관련 없는 도구라면 그 도구가 해결하는 개발 문제와 사용 흐름만 설명합니다.
- 출처에 없는 숫자, 인용, 사건, 제품 기능을 지어내지 않습니다. 불확실하면 단정하지 않습니다.
- 선정적 제목, 광고 클릭 유도, 의료·법률·투자 조언, 타사 비방을 쓰지 않습니다.
- 모든 섹션의 source_ids에는 아래 입력의 id를 하나 이상 넣습니다.
- 제목 후보 3개는 서로 다르게 만들되 과장·낚시를 피하고, 오늘 다루는 핵심 모델·프로젝트 이름을 자연스럽게 포함합니다. 태그는 5~8개, # 없이 작성합니다.
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
- 일반인 설명에는 비유를 최대 한 번만 쓰고, 과장된 말투·강의안 말투·독자 호명은 피합니다.
- "AI 기술이 빠르게 발전", "오늘 살펴볼 소식", "독자 여러분", "함께 살펴보", "실질적인 인사이트", "가치를 창출", "다음 주에도"는 절대 쓰지 않습니다.
- `editorial_disclosure`는 빈 문자열로 둡니다. 공개 글 안에 작성 방식이나 검토 과정에 관한 언급을 넣지 않습니다.
- JSON 구조와 모든 section의 source_ids는 유지합니다. 다른 문장 없이 JSON 하나만 반환합니다.

날짜: {date}

[확인된 출처]
{source_payload}

[다시 편집할 초안]
{draft_payload}

[다시 편집해야 하는 이유]
{marker_payload}
"""


def _request_json(endpoint: str, prompt: str, temperature: float) -> dict[str, Any]:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        },
    }
    payload = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.loads(response.read().decode("utf-8"))
    text = result["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(_strip_json_fence(text))
    if not isinstance(parsed, dict):
        raise ValueError("Gemini가 JSON 객체를 반환하지 않았습니다.")
    return parsed


def _rewrite_reasons(draft: dict[str, Any], sources: list[SourceItem]) -> list[str]:
    reasons = generic_editorial_markers(_draft_text(draft))
    if len(mentioned_projects(str(draft.get("intro") or ""), sources)) < 2:
        reasons.append("도입부가 실제로 다루는 프로젝트 이름을 최소 두 개 직접 언급하지 않았습니다.")
    return reasons


def generate_with_gemini(date: str, sources: list[SourceItem], site: dict[str, Any]) -> Draft:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 없습니다. .env.example과 README의 설정 절차를 확인하세요.")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
    encoded_key = urllib.parse.quote(api_key, safe="")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={encoded_key}"
    last_error: Exception | None = None
    for retry in range(3):
        try:
            raw_draft = _request_json(endpoint, make_prompt(date, sources, site), temperature=0.35)
            raw_draft["date"] = date
            raw_draft["model"] = model
            raw_draft["editorial_disclosure"] = ""
            for _ in range(2):
                reasons = _rewrite_reasons(raw_draft, sources)
                if not reasons:
                    break
                raw_draft = _request_json(endpoint, make_rewrite_prompt(date, sources, raw_draft, reasons), temperature=0.5)
                raw_draft["date"] = date
                raw_draft["model"] = model
                raw_draft["editorial_disclosure"] = ""
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
    titles = [
        f"{date} AI 모델·에이전트 브리핑: GitHub·Hugging Face 프로젝트와 실무 포인트",
        f"AI 엔지니어 데일리: 모델·에이전트·오픈소스 프로젝트 {len(sources)}건 분석",
        f"오늘의 AI 모델 뉴스 | 프로젝트 검증부터 배포 판단까지",
    ]
    lead_projects = ", ".join(project_aliases(sources)[:2])
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
