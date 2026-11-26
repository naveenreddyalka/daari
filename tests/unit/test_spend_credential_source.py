"""credential_source + frontier_slot_id on every billed spend row (#2314)."""

from __future__ import annotations

import sqlite3

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.auth.frontier_binding import credential_source_for_meta
from daari.auth.virtual_keys import VirtualKey
from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.config.settings import Settings
from daari.gateway.internal import (
    DaariMeta,
    InternalRequest,
    InternalResponse,
    Message,
    RequestMeta,
)
from daari.observability.metrics import Metrics
from daari.observability.render import report_markdown
from daari.observability.spend import (
    EXPORT_FIELDS,
    GROUP_BY_DIMS,
    SpendContext,
    SpendLedger,
    bind_spend_context,
    current_spend_context,
    export_dict,
    install_spend_hook,
)
from daari.observability.usage import UsageLedger
from daari.router.frontier import FrontierExecutor
from daari.router.frontier_pool import FrontierPool, ProviderSlot
from daari.router.router import AppContext, OllamaExecutor, Router
from daari.server.app import create_app
from daari.server.auth import AuthClaims, apply_auth_claims_to_meta
from tests.conftest import NoopEmbedder

SINCE = "2026-01-01T00:00:00+00:00"
TS = "2026-06-15T12:00:00+00:00"

_PRE_2314_SCHEMA = """
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
    usage_speed TEXT NOT NULL DEFAULT '',
    service_tier TEXT NOT NULL DEFAULT ''
);
"""


def _row(ledger: SpendLedger, **overrides) -> None:
    payload = {
        "ts": TS,
        "request_id": "req-a",
        "key_id": "key-1",
        "team_id": "team-x",
        "client_id": "client-a",
        "user_id": "alice",
        "model": "gpt-4o-mini",
        "provider": "openai",
        "tier": "L6",
        "input_tokens": 1000,
        "output_tokens": 0,
        "cost_usd": 0.10,
        "cost_avoided_usd": 0.0,
        "cache_hit": False,
    }
    payload.update(overrides)
    ledger.record(**payload)


def _request(**meta_kwargs) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="escalate me")],
        model="daari",
        meta=RequestMeta(**meta_kwargs),
    )


def _l6(provider: str = "primary") -> InternalResponse:
    return InternalResponse(
        content=f"answer from {provider}",
        model="gpt-4o-mini",
        daari_meta=DaariMeta(
            tier="L6",
            executor="frontier",
            provider_id=provider,
            model="gpt-4o-mini",
            input_tokens=80,
            output_tokens=20,
            usage_estimated=False,
            cost_usd=0.05,
        ),
    )


def _pool(slot_id: str = "primary") -> tuple[FrontierPool, FrontierExecutor]:
    executor = FrontierExecutor(
        base_url="http://primary", default_model="a", api_key="sk-global", provider=slot_id
    )

    async def ok(request, *, escalated_from, local_confidence):
        return _l6(slot_id)

    executor.execute = ok  # type: ignore[method-assign]
    pool = FrontierPool(
        slots=[ProviderSlot(id=slot_id, executor=executor, keys=["sk-global"])],
        api_key="sk-global",
        default_model="gpt-4o-mini",
    )
    return pool, executor


# --- ledger schema -----------------------------------------------------------


def test_migrate_adds_credential_columns_and_keeps_old_rows_readable(tmp_path):
    path = tmp_path / "spend.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(_PRE_2314_SCHEMA)
        conn.execute(
            "INSERT INTO spend_requests (ts, request_id, key_id, model, tier, cost_usd)"
            " VALUES (?, 'old-row', 'key-old', 'gpt-4o-mini', 'L6', 0.5)",
            (TS,),
        )
    ledger = SpendLedger(path, enabled=True)
    assert ledger.enabled is True
    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(spend_requests)")}
    assert {"credential_source", "frontier_slot_id"} <= columns

    rows = list(ledger.iter_rows(since=SINCE))
    assert [r["request_id"] for r in rows] == ["old-row"]
    assert rows[0]["credential_source"] == ""
    assert rows[0]["frontier_slot_id"] == ""
    exported = export_dict(rows[0])
    assert exported["credential_source"] == ""
    assert exported["frontier_slot_id"] == ""

    _row(ledger, request_id="new-row", credential_source="team", frontier_slot_id="openai-byok")
    rows = {r["request_id"]: r for r in ledger.iter_rows(since=SINCE)}
    assert rows["new-row"]["credential_source"] == "team"
    assert rows["new-row"]["frontier_slot_id"] == "openai-byok"


