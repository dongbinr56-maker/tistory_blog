from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any

from .models import Draft, SourceItem


def _strip_json_fence(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s*```$", "", value).strip()


def make_prompt(date: str, sources: list[SourceItem], site: dict[str, Any]) -> str:
    source_payload = [item.to_dict() for item in sources]
    return f"""당신은 AI 엔지니어·ML 엔지니어·모델링 엔지니어를 위한 한국어 기술 블로그의 수석 편집자입니다. 아래 출처만 근거로 {date}의 티스토리 초안을 작성하세요.

가장 중요한 규칙:
- 독자는 AI를 처음 접하는 일반인부터 실무 AI 엔지니어까지다. 각 이슈를 plain_explanation에서 먼저 쉬운 비유와 일상어로 2~3문장 설명하고, why_it_matters와 editorial_take에서 모델·에이전트·배포·오픈소스 관점의 실무적 의미를 자연스러운 문장으로 설명합니다.
- 원문을 복제·번역·문장 치환하지 말고, 사실을 짧게 요약한 뒤 독자에게 새로운 가치를 주는 분석을 작성합니다.
- 각 이슈에서 what_happened(확인된 사실), plain_explanation(일반인 설명), why_it_matters(영향), editorial_take(엔지니어 관점), reader_action(직접 해볼 점검)을 명확히 분리합니다.
- 모델 구조·학습 데이터·라이선스·성능 수치·GitHub 스타 수·Hugging Face 다운로드 수는 입력 verification에 실제 값이 있을 때만 자연스러운 문장으로 인용합니다. 값이 없으면 그 항목을 언급하지 않습니다.
- 표, JSON, 사전, 체크리스트 형태로 "모델: 해당 없음" 같은 빈 항목을 나열하지 않습니다. 모델과 직접 관련 없는 도구라면 그 도구가 해결하는 개발 문제와 사용 흐름만 설명합니다.
- 출처에 없는 숫자, 인용, 사건, 제품 기능을 지어내지 않습니다. 불확실하면 단정하지 않습니다.
- 선정적 제목, 광고 클릭 유도, 의료·법률·투자 조언, 타사 비방을 쓰지 않습니다.
- 모든 섹션의 source_ids에는 아래 입력의 id를 하나 이상 넣습니다.
- 제목 후보 3개는 서로 다르게 만들되 과장·낚시를 피하고, 오늘 다루는 핵심 모델·프로젝트 이름을 자연스럽게 포함합니다. 태그는 5~8개, # 없이 작성합니다.
- 전체 본문은 밀도 있게 쓰고, 각 editorial_take은 3문장 이상입니다. 뜬구름 잡는 생산성 조언이나 일반론은 금지합니다.
- `editorial_disclosure`에는 "AI는 초안 작성에 활용했고, 발행 전 사람이 사실과 출처를 검토합니다."라는 취지의 문장을 포함합니다.

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
  "editorial_disclosure": "AI 활용 및 사람 검토 고지"
}}

[입력 출처]
{json.dumps(source_payload, ensure_ascii=False, indent=2)}
"""


def generate_with_gemini(date: str, sources: list[SourceItem], site: dict[str, Any]) -> Draft:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 없습니다. .env.example과 README의 설정 절차를 확인하세요.")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
    encoded_key = urllib.parse.quote(api_key, safe="")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={encoded_key}"
    body = {
        "contents": [{"parts": [{"text": make_prompt(date, sources, site)}]}],
        "generationConfig": {
            "temperature": 0.35,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        },
    }
    payload = json.dumps(body).encode("utf-8")
    last_error: Exception | None = None
    for retry in range(3):
        try:
            request = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            raw_draft = json.loads(_strip_json_fence(text))
            raw_draft["date"] = date
            raw_draft["model"] = model
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
                    f"{source.source} 원문은 {source.summary} 이 항목은 AI 모델을 실제 제품과 개발 흐름에 연결해 살펴볼 수 있는 출발점입니다."
                ),
                "plain_explanation": (
                    "이 소식은 AI를 더 똑똑하게 만드는 방법 자체보다, 이미 있는 모델을 사람들이 쓸 수 있는 도구로 옮기는 과정에 가깝습니다. "
                    "자동차의 엔진만 좋아도 운전하기 어렵다면 쓸모가 줄어드는 것처럼, 모델도 데이터·도구·검증 환경이 함께 갖춰져야 실제 가치가 생깁니다."
                ),
                "why_it_matters": (
                    "모델의 성능만 비교하는 방식은 이제 충분하지 않습니다. 어떤 입력을 허용하고, 어떤 도구를 연결하며, 실패를 어떻게 감지할지가 "
                    "사용자 경험과 운영 비용을 함께 결정하기 때문입니다. 특히 모델을 서비스에 넣는 팀은 재현 가능한 평가 기준을 먼저 만드는 편이 안전합니다."
                ),
                "editorial_take": (
                    "엔지니어 관점에서는 모델 이름을 바꾸는 일보다 인터페이스를 고정하는 일이 먼저입니다. "
                    "입력 스키마, 프롬프트 버전, 도구 호출, 평가 샘플을 기록해야 모델을 교체했을 때 성능 변화의 이유를 추적할 수 있습니다. "
                    "새 모델이나 저장소를 도입할 때도 데모의 인상보다 작은 대표 데이터셋에서 재현 가능한 실험을 만드는 편이 장기적으로 더 빠릅니다."
                ),
                "reader_action": (
                    "이번 주에 모델 호출 하나를 골라 입력 예시 20개, 기대 출력, 실패 기준을 표로 만든 뒤 현재 모델과 새 후보를 같은 조건에서 비교해 보세요."
                ),
            }
        )
    titles = [
        f"{date} AI 모델·에이전트 브리핑: GitHub·Hugging Face 프로젝트와 실무 포인트",
        f"AI 엔지니어 데일리: 모델·에이전트·오픈소스 프로젝트 {len(sources)}건 분석",
        f"오늘의 AI 모델 뉴스 | 프로젝트 검증부터 배포 판단까지",
    ]
    raw = {
        "date": date,
        "title": titles[0],
        "title_candidates": titles,
        "tags": ["AI모델", "AI에이전트", "오픈소스AI", "GitHub", "HuggingFace", "ML엔지니어링"],
        "meta_description": f"{date}의 AI 모델·에이전트·오픈소스 프로젝트 {len(sources)}건을 일반인 설명과 엔지니어 검증 관점으로 정리했습니다.",
        "intro": (
            "오늘의 초점은 AI 모델을 직접 만들거나, 팀의 제품에 붙이거나, 오픈소스 모델을 평가하는 사람에게 실제로 중요한 변화입니다. "
            "뉴스를 넓게 훑는 대신 모델·에이전트·컴퓨팅·오픈소스의 연결점만 골랐습니다.\n\n"
            "각 이슈는 먼저 쉬운 말로 설명하고, 이어서 엔지니어가 실제 도입 전에 확인할 판단 기준을 덧붙입니다. "
            "원문을 대신하지 않으므로 배포나 도입 판단 전에는 반드시 출처와 공식 프로젝트 페이지를 다시 확인해 주세요."
        ),
        "sections": sections,
        "closing": (
            "좋은 AI 뉴스는 모델 이름을 외우게 하기보다, 다음 실험의 가설을 더 선명하게 만듭니다. "
            "오늘의 프로젝트 중 하나를 골라 작은 평가 세트로 직접 확인해 보면, 화제성과 실제 적합성의 차이를 더 빨리 알 수 있습니다."
        ),
        "editorial_disclosure": "이 글은 공개된 출처를 바탕으로 재구성했습니다. AI는 초안 작성에 활용했고, 발행 전 사람이 사실과 출처를 검토합니다.",
        "model": "local-demo",
    }
    return Draft.from_dict(raw, sources)
