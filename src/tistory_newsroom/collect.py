from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as etree
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any

from .models import SourceItem

USER_AGENT = "TistoryNewsroom/0.2 (+https://github.com/)"
KST = dt.timezone(dt.timedelta(hours=9))
TOPIC_TERMS: dict[str, tuple[str, ...]] = {
    "생성형 AI": ("생성형 ai", "generative ai", "llm", "언어 모델", "foundation model", "claude", "anthropic", "gemini", "chatgpt", "openai"),
    "AI 에이전트": ("ai 에이전트", "agentic", "agent", "에이전트", "멀티 에이전트"),
    "컴퓨터 비전": ("컴퓨터 비전", "computer vision", "vision model", "비전 모델", "이미지 모델"),
    "AI 모델링": ("모델 학습", "파인튜닝", "fine-tuning", "추론", "inference", "훈련", "training"),
    "오픈소스": ("오픈소스", "open source", "라이선스", "license"),
    "개발 도구": ("개발 도구", "developer tool", "claude code", "codex", "cursor", "ide"),
    "GitHub 프로젝트": ("github.com", "github", "깃허브"),
    "Hugging Face": ("huggingface.co", "hugging face", "허깅페이스", "hf model", "hf space", "데이터셋"),
    "온디바이스 AI": ("온디바이스", "on-device", "on device", "로컬 ai", "local ai"),
    "NPU·GPU·엣지 AI": ("npu", "gpu", "edge ai", "엣지 ai", "tpu", "가속기"),
}
MODEL_TERMS = ("model", "모델", "llm", "transformer", "추론", "inference", "학습", "training", "파인튜닝", "fine-tuning", "checkpoint", "dataset", "데이터셋")


@dataclass(frozen=True)
class ListingCandidate:
    source: str
    listing_url: str
    listing_title: str


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.links: list[tuple[str, str]] = []
        self._link: tuple[str, list[str]] | None = None
        self._capture: str | None = None
        self._parts: list[str] = []
        self.h1: list[str] = []
        self.times: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {name.lower(): value or "" for name, value in attrs_list}
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key and attrs.get("content"):
                self.meta.setdefault(key, attrs["content"])
        elif tag == "link" and "canonical" in attrs.get("rel", "").lower() and attrs.get("href"):
            self.meta.setdefault("canonical", attrs["href"])
        elif tag == "a" and attrs.get("href"):
            self._link = (attrs["href"], [])
        elif tag in {"h1", "time", "title"}:
            self._capture = tag
            self._parts = []
            if tag == "time" and attrs.get("datetime"):
                self.times.append(attrs["datetime"])

    def handle_data(self, data: str) -> None:
        if self._link is not None:
            self._link[1].append(data)
        if self._capture is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._link is not None:
            href, parts = self._link
            self.links.append((href, _clean_text(" ".join(parts))))
            self._link = None
        if tag == self._capture:
            value = _clean_text(" ".join(self._parts))
            if value:
                if tag == "h1":
                    self.h1.append(value)
                elif tag == "time":
                    self.times.append(value)
                else:
                    self.meta.setdefault("title", value)
            self._capture = None
            self._parts = []


def _clean_text(value: str | None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def _absolute(url: str, base: str) -> str:
    return urllib.parse.urljoin(base, html.unescape(url))


def _fetch_bytes(url: str, accept: str = "text/html,*/*", attempts: int = 3) -> tuple[bytes, str]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "ko,en;q=0.8"})
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read(3_000_000), response.headers.get("Content-Type", "")
        except Exception as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"페이지 확인 실패: {url} ({last_error})")


def _fetch_text(url: str, accept: str = "text/html,*/*") -> str:
    body, _ = _fetch_bytes(url, accept)
    return body.decode("utf-8", "ignore")


def _parse_datetime(value: str | None) -> dt.datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            try:
                parsed = dt.datetime.fromisoformat(raw[:10])
            except ValueError:
                return None
    return parsed.replace(tzinfo=KST) if parsed.tzinfo is None else parsed.astimezone(KST)


def _metadata(page: str) -> dict[str, str]:
    parser = _PageParser()
    parser.feed(page)
    title = parser.meta.get("og:title") or parser.meta.get("twitter:title") or parser.meta.get("title") or (parser.h1[0] if parser.h1 else "")
    description = parser.meta.get("og:description") or parser.meta.get("description") or ""
    image = parser.meta.get("og:image") or parser.meta.get("twitter:image") or ""
    published = parser.meta.get("article:published_time") or ""
    if not published:
        matched = re.search(r'"datePublished"\s*:\s*"([^"]+)"', page)
        published = matched.group(1) if matched else ""
    if not published:
        published = parser.meta.get("date") or (parser.times[0] if parser.times else "")
    return {
        "title": _clean_text(title),
        "description": _clean_text(description),
        "image": _absolute(image, parser.meta.get("canonical") or "") if image else "",
        "published": _parse_datetime(published).isoformat() if _parse_datetime(published) else "",
        "site_name": _clean_text(parser.meta.get("og:site_name") or ""),
        "canonical": _absolute(parser.meta.get("canonical") or "", "") if parser.meta.get("canonical") else "",
    }


