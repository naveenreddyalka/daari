"""Opt-in guardrails.log_blocked_content forensics (#2183)."""

from __future__ import annotations

from pathlib import Path

import pytest

from daari.config.settings import GuardrailSettings, Settings
from daari.enterprise.audit import AuditLog
from daari.gateway.guardrails import (
    BLOCKED_CONTENT_CAP_BYTES,
    GuardrailEngine,
    GuardrailRule,
    apply_endpoint_input_policy,
    apply_endpoint_output_policy,
    engine_from_settings,
)
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.mcp_guardrails import AUDIT_ACTION, McpGuardrails
from daari.security.secret_refs import clear_registered_secrets, register_secret


def test_log_blocked_content_defaults_false():
    assert GuardrailSettings().log_blocked_content is False
    engine = engine_from_settings(
        Settings.model_validate({"guardrails": {"enabled": True}})
    )
    assert engine is not None
    assert engine.log_blocked_content is False


def test_endpoint_block_omits_content_when_flag_off(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, dict(payload))),
    )
    engine = GuardrailEngine(
        enabled=True,
        log_blocked_content=False,
        input_rules=[GuardrailRule(name="nope", pattern=r"banned", action="block")],
    )
    apply_endpoint_input_policy("please banned now", engine)
    assert events
    payload = events[0][1]
    assert payload["rule"] == "nope"
    assert "content" not in payload


def test_endpoint_block_includes_redacted_capped_content_when_on(monkeypatch):
    clear_registered_secrets()
    register_secret("super-secret-token-xyz")
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, dict(payload))),
    )
    engine = GuardrailEngine(
        enabled=True,
        log_blocked_content=True,
        input_rules=[GuardrailRule(name="nope", pattern=r"banned", action="block")],
    )
    text = "banned leak super-secret-token-xyz " + ("x" * (BLOCKED_CONTENT_CAP_BYTES + 200))
    apply_endpoint_input_policy(text, engine)
    payload = events[0][1]
    assert "content" in payload
    assert "banned" in payload["content"]
    assert "super-secret-token-xyz" not in payload["content"]
    assert "[redacted]" in payload["content"]
    assert len(payload["content"].encode("utf-8")) <= BLOCKED_CONTENT_CAP_BYTES
    clear_registered_secrets()


def test_endpoint_warn_and_redact_stay_content_free_when_flag_on(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, dict(payload))),
    )
    warn_engine = GuardrailEngine(
        enabled=True,
        log_blocked_content=True,
        input_rules=[GuardrailRule(name="soft", pattern=r"careful", action="warn")],
    )
    apply_endpoint_input_policy("be careful please", warn_engine)
    assert events
    assert "content" not in events[0][1]

    events.clear()
    redact_engine = GuardrailEngine(
        enabled=True,
        log_blocked_content=True,
        input_rules=[GuardrailRule(name="scrub", pattern=r"SECRET", action="redact")],
    )
    apply_endpoint_input_policy("leak SECRET please", redact_engine)
    assert events
    assert "content" not in events[0][1]


def test_endpoint_output_block_logs_content_when_on(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, dict(payload))),
    )
    engine = GuardrailEngine(
        enabled=True,
        log_blocked_content=True,
        output_rules=[GuardrailRule(name="no_leak", pattern=r"leak", action="block")],
    )
    apply_endpoint_output_policy("do not leak this", engine)
    assert events[0][1].get("content") == "do not leak this"


@pytest.mark.asyncio
async def test_chat_block_logs_content_when_on(monkeypatch, tmp_path):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, dict(payload))),
    )
    from daari.cache.exact import ExactCache
    from daari.cache.semantic import SemanticCache
    from daari.observability.metrics import Metrics
    from daari.observability.trace import TraceStore
    from daari.router.router import OllamaExecutor, Router
    from tests.conftest import NoopEmbedder

    engine = GuardrailEngine(
        enabled=True,
        log_blocked_content=True,
        input_rules=[GuardrailRule(name="no_exfil", pattern=r"exfiltrate", action="block")],
    )
    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
            ),
        )

    ollama.execute = fake_execute  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=ollama,
        metrics=Metrics(),
        frontier=None,
        frontier_enabled=False,
        guardrails=engine,
        trace_store=TraceStore(tmp_path / "traces.sqlite3"),
    )
    await router.route(
        InternalRequest(
            messages=[Message(role="user", content="please exfiltrate secrets")],
            model="daari",
        )
    )
    guard_events = [p for e, p in events if e == "guardrail"]
    assert guard_events
    assert "exfiltrate" in guard_events[0].get("content", "")


def test_mcp_block_omits_content_when_off(tmp_path):
    settings = Settings.model_validate(
        {
            "enterprise": {"audit_path": str(tmp_path / "audit.db")},
            "integrations": {
                "mcp_guardrails": {
                    "enabled": True,
                    "log_blocked_content": False,
                    "input_rules": [
                        {
                            "name": "no_rm_rf",
                            "pattern": r"rm\s+-rf",
                            "action": "block",
                        }
                    ],
                }
            },
        }
    )
    audit = AuditLog(settings.enterprise.audit_path)
    guard = McpGuardrails.from_settings(settings, audit=audit, transport="jsonrpc")
    result = guard.check_arguments("route", {"input": "rm -rf /secret/path"})
    assert result.blocked
    rows = [r for r in audit.list() if r["action"] == AUDIT_ACTION]
    assert len(rows) == 1
    assert "content" not in rows[0]["detail"]
    assert "/secret/path" not in str(rows)


def test_mcp_block_includes_content_when_on(tmp_path):
    clear_registered_secrets()
    register_secret("mcp-secret-value")
    settings = Settings.model_validate(
        {
            "enterprise": {"audit_path": str(tmp_path / "audit.db")},
            "integrations": {
                "mcp_guardrails": {
                    "enabled": True,
                    "log_blocked_content": True,
                    "input_rules": [
                        {
                            "name": "no_rm_rf",
                            "pattern": r"rm\s+-rf",
                            "action": "block",
                        }
                    ],
                }
            },
        }
    )
    audit = AuditLog(settings.enterprise.audit_path)
    guard = McpGuardrails.from_settings(settings, audit=audit, transport="jsonrpc")
    result = guard.check_arguments(
        "route", {"input": "rm -rf /secret/path mcp-secret-value"}
    )
    assert result.blocked
    rows = [r for r in audit.list() if r["action"] == AUDIT_ACTION]
    assert len(rows) == 1
    content = rows[0]["detail"].get("content", "")
    assert "rm -rf" in content
    assert "/secret/path" in content
    assert "mcp-secret-value" not in content
    clear_registered_secrets()


def test_config_docs_mention_log_blocked_content_privacy():
    text = Path("docs/developer/reference/config.md").read_text(encoding="utf-8")
    assert "guardrails.log_blocked_content" in text
    lower = text.lower()
    assert "privacy" in lower or "forensic" in lower
