"""MCP guardrails on tools/call arguments and results (issue #317)."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import GuardrailRuleSettings, GuardrailSettings
from daari.enterprise.audit import AuditLog
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.mcp_guardrails import AUDIT_ACTION, LEGACY_ERROR_CODE
from daari.gateway.mcp_policy import TOOL_DENIED
from daari.gateway.mcp_tasks import TASKS_META_KEY
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import mock_all_ollama_executors

pytestmark = pytest.mark.asyncio

AWS_KEY = "AKIAABCDEFGHIJKLMNOP"


def _guardrails(**overrides) -> GuardrailSettings:
    base = {
        "enabled": True,
        "input_rules": [
            GuardrailRuleSettings(name="no_rm_rf", pattern=r"rm\s+-rf", action="block")
        ],
        "output_rules": [GuardrailRuleSettings(name="secrets", kind="secret", action="redact")],
    }
    base.update(overrides)
    return GuardrailSettings(**base)


def _app(settings, monkeypatch, *, content: str = "routed", team=None):
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("agent", client_id="agent", team=team)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async def fake_execute(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content=content,
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    return app, {"Authorization": f"Bearer {created.plaintext}"}, created.key.key_id


async def _call(client, arguments, *, headers, meta=None):
    params = {"name": "route", "arguments": arguments}
    if meta:
        params["_meta"] = meta
    return await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params},
        headers=headers,
    )


def _trip_rows(settings):
    return [
        row
        for row in AuditLog(settings.enterprise.audit_path).list()
        if row["action"] == AUDIT_ACTION
    ]


async def test_no_guardrails_configured_changes_nothing(settings, monkeypatch):
    app, headers, _ = _app(settings, monkeypatch, content=f"key {AWS_KEY}")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _call(client, {"input": "rm -rf /tmp/x"}, headers=headers)
    assert response.json()["result"]["content"][0]["text"] == f"key {AWS_KEY}"
    assert _trip_rows(settings) == []


async def test_allowed_call_passes_and_writes_no_trip_row(settings, monkeypatch):
    settings.integrations.mcp_guardrails = _guardrails()
    app, headers, _ = _app(settings, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _call(client, {"input": "list files"}, headers=headers)
    assert response.json()["result"]["content"][0]["text"] == "routed"
    assert _trip_rows(settings) == []


async def test_input_trip_is_jsonrpc_error_naming_the_rule(settings, monkeypatch):
    settings.integrations.mcp_guardrails = _guardrails()
    app, headers, key_id = _app(settings, monkeypatch, team="eng")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _call(client, {"input": "please rm -rf /"}, headers=headers)
    assert response.status_code == 200
    error = response.json()["error"]
    assert error["code"] == TOOL_DENIED
    assert "no_rm_rf" in error["message"]
    assert error["data"] == {"tool": "route", "rule": "no_rm_rf", "direction": "input"}

    rows = _trip_rows(settings)
    assert len(rows) == 1
    row = rows[0]
    assert row["actor"] == key_id
    assert row["role"] == "eng"
    assert row["detail"] == {
        "tool": "route",
        "rule": "no_rm_rf",
        "direction": "input",
        "action": "block",
        "transport": "jsonrpc",
    }
    assert "rm -rf" not in str(rows)


async def test_output_trip_redacts_secret_in_result(settings, monkeypatch):
    settings.integrations.mcp_guardrails = _guardrails()
    app, headers, _ = _app(settings, monkeypatch, content=f"token is {AWS_KEY} ok")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _call(client, {"input": "show env"}, headers=headers)
    text = response.json()["result"]["content"][0]["text"]
    assert AWS_KEY not in text
    assert text == "token is <aws_key> ok"

    rows = _trip_rows(settings)
    assert len(rows) == 1
    assert rows[0]["detail"]["direction"] == "output"
    assert rows[0]["detail"]["rule"] == "secret:aws_key"
    assert rows[0]["detail"]["action"] == "redact"
    assert AWS_KEY not in str(rows)


async def test_output_block_replaces_result_with_block_message(settings, monkeypatch):
    settings.integrations.mcp_guardrails = _guardrails(
        output_rules=[
            GuardrailRuleSettings(name="no_leak", pattern="internal-only", action="block")
        ],
        block_message="Result withheld by daari guardrail.",
    )
    app, headers, _ = _app(settings, monkeypatch, content="this is internal-only data")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _call(client, {"input": "dump"}, headers=headers)
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["content"][0]["text"] == "Result withheld by daari guardrail."
    assert "internal-only" not in str(response.json())


async def test_task_results_are_scrubbed_too(settings, monkeypatch, tmp_path):
    settings.integrations.mcp_guardrails = _guardrails()
    settings.integrations.mcp_tasks.path = str(tmp_path / "mcp-tasks")
    app, headers, _ = _app(settings, monkeypatch, content=f"secret {AWS_KEY}")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await _call(
            client, {"input": "long"}, headers=headers, meta={TASKS_META_KEY: True}
        )
        task_id = created.json()["result"]["taskId"]
        for _ in range(50):
            poll = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tasks/get",
                    "params": {"taskId": task_id},
                },
                headers=headers,
            )
            if poll.json()["result"]["status"] == "completed":
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("task did not complete")
    text = poll.json()["result"]["result"]["content"][0]["text"]
    assert text == "secret <aws_key>"


async def test_legacy_rest_input_trip_is_403_with_code(settings, monkeypatch):
    settings.integrations.mcp_guardrails = _guardrails()
    app, headers, _ = _app(settings, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        via_call = await client.post(
            "/v1/mcp/query",
            json={
                "tool": "tools/call",
                "args": {"name": "route", "arguments": {"input": "rm -rf ~"}},
            },
            headers=headers,
        )
        direct = await client.post(
            "/v1/mcp/query", json={"tool": "route", "input": "rm -rf ~"}, headers=headers
        )
    for response in (via_call, direct):
        assert response.status_code == 403
        payload = response.json()
        assert payload["ok"] is False
        assert payload["result"]["error"]["code"] == LEGACY_ERROR_CODE
        assert payload["result"]["error"]["details"]["rule"] == "no_rm_rf"
    rows = _trip_rows(settings)
    assert {row["detail"]["transport"] for row in rows} == {"rest"}
    assert len(rows) == 2


async def test_legacy_rest_output_is_redacted(settings, monkeypatch):
    settings.integrations.mcp_guardrails = _guardrails()
    app, headers, _ = _app(settings, monkeypatch, content=f"k={AWS_KEY}")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        via_call = await client.post(
            "/v1/mcp/query",
            json={"tool": "tools/call", "args": {"name": "route", "arguments": {"input": "x"}}},
            headers=headers,
        )
        direct = await client.post(
            "/v1/mcp/query", json={"tool": "route", "input": "x"}, headers=headers
        )
    assert via_call.json()["result"]["result"]["content"] == "k=<aws_key>"
    assert direct.json()["result"]["content"] == "k=<aws_key>"
