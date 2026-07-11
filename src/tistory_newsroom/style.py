from __future__ import annotations

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


def generic_editorial_markers(text: str) -> list[str]:
    return [marker for marker in GENERIC_EDITORIAL_MARKERS if marker in text]


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
