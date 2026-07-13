from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _prose(value: Any) -> str:
    """Normalize a model-written text field.

    Gemini occasionally wraps project names in markdown backticks, which the
    escaped Tistory HTML then shows literally. Strip them at the boundary.
    """
    return str(value or "").replace("`", "")


@dataclass(frozen=True)
class SourceItem:
    id: str
    source: str
    topic: str
    title: str
    url: str
    published_at: str
    summary: str
    listing_url: str = ""
    introduced_at: str = ""
    image_url: str = ""
    official_url: str = ""
    canonical_key: str = ""
    verification: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SourceItem":
        return cls(
            id=str(value.get("id") or value["url"]),
            source=str(value["source"]),
            topic=str(value.get("topic") or "IT"),
            title=str(value["title"]),
            url=str(value["url"]),
            published_at=str(value.get("published_at") or ""),
            summary=str(value.get("summary") or ""),
            listing_url=str(value.get("listing_url") or ""),
            introduced_at=str(value.get("introduced_at") or ""),
            image_url=str(value.get("image_url") or ""),
            official_url=str(value.get("official_url") or ""),
            canonical_key=str(value.get("canonical_key") or ""),
            verification={str(key): str(item) for key, item in dict(value.get("verification") or {}).items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ArticleSection:
    headline: str
    source_ids: list[str]
    what_happened: str
    plain_explanation: str
    why_it_matters: str
    technical_details: str
    editorial_take: str
    reader_action: str
    verification_notes: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ArticleSection":
        return cls(
            headline=_prose(value.get("headline")),
            source_ids=[str(item) for item in value.get("source_ids", [])],
            what_happened=_prose(value.get("what_happened")),
            plain_explanation=_prose(value.get("plain_explanation")),
            why_it_matters=_prose(value.get("why_it_matters")),
            technical_details=_prose(value.get("technical_details")),
            editorial_take=_prose(value.get("editorial_take")),
            reader_action=_prose(value.get("reader_action")),
            verification_notes=_prose(value.get("verification_notes")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Draft:
    date: str
    title: str
    title_candidates: list[str]
    tags: list[str]
    meta_description: str
    intro: str
    sections: list[ArticleSection]
    closing: str
    editorial_disclosure: str
    model: str
    article_count_note: str = ""
    images: dict[str, dict[str, str]] = field(default_factory=dict)
    source_items: list[SourceItem] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any], source_items: list[SourceItem]) -> "Draft":
        return cls(
            date=str(value["date"]),
            title=_prose(value.get("title")),
            title_candidates=[_prose(item) for item in value.get("title_candidates", [])],
            tags=[str(item).strip().lstrip("#").replace("`", "") for item in value.get("tags", []) if str(item).strip()],
            meta_description=_prose(value.get("meta_description")),
            intro=_prose(value.get("intro")),
            sections=[ArticleSection.from_dict(item) for item in value.get("sections", [])],
            closing=_prose(value.get("closing")),
            editorial_disclosure=str(value.get("editorial_disclosure") or ""),
            model=str(value.get("model") or "unknown"),
            article_count_note=str(value.get("article_count_note") or ""),
            images={str(key): {str(image_key): str(image_value) for image_key, image_value in dict(image).items()} for key, image in dict(value.get("images") or {}).items()},
            source_items=source_items,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "title": self.title,
            "title_candidates": self.title_candidates,
            "tags": self.tags,
            "meta_description": self.meta_description,
            "intro": self.intro,
            "sections": [section.to_dict() for section in self.sections],
            "closing": self.closing,
            "editorial_disclosure": self.editorial_disclosure,
            "model": self.model,
            "article_count_note": self.article_count_note,
            "images": self.images,
            "source_items": [item.to_dict() for item in self.source_items],
        }


@dataclass
class QualityReport:
    status: str
    errors: list[str]
    warnings: list[str]
    checks: dict[str, bool]
    manual_review_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
