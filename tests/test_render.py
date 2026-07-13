import json
import tempfile
import unittest
from pathlib import Path

from tistory_newsroom.generate import generate_demo
from tistory_newsroom.models import SourceItem
from tistory_newsroom.quality import inspect_draft
from tistory_newsroom.render import _copy_page, render_article_html, write_outputs


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.site = {
            "blog_name": "테스트 블로그",
            "author_name": "테스터",
            "contact_email": "writer@myblog.kr",
            "blog_url": "https://myblog.tistory.com",
            "minimum_body_characters": 1500,
            "required_source_count": 3,
            "default_category": "IT",
        }
        self.sources = [
            SourceItem(
                f"id-{number}", "출처", "AI 모델링", f"이슈 {number}", f"https://example.org/{number}", "", "AI 모델 평가와 배포 조건을 설명합니다.",
                official_url="https://github.com/test/project" if number == 1 else "",
                verification={"project_kind": "github", "project_name": "test/project", "license": "MIT"} if number == 1 else {},
            )
            for number in range(1, 4)
        ]

    def test_article_escapes_unsafe_title(self):
        draft = generate_demo("2026-07-11", self.sources, self.site)
        draft.title = "<script>alert(1)</script> 안전한 제목입니다"
        article = render_article_html(draft, self.site)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", article)
        self.assertNotIn("<h1><script>", article)
        self.assertNotIn("기술적으로 확인한 내용", article)
        self.assertNotIn("오늘은 기준을 충족한 기사", article)
        self.assertNotIn("AI는 초안 작성", article)
        self.assertNotIn("발행 전 사람이", article)
        self.assertNotIn("<aside", article)

    def test_article_has_no_fixed_section_scaffolding(self):
        draft = generate_demo("2026-07-11", self.sources, self.site)
        article = render_article_html(draft, self.site)
        for label in ("이번 변화의 요점", "쉽게 풀어 보면", "실무에서 달라지는 점", "먼저 볼 지점", "확인해 볼 것", "ISSUE 0", "<h3>", "마무리</h2>", 'class="hero-image"'):
            self.assertNotIn(label, article)
        self.assertIn('class="action"', article)
        self.assertIn('class="sources"', article)
        self.assertIn('class="closing"', article)
        self.assertIn(".editor-note", article)

    def test_published_draft_page_is_noindex_wrapped(self):
        draft = generate_demo("2026-07-11", self.sources, self.site)
        report = inspect_draft(draft, self.site)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_outputs(root, draft, report, self.site)
            page = (root / "docs" / "tistory" / "2026-07-11.html").read_text(encoding="utf-8")
        self.assertTrue(page.startswith("<!doctype html"))
        self.assertIn('<meta name="robots" content="noindex,nofollow">', page)
        self.assertIn('<article class="tistory-newsroom"', page)
        self.assertIn("</article>", page)

    def test_copy_page_editor_note_is_an_optional_override(self):
        page = _copy_page([{"date": "2026-07-11", "title": "초안", "title_candidates": [], "tags": [], "quality_status": "OK", "publish_checklist": [], "html_path": "tistory/2026-07-11.html"}])
        self.assertIn("작성자 코멘트 (선택)", page)
        self.assertIn("applyEditorNote", page)
        self.assertNotIn("note.length<60", page)

    def test_article_includes_the_generated_editor_comment(self):
        draft = generate_demo("2026-07-11", self.sources, self.site)
        article = render_article_html(draft, self.site)
        self.assertIn('<section class="editor-note">', article)
        self.assertIn(draft.editor_comment[:20], article)

    def test_copy_page_shows_run_warnings(self):
        page = _copy_page([{"date": "2026-07-11", "title": "초안", "title_candidates": [], "tags": [], "quality_status": "OK", "publish_checklist": [], "warnings": ["수집 경고: 요즘IT 405"], "html_path": "tistory/2026-07-11.html"}])
        self.assertIn("실행 경고", page)
        self.assertIn("values(raw.warnings)", page)

    def test_review_surfaces_are_noindex(self):
        page = _copy_page([])
        self.assertIn('<meta name="robots" content="noindex,nofollow">', page)

    def test_outputs_include_copy_page(self):
        draft = generate_demo("2026-07-11", self.sources, self.site)
        report = inspect_draft(draft, self.site)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_outputs(root, draft, report, self.site)
            self.assertTrue((root / "docs" / "tistory" / "2026-07-11.html").exists())
            self.assertTrue((root / "docs" / "index.html").exists())
            self.assertTrue((root / "docs" / "adsense-checklist.html").exists())
            self.assertTrue((root / "docs" / "tistory-pages" / "index.html").exists())
            contact_page = (root / "docs" / "tistory-pages" / "contact.html").read_text(encoding="utf-8")
            self.assertIn("writer@myblog.kr", contact_page)
            self.assertNotIn("{{contact_email}}", contact_page)

    def test_policy_pages_resolve_josa_and_are_noindex(self):
        draft = generate_demo("2026-07-11", self.sources, self.site)
        report = inspect_draft(draft, self.site)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_outputs(root, draft, report, self.site)
            about = (root / "docs" / "tistory-pages" / "about.html").read_text(encoding="utf-8")
            privacy = (root / "docs" / "tistory-pages" / "privacy.html").read_text(encoding="utf-8")
        self.assertIn("테스터는", about)
        self.assertIn("테스트 블로그를", about)
        self.assertNotIn("은(는)", about)
        self.assertNotIn("을(를)", about)
        self.assertIn("테스트 블로그는", privacy)
        self.assertNotIn("초안", privacy)
        self.assertIn('<meta name="robots" content="noindex,nofollow">', privacy)
        self.assertIn("본문 HTML 복사", about)

    def test_copy_page_escapes_dynamic_values(self):
        page = _copy_page([{"date": "2026-07-11", "title": "</script><img src=x onerror=alert(1)>", "title_candidates": [], "tags": [], "quality_status": "OK", "publish_checklist": [], "html_path": "tistory/2026-07-11.html"}])
        self.assertIn("function escapeHtml", page)
        self.assertIn("<\\/script>", page)

    def test_copy_page_defaults_to_html_and_uses_one_article_source(self):
        page = _copy_page([{"date": "2026-07-11", "title": "초안", "title_candidates": [], "tags": [], "quality_status": "OK", "publish_checklist": [], "html_path": "tistory/2026-07-11.html"}])
        self.assertIn('aria-selected="true"', page)
        self.assertIn('data-tab="html"', page)
        self.assertIn('data-tab="view"', page)
        self.assertIn('frame.src=raw.html_path', page)
        self.assertIn("pageText.indexOf('<article'", page)
        self.assertIn("pageText.lastIndexOf('</article>')", page)

    def test_copy_page_can_dispatch_a_same_day_regeneration_without_storing_the_token(self):
        page = _copy_page(
            [{"date": "2026-07-11", "title": "초안", "title_candidates": [], "tags": [], "quality_status": "OK", "publish_checklist": [], "html_path": "tistory/2026-07-11.html"}],
            {"github_repository": "owner/repository", "github_branch": "main", "github_workflow_file": "daily-tistory-draft.yml"},
        )
        self.assertIn("원문 재생성", page)
        self.assertIn("/dispatches", page)
        self.assertIn("refresh:'true'", page)
        self.assertIn("GitHub fine-grained PAT", page)
        self.assertNotIn("localStorage", page)

    def test_fact_review_keeps_verified_metrics_out_of_the_article_body(self):
        draft = generate_demo("2026-07-11", self.sources, self.site)
        report = inspect_draft(draft, self.site)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_outputs(root, draft, report, self.site)
            metadata = json.loads((root / "docs/tistory/2026-07-11.json").read_text(encoding="utf-8"))
            self.assertIn("fact_review", metadata)
            self.assertEqual(metadata["fact_review"][0]["official_url"], "https://github.com/test/project")
            page = (root / "docs/index.html").read_text(encoding="utf-8")
            self.assertIn("사실·수치 검토", page)
            self.assertIn("fact_review", page)

    def test_copy_page_offers_the_hero_thumbnail_download(self):
        page = _copy_page([{
            "date": "2026-07-11", "title": "초안", "title_candidates": [], "tags": [], "quality_status": "OK",
            "publish_checklist": [], "html_path": "tistory/2026-07-11.html",
            "images": {"hero": {"url": "tistory/assets/2026-07-11/hero.png"}},
        }])
        self.assertIn("대표 이미지 다운로드", page)
        self.assertIn("본문에는 들어가지 않습니다", page)
        self.assertIn("downloadHero", page)
        self.assertIn("tistory-대표이미지-", page)
        self.assertNotIn("const thumbnail=current?.images?.thumbnail", page)
        self.assertIn("response.blob()", page)