def _rss_listings(url: str, source: str, limit: int) -> list[ListingCandidate]:
    raw, _ = _fetch_bytes(url, "application/rss+xml,application/xml,text/xml,*/*")
    root = etree.fromstring(raw)
    listings: list[ListingCandidate] = []
    for item in root.findall("./channel/item")[:limit]:
        title = _clean_text(item.findtext("title"))
        link = _clean_text(item.findtext("link"))
        if title and link:
            listings.append(ListingCandidate(source, link, title))
    return listings


def _geeknews_listings(url: str, source: str, limit: int) -> list[ListingCandidate]:
    page = _fetch_text(url)
    parser = _PageParser()
    parser.feed(page)
    listings: list[ListingCandidate] = []
    seen: set[str] = set()
    for href, title in parser.links:
        absolute = _absolute(href, url)
        if "news.hada.io/topic?id=" not in absolute or absolute in seen or not title:
            continue
        seen.add(absolute)
        listings.append(ListingCandidate(source, absolute, title))
        if len(listings) == limit:
            break
    return listings


def _extract_geeknews_original(page: str, listing_url: str) -> str:
    matched = re.search(r'"sharedContent"\s*:\s*\{.*?"url"\s*:\s*"([^"]+)"', page, flags=re.DOTALL)
    if matched:
        return html.unescape(matched.group(1).replace("\\/", "/"))
    parser = _PageParser()
    parser.feed(page)
    for href, _ in parser.links:
        absolute = _absolute(href, listing_url)
        host = urllib.parse.urlparse(absolute).netloc.lower()
        if absolute.startswith("https://") and host and not host.endswith("news.hada.io"):
            return absolute
    return ""


def _find_official_url(*pages: str) -> str:
    pattern = r'https?://(?:www\.)?(?:github\.com|huggingface\.co)/(?:[^\s"<>?#]+)(?:/[^\s"<>?#]+)?'
    for page in pages:
        match = re.search(pattern, html.unescape(page), flags=re.IGNORECASE)
        if match:
            return match.group(0).rstrip(".,);]}")
    return ""


def _official_facts(url: str) -> dict[str, str]:
    parsed = urllib.parse.urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    facts: dict[str, str] = {"official_url": url}
    try:
        if parsed.netloc.lower().endswith("github.com") and len(parts) >= 2:
            owner, repo = parts[0], parts[1]
            api, _ = _fetch_bytes(f"https://api.github.com/repos/{owner}/{repo}", "application/vnd.github+json")
            data = json.loads(api.decode("utf-8"))
            facts.update({
                "project_name": str(data.get("full_name") or f"{owner}/{repo}"),
                "project_owner": str((data.get("owner") or {}).get("login") or owner),
                "project_description": str(data.get("description") or ""),
                "license": str((data.get("license") or {}).get("spdx_id") or (data.get("license") or {}).get("name") or ""),
                "updated_at": str(data.get("updated_at") or ""),
                "project_kind": "github",
            })
        elif parsed.netloc.lower().endswith("huggingface.co") and parts:
            kind = "models"
            model_id = "/".join(parts)
            if parts[0] in {"datasets", "spaces"} and len(parts) >= 3:
                kind, model_id = parts[0], "/".join(parts[1:])
            endpoint = f"https://huggingface.co/api/{kind}/{model_id}"
            api, _ = _fetch_bytes(endpoint, "application/json")
            data = json.loads(api.decode("utf-8"))
            facts.update({
                "project_name": str(data.get("id") or model_id),
                "project_owner": str(data.get("author") or (data.get("cardData") or {}).get("license") or ""),
                "project_description": str(data.get("description") or ""),
                "license": str((data.get("cardData") or {}).get("license") or data.get("license") or ""),
                "updated_at": str(data.get("lastModified") or ""),
                "project_kind": "huggingface",
            })
    except Exception:
        # Official metadata is a bonus, never an excuse to invent a value.
        return facts
    return facts


def _topics(text: str, official_url: str) -> list[str]:
    lowered = (text + " " + official_url).lower()
    return [topic for topic, terms in TOPIC_TERMS.items() if any(term in lowered for term in terms)]


def _canonical(url: str, official_url: str) -> str:
    value = official_url or url
    parsed = urllib.parse.urlparse(value)
    clean = parsed._replace(query="", fragment="")
    return urllib.parse.urlunparse(clean).rstrip("/").lower()


