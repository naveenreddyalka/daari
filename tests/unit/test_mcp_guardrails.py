"""Pure-function coverage for MCP guardrails and the egress client hooks (issue #317)."""

from __future__ import annotations

import httpx
import pytest

from daari.config.settings import GuardrailRuleSettings, GuardrailSettings, Settings
from daari.enterprise.audit import AuditLog
from daari.gateway.internal import InternalRequest, Message
from daari.gateway.mcp_guardrails import (
    AUDIT_ACTION,
    McpGuardrails,
    arguments_text,
)
from daari.providers.mcp_egress import McpEgressProvider, McpServerConfig, build_mcp_providers

AWS_KEY = "AKIAABCDEFGHIJKLMNOP"


def _settings(tmp_path, **overrides) -> Settings:
    settings = Settings.model_validate({"enterprise": {"audit_path": str(tmp_path / "audit.db")}})
    block = {
        "enabled": True,
        "input_rules": [
            GuardrailRuleSettings(name="no_rm_rf", pattern=r"rm\s+-rf", action="block")
        ],
        "output_rules": [GuardrailRuleSettings(name="secrets", kind="secret", action="redact")],
    }
    block.update(overrides)
    settings.integrations.mcp_guardrails = GuardrailSettings(**block)
    return settings


class TestArgumentsText:
    def test_flattens_nested_leaf_values(self):
        text = arguments_text({"cmd": "rm -rf /", "opts": {"flags": ["-v", 2], "dry": True}})
        assert "rm -rf /" in text
        assert "-v" in text
        assert "2" in text
        assert "true" in text.lower()

    def test_non_dict_is_stringified(self):
        assert arguments_text("plain") == "plain"
        assert arguments_text(None) == ""


class TestMcpGuardrails:
    def test_disabled_when_not_configured(self, tmp_path):
        settings = Settings.model_validate({"enterprise": {"audit_path": str(tmp_path / "a.db")}})
        guard = McpGuardrails.from_settings(settings, transport="jsonrpc")
        assert not guard.enabled
        assert not guard.check_arguments("route", {"input": "rm -rf /"}).tripped
        payload = {"content": [{"type": "text", "text": AWS_KEY}], "isError": False}
        rewritten, result = guard.check_tool_result("route", payload)
        assert rewritten == payload
        assert not result.tripped

    def test_input_block_audits_rule_and_direction_without_payload(self, tmp_path):
        settings = _settings(tmp_path)
        audit = AuditLog(settings.enterprise.audit_path)
        guard = McpGuardrails.from_settings(settings, audit=audit, transport="jsonrpc")
        result = guard.check_arguments("route", {"input": "rm -rf /secret/path"})
        assert result.blocked
        assert result.hits[0].rule == "no_rm_rf"
        rows = [r for r in audit.list() if r["action"] == AUDIT_ACTION]
        assert len(rows) == 1
        assert rows[0]["actor"] == "anonymous"
        assert rows[0]["detail"] == {
            "tool": "route",
            "rule": "no_rm_rf",
            "direction": "input",
            "action": "block",
            "transport": "jsonrpc",
        }
        assert "/secret/path" not in str(rows)

    def test_tool_result_redacts_every_text_item(self, tmp_path):
        guard = McpGuardrails.from_settings(_settings(tmp_path), transport="jsonrpc")
        payload = {
            "content": [
                {"type": "text", "text": f"a {AWS_KEY}"},
                {"type": "image", "data": "..."},
                {"type": "text", "text": f"b {AWS_KEY}"},
            ],
            "isError": False,
        }
        rewritten, result = guard.check_tool_result("route", payload)
        assert result.tripped and not result.blocked
        assert rewritten["content"][0]["text"] == "a <aws_key>"
        assert rewritten["content"][1] == {"type": "image", "data": "..."}
        assert rewritten["content"][2]["text"] == "b <aws_key>"
        assert payload["content"][0]["text"] == f"a {AWS_KEY}", "input payload must not be mutated"

    def test_tool_result_block_replaces_content(self, tmp_path):
        settings = _settings(
            tmp_path,
            output_rules=[GuardrailRuleSettings(name="no_leak", pattern="leak", action="block")],
            block_message="withheld",
        )
        guard = McpGuardrails.from_settings(settings, transport="jsonrpc")
        payload = {"content": [{"type": "text", "text": "ok"}, {"type": "text", "text": "leak!"}]}
        rewritten, result = guard.check_tool_result("route", payload)
        assert result.blocked
        assert rewritten == {"content": [{"type": "text", "text": "withheld"}], "isError": True}

    def test_legacy_result_dict_with_string_content(self, tmp_path):
        guard = McpGuardrails.from_settings(_settings(tmp_path), transport="rest")
        rewritten, result = guard.check_legacy_result("route", {"content": f"x {AWS_KEY}"})
        assert rewritten == {"content": "x <aws_key>"}
        assert result.tripped

    def test_legacy_result_non_string_payload_is_checked_as_json(self, tmp_path):
        settings = _settings(
            tmp_path,
            output_rules=[GuardrailRuleSettings(name="no_leak", pattern="leak", action="block")],
            block_message="withheld",
        )
        guard = McpGuardrails.from_settings(settings, transport="rest")
        rewritten, result = guard.check_legacy_result("stats", {"tiers": {"L3": "leak"}})
        assert result.blocked
        assert rewritten == {"content": "withheld"}


def _patch_transport(monkeypatch, handler):
    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)


def _request(text: str) -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="daari")


@pytest.mark.asyncio
async def test_egress_blocks_outbound_arguments_before_posting(monkeypatch, tmp_path):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})

    _patch_transport(monkeypatch, handler)
    settings = _settings(tmp_path)
    audit = AuditLog(settings.enterprise.audit_path)
    guard = McpGuardrails.from_settings(settings, audit=audit, transport="egress")
    provider = McpEgressProvider(
        McpServerConfig(id="demo", url="http://mcp.test/rpc"), guardrails=guard
    )
    response = await provider.execute(_request("@mcp:demo run_shell rm -rf /"))
    assert seen == []
    assert response.daari_meta.warning == "guardrail_blocked"
    assert "no_rm_rf" in response.content
    rows = [r for r in audit.list() if r["action"] == AUDIT_ACTION]
    assert rows[0]["detail"]["tool"] == "run_shell"
    assert rows[0]["detail"]["transport"] == "egress"
    assert rows[0]["detail"]["direction"] == "input"


@pytest.mark.asyncio
async def test_egress_scrubs_inbound_results(monkeypatch, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": f"key={AWS_KEY}"}]},
            },
        )

    _patch_transport(monkeypatch, handler)
    guard = McpGuardrails.from_settings(_settings(tmp_path), transport="egress")
    provider = McpEgressProvider(
        McpServerConfig(id="demo", url="http://mcp.test/rpc"), guardrails=guard
    )
    response = await provider.execute(_request("@mcp:demo get_key"))
    assert AWS_KEY not in response.content
    assert "<aws_key>" in response.content


@pytest.mark.asyncio
async def test_egress_without_guardrails_is_unchanged(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": AWS_KEY})

    _patch_transport(monkeypatch, handler)
    (provider,) = build_mcp_providers([{"id": "demo", "url": "http://mcp.test/rpc"}])
    response = await provider.execute(_request("@mcp:demo get_key rm -rf /"))
    assert AWS_KEY in response.content