def test_export_fields_and_group_by_dims_include_credential_columns():
    assert "credential_source" in EXPORT_FIELDS
    assert "frontier_slot_id" in EXPORT_FIELDS
    assert "credential_source" in GROUP_BY_DIMS
    assert "frontier_slot_id" in GROUP_BY_DIMS


def test_record_from_usage_copies_binding_from_spend_context(tmp_path):
    usage = UsageLedger(tmp_path / "ledger.sqlite3")
    spend = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    install_spend_hook(usage, spend)
    bind_spend_context(
        SpendContext(
            key_id="key-a",
            team_id="team-1",
            request_id="req-bound",
            requested_model="gpt-4o-mini",
            pricing=Settings().pricing,
            credential_source="key",
            frontier_slot_id="primary",
        )
    )
    usage.record(tier="L6", model="gpt-4o-mini", input_tokens=1000, output_tokens=10)
    row = next(spend.iter_rows(since=SINCE))
    assert row["credential_source"] == "key"
    assert row["frontier_slot_id"] == "primary"


def test_by_credential_rollup_and_group_by(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    _row(ledger, request_id="g1", credential_source="global", frontier_slot_id="openai", cost_usd=0.10)
    _row(ledger, request_id="g2", credential_source="global", frontier_slot_id="openai", cost_usd=0.05)
    _row(
        ledger,
        request_id="t1",
        team_id="team-y",
        credential_source="team",
        frontier_slot_id="openai",
        cost_usd=0.20,
    )
    _row(ledger, request_id="k1", credential_source="key", frontier_slot_id="anthropic", cost_usd=0.02)
    _row(ledger, request_id="local", tier="L3", provider="", credential_source="", cost_usd=0.0)

    rollup = {
        (r["credential_source"], r["frontier_slot_id"]): r
        for r in ledger.by_credential(since=SINCE)
    }
    assert set(rollup) == {("global", "openai"), ("team", "openai"), ("key", "anthropic")}
    assert rollup[("global", "openai")]["requests"] == 2
    assert rollup[("global", "openai")]["cost_usd"] == pytest.approx(0.15)
    assert rollup[("team", "openai")]["cost_usd"] == pytest.approx(0.20)
    assert rollup[("key", "anthropic")]["requests"] == 1

    scoped = ledger.by_credential(since=SINCE, team_id="team-y")
    assert [(r["credential_source"], r["cost_usd"]) for r in scoped] == [("team", pytest.approx(0.20))]

    grouped = {r["credential_source"]: r for r in ledger.grouped_report(since=SINCE, group_by="credential_source")}
    assert grouped["global"]["requests"] == 2
    assert grouped["key"]["cost_usd"] == pytest.approx(0.02)


# --- binding -> credential_source ---------------------------------------------


def test_credential_source_for_meta_precedence():
    assert credential_source_for_meta(RequestMeta()) == "global"
    assert credential_source_for_meta(RequestMeta(frontier_pool="openai-byok")) == "global"
    assert (
        credential_source_for_meta(
            RequestMeta(frontier_api_key="sk-t", frontier_credential_source="team")
        )
        == "team"
    )
    assert (
        credential_source_for_meta(
            RequestMeta(frontier_api_key="sk-k", frontier_credential_source="key")
        )
        == "key"
    )
    # Bound credential with no recorded origin is attributed to the key.
    assert credential_source_for_meta(RequestMeta(frontier_api_key="sk-k")) == "key"


def test_apply_auth_claims_stamps_key_over_team_source():
    vk = VirtualKey(key_id="k1", name="alice", prefix="dk_", team_id="eng")
    claims = AuthClaims(
        kind="virtual",
        key_id="k1",
        virtual_key=vk,
        team_frontier_api_key="sk-team",
    )
    meta = RequestMeta()
    apply_auth_claims_to_meta(meta, claims)
    assert meta.frontier_api_key == "sk-team"
    assert meta.frontier_credential_source == "team"

    vk_bound = VirtualKey(
        key_id="k2", name="bob", prefix="dk_", team_id="eng", frontier_api_key="sk-key"
    )
    claims = AuthClaims(
        kind="virtual",
        key_id="k2",
        virtual_key=vk_bound,
        team_frontier_api_key="sk-team",
    )
    meta = RequestMeta()
    apply_auth_claims_to_meta(meta, claims)
    assert meta.frontier_api_key == "sk-key"
    assert meta.frontier_credential_source == "key"

    meta = RequestMeta()
    apply_auth_claims_to_meta(
        meta, AuthClaims(kind="virtual", key_id="k3", virtual_key=vk)
    )
    assert meta.frontier_api_key is None
    assert meta.frontier_credential_source is None


# --- frontier pool stamps the winning slot -----------------------------------


@pytest.mark.asyncio
async def test_pool_execute_stamps_meta_and_spend_context():
    pool, _executor = _pool("primary")
    bind_spend_context(SpendContext(request_id="r1"))
    unbound = await pool.execute(_request(), escalated_from="L3", local_confidence=0.2)
    assert unbound.daari_meta.credential_source == "global"
    assert unbound.daari_meta.frontier_slot_id == "primary"
    ctx = current_spend_context()
    assert ctx is not None
    assert (ctx.credential_source, ctx.frontier_slot_id) == ("global", "primary")

    bind_spend_context(SpendContext(request_id="r2"))
    team = await pool.execute(
        _request(frontier_api_key="sk-team", frontier_credential_source="team"),
        escalated_from="L3",
        local_confidence=0.2,
    )
    assert team.daari_meta.credential_source == "team"
    ctx = current_spend_context()
    assert ctx is not None and ctx.credential_source == "team"

    key = await pool.execute(
        _request(frontier_api_key="sk-key", frontier_credential_source="key"),
        escalated_from="L3",
        local_confidence=0.2,
    )
    assert key.daari_meta.credential_source == "key"
    assert key.daari_meta.frontier_slot_id == "primary"
    assert pool.last_credential_source == "key"
    assert pool.last_frontier_slot_id == "primary"


@pytest.mark.asyncio
async def test_pool_stream_stamps_spend_context_and_last_slot():
    executor = FrontierExecutor(
        base_url="http://byok", default_model="a", api_key="sk-global", provider="openai-byok"
    )

    async def fake_stream(request, *, escalated_from, local_confidence):
        yield "data: {}\n\n"

    executor.stream = fake_stream  # type: ignore[method-assign]
    pool = FrontierPool(
        slots=[ProviderSlot(id="openai-byok", executor=executor, keys=["sk-global"])]
    )
    bind_spend_context(SpendContext(request_id="s1"))
    events = [
        event
        async for event in pool.stream(
            _request(frontier_pool="openai-byok", frontier_api_key="sk-team", frontier_credential_source="team"),
            escalated_from="L3",
            local_confidence=0.2,
        )
    ]
    assert events
    ctx = current_spend_context()
    assert ctx is not None
    assert (ctx.credential_source, ctx.frontier_slot_id) == ("team", "openai-byok")
    assert pool.last_credential_source == "team"
    assert pool.last_frontier_slot_id == "openai-byok"


# --- router record site -------------------------------------------------------


def _router(tmp_path, frontier, *, ledger: UsageLedger) -> Router:
    local = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=local,
        ollama_l3=local,
        ollama_l4=local,
        ollama_l5=local,
        metrics=Metrics(),
        frontier=frontier,
        frontier_enabled=True,
        usage_ledger=ledger,
        frontier_price_per_1k_tokens=0.002,
        virtual_models={"byok-chat": ["openai/gpt-4o-mini"]},
    )
    spend = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    router.spend_ledger = spend
    install_spend_hook(ledger, spend)
    return router


