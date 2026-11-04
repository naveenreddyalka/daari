"""Request tags matchable by signal_overrides (#2078)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from daari.config.settings import SignalOverrideRule
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.router.profile import build_prompt_profile
from daari.router.signals import (
    extract_signals,
    match_signal_override,
    parse_request_tags,
)


def _req(**kwargs) -> InternalRequest:
    messages = kwargs.pop("messages", [Message(role="user", content="hello there")])
    meta = kwargs.pop("meta", RequestMeta())
    return InternalRequest(messages=messages, model="daari", meta=meta, **kwargs)


def test_parse_header_only():
    assert parse_request_tags(header="eval, canary") == ["canary", "eval"]


def test_parse_body_only_list():
    assert parse_request_tags(metadata={"tags": ["eval", "prod"]}) == ["eval", "prod"]


def test_parse_body_only_string():
    assert parse_request_tags(metadata={"tags": "eval,prod"}) == ["eval", "prod"]


def test_parse_union_header_and_body():
    tags = parse_request_tags(
        header="canary",
        metadata={"tags": ["eval", "canary"]},
    )
    assert tags == ["canary", "eval"]


def test_parse_ignores_empty_and_whitespace():
    assert parse_request_tags(header=" , ,  ") == []
    assert parse_request_tags(metadata={"tags": ["", "  ", "ok"]}) == ["ok"]
    assert parse_request_tags(metadata={"tags": None}) == []


def test_extract_signals_includes_tags():
    request = _req(meta=RequestMeta(tags=["eval", "canary"]))
    profile = build_prompt_profile(request)
    signals = extract_signals(request, profile)
    assert signals["tags"] == ["canary", "eval"]


def test_tags_intersection_match():
    signals = {
        "has_images": False,
        "has_tools": False,
        "tool_count": 0,
        "approx_context_tokens": "lt_1k",
        "client_agent": "none",
        "category": "chat",
        "complexity": "trivial",
        "phase": None,
        "tags": ["eval", "canary"],
    }
    rules = [
        SignalOverrideRule(
            id="eval-cap",
            match={"tags": ["eval", "nightly"]},
            max_tier="L3",
        )
    ]
    matched = match_signal_override(signals, rules)
    assert matched is not None
    assert matched.id == "eval-cap"


def test_tag_singular_alias_match():
    signals = {
        "tags": ["canary"],
        "has_images": False,
        "has_tools": False,
        "tool_count": 0,
        "approx_context_tokens": "lt_1k",
        "client_agent": "none",
        "category": "chat",
        "complexity": "trivial",
        "phase": None,
    }
    rule = SignalOverrideRule(id="canary", match={"tag": "canary"}, max_tier="L4")
    assert match_signal_override(signals, [rule]) is not None


def test_tags_no_match_passthrough():
    signals = {
        "tags": ["prod"],
        "has_images": False,
        "has_tools": False,
        "tool_count": 0,
        "approx_context_tokens": "lt_1k",
        "client_agent": "none",
        "category": "chat",
        "complexity": "trivial",
        "phase": None,
    }
    rules = [
        SignalOverrideRule(id="eval", match={"tags": ["eval"]}, max_tier="L3"),
    ]
    assert match_signal_override(signals, rules) is None


def test_empty_request_tags_do_not_match_tag_rule():
    signals = {
        "tags": [],
        "has_images": False,
        "has_tools": False,
        "tool_count": 0,
        "approx_context_tokens": "lt_1k",
        "client_agent": "none",
        "category": "chat",
        "complexity": "trivial",
        "phase": None,
    }
    rules = [
        SignalOverrideRule(id="any", match={"tags": ["eval"]}, category="doc_qa"),
    ]
    assert match_signal_override(signals, rules) is None


def test_rule_rejects_empty_tags_list():
    with pytest.raises(ValidationError, match="tags"):
        SignalOverrideRule(id="bad", match={"tags": []}, max_tier="L3")


def test_rule_rejects_non_string_tag():
    with pytest.raises(ValidationError):
        SignalOverrideRule(id="bad", match={"tags": [1]}, max_tier="L3")
