"""Shared USD budgets per named model_group (#1109)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.budgets import (
    model_group_budget_status,
    model_group_budgets_of,
    model_group_spend_report_rows,
    parse_model_group_budgets,
)
from daari.auth.model_access import groups_for_model
from daari.auth.virtual_keys import BudgetWindow, VirtualKeyStore
from daari.gateway.budget_headers import BUDGET_SCOPE_HEADER, BUDGET_WARNING_HEADER
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.spend import EXPORT_FIELDS, export_dict
from daari.observability.usage import UsageLedger
from daari.router.router import AppContext
from daari.server.app import create_app

CHAT_GPT = {"model": "gpt-4-custom", "messages": [{"role": "user", "content": "hi"}]}
CATALOG = {"coding-agents": ["gpt-4*", "claude-*"]}


def _mock_execute(app):
    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.ollama.execute = fake


def _app_with_keys(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    settings.model_groups = dict(CATALOG)
    settings.frontier.soft_budget_ratio = 0.8
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    _mock_execute(app)
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    app.state.ctx.router.usage_ledger = ledger
    return app, store, ledger


def _record_group_spend(ledger: UsageLedger, *, model: str, usd: float, client_id: str = "any") -> None:
    ledger.record(
        tier="L6",
        client_id=client_id,
        model=model,
        input_tokens=int(usd / 0.002 * 1000),
        output_tokens=0,
    )


def test_groups_for_model_matches_catalog_patterns():
    assert groups_for_model("gpt-4-custom", CATALOG) == ("coding-agents",)
    assert groups_for_model("claude-3-opus", CATALOG) == ("coding-agents",)
    assert groups_for_model("llama3.2:3b", CATALOG) == ()


def test_parse_and_attach_model_group_budgets_on_key(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    key = store.create(
        "a",
        client_id="key-a",
        model_group_budgets={"coding-agents": [BudgetWindow("day", 5.0)]},
    )
    resolved = store.resolve(key.plaintext)
    assert resolved is not None
    budgets = model_group_budgets_of(resolved)
    assert "coding-agents" in budgets
    assert budgets["coding-agents"][0].max_usd == 5.0
    assert parse_model_group_budgets(
        {"coding-agents": [{"duration": "day", "max_usd": 1.0}]}
    )["coding-agents"][0].max_usd == 1.0


def test_model_group_budget_status_allow_soft_hard(tmp_path, settings):
    settings.model_groups = dict(CATALOG)
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    key = store.create(
        "a",
        client_id="key-a",
        model_group_budgets={"coding-agents": [BudgetWindow("day", 1.0)]},
    )
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    resolved = store.resolve(key.plaintext)
    assert resolved is not None

    under = model_group_budget_status(
        "gpt-4-custom",
        resolved,
        None,
        ledger,
        catalog=CATALOG,
        client_id="key-a",
    )
    assert under
    assert not under[0].exceeded
    assert not under[0].in_soft_band(0.8)

    _record_group_spend(ledger, model="gpt-4-custom", usd=0.8, client_id="other-key")
    soft = model_group_budget_status(
        "gpt-4-custom",
        resolved,
        None,
        ledger,
        catalog=CATALOG,
        client_id="key-a",
    )
    assert soft[0].in_soft_band(0.8)
    assert not soft[0].exceeded

    _record_group_spend(ledger, model="claude-3-opus-custom", usd=0.2, client_id="third")
    hard = model_group_budget_status(
        "gpt-4-custom",
        resolved,
        None,
        ledger,
        catalog=CATALOG,
        client_id="key-a",
    )
    assert hard[0].exceeded
    assert hard[0].scope == "model_group"


@pytest.mark.asyncio
async def test_gateway_allow_soft_warn_hard_reject(settings, tmp_path):
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create(
        "a",
        client_id="key-a",
        model_group_budgets={"coding-agents": [BudgetWindow("day", 1.0)]},
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        allow = await client.post(
            "/v1/chat/completions",
            json=CHAT_GPT,
            headers={
                "Authorization": f"Bearer {key.plaintext}",
                "X-Daari-No-Cache": "true",
                "X-Daari-Meta": "true",
            },
        )
        assert allow.status_code == 200
        assert BUDGET_WARNING_HEADER not in allow.headers

        _record_group_spend(ledger, model="gpt-4-custom", usd=0.8, client_id="peer")
        soft = await client.post(
            "/v1/chat/completions",
            json=CHAT_GPT,
            headers={
                "Authorization": f"Bearer {key.plaintext}",
                "X-Daari-No-Cache": "true",
                "X-Daari-Meta": "true",
            },
        )
        assert soft.status_code == 200
        assert soft.headers[BUDGET_WARNING_HEADER] == "soft"
        assert soft.headers[BUDGET_SCOPE_HEADER] == "model_group"
        assert soft.json()["daari_meta"]["warning"] == "budget_warning"

        _record_group_spend(ledger, model="gpt-4-custom", usd=0.2, client_id="peer2")
        hard = await client.post(
            "/v1/chat/completions",
            json=CHAT_GPT,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
        assert hard.status_code == 402
        err = hard.json()["error"]
        assert err["type"] == "budget_exceeded"
        assert err["scope"] == "model_group"
        assert err["model_group"] == "coding-agents"
        assert BUDGET_WARNING_HEADER not in hard.headers


@pytest.mark.asyncio
async def test_report_exposes_model_group_spend(settings, tmp_path):
    app, store, ledger = _app_with_keys(settings, tmp_path)
    store.create(
        "a",
        client_id="key-a",
        model_group_budgets={"coding-agents": [BudgetWindow("day", 10.0)]},
    )
    _record_group_spend(ledger, model="gpt-4-custom", usd=1.5, client_id="key-a")
    rows = model_group_spend_report_rows(
        store,
        ledger,
        catalog=CATALOG,
        soft_ratio=0.8,
        pricing=None,
        fallback_per_1k=0.002,
    )
    assert any(r["model_group"] == "coding-agents" and r["spend_usd"] >= 1.4 for r in rows)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        report = await client.get(
            "/v1/daari/report",
            headers={"Authorization": "Bearer master"},
        )
        assert report.status_code == 200
        body = report.json()
        assert "model_group_spend" in body
        assert any(r["model_group"] == "coding-agents" for r in body["model_group_spend"])


def test_spend_export_includes_model_group_field():
    assert "model_group" in EXPORT_FIELDS
    row = export_dict(
        {
            "ts": "2026-01-01T00:00:00+00:00",
            "request_id": "r1",
            "key_id": "k",
            "team_id": "",
            "client_id": "c",
            "model": "gpt-4-custom",
            "tier": "L6",
            "input_tokens": 10,
            "output_tokens": 5,
            "cached_tokens": 0,
            "cache_write_tokens": 0,
            "cost_usd": 0.01,
            "cost_avoided_usd": 0.0,
            "cache_hit": False,
            "model_group": "coding-agents",
        }
    )
    assert row["model_group"] == "coding-agents"
