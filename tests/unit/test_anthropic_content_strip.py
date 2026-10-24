"""Anthropic 2026-10-21 strips assistant documents + user citations (#1891)."""

from __future__ import annotations

from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.gateway.sampling import SamplingParams
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.router.anthropic_messages import apply_anthropic_version_content_compat
from daari.router.frontier import FrontierExecutor
import daari.router.frontier as frontier_mod


def _doc_block() -> dict:
    return {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": "AQID",
        },
        "citations": {"enabled": True},
    }


def _assistant_with_document() -> dict:
    return {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "see attached"},
            _doc_block(),
        ],
    }


def _user_with_citations() -> dict:
    return {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "quoted",
                "citations": [
                    {
                        "type": "char_location",
                        "cited_text": "x",
                        "document_index": 0,
                        "start_char_index": 0,
                        "end_char_index": 1,
                    }
                ],
            },
            {
                "type": "search_result",
                "source": "web",
                "title": "hit",
                "content": [
                    {
                        "type": "text",
                        "text": "nested",
                        "citations": [{"type": "char_location", "cited_text": "n"}],
                    }
                ],
            },
        ],
    }


def _user_tool_result_with_nested_document() -> dict:
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "toolu_1",
                "content": [
                    {"type": "text", "text": "fetched"},
                    _doc_block(),
                ],
            }
        ],
    }


def _payload_with_banned_content(*, version: str | None = "2026-10-21") -> dict:
    return {
        "model": "claude",
        "messages": [_assistant_with_document(), _user_with_citations()],
        "max_tokens": 50,
        "stream": False,
    }


def test_2026_10_21_strips_top_level_assistant_documents():
    payload = {
        "model": "claude",
        "messages": [_assistant_with_document(), {"role": "user", "content": "ok"}],
        "max_tokens": 50,
    }
    kinds = apply_anthropic_version_content_compat(payload, "2026-10-21")
    assistant = payload["messages"][0]
    assert assistant["content"] == [{"type": "text", "text": "see attached"}]
    assert "anthropic_document_stripped" in kinds


def test_2026_10_21_keeps_nested_documents_in_tool_results():
    payload = {
        "model": "claude",
        "messages": [_user_tool_result_with_nested_document()],
        "max_tokens": 50,
    }
    kinds = apply_anthropic_version_content_compat(payload, "2026-10-21")
    tool_content = payload["messages"][0]["content"][0]["content"]
    assert any(b.get("type") == "document" for b in tool_content)
    assert "anthropic_document_stripped" not in kinds


def test_2026_10_21_strips_user_and_search_result_citations():
    payload = {
        "model": "claude",
        "messages": [_user_with_citations()],
        "max_tokens": 50,
    }
    kinds = apply_anthropic_version_content_compat(payload, "2026-10-21")
    user_content = payload["messages"][0]["content"]
    assert "citations" not in user_content[0]
    assert "citations" not in user_content[1]["content"][0]
    assert "anthropic_citations_stripped" in kinds


def test_2026_10_21_keeps_document_citations_enabled_and_assistant_citations():
    payload = {
        "model": "claude",
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "answer",
                        "citations": [{"type": "char_location", "cited_text": "a"}],
                    },
                    _doc_block(),
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "text", "media_type": "text/plain", "data": "hi"},
                        "citations": {"enabled": True},
                    }
                ],
            },
        ],
        "max_tokens": 50,
    }
    apply_anthropic_version_content_compat(payload, "2026-10-21")
    assistant_text = payload["messages"][0]["content"][0]
    assert assistant_text["citations"] == [{"type": "char_location", "cited_text": "a"}]
    assert all(b.get("type") != "document" for b in payload["messages"][0]["content"])
    user_doc = payload["messages"][1]["content"][0]
    assert user_doc["citations"] == {"enabled": True}


def test_legacy_version_leaves_document_and_citations():
    payload = {
        "model": "claude",
        "messages": [_assistant_with_document(), _user_with_citations()],
        "max_tokens": 50,
    }
    kinds = apply_anthropic_version_content_compat(payload, "2023-06-01")
    assert kinds == []
    assert any(b.get("type") == "document" for b in payload["messages"][0]["content"])
    assert "citations" in payload["messages"][1]["content"][0]


def test_content_strip_records_soft_warnings_and_prometheus(monkeypatch):
    """Frontier _anthropic_payload records soft_warnings for content strips (#1891)."""
    metrics = Metrics()
    executor = FrontierExecutor(
        api_key="sk-ant-test",
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-0",
        provider="anthropic",
        metrics=metrics,
    )
    monkeypatch.setattr(
        frontier_mod,
        "to_anthropic_payload",
        lambda *a, **k: _payload_with_banned_content(),
    )
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        temperature=None,
        sampling=SamplingParams(max_tokens=50),
        meta=RequestMeta(anthropic_version="2026-10-21"),
    )
    out = executor._anthropic_payload(request, stream=False)
    assert all(b.get("type") != "document" for b in out["messages"][0]["content"])
    assert "citations" not in out["messages"][1]["content"][0]
    assert metrics.soft_warnings.get("anthropic_document_stripped") == 1
    assert metrics.soft_warnings.get("anthropic_citations_stripped") == 1
    text = render_prometheus(metrics)
    assert 'daari_soft_warnings_total{kind="anthropic_document_stripped"} 1' in text
    assert 'daari_soft_warnings_total{kind="anthropic_citations_stripped"} 1' in text


def test_content_strip_soft_warning_absent_when_clean_or_legacy(monkeypatch):
    metrics = Metrics()
    executor = FrontierExecutor(
        api_key="sk-ant-test",
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-0",
        provider="anthropic",
        metrics=metrics,
    )
    clean = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        temperature=None,
        sampling=SamplingParams(max_tokens=50),
        meta=RequestMeta(anthropic_version="2026-10-21"),
    )
    executor._anthropic_payload(clean, stream=False)
    assert metrics.soft_warnings.get("anthropic_document_stripped") is None
    assert metrics.soft_warnings.get("anthropic_citations_stripped") is None

    monkeypatch.setattr(
        frontier_mod,
        "to_anthropic_payload",
        lambda *a, **k: _payload_with_banned_content(),
    )
    legacy = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        temperature=None,
        sampling=SamplingParams(max_tokens=50),
        meta=RequestMeta(anthropic_version="2023-06-01"),
    )
    out = executor._anthropic_payload(legacy, stream=False)
    assert any(b.get("type") == "document" for b in out["messages"][0]["content"])
    assert "citations" in out["messages"][1]["content"][0]
    assert metrics.soft_warnings.get("anthropic_document_stripped") is None
    assert metrics.soft_warnings.get("anthropic_citations_stripped") is None