def _verify_listing(candidate: ListingCandidate, now: dt.datetime, lookback_hours: int) -> SourceItem | None:
    listing_page = _fetch_text(candidate.listing_url)
    listing_meta = _metadata(listing_page)
    source_page = listing_page
    source_meta = listing_meta
    article_url = candidate.listing_url
    introduced_at = ""
    if candidate.source == "GeekNews":
        introduced_at = listing_meta["published"]
        article_url = _extract_geeknews_original(listing_page, candidate.listing_url)
        if not article_url:
            return None
        source_page = _fetch_text(article_url)
        source_meta = _metadata(source_page)
    published = source_meta["published"] or introduced_at
    recent_time = _parse_datetime(introduced_at or published)
    if recent_time is None or recent_time < now - dt.timedelta(hours=lookback_hours) or recent_time > now + dt.timedelta(minutes=10):
        return None
    title = source_meta["title"] or candidate.listing_title
    if not title:
        return None
    official_url = _find_official_url(source_page, listing_page)
    facts = _official_facts(official_url) if official_url else {}
    # Body HTML contains navigation, social links and CSS terms such as
    # "space". Only metadata verified for this actual article may determine
    # topical relevance; otherwise unrelated links get selected as AI news.
    evidence = " ".join((title, source_meta["description"], listing_meta["description"], official_url, facts.get("project_description", ""), facts.get("project_name", "")))
    matched_topics = _topics(evidence, official_url)
    if not matched_topics:
        return None
    source_name = source_meta["site_name"] or urllib.parse.urlparse(article_url).netloc
    digest = hashlib.sha256(_canonical(article_url, official_url).encode("utf-8")).hexdigest()[:16]
    verification = {
        "article_title_verified": title,
        "article_source_verified": source_name,
        "article_published_verified": published,
        "article_url_verified": article_url,
        "geeknews_listing_url": candidate.listing_url if candidate.source == "GeekNews" else "",
        **facts,
    }
    return SourceItem(
        id=f"{candidate.source.lower().replace(' ', '-')}-{digest}",
        source=source_name,
        topic=", ".join(matched_topics),
        title=title,
        url=article_url,
        published_at=published,
        summary=(source_meta["description"] or listing_meta["description"])[:1200],
        listing_url=candidate.listing_url,
        introduced_at=introduced_at,
        image_url=source_meta["image"] or listing_meta["image"],
        official_url=official_url,
        canonical_key=_canonical(article_url, official_url),
        verification=verification,
    )


def collect_candidates(config: dict[str, Any], now: dt.datetime | None = None) -> tuple[list[SourceItem], list[str]]:
    now = now or dt.datetime.now(KST)
    selection = config.get("selection", {})
    limit = int(selection.get("max_candidates_per_source", 15))
    lookback_hours = int(selection.get("lookback_hours", 24))
    errors: list[str] = []
    verified: list[SourceItem] = []
    seen: set[str] = set()
    for source in config.get("sources", []):
        try:
            if source.get("type") == "yozm_rss":
                listings = _rss_listings(str(source["url"]), str(source["name"]), limit)
            elif source.get("type") == "geeknews_html":
                listings = _geeknews_listings(str(source["url"]), str(source["name"]), limit)
            else:
                raise ValueError(f"지원하지 않는 수집기: {source.get('type')}")
            for listing in listings:
                try:
                    item = _verify_listing(listing, now, lookback_hours)
                    if item and item.canonical_key not in seen:
                        seen.add(item.canonical_key)
                        verified.append(item)
                except Exception as error:
                    errors.append(f"검증 제외: {listing.listing_url} ({error})")
        except Exception as error:
            errors.append(f"수집 실패: {source.get('name')} ({error})")
    return verified, errors


def _score(item: SourceItem) -> int:
    corpus = f"{item.title} {item.summary} {item.topic} {item.official_url}".lower()
    score = sum(5 for terms in TOPIC_TERMS.values() if any(term in corpus for term in terms))
    score += sum(2 for term in MODEL_TERMS if term in corpus)
    if item.verification.get("project_kind") in {"github", "huggingface"}:
        score += 20
    if item.official_url:
        score += 5
    return score


def choose_diverse(items: list[SourceItem], count: int, excluded_terms: list[str]) -> list[SourceItem]:
    """Choose up to three recent, verified items with one GitHub/HF item required."""
    blocked = [term.lower() for term in excluded_terms]
    eligible = [item for item in items if not any(term in f"{item.title} {item.summary}".lower() for term in blocked)]
    ordered = sorted(eligible, key=lambda item: (_score(item), item.published_at, item.title), reverse=True)
    project = next((item for item in ordered if item.verification.get("project_kind") in {"github", "huggingface"}), None)
    if project is None:
        return []
    selected = [project]
    seen_sources = {project.source}
    seen_topics = {project.topic}
    for item in ordered:
        if item in selected:
            continue
        if item.source in seen_sources and item.topic in seen_topics:
            continue
        selected.append(item)
        seen_sources.add(item.source)
        seen_topics.add(item.topic)
        if len(selected) == count:
            break
    return selected


def collection_payload(date: str, candidates: list[SourceItem], selected: list[SourceItem], errors: list[str]) -> dict[str, Any]:
    return {
        "date": date,
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "selection_rule": "최근 24시간 검증 기사 중 GitHub 또는 Hugging Face 공식 프로젝트 1건 이상 필수",
        "candidates": [item.to_dict() for item in candidates],
        "selected": [item.to_dict() for item in selected],
        "collector_errors": errors,
    }
