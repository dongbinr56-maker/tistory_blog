import unittest

from tistory_newsroom.site_audit import audit_live_site


BASE = "https://example.tistory.com/"


def sitemap(urls):
    rows = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset>{rows}</urlset>'


class LiveSiteAuditTest(unittest.TestCase):
    def test_ready_site_has_twenty_posts_four_notices_and_evidence(self):
        post_urls = [f"{BASE}{number}" for number in range(47, 67)]
        notice_urls = [f"{BASE}notice/{number}" for number in range(41, 45)]
        pages = {
            f"{BASE}sitemap.xml": (200, sitemap([BASE, *post_urls, *notice_urls])),
            BASE: (200, '<a href="/notice/41">소개</a>'),
        }
        evidence = "검증 방식 실행 여부 확인일 사용한 자료 증거 자료: 화면과 검증 메모"
        pages.update({url: (200, evidence) for url in post_urls})
        pages.update({url: (200, "신뢰 공지") for url in notice_urls})

        result = audit_live_site(BASE, fetcher=lambda url: pages.get(url, (200, "")))

        self.assertEqual(result.status, "READY_FOR_ADSENSE_REVIEW")
        self.assertEqual(result.broken_internal_links, [])
        self.assertEqual(result.missing_evidence_urls, [])

    def test_broken_footer_and_forbidden_posts_block_review(self):
        post_urls = [f"{BASE}{number}" for number in (40, *range(47, 67))]
        notice_urls = [f"{BASE}notice/{number}" for number in range(41, 45)]
        pages = {
            f"{BASE}sitemap.xml": (200, sitemap([BASE, *post_urls, *notice_urls])),
            BASE: (200, '<a href="/about">소개</a><a href="/privacy">개인정보</a>'),
            f"{BASE}about": (404, ""),
            f"{BASE}privacy": (404, ""),
        }
        pages.update({url: (200, "본문") for url in post_urls})
        pages.update({url: (200, "신뢰 공지") for url in notice_urls})

        result = audit_live_site(BASE, fetcher=lambda url: pages.get(url, (200, "")))

        self.assertEqual(result.status, "BLOCKED")
        self.assertIn(f"{BASE}40", result.forbidden_public_urls)
        self.assertEqual(len(result.broken_internal_links), 2)
        self.assertTrue(result.missing_evidence_urls)

    def test_code_like_href_is_not_crawled_as_a_real_link(self):
        post_urls = [f"{BASE}{number}" for number in range(47, 67)]
        notice_urls = [f"{BASE}notice/{number}" for number in range(41, 45)]
        pages = {
            f"{BASE}sitemap.xml": (200, sitemap([BASE, *post_urls, *notice_urls])),
            BASE: (200, '<a href="/<a href=https:/docs.example.com">코드 예시</a>'),
        }
        evidence = "검증 방식 실행 여부 확인일 사용한 자료 증거 자료: 화면과 검증 메모"
        pages.update({url: (200, evidence) for url in post_urls})
        pages.update({url: (200, "신뢰 공지") for url in notice_urls})

        def fetcher(url):
            self.assertNotIn("<", url)
            self.assertNotIn(" ", url)
            return pages.get(url, (200, ""))

        result = audit_live_site(BASE, fetcher=fetcher)

        self.assertEqual(result.status, "READY_FOR_ADSENSE_REVIEW")

    def test_invalid_sitemap_blocks_with_a_diagnosable_error(self):
        result = audit_live_site(BASE, fetcher=lambda _url: (200, "not xml"))

        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(result.errors)
