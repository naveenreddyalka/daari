"""Lifetime lifetime spend caps and temporary budget boosts (#936)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.auth.budgets import (
    active_budget_boosts,
    apply_boost_usd,
    budget_error,
    budget_status,
    first_exceeded_window,
    normalize_duration,
    parse_window_flag,
    reset_at,
    window_label,
)
from daari.auth.virtual_keys import BudgetWindow, VirtualKey, VirtualKeyStore
from daari.cli.app import app
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.usage import UsageLedger
from daari.router.router import AppContext
from daari.server.app import create_app

CHAT = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}


def test_normalize_lifetime_aliases():
    assert normalize_duration("lifetime") == "lifetime"
    assert normalize_duration("total") == "lifetime"
    assert normalize_duration("all") == "lifetime"
    assert window_label("lifetime") == "lifetime"
    assert window_label("total") == "lifetime"


def test_parse_lifetime_window_disallows_rollover():
    window = parse_window_flag("lifetime=50:rollover")
    assert window.duration == "lifetime"
    assert window.max_usd == 50.0
    assert window.rollover is False


def test_lifetime_reset_at_is_never():
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    assert reset_at("lifetime", now=now) == ""


def test_lifetime_402_names_window_without_reset():
    body = budget_error(
        client_id="k1",
        window=BudgetWindow("lifetime", 50.0),
        spend=60.0,
        scope="key",
    )
    assert body["window"] == "lifetime"
    assert body["budget_usd"] == pytest.approx(50.0)
    assert "Resets at" not in body["message"]
    assert body.get("reset_at") in ("", None)


def test_ledger_all_time_spend_spans_months(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "u.sqlite3")
    # 500 tokens @ 0.002/1k = $1
    ledger.record(tier="L6", client_id="k1", model="", input_tokens=500_000, output_tokens=0, day="2026-01-01")
    ledger.record(tier="L6", client_id="k1", model="", input_tokens=500_000, output_tokens=0, day="2026-08-15")
    assert ledger.frontier_spend_usd_for_client("k1", window="lifetime") == pytest.approx(2.0, abs=1e-6)
    assert ledger.request_count_for_client("k1", window="lifetime") == 2


def test_budget_status_lifetime_no_rollover(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "u.sqlite3")
    ledger.record(tier="L6", client_id="k1", model="", input_tokens=500_000, output_tokens=0, day="2026-01-01")
    key = VirtualKey(
        key_id="id1",
        name="n",
        prefix="vk",
        budget_windows=(BudgetWindow("lifetime", 1.5),),
    )
    statuses = budget_status(key, None, ledger, client_id="k1", team_client_ids=[])
    assert len(statuses) == 1
    assert statuses[0].window.duration == "lifetime"
    assert statuses[0].spend == pytest.approx(1.0, abs=1e-6)
    assert statuses[0].limit == pytest.approx(1.5)
    assert not statuses[0].exceeded


def test_active_boosts_filter_expired():
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    future = (now + timedelta(days=1)).isoformat()
    past = (now - timedelta(days=1)).isoformat()
    meta = {
        "budget_boosts": [
            {"id": "a", "usd": 10.0, "until": future, "granted_at": past},
            {"id": "b", "usd": 5.0, "until": past, "granted_at": past},
        ]
    }
    active = active_budget_boosts(meta, now=now)
    assert len(active) == 1
    assert active[0]["id"] == "a"
    assert apply_boost_usd(meta, now=now) == pytest.approx(10.0)


def test_boost_raises_effective_limit(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "u.sqlite3")
    ledger.record(tier="L6", client_id="k1", model="", input_tokens=1_000_000, output_tokens=0)
    until = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    key = VirtualKey(
        key_id="id1",
        name="n",
        prefix="vk",
        budget_windows=(BudgetWindow("day", 1.0),),
        metadata={
            "budget_boosts": [{"id": "b1", "usd": 2.0, "until": until, "granted_at": until}],
        },
    )
    statuses = budget_status(key, None, ledger, client_id="k1", team_client_ids=[])
    assert statuses[0].limit == pytest.approx(3.0)
    assert not statuses[0].exceeded


def test_cli_budget_boost_and_show(tmp_path: Path, monkeypatch):
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("bot", daily_budget_usd=1.0)
    until = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["keys", "budget-boost", created.key.key_id, "--usd", "25", "--until", until],
    )
    assert result.exit_code == 0, result.output
    show = runner.invoke(app, ["keys", "show", created.key.key_id])
    assert show.exit_code == 0, show.output
    assert "boost" in show.output.lower()
    assert "25" in show.output

def _mock_execute(app_obj):
    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    app_obj.state.ctx.router.ollama.execute = fake


def _app_with_keys(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    app_obj = create_app(settings)
    app_obj.state.ctx = AppContext.from_settings(settings)
    app_obj.state.virtual_key_store = store
    app_obj.state.ctx.virtual_key_store = store
    _mock_execute(app_obj)
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    app_obj.state.ctx.router.usage_ledger = ledger
    return app_obj, store, ledger


@pytest.mark.asyncio
async def test_lifetime_cap_trips_402_across_ledger_periods(settings, tmp_path):
    """Spend on different calendar months still counts against a lifetime window."""
    app_obj, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create(
        "lifetime-bot",
        client_id="life-a",
        budget_windows=[BudgetWindow("lifetime", 1.0)],
    )
    ledger.record(
        tier="L6",
        client_id="life-a",
        model="",
        input_tokens=400_000,
        output_tokens=0,
        day="2026-01-05",
    )
    ledger.record(
        tier="L6",
        client_id="life-a",
        model="",
        input_tokens=400_000,
        output_tokens=0,
        day="2026-06-20",
    )

    transport = ASGITransport(app=app_obj)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )

    assert response.status_code == 402
    error = response.json()["error"]
    assert error["window"] == "lifetime"
    assert error["scope"] == "key"
    assert error["spend_usd"] >= 1.0


def test_first_exceeded_lifetime_request_quota(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "u.sqlite3")
    for day in ("2026-01-01", "2026-02-01", "2026-03-01"):
        ledger.record(tier="L3", client_id="k1", day=day)
    key = VirtualKey(
        key_id="id1",
        name="n",
        prefix="vk",
        budget_windows=(BudgetWindow("lifetime", 0.0, max_requests=2),),
    )
    body = first_exceeded_window(key, None, ledger, client_id="k1", team_client_ids=[])
    assert body is not None
    assert body["window"] == "lifetime"
    assert body["quota"] == "requests"
