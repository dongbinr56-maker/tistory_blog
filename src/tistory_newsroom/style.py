from __future__ import annotations

import re
from typing import Iterable

from .models import SourceItem


# These phrases are not inherently wrong Korean. In a daily technical digest,
# however, they repeatedly signal a padded, generic AI summary instead of an
# editor's concrete reading of the sources.
GENERIC_EDITORIAL_MARKERS = (
    "AI 기술이 빠르게 발전",
    "AI 에이전트의 복잡성이 심화",
    "오늘 살펴볼 소식",
    "오늘 공유할 소식",
    "독자 여러분",
    "함께 살펴보",
    "실질적인 고민",
    "실질적인 인사이트",
    "균형점을 탐색",
    "가치를 창출",
    "다음 주에도",
    "AI 시대를 이끌어갈",
    "오늘 살펴본 소식들은",
    "AI 엔지니어링이 단순히",
    "다층적인 과제",
    "핵심 역량",
    "중요한 역할을 합니다",
    "중요한 역할을 할",
    "중요한 참고 자료",
    "의미가 큽니다",
    "확장이 기대됩니다",
    "상기시킵니다",
    "단면들입니다",
    "다시금 생각하게 합니다",
)


# Fixed strings alone lose the blocklist game: the model swaps "다층적인 과제"
# for "다층적인 도전" and passes. Patterns with usage limits catch the habit
# instead of one spelling of it. A limit of N flags the (N+1)th occurrence.
GENERIC_PATTERN_RULES: tuple[tuple[str, int, str], ...] = (
    (r"마치[^.!?]{0,40}(?:처럼|같이|같은|같아서)", 1, "'마치 ~처럼' 식 비유"),
    (r"기여(?:합니다|할 것입니다|하고 있습니다)", 1, "'~에 기여합니다' 식 마무리"),
    (r"(?:중요한|결정적인|핵심적인)\s?(?:역할|기반|과제|요소|계기)", 1, "'중요한/결정적인/핵심적인 역할·기반·과제' 식 수식"),
    (r"필수적입니다", 1, "'필수적입니다' 단정"),
    (r"(?:빠르게|급속히|비약적으로)\s?(?:발전|진화|성장|확산)", 0, "'AI가 빠르게 발전한다' 식 배경 설명"),
    (r"다층적", 0, "'다층적' 수식"),
    (r"새로운 (?:가능성|지평|장을)", 0, "'새로운 가능성을 제시한다' 식 전망"),
    (r"보여줍니다", 1, "'~을 보여줍니다' 식 결론"),
    (r"가능하게 (?:합니다|하는|하여|해\b)", 1, "'~을 가능하게 합니다' 식 문장"),
    (r"진입 장벽을 낮", 0, "'진입 장벽을 낮춘다' 상투구"),
    (r"생산성[을과이]\s?(?:크게 )?(?:높|향상|끌어올)", 1, "'생산성을 높입니다' 상투구"),
    (r"(?:될|할 수 있을) 것입니다", 2, "'~할 수 있을 것입니다' 식 막연한 전망"),
)


def generic_editorial_markers(text: str) -> list[str]:
    return [marker for marker in GENERIC_EDITORIAL_MARKERS if marker in text]


def generic_pattern_reasons(text: str) -> list[str]:
    reasons: list[str] = []
    for pattern, limit, label in GENERIC_PATTERN_RULES:
        count = len(re.findall(pattern, text))
        if count > limit:
            reasons.append(
                f"{label} 표현이 {count}회 나타납니다(허용 {limit}회). 관찰한 사실과 조건, 트레이드오프를 담은 문장으로 바꾸세요."
            )
    return reasons


def _shares_long_run(first: str, second: str, run: int = 18) -> bool:
    a = re.sub(r"\s+", "", first)
    b = re.sub(r"\s+", "", second)
    if len(a) < run or len(b) < run:
        return False
    chunks = {a[index:index + run] for index in range(len(a) - run + 1)}
    return any(b[index:index + run] in chunks for index in range(len(b) - run + 1))


def section_overlap_reasons(section_pairs: Iterable[tuple[str, str]]) -> list[str]:
    """Flag sections whose impact analysis repeats the editorial take almost verbatim."""
    reasons: list[str] = []
    for number, (why_it_matters, editorial_take) in enumerate(section_pairs, start=1):
        if _shares_long_run(why_it_matters, editorial_take):
            reasons.append(
                f"{number}번째 이슈의 영향 분석(why_it_matters)과 작성자 관점(editorial_take)이 같은 문장을 반복합니다. 두 필드는 서로 다른 내용을 담아야 합니다."
            )
    return reasons


def _source_aliases(source: SourceItem) -> list[str]:
    aliases: list[str] = []
    for candidate in (source.verification.get("project_name", ""), source.title):
        value = candidate.strip()
        if value and value not in aliases:
            aliases.append(value)
        if "/" in value:
            tail = value.rsplit("/", 1)[-1].strip()
            if len(tail) >= 3 and tail not in aliases:
                aliases.append(tail)
        for separator in (" – ", " - ", ":"):
            if separator in value:
                leading = value.split(separator, 1)[0].strip()
                if len(leading) >= 3 and leading not in aliases:
                    aliases.append(leading)
    return aliases


def project_aliases(sources: Iterable[SourceItem]) -> list[str]:
    """Extract one readable, distinct project name per selected source."""
    names: list[str] = []
    for source in sources:
        aliases = _source_aliases(source)
        if aliases and aliases[0] not in names:
            names.append(aliases[0])
    return names


def mentioned_projects(text: str, sources: Iterable[SourceItem]) -> list[str]:
    lowered = text.lower()
    mentioned: list[str] = []
    for source in sources:
        aliases = _source_aliases(source)
        if not aliases:
            continue
        project_name = aliases[0]
        if any(len(alias) >= 3 and alias.lower() in lowered for alias in _source_aliases(source)):
            if project_name not in mentioned:
                mentioned.append(project_name)
    return mentioned
