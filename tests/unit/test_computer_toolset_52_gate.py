"""Reject legacy computer_* tools on Fable/Mythos 5.2 non-Bedrock egress (#2206)."""

from __future__ import annotations

import pytest

from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.gateway.sampling import SamplingParams
from daari.router.anthropic_messages import (
    LEGACY_COMPUTER_TOOL_TYPES,
    LegacyComputerToolRejected,
    enforce_computer_toolset_for_52,
    is_bedrock_anthropic_base,
    legacy_computer_tool_types,
)
from daari.router.frontier import FrontierExecutor


def _req(*, tools: list[dict]) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="click")],
        model="daari",
        sampling=SamplingParams(max_tokens=50),
        tools=tools,
        meta=RequestMeta(),
    )


class TestLegacyDetection:
    def test_finds_20251124_and_20250124(self):
        tools = [
            {"type": "computer_20251124", "name": "computer", "display_width_px": 1024},
            {"type": "computer_20250124", "name": "computer"},
            {"type": "function", "function": {"name": "other"}},
        ]
        found = legacy_computer_tool_types(tools)
        assert found == ["computer_20251124", "computer_20250124"]
        assert found[0] in LEGACY_COMPUTER_TOOL_TYPES

    def test_preserves_anthropic_type_marker(self):
        tools = [{"type": "function", "anthropic_type": "computer_20251124", "function": {"name": "computer"}}]
        assert legacy_computer_tool_types(tools) == ["computer_20251124"]


class TestBedrockBase:
    def test_bedrock_hosts(self):
        assert is_bedrock_anthropic_base(
            "https://bedrock-runtime.us-east-1.amazonaws.com"
        )
        assert is_bedrock_anthropic_base(
            "https://bedrock-runtime.us-west-2.amazonaws.com/model"
        )

    def test_claude_api_not_bedrock(self):
        assert not is_bedrock_anthropic_base("https://api.anthropic.com")
        assert not is_bedrock_anthropic_base("")


class TestEnforceGate:
    def test_52_legacy_rejects_with_toolset_name(self):
        tools = [{"type": "computer_20251124", "name": "computer", "display_width_px": 800}]
        with pytest.raises(LegacyComputerToolRejected, match="computer_toolset_20260801") as exc:
            enforce_computer_toolset_for_52(
                tools,
                model="claude-fable-5-2",
                base_url="https://api.anthropic.com",
            )
        assert "computer_20251124" in str(exc.value)

    def test_mythos_52_dated_alias_rejects(self):
        tools = [{"type": "computer_20250124", "name": "computer"}]
        with pytest.raises(LegacyComputerToolRejected, match="computer_toolset_20260801"):
            enforce_computer_toolset_for_52(
                tools,
                model="anthropic.claude-mythos-5-2-20261109",
                base_url="https://api.anthropic.com",
            )

    def test_bedrock_52_allows_legacy(self):
        tools = [{"type": "computer_20251124", "name": "computer"}]
        enforce_computer_toolset_for_52(
            tools,
            model="claude-fable-5-2",
            base_url="https://bedrock-runtime.us-east-1.amazonaws.com",
        )

    def test_opus_55_unchanged(self):
        tools = [{"type": "computer_20251124", "name": "computer"}]
        enforce_computer_toolset_for_52(
            tools,
            model="claude-opus-5-5",
            base_url="https://api.anthropic.com",
        )

    def test_52_without_legacy_ok(self):
        tools = [{"type": "computer_toolset_20260801"}]
        enforce_computer_toolset_for_52(
            tools,
            model="claude-fable-5-2",
            base_url="https://api.anthropic.com",
        )


class TestFrontierPayloadGate:
    def test_anthropic_payload_raises_on_legacy(self):
        exe = FrontierExecutor(
            base_url="https://api.anthropic.com",
            api_key="sk-test",
            default_model="claude-fable-5-2",
            provider="anthropic",
        )
        req = _req(
            tools=[
                {
                    "type": "function",
                    "anthropic_type": "computer_20251124",
                    "function": {"name": "computer", "parameters": {}},
                }
            ]
        )
        with pytest.raises(LegacyComputerToolRejected, match="computer_toolset_20260801"):
            exe._anthropic_payload(req, stream=False)

    def test_bedrock_executor_allows_legacy(self):
        exe = FrontierExecutor(
            base_url="https://bedrock-runtime.us-east-1.amazonaws.com",
            api_key="sk-test",
            default_model="claude-fable-5-2",
            provider="anthropic",
        )
        req = _req(
            tools=[
                {
                    "type": "function",
                    "anthropic_type": "computer_20251124",
                    "function": {"name": "computer", "parameters": {}},
                }
            ]
        )
        # Must not raise — Bedrock still accepts the earlier tool.
        payload = exe._anthropic_payload(req, stream=False)
        assert payload["model"] == "claude-fable-5-2"