@pytest.mark.asyncio
async def test_router_l6_row_records_credential_source_and_slot(tmp_path):
    pool, _executor = _pool("openai")
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    router = _router(tmp_path, pool, ledger=ledger)

    unbound = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="byok-chat",
        meta=RequestMeta(key_id="k-global", team_id="eng"),
    )
    response = await router.route(unbound)
    assert response.daari_meta.tier == "L6"
    assert response.daari_meta.credential_source == "global"
    assert response.daari_meta.frontier_slot_id == "openai"

    bound = InternalRequest(
        messages=[Message(role="user", content="hi again")],
        model="byok-chat",
        meta=RequestMeta(
            key_id="k-bound",
            team_id="eng",
            frontier_api_key="sk-key",
            frontier_credential_source="key",
        ),
    )
    response = await router.route(bound)
    assert response.daari_meta.credential_source == "key"

    rows = {r["key_id"]: r for r in router.spend_ledger.iter_rows(since="1970-01-01T00:00:00+00:00")}
    assert rows["k-global"]["credential_source"] == "global"
    assert rows["k-global"]["frontier_slot_id"] == "openai"
    assert rows["k-bound"]["credential_source"] == "key"
    assert rows["k-bound"]["frontier_slot_id"] == "openai"
    assert float(rows["k-bound"]["cost_usd"]) > 0


