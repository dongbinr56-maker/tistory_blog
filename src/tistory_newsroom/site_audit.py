from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urljoin, urlparse


Fetch = Callable[[str], tuple[int, str]]
EVIDENCE_LABELS = ("검증 방식", "실행 여부", "확인일", "사용한 자료")


@dataclass
class LiveAuditResult:
    status: str
    post_urls: list[str]
    notice_urls: list[str]
    broken_internal_links: list[str]
    missing_evidence_urls: list[str]
    forbidden_public_urls: list[str]
    missing_representative_evidence: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.add(href)


def fetch_url(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "tistory-newsroom-live-audit/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            encoding = response.headers.get_content_charset() or "utf-8"
            return response.status, response.read().decode(encoding, errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, ValueError) as error:
        return 599, str(error)


def _sitemap_urls(xml: str) -> list[str]:
    root = ET.fromstring(xml)
    return [node.text.strip() for node in root.iter() if node.tag.endswith("loc") and node.text]


def _internal_links(base_url: str, page_url: str, html: str) -> set[str]:
    parser = _LinkParser()
    parser.feed(html)
    host = urlparse(base_url).netloc
    links: set[str] = set()
    for href in parser.links:
        if (
            href.startswith(("#", "javascript:", "mailto:", "tel:"))
            or any(character in href for character in "<>\r\n\t ")
        ):
            continue
        target = urljoin(page_url, href)
        parsed = urlparse(target)
        if parsed.netloc == host:
            links.add(parsed._replace(fragment="").geturl())
    return links


def audit_live_site(
    base_url: str,
    *,
    expected_post_count: int = 20,
    expected_notice_count: int = 4,
    forbidden_post_ids: tuple[int, ...] = (40, 44, 45, 46),
    representative_post_ids: tuple[int, ...] = (53, 64, 66),
    fetcher: Fetch = fetch_url,
) -> LiveAuditResult:
    base_url = base_url.rstrip("/") + "/"
    errors: list[str] = []
    sitemap_status, sitemap_xml = fetcher(urljoin(base_url, "sitemap.xml"))
    if sitemap_status != 200:
        return LiveAuditResult(
            status="BLOCKED",
            post_urls=[],
            notice_urls=[],
            broken_internal_links=[],
            missing_evidence_urls=[],
            forbidden_public_urls=[],
            missing_representative_evidence=[],
            errors=[f"sitemap.xml HTTP {sitemap_status}"],
        )

    try:
        urls = _sitemap_urls(sitemap_xml)
    except ET.ParseError as error:
        return LiveAuditResult(
            status="BLOCKED",
            post_urls=[],
            notice_urls=[],
            broken_internal_links=[],
            missing_evidence_urls=[],
            forbidden_public_urls=[],
            missing_representative_evidence=[],
            errors=[f"sitemap.xml parse error: {error}"],
        )

    post_urls = sorted(url for url in urls if re.search(r"/\d+$", url) and "/notice/" not in url)
    notice_urls = sorted(url for url in urls if re.search(r"/notice/\d+$", url))
    if len(post_urls) != expected_post_count:
        errors.append(f"expected {expected_post_count} public posts, found {len(post_urls)}")
    if len(notice_urls) != expected_notice_count:
        errors.append(f"expected {expected_notice_count} notices, found {len(notice_urls)}")

    forbidden_urls = {urljoin(base_url, str(post_id)) for post_id in forbidden_post_ids}
    forbidden_public_urls = sorted(forbidden_urls & set(post_urls))

    page_bodies: dict[str, str] = {}
    links: set[str] = set()
    for page_url in [base_url, *post_urls, *notice_urls]:
        status, body = fetcher(page_url)
        if status != 200:
            errors.append(f"{page_url} HTTP {status}")
            continue
        page_bodies[page_url] = body
        links.update(_internal_links(base_url, page_url, body))

    broken_internal_links = []
    for link in sorted(links):
        status, _ = fetcher(link)
        if status >= 400:
            broken_internal_links.append(f"{status} {link}")

    missing_evidence_urls = [
        url for url in post_urls
        if url in page_bodies and not all(label in page_bodies[url] for label in EVIDENCE_LABELS)
    ]
    missing_representative_evidence = []
    for post_id in representative_post_ids:
        url = urljoin(base_url, str(post_id))
        body = page_bodies.get(url, "")
        if url not in post_urls or "증거 자료" not in body or "별도 실행 증거 없음" in body:
            missing_representative_evidence.append(url)

    blocked = any(
        (
            errors,
            broken_internal_links,
            missing_evidence_urls,
            forbidden_public_urls,
            missing_representative_evidence,
        )
    )
    return LiveAuditResult(
        status="BLOCKED" if blocked else "READY_FOR_ADSENSE_REVIEW",
        post_urls=post_urls,
        notice_urls=notice_urls,
        broken_internal_links=broken_internal_links,
        missing_evidence_urls=missing_evidence_urls,
        forbidden_public_urls=forbidden_public_urls,
        missing_representative_evidence=missing_representative_evidence,
        errors=errors,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit the live Tistory site before an AdSense review request")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-posts", type=int, default=20)
    parser.add_argument("--expected-notices", type=int, default=4)
    args = parser.parse_args(argv)
    result = audit_live_site(
        args.base_url,
        expected_post_count=args.expected_posts,
        expected_notice_count=args.expected_notices,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status == "READY_FOR_ADSENSE_REVIEW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
