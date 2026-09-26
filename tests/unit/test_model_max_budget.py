"""Team-level model_max_budget map with key overrides (#1113)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.budgets import (
    effective_model_max_budget,
    model_max_budget_of,
    model_max_budget_status,
    parse_model_max_budget,
    team_model_spend_report_rows,
)
from daari.auth.virtual_keys import VirtualKeyStore
from daari.gateway.budget_headers import BUDGET_SCOPE_HEADER, BUDGET_WARNING_HEADER
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.usage import UsageLedger
from daari.router.router import AppContext
from daari.server.app import create_app

CHAT_GPT = {"model": "gpt-4-custom", "messages": [{"role": "user", "content": "hi"}]}


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


def _record_model_spend(
    ledger: UsageLedger, *, model: str, usd: float, client_id: str = "any"
) -> None:
    ledger.record(
        tier="L6",
        client_id=client_id,
        model=model,
        input_tokens=int(usd / 0.002 * 1000),
        output_tokens=0,
    )


def test_parse_bare_float_is_daily_window():
    parsed = parse_model_max_budget({"gpt-4*": 5.0})
    assert parsed["gpt-4*"][0].duration == "day"
    assert parsed["gpt-4*"][0].max_usd == 5.0


def test_team_default_key_override(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    team = store.create_team(
        "eng",
        model_max_budget={"gpt-4*": 10.0, "claude-*": 3.0},
    )
    key = store.create(
        "a",
        client_id="key-a",
        team="eng",
        model_max_budget={"gpt-4*": 1.0},
    )
    resolved = store.resolve(key.plaintext)
    assert resolved is not None
    team_row = store.get_team(team.team_id)
    assert model_max_budget_of(team_row)["claude-*"][0].max_usd == 3.0
    effective = effective_model_max_budget(resolved, team_row)
    assert effective["gpt-4*"][0].max_usd == 1.0  # key override
    assert effective["claude-*"][0].max_usd == 3.0  # team fallback
    unset = store.create("b", client_id="key-b", team="eng")
    unset_key = store.resolve(unset.plaintext)
    assert unset_key is not None
    assert effective_model_max_budget(unset_key, team_row)["gpt-4*"][0].max_usd == 10.0


def test_model_max_budget_status_allow_soft_hard(tmp_path, settings):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    team = store.create_team("eng", model_max_budget={"gpt-4*": 1.0})
    key = store.create("a", client_id="key-a", team="eng")
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    resolved = store.resolve(key.plaintext)
    assert resolved is not None
    team_row = store.get_team(team.team_id)
    team_ids = store.team_client_ids(team.team_id)

    under = model_max_budget_status(
        "gpt-4-custom",
        resolved,
        team_row,
        ledger,
        client_id="key-a",
        team_client_ids=team_ids,
    )
    assert under
    assert not under[0].exceeded
    assert not under[0].in_soft_band(0.8)

    _record_model_spend(ledger, model="gpt-4-custom", usd=0.8, client_id="key-a")
    soft = model_max_budget_status(
        "gpt-4-custom",
        resolved,
        team_row,
        ledger,
        client_id="key-a",
        team_client_ids=team_ids,
    )
    assert soft[0].in_soft_band(0.8)
    assert not soft[0].exceeded

    _record_model_spend(ledger, model="gpt-4-turbo", usd=0.2, client_id="peer")
    # peer not on team — should not count toward team cap
    still_soft = model_max_budget_status(
        "gpt-4-custom",
        resolved,
        team_row,
        ledger,
        client_id="key-a",
        team_client_ids=team_ids,
    )
    assert not still_soft[0].exceeded

    _record_model_spend(ledger, model="gpt-4-custom", usd=0.25, client_id="key-a")
    hard = model_max_budget_status(
        "gpt-4-custom",
        resolved,
        team_row,
        ledger,
        client_id="key-a",
        team_client_ids=team_ids,
    )
    assert hard[0].exceeded
    assert hard[0].scope == "model"
    assert hard[0].model_pattern == "gpt-4*"


@pytest.mark.asyncio
async def test_gateway_team_default_key_override_exceed(settings, tmp_path):
    app, store, ledger = _app_with_keys(settings, tmp_path)
    store.create_team("eng", model_max_budget={"gpt-4*": 10.0})
    key = store.create(
        "a",
        client_id="key-a",
        team="eng",
        model_max_budget={"gpt-4*": 1.0},
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

        _record_model_spend(ledger, model="gpt-4-custom", usd=0.8, client_id="key-a")
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
        assert soft.headers[BUDGET_SCOPE_HEADER] == "model"

        _record_model_spend(ledger, model="gpt-4-custom", usd=0.25, client_id="key-a")
        hard = await client.post(
            "/v1/chat/completions",
            json=CHAT_GPT,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
        assert hard.status_code == 402
        err = hard.json()["error"]
        assert err["type"] == "budget_exceeded"
        assert err["scope"] == "model"
        assert err["model_pattern"] == "gpt-4*"


@pytest.mark.asyncio
async def test_report_exposes_team_model_spend(settings, tmp_path):
    app, store, ledger = _app_with_keys(settings, tmp_path)
    store.create_team("eng", model_max_budget={"gpt-4*": 10.0})
    store.create("a", client_id="key-a", team="eng")
    _record_model_spend(ledger, model="gpt-4-custom", usd=1.5, client_id="key-a")
    rows = team_model_spend_report_rows(
        store,
        ledger,
        soft_ratio=0.8,
        pricing=None,
        fallback_per_1k=0.002,
    )
    assert any(r["model_pattern"] == "gpt-4*" and r["spend_usd"] >= 1.4 for r in rows)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        report = await client.get(
            "/v1/daari/report",
            headers={"Authorization": "Bearer master"},
        )
        assert report.status_code == 200
        body = report.json()
        assert "team_model_spend" in body
        assert any(r["model_pattern"] == "gpt-4*" for r in body["team_model_spend"])


def test_missing_map_is_unlimited(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    key = store.create("a", client_id="key-a")
    resolved = store.resolve(key.plaintext)
    assert resolved is not None
    assert effective_model_max_budget(resolved, None) == {}
