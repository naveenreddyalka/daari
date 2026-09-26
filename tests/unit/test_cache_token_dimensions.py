"""Cache-read / cache-write token dimensions (#1105).

Kong-parity: Anthropic usage fields reach cost + OTel + ledgers as distinct
cache_read / cache_creation dims.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager

import httpx
import pytest

from daari.gateway.internal import InternalRequest, Message
from daari.gateway.provider_prefs import usage_cost_and_cache
from daari.observability.spend import (
    EXPORT_FIELDS,
    SpendContext,
    SpendLedger,
    bind_spend_context,
    compute_request_usd,
    export_dict,
    install_spend_hook,
)
from daari.observability.usage import UsageLedger
from daari.pricing import cost_usd
from daari.router.frontier import FrontierExecutor


def test_anthropic_usage_fields_parsed_as_read_and_write():
    cost, cached, write = usage_cost_and_cache(
        {
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 50,
                "cache_read_input_tokens": 400,
                "cache_creation_input_tokens": 200,
            }
        }
    )
    assert cost is None
    assert cached == 400
    assert write == 200


def test_openai_cached_tokens_remain_read_with_zero_write():
    cost, cached, write = usage_cost_and_cache(
        {
            "usage": {
                "prompt_tokens": 80,
                "completion_tokens": 10,
                "cost": 0.0042,
                "prompt_tokens_details": {"cached_tokens": 64},
            }
        }
    )
    assert cost == pytest.approx(0.0042)
    assert cached == 64
    assert write == 0


@pytest.mark.asyncio
async def test_anthropic_frontier_records_cache_dims_on_meta():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "cached reply"}],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 700,
                    "cache_creation_input_tokens": 100,
                },
            },
        )

    executor = FrontierExecutor(
        base_url="https://api.anthropic.com",
        default_model="claude-haiku-4-5",
        api_key="sk-ant-test",
        provider="anthropic",
        transport=httpx.MockTransport(handler),
    )
    request = InternalRequest(
        messages=[Message(role="user", content="hello")],
        model="daari",
    )
    response = await executor.execute(request, escalated_from="L3", local_confidence=0.2)
    assert response.daari_meta.cached_tokens == 700
    assert response.daari_meta.cache_write_tokens == 100
    assert response.daari_meta.input_tokens == 1000
    assert response.daari_meta.output_tokens == 20


def test_cost_usd_receives_cache_write_tokens():
    from daari.config.settings import Settings

    settings = Settings()
    spent = cost_usd(
        "claude-haiku-4-5",
        1_000_000,
        0,
        settings.pricing,
        fallback_per_1k=0.002,
        cached_input_tokens=0,
        cache_write_tokens=1_000_000,
        cache_ttl="1h",
    )
    assert spent > 0


def test_compute_request_usd_bills_cache_writes():
    from daari.config.settings import Settings

    settings = Settings()
    with_write, _ = compute_request_usd(
        tier="L6",
        model="claude-haiku-4-5",
        input_tokens=1_000_000,
        output_tokens=0,
        cached_tokens=0,
        cache_write_tokens=1_000_000,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
        service_tier=None,
        cache_ttl="1h",
    )
    without, _ = compute_request_usd(
        tier="L6",
        model="claude-haiku-4-5",
        input_tokens=1_000_000,
        output_tokens=0,
        cached_tokens=0,
        cache_write_tokens=0,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
    )
    assert with_write > without


def test_usage_ledger_persists_cache_dims(tmp_path):
    ledger = UsageLedger(tmp_path / "ledger.sqlite3")
    ledger.record(
        tier="L6",
        model="claude-haiku-4-5",
        input_tokens=1000,
        output_tokens=50,
        cached_tokens=400,
        cache_write_tokens=200,
        day="2026-09-26",
    )

    with sqlite3.connect(tmp_path / "ledger.sqlite3") as conn:
        row = conn.execute(
            "SELECT cached_tokens, cache_write_tokens FROM usage"
        ).fetchone()
    assert row == (400, 200)


def test_usage_ledger_migrates_cache_columns_on_old_db(tmp_path):

    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE usage (
                day TEXT NOT NULL,
                tier TEXT NOT NULL,
                model TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT '',
                requests INTEGER NOT NULL DEFAULT 0,
                cache_hits INTEGER NOT NULL DEFAULT 0,
                prompt_chars INTEGER NOT NULL DEFAULT 0,
                completion_chars INTEGER NOT NULL DEFAULT 0,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, tier, model)
            )
            """
        )
        conn.execute(
            "INSERT INTO usage VALUES ('2026-09-01','L3','m','',1,0,10,10,2,2)"
        )
    ledger = UsageLedger(path)
    ledger.record(
        tier="L6",
        model="claude",
        cached_tokens=10,
        cache_write_tokens=5,
        day="2026-09-26",
        input_tokens=1,
        output_tokens=1,
    )
    with sqlite3.connect(path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(usage)")}
        assert "cached_tokens" in cols
        assert "cache_write_tokens" in cols
        row = conn.execute(
            "SELECT cached_tokens, cache_write_tokens FROM usage WHERE day='2026-09-26'"
        ).fetchone()
    assert row == (10, 5)


def test_spend_ledger_splits_read_and_write(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    ledger.record(
        ts="2026-09-26T00:00:00+00:00",
        request_id="req-cache",
        model="claude-haiku-4-5",
        tier="L6",
        input_tokens=1000,
        output_tokens=20,
        cached_tokens=700,
        cache_write_tokens=100,
        cost_usd=0.01,
    )
    row = next(ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))
    assert row["cached_tokens"] == 700
    assert row["cache_write_tokens"] == 100
    exported = export_dict(row)
    assert exported["cached_tokens"] == 700
    assert exported["cache_write_tokens"] == 100
    assert "cache_write_tokens" in EXPORT_FIELDS


def test_spend_hook_forwards_cache_write(tmp_path):
    from daari.config.settings import Settings

    usage = UsageLedger(tmp_path / "ledger.sqlite3")
    spend = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    install_spend_hook(usage, spend)
    settings = Settings()
    bind_spend_context(
        SpendContext(
            request_id="req-w",
            requested_model="claude-haiku-4-5",
            pricing=settings.pricing,
            fallback_per_1k=0.002,
        )
    )
    usage.record(
        tier="L6",
        model="claude-haiku-4-5",
        input_tokens=1_000_000,
        output_tokens=0,
        cached_tokens=0,
        cache_write_tokens=1_000_000,
        reported_cost=None,
    )
    row = next(spend.iter_rows(since="2000-01-01T00:00:00+00:00"))
    assert row["cache_write_tokens"] == 1_000_000
    assert row["cost_usd"] > 0


def test_postgres_spend_round_trip_mocked(monkeypatch):
    """Ledger round-trip on postgres backend (mocked connection)."""
    from daari.observability.spend import PostgresSpendLedger

    stored: list[tuple] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            if params and "INSERT" in sql.upper():
                stored.append(params)
            self._last_sql = sql
            self._params = params

        def fetchmany(self, n):
            if stored and "SELECT" in getattr(self, "_last_sql", "").upper():
                row = stored[0]
                # ts, request_id, key_id, team_id, client_id, model, tier,
                # input, output, cached, cache_write, cost, avoided, cache_hit
                return [
                    (
                        row[0],
                        row[1],
                        row[2],
                        row[3],
                        row[4],
                        row[5],
                        row[6],
                        row[7],
                        row[8],
                        row[9],
                        row[10],
                        row[11],
                        row[12],
                        row[13],
                    )
                ]
            return []

        def fetchone(self):
            return (0,)

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    @contextmanager
    def fake_pooled(dsn: str):
        yield FakeConn()

    monkeypatch.setattr("daari.gateway.pg_pool.pooled_connection", fake_pooled)
    ledger = PostgresSpendLedger.__new__(PostgresSpendLedger)
    ledger.dsn = "postgresql://x/y"
    ledger.enabled = True
    ledger._lock = __import__("threading").Lock()
    ledger.record(
        ts="2026-09-26T00:00:00+00:00",
        request_id="pg-req",
        model="claude",
        tier="L6",
        input_tokens=10,
        output_tokens=2,
        cached_tokens=4,
        cache_write_tokens=3,
        cost_usd=0.1,
    )
    assert stored, "expected INSERT"
    assert stored[0][9] == 4  # cached_tokens
    assert stored[0][10] == 3  # cache_write_tokens

