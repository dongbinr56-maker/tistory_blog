import json
import unittest
from unittest.mock import patch

from tistory_newsroom.generate import (
    _gate_repair_reasons,
    _request_json,
    _response_text,
    make_rewrite_prompt,
    merge_title_candidates,
    newsroom_title_candidates,
)
from tistory_newsroom.models import SourceItem


class GateRepairTest(unittest.TestCase):
    def _secondary_source(self):
        return [
            SourceItem(
                id="a", source="www.thevccorner.com", topic="생성형 AI", title="SaaS 기사",
                url="https://www.thevccorner.com/post", published_at="", summary="AI 에이전트와 SaaS에 대한 분석 기사입니다.",
            )
        ]

    def test_flags_short_fields_and_missing_attribution(self):
        draft = {"sections": [{
            "source_ids": ["a"],
            "what_happened": "귀속 없이 쓴 사실 요약입니다.",
            "plain_explanation": "짧은 설명",
            "why_it_matters": "영" * 60,
            "editorial_take": "판" * 130,
            "reader_action": "행" * 45,
        }]}
        reasons = _gate_repair_reasons(draft, self._secondary_source())
        self.assertTrue(any("plain_explanation" in reason for reason in reasons))
        self.assertTrue(any("www.thevccorner.com" in reason for reason in reasons))

    def test_accepts_attribution_written_without_the_www_prefix(self):
        draft = {"sections": [{
            "source_ids": ["a"],
            "what_happened": "thevccorner.com의 분석에 따르면 SaaS의 가치가 업무 완결로 이동하고 있습니다.",
            "plain_explanation": "설" * 90,
            "why_it_matters": "영" * 60,
            "editorial_take": "판" * 130,
            "reader_action": "행" * 45,
        }]}
        self.assertEqual(_gate_repair_reasons(draft, self._secondary_source()), [])


class ResponseParsingTest(unittest.TestCase):
    def test_blocked_response_reports_the_block_reason(self):
        with self.assertRaises(ValueError) as context:
            _response_text({"promptFeedback": {"blockReason": "SAFETY"}})
        self.assertIn("SAFETY", str(context.exception))

    def test_truncated_response_reports_the_finish_reason(self):
        result = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": '{"partial": '}]}}]}
        with self.assertRaises(ValueError) as context:
            _response_text(result)
        self.assertIn("MAX_TOKENS", str(context.exception))

    def test_multi_part_text_is_joined(self):
        result = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"a"'}, {"text": ": 1}"}]}}]}
        self.assertEqual(_response_text(result), '{"a": 1}')

    def test_api_key_travels_in_a_header_not_the_url(self):
        captured = {}

        class _FakeResponse:
            def read(self):
                payload = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "{}"}]}}]}
                return json.dumps(payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["key"] = request.get_header("X-goog-api-key")
            return _FakeResponse()

        with patch("tistory_newsroom.generate.urllib.request.urlopen", side_effect=fake_urlopen):
            _request_json("https://example.googleapis.com/v1beta/models/m:generateContent", "secret-key", "프롬프트", 0.2)
        self.assertEqual(captured["key"], "secret-key")
        self.assertNotIn("secret-key", captured["url"])


class GeneratePromptTest(unittest.TestCase):
    def test_rewrite_prompt_includes_the_triggered_reasons(self):
        source = SourceItem(
            id="ecc",
            source="GitHub",
            topic="AI 에이전트",
            title="affaan-m/ECC",
            url="https://github.com/affaan-m/ECC",
            published_at="2026-07-11T07:00:00+09:00",
            summary="AI 에이전트 하네스 프로젝트",
            official_url="https://github.com/affaan-m/ECC",
            verification={"project_name": "affaan-m/ECC"},
        )
        prompt = make_rewrite_prompt("2026-07-11", [source], {"intro": "", "sections": []}, ["도입부가 일반적입니다."])
        self.assertIn("도입부가 일반적입니다.", prompt)
        self.assertIn("ECC", prompt)

    def _sources(self):
        return [
            SourceItem(
                id="first", source="GitHub", topic="AI 모델링", title="owner/first-project",
                url="https://github.com/owner/first-project", published_at="", summary="공식 프로젝트입니다.",
                official_url="https://github.com/owner/first-project", verification={"project_name": "owner/first-project"},
            ),
            SourceItem(
                id="second", source="GitHub", topic="AI 에이전트", title="owner/second-project",
                url="https://github.com/owner/second-project", published_at="", summary="공식 프로젝트입니다.",
                official_url="https://github.com/owner/second-project", verification={"project_name": "owner/second-project"},
            ),
        ]

    def test_fallback_titles_keep_the_newsroom_format(self):
        candidates = newsroom_title_candidates(self._sources())

        self.assertEqual(len(candidates), 3)
        self.assertEqual(len({candidate.casefold() for candidate in candidates}), 3)
        self.assertTrue(all(candidate.startswith("[AI 뉴스룸] | ") for candidate in candidates))
        self.assertIn("first-project", candidates[0])

    def test_merged_titles_prefer_the_model_and_keep_one_fixed_format_fallback(self):
        merged = merge_title_candidates({
            "title": "first-project가 바꾸는 에이전트 평가 흐름",
            "title_candidates": [
                "first-project가 바꾸는 에이전트 평가 흐름",
                "second-project 도입 전에 확인할 세 가지",
                "에이전트 평가와 배포, 이번 주에 짚어볼 지점",
            ],
        }, self._sources())

        self.assertEqual(merged[0], "first-project가 바꾸는 에이전트 평가 흐름")
        self.assertEqual(len(merged), 4)
        self.assertEqual(sum(candidate.startswith("[AI 뉴스룸] | ") for candidate in merged), 1)
        self.assertTrue(all(15 <= len(candidate) <= 75 for candidate in merged))

    def test_merged_titles_skip_invalid_model_output_and_fill_from_the_fallback(self):
        merged = merge_title_candidates({
            "title": "AI 에이전트 성능과 복잡한 운영 환경, 배포 보안, 규제 이슈, 서비스 안정성, 모델 활용 전략까지 모두 한 번에 설명하는 지나치게 긴 제목입니다",
            "title_candidates": ["짧은 제목", "ECC와 HimitsuShell: AI 배포에서 먼저 볼 두 가지"],
        }, self._sources())

        self.assertEqual(merged[0], "ECC와 HimitsuShell: AI 배포에서 먼저 볼 두 가지")
        self.assertGreaterEqual(len(merged), 3)
        self.assertEqual(len({candidate.casefold() for candidate in merged}), len(merged))
