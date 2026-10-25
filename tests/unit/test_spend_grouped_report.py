"""Dimension-grouped spend reports + service_tier persistence (#1931)."""

from __future__ import annotations

import json
import sqlite3

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.cli.app import app as cli_app
from daari.observability.spend import SpendLedger
from daari.router.router import AppContext
from daari.server.app import create_app

SINCE = "2026-01-01T00:00:00+00:00"
DAY_A = "2026-06-15T10:00:00+00:00"
DAY_B = "2026-06-16T10:00:00+00:00"


def _row(ledger: SpendLedger, **overrides) -> None:
    payload = {
        "ts": DAY_A,
        "request_id": "req-a",
        "key_id": "key-1",
        "team_id": "team-x",
        "client_id": "client-a",
        "user_id": "alice",
        "model": "claude-haiku-4-5",
        "provider": "",
        "tier": "L6",
        "input_tokens": 100,
        "output_tokens": 20,
        "cost_usd": 0.10,
        "cost_avoided_usd": 0.0,
        "cache_hit": False,
        "usage_speed": "standard",
        "service_tier": "default",
    }
    payload.update(overrides)
    ledger.record(**payload)


def test_migrate_adds_service_tier_column(tmp_path):
    path = tmp_path / "spend.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE spend_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            request_id TEXT NOT NULL,
            key_id TEXT NOT NULL DEFAULT '',
            team_id TEXT NOT NULL DEFAULT '',
            client_id TEXT NOT NULL DEFAULT '',
            user_id TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            provider TEXT NOT NULL DEFAULT '',
            tier TEXT NOT NULL DEFAULT '',
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cached_tokens INTEGER NOT NULL DEFAULT 0,
            cache_write_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL DEFAULT 0,
            cost_avoided_usd REAL NOT NULL DEFAULT 0,
            cache_hit INTEGER NOT NULL DEFAULT 0,
            usage_speed TEXT NOT NULL DEFAULT ''
        );
        """
    )
    conn.commit()
    conn.close()

    ledger = SpendLedger(path, enabled=True)
    _row(ledger, service_tier="priority", request_id="req-new")
    rows = list(ledger.iter_rows(since=SINCE))
    assert len(rows) == 1
    assert rows[0]["service_tier"] == "priority"


def test_grouped_report_multi_dim_and_day_bucket(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    _row(
        ledger,
        request_id="a1",
        model="claude-haiku-4-5",
        service_tier="default",
        ts=DAY_A,
        cost_usd=0.10,
        input_tokens=100,
        output_tokens=10,
    )
    _row(
        ledger,
        request_id="a2",
        model="claude-haiku-4-5",
        service_tier="default",
        ts=DAY_A,
        cost_usd=0.05,
        input_tokens=50,
        output_tokens=5,
    )
    _row(
        ledger,
        request_id="b1",
        model="claude-haiku-4-5",
        service_tier="priority",
        ts=DAY_A,
        cost_usd=0.20,
        input_tokens=200,
        output_tokens=20,
    )
    _row(
        ledger,
        request_id="c1",
        model="claude-opus-5-5",
        service_tier="default",
        ts=DAY_B,
        cost_usd=0.50,
        input_tokens=500,
        output_tokens=50,
    )
    rows = ledger.grouped_report(
        since=SINCE,
        group_by=["model", "service_tier"],
        bucket="day",
    )
    by_key = {
        (r["bucket"], r["model"], r["service_tier"]): r for r in rows
    }
    day_a = DAY_A[:10]
    day_b = DAY_B[:10]
    assert by_key[(day_a, "claude-haiku-4-5", "default")]["requests"] == 2
    assert abs(by_key[(day_a, "claude-haiku-4-5", "default")]["cost_usd"] - 0.15) < 1e-9
    assert by_key[(day_a, "claude-haiku-4-5", "default")]["input_tokens"] == 150
    assert by_key[(day_a, "claude-haiku-4-5", "priority")]["requests"] == 1
    assert by_key[(day_b, "claude-opus-5-5", "default")]["requests"] == 1

    monthly = ledger.grouped_report(
        since=SINCE,
        group_by=["model"],
        bucket="month",
        until="2026-07-01T00:00:00+00:00",
    )
    assert {r["bucket"] for r in monthly} == {"2026-06"}
    haiku = next(r for r in monthly if r["model"] == "claude-haiku-4-5")
    assert haiku["requests"] == 3


def test_spend_report_group_by_cli_json(tmp_path, monkeypatch):
    spend_path = tmp_path / "spend.sqlite3"
    ledger = SpendLedger(spend_path, enabled=True)
    _row(ledger, service_tier="default", cost_usd=0.10)
    _row(ledger, request_id="r2", service_tier="priority", cost_usd=0.20)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("DAARI_USAGE__SPEND__ENABLED", "true")
    monkeypatch.setenv("DAARI_USAGE__SPEND__PATH", str(spend_path))
    from daari.config.settings import get_settings

    get_settings.cache_clear()
    result = CliRunner().invoke(
        cli_app,
        [
            "spend",
            "report",
            "--since",
            SINCE,
            "--group-by",
            "model,service_tier",
            "--bucket",
            "day",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert len(payload) == 2
    tiers = {row["service_tier"] for row in payload}
    assert tiers == {"default", "priority"}


@pytest.mark.asyncio
async def test_http_spend_report_group_by_analyst_scoped(settings, tmp_path):
    spend_path = tmp_path / "spend.sqlite3"
    settings.server.api_key = "master-sekret"
    settings.enterprise.sso.enabled = False
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(spend_path)
    settings.usage.path = str(tmp_path / "usage.sqlite3")

    ledger = SpendLedger(spend_path, enabled=True)
    _row(ledger, team_id="team-1", service_tier="default", cost_usd=0.10)
    _row(
        ledger,
        request_id="other",
        team_id="team-2",
        service_tier="priority",
        cost_usd=0.99,
    )

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.ctx.router.spend_ledger = ledger
    headers = {"Authorization": "Bearer master-sekret"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bad = await client.get(
            "/v1/daari/spend/report",
            params={"since": SINCE, "group_by": "notadim"},
            headers=headers,
        )
        assert bad.status_code == 400

        resp = await client.get(
            "/v1/daari/spend/report",
            params={
                "since": SINCE,
                "group_by": "model,service_tier",
                "bucket": "day",
                "team": "team-1",
            },
            headers=headers,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["team_id"] == "team-1"
    assert len(body["rows"]) == 1
    assert body["rows"][0]["service_tier"] == "default"
    assert abs(body["rows"][0]["cost_usd"] - 0.10) < 1e-9