# --- daari report rollup -------------------------------------------------------


@pytest.mark.asyncio
async def test_report_endpoint_and_markdown_split_frontier_spend_by_credential(settings, tmp_path):
    settings.server.api_key = "master"
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    spend = app.state.ctx.router.spend_ledger
    assert spend is not None and spend.enabled
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    _row(spend, ts=now, request_id="g1", credential_source="global", frontier_slot_id="openai", cost_usd=0.30)
    _row(spend, ts=now, request_id="t1", credential_source="team", frontier_slot_id="openai", cost_usd=0.20)
    _row(spend, ts=now, request_id="k1", credential_source="key", frontier_slot_id="anthropic", cost_usd=0.10)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/daari/report?days=1", headers={"Authorization": "Bearer master"}
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    rows = payload["frontier_credential_spend"]
    by_source = {(r["credential_source"], r["frontier_slot_id"]): r for r in rows}
    assert by_source[("global", "openai")]["cost_usd"] == pytest.approx(0.30)
    assert by_source[("team", "openai")]["cost_usd"] == pytest.approx(0.20)
    assert by_source[("key", "anthropic")]["requests"] == 1

    md = report_markdown(payload, days=1)
    assert "Frontier spend by credential" in md
    assert "| team | openai |" in md


def test_report_cli_text_prints_credential_rollup(monkeypatch):
    payload = {
        "enabled": True,
        "days": [],
        "totals": {"requests": 3, "cache_hits": 0, "local_requests": 0, "frontier_requests": 3},
        "frontier_credential_spend": [
            {
                "credential_source": "team",
                "frontier_slot_id": "openai",
                "requests": 2,
                "cost_usd": 0.2,
                "cost_avoided_usd": 0.0,
            },
            {
                "credential_source": "global",
                "frontier_slot_id": "openai",
                "requests": 1,
                "cost_usd": 0.3,
                "cost_avoided_usd": 0.0,
            },
        ],
    }

    def fake_get(url, timeout=5.0):
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    from daari.cli.app import app as cli_app

    result = CliRunner().invoke(cli_app, ["report"])
    assert result.exit_code == 0, result.output
    assert "frontier spend by credential" in result.output
    assert "team" in result.output and "0.2000" in result.output
    assert "global" in result.output and "0.3000" in result.output
