"""Per-row ``credential_source`` on billed ledger rows (team BYOK reconcile, #2315)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message, RequestMeta
from daari.observability.spend import SpendContext, SpendLedger, install_spend_hook
from daari.observability.usage import UsageLedger
from daari.router.router import AppContext
from daari.server.auth import AuthClaims, apply_auth_claims_to_meta


def _sources(path: Path) -> list[tuple[str, str]]:
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT request_id, credential_source FROM spend_requests ORDER BY id"
        ).fetchall()


def test_migrate_adds_credential_source_and_keeps_old_rows_readable(tmp_path: Path):
    path = tmp_path / "spend.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE spend_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                request_id TEXT NOT NULL,
                key_id TEXT NOT NULL DEFAULT '',
                team_id TEXT NOT NULL DEFAULT '',
                client_id TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                tier TEXT NOT NULL DEFAULT '',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cached_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0,
                cost_avoided_usd REAL NOT NULL DEFAULT 0,
                cache_hit INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO spend_requests (ts, request_id, model, tier, cost_usd)
            VALUES ('2026-09-03T12:00:00Z', 'old', 'claude-sonnet-4-5', 'L6', 0.5);
            """
        )
    ledger = SpendLedger(path, enabled=True)
    assert ledger.enabled
    ledger.record(request_id="new", model="claude-sonnet-4-5", tier="L6", credential_source="team")
    assert _sources(path) == [("old", ""), ("new", "team")]
    rows = list(ledger.iter_rows(since="2026-01-01T00:00:00Z"))
    assert [row["request_id"] for row in rows] == ["old", "new"]


def test_record_from_usage_stamps_source_only_on_frontier_rows(tmp_path: Path):
    path = tmp_path / "spend.sqlite3"
    ledger = SpendLedger(path, enabled=True)
    ledger.record_from_usage(
        SpendContext(request_id="k1", credential_source="key"),
        tier="L6",
        model="claude-sonnet-4-5",
        input_tokens=10,
        output_tokens=5,
    )
    ledger.record_from_usage(
        SpendContext(request_id="g1"),
        tier="L6",
        model="claude-sonnet-4-5",
        input_tokens=10,
        output_tokens=5,
    )
    ledger.record_from_usage(
        SpendContext(request_id="local", credential_source="team"),
        tier="L3",
        model="llama3.2:3b",
        input_tokens=10,
        output_tokens=5,
    )
    assert _sources(path) == [("k1", "key"), ("g1", "global"), ("local", "")]


def test_apply_auth_claims_stamps_credential_source_key_over_team(tmp_path: Path):
    from daari.auth.virtual_keys import VirtualKeyStore

    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    store.create_team("eng", frontier_api_key="sk-team")
    bound_key = store.create("k", team="eng", frontier_api_key="sk-key")
    team_only = store.create("t", team="eng")
    pool_only = store.create("p", frontier_pool="backup")

    key_meta = RequestMeta()
    apply_auth_claims_to_meta(
        key_meta,
        AuthClaims(
            kind="virtual",
            key_id=bound_key.key.key_id,
            virtual_key=bound_key.key,
            team_frontier_api_key="sk-team",
        ),
    )
    assert key_meta.frontier_api_key == "sk-key"
    assert key_meta.frontier_credential_source == "key"

    team_meta = RequestMeta()
    apply_auth_claims_to_meta(
        team_meta,
        AuthClaims(
            kind="virtual",
            key_id=team_only.key.key_id,
            virtual_key=team_only.key,
            team_frontier_api_key="sk-team",
        ),
    )
    assert team_meta.frontier_api_key == "sk-team"
    assert team_meta.frontier_credential_source == "team"

    pool_meta = RequestMeta()
    apply_auth_claims_to_meta(
        pool_meta,
        AuthClaims(kind="virtual", key_id=pool_only.key.key_id, virtual_key=pool_only.key),
    )
    assert pool_meta.frontier_pool == "backup"
    assert pool_meta.frontier_api_key is None
    assert pool_meta.frontier_credential_source is None


def _response(tier: str, model: str) -> InternalResponse:
    return InternalResponse(
        content="ok",
        model=model,
        daari_meta=DaariMeta(
            tier=tier,
            executor="frontier" if tier == "L6" else "ollama",
            provider_id="anthropic" if tier == "L6" else "ollama",
            model=model,
            input_tokens=100,
            output_tokens=20,
        ),
    )


@pytest.mark.asyncio
async def test_router_ledger_record_writes_credential_source(tmp_path: Path, settings):
    settings = settings.model_copy(
        update={"usage": settings.usage.model_copy(update={"db_path": str(tmp_path / "usage.db")})}
    )
    ctx = AppContext.from_settings(settings)
    ctx.router.usage_ledger = UsageLedger(tmp_path / "usage.db")
    spend_path = tmp_path / "spend.sqlite3"
    spend = SpendLedger(spend_path, enabled=True)
    ctx.router.spend_ledger = spend
    install_spend_hook(ctx.router.usage_ledger, spend)

    def _request(request_id: str, **meta_kwargs) -> InternalRequest:
        return InternalRequest(
            messages=[Message(role="user", content="hi")],
            model="claude-sonnet-4-5",
            meta=RequestMeta(request_id=request_id, **meta_kwargs),
        )

    ctx.router._ledger_record(
        _request("team-row", frontier_api_key="sk-team", frontier_credential_source="team"),
        _response("L6", "claude-sonnet-4-5"),
    )
    ctx.router._ledger_record(
        _request("key-row", frontier_api_key="sk-key", frontier_credential_source="key"),
        _response("L6", "claude-sonnet-4-5"),
    )
    ctx.router._ledger_record(_request("global-row"), _response("L6", "claude-sonnet-4-5"))
    ctx.router._ledger_record(
        _request("local-row", frontier_credential_source="team"),
        _response("L3", "llama3.2:3b"),
    )
    assert _sources(spend_path) == [
        ("team-row", "team"),
        ("key-row", "key"),
        ("global-row", "global"),
        ("local-row", ""),
    ]
