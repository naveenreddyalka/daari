"""Hermetic gateway coverage for the 2026-10-24/27 waves (#1930, #1960, #1980).

Covers streamed TTS spend, Responses completion webhooks, org enforcement
ingest, Decisions input_json+image L0, Anthropic stream cache writes,
user_rpd isolation, fleet-shared breakers, grouped spend reports, per-family
breaker reset, Anthropic metadata.user_id RPD, AAIF skills prefix, Phonon
format/language tags, at-rest response sealing, gpt-6.1-terra billing, and
SEP-2640 skills doors under MCP grant governance. Same convention as other
non-@integration modules under tests/integration/.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_limit import MemoryCounterBackend, RateLimiter
from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import AnthropicSettings, _load_skills_system_prefix
from daari.enterprise.anthropic_org_webhooks import (
    ENFORCEMENT_OPENED,
    sign_standard_webhook,
)
from daari.enterprise.enforcement_sync import EnforcementStore
from daari.gateway import speech, systemone
from daari.gateway.cost_headers import COST_HEADER
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.mcp_policy import TOOL_DENIED
from daari.observability.budget_alerts import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    verify_webhook_signature,
)
from daari.observability.responses_webhooks import wait_responses_webhooks
from daari.observability.spend import SpendLedger
from daari.pricing import cost_usd
from daari.router import breaker_redis
from daari.router.circuit_breaker import CircuitBreaker
from daari.router.frontier import FrontierExecutor
from daari.router.router import AppContext
from daari.security.at_rest import AtRestDecryptError, is_sealed, reset_at_rest
from daari.server.app import create_app
from tests.conftest import META_HEADERS, mock_all_ollama_executors

SECRET_RAW = b"test-org-webhook-secret-key!!"
ORG_SECRET = "whsec_" + base64.b64encode(SECRET_RAW).decode()
FROZEN = 1_700_000_030.0
CHAT = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def _enable_spend(settings, tmp_path):
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")


def _spend_rows(app):
    ledger = app.state.ctx.router.spend_ledger
    return list(ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))


def _freeze(monkeypatch, clock: dict[str, float]) -> None:
    monkeypatch.setattr(time, "time", lambda: clock["now"])
    monkeypatch.setattr("daari.auth.rate_limit.time.time", lambda: clock["now"])


def _org_event(event_type: str, *, profile_id: str) -> dict:
    return {
        "type": "event",
        "id": "whe_wave_coverage_1",
        "created_at": "2026-10-15T17:02:41Z",
        "data": {
            "type": event_type,
            "id": profile_id,
            "enforcement_action_id": "enac_wave_1",
            "organization_id": "org_wave_1",
        },
    }


def _signed_org_headers(body: bytes, secret: str = ORG_SECRET) -> dict[str, str]:
    msg_id = "msg_wave_org_1"
    timestamp = str(int(time.time()))
    return {
        "webhook-id": msg_id,
        "webhook-timestamp": timestamp,
        "webhook-signature": sign_standard_webhook(body, secret, msg_id, timestamp),
        "content-type": "application/json",
    }


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = int(ex)
        return True

    def incr(self, key: str) -> int:
        cur = int(self.store.get(key) or 0) + 1
        self.store[key] = str(cur)
        return cur

    def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = int(seconds)
        return True

    def delete(self, *keys: str) -> int:
        n = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                n += 1
            self.ttls.pop(key, None)
        return n

    def keys(self, pattern: str) -> list[str]:
        prefix = pattern.rstrip("*")
        return [k for k in self.store if k.startswith(prefix)]


@pytest.fixture(autouse=True)
def _clean_shared_breakers():
    breaker_redis.set_breaker_redis(None)
    systemone.reset_systemone_breakers()
    systemone.set_systemone_breaker_redis(None)
    yield
    breaker_redis.set_breaker_redis(None)
    systemone.reset_systemone_breakers()
    systemone.set_systemone_breaker_redis(None)


# --- (a) streamed TTS + spend ---


@pytest.mark.asyncio
async def test_streamed_speech_records_spend_row(settings, tmp_path, monkeypatch):
    """Chunked /v1/audio/speech finalizes a tts spend row (#1930)."""

    class _FakeUpstream:
        status_code = 200
        headers = httpx.Headers(
            {"content-type": "audio/mpeg", "transfer-encoding": "chunked"}
        )

        async def aiter_bytes(self, chunk_size: int = 65536):
            yield b"FIRST"
            yield b"SECOND"

        async def aread(self):
            raise AssertionError("stream path must not buffer via aread")

    @asynccontextmanager
    async def _fake_stream(client, method, url, **kwargs):
        assert method == "POST"
        yield _FakeUpstream()

    monkeypatch.setattr(speech, "deadline_bounded_stream", _fake_stream)
    speech._http = httpx.AsyncClient()
    _enable_spend(settings, tmp_path)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.tts.base_url = "http://tts.local/v1"
    settings.tts.model = "kokoro"
    store = VirtualKeyStore(settings.virtual_keys_path)
    key = store.create("bot", client_id="client-bot", team="eng")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={"model": "ignored", "input": "stream charge", "voice": "alloy"},
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
    assert response.status_code == 200, response.text
    assert response.content == b"FIRSTSECOND"
    rows = _spend_rows(app)
    assert len(rows) == 1
    assert rows[0]["tier"] == "tts"
    assert rows[0]["key_id"] == key.key.key_id
    assert rows[0]["model"] == "kokoro"
    await speech.aclose_http()


# --- (b) Responses completion webhook ---


@pytest.mark.asyncio
async def test_background_responses_delivers_signed_completion_webhook(
    settings, monkeypatch
):
    seen: list[httpx.Request] = []

    class Capture(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

    transport = Capture()
    real_deliver = __import__(
        "daari.observability.responses_webhooks", fromlist=["deliver_responses_completion_webhook"]
    ).deliver_responses_completion_webhook

    def deliver_with_capture(**kwargs):
        kwargs["transport"] = transport
        return real_deliver(**kwargs)

    monkeypatch.setattr(
        "daari.observability.responses_webhooks.deliver_responses_completion_webhook",
        deliver_with_capture,
    )

    settings.alerts.responses_completion_webhook_url = "https://hooks.example/responses"
    settings.alerts.responses_completion_webhook_secret = "whsec_test"
    app = _app(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="done in background",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=5),
        )

    app.state.ctx.router.route = fake_route

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "later", "background": True},
        )
        assert created.status_code == 200
        assert created.json()["status"] == "queued"
        response_id = created.json()["id"]
        body = None
        for _ in range(40):
            fetched = await client.get(f"/v1/responses/{response_id}")
            body = fetched.json()
            if body.get("status") == "completed":
                break
            await asyncio.sleep(0.05)
    assert body is not None and body["status"] == "completed"
    wait_responses_webhooks(timeout=5.0)
    assert len(seen) == 1
    req = seen[0]
    assert str(req.url) == "https://hooks.example/responses"
    raw = req.content
    ts = req.headers[TIMESTAMP_HEADER]
    sig = req.headers[SIGNATURE_HEADER]
    assert verify_webhook_signature(raw, sig, "whsec_test", ts)
    payload = json.loads(raw)
    assert payload["status"] == "completed"
    assert payload["id"] == response_id


# --- (c) org enforcement webhook ---


@pytest.mark.asyncio
async def test_org_enforcement_webhook_updates_readable_state(
    settings, tmp_path, monkeypatch
):
    settings.server.api_key = ""
    settings.server.virtual_keys.enabled = False
    profile_id = "uprof_wave_coverage"
    settings.anthropic = AnthropicSettings(
        org_webhook_signing_secret=ORG_SECRET,
        enforcement_state_path=str(tmp_path / "enforcement.json"),
        user_profiles={"erin": profile_id},
    )
    app = _app(settings)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(f"/v1/user_profiles/{profile_id}")
        return httpx.Response(
            200,
            json={
                "type": "user_profile",
                "id": profile_id,
                "enforcement_status": "banned",
                "enforcement_actions": [
                    {
                        "type": "ban",
                        "id": "enac_wave_1",
                        "reason": "fraud_or_abuse",
                        "opened_at": "2026-10-15T17:02:41Z",
                        "expires_at": None,
                    }
                ],
            },
        )

    monkeypatch.setattr(
        "daari.enterprise.anthropic_org_webhooks._default_transport",
        lambda: httpx.MockTransport(handler),
    )
    monkeypatch.setattr(
        type(settings),
        "resolve_frontier_api_key",
        lambda self: "sk-ant-test",
        raising=False,
    )

    body = json.dumps(_org_event(ENFORCEMENT_OPENED, profile_id=profile_id)).encode()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/daari/webhooks/anthropic/org",
            content=body,
            headers=_signed_org_headers(body),
        )
    assert response.status_code == 200
    assert response.json()["enforcement_status"] == "banned"
    store = EnforcementStore(Path(settings.anthropic.enforcement_state_path))
    rows = store.load()
    assert len(rows) == 1
    assert rows[0]["profile_id"] == profile_id
    assert rows[0]["enforcement_status"] == "banned"
    assert rows[0]["end_users"] == ["erin"]


# --- (d) decisions input_json + image + L0 ---


@pytest.mark.asyncio
async def test_decisions_input_json_and_image_l0_fingerprint(settings, monkeypatch):
    from daari.gateway import systemone

    calls = {"n": 0}
    systemone_ok = {
        "model": "nimble",
        "answers": {
            "department": {
                "type": "choice",
                "choice": "billing",
                "probabilities": {"billing": 0.9, "other": 0.1},
                "confidence": 0.9,
            }
        },
        "usage": {"input_tokens": 40, "output_tokens": 1},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        payload = json.loads(request.read())
        assert "49" in payload["state"] or "duplicate" in payload["state"].lower()
        assert payload.get("images") == ["aGVsbG8="]
        return httpx.Response(200, json=systemone_ok)

    systemone._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.systemone.httpx.AsyncClient", Patched)
    settings.ollama.base_url = "http://ollama.local:11434"
    app = _app(settings)

    body = {
        "model": "nimble",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Inspect the charge."},
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,aGVsbG8=",
                    },
                ],
            }
        ],
        "input_json": {
            "ticket": {"body": "Please refund the duplicate charge."},
            "order": {"charges": [49, 49]},
        },
        "questions": [
            {
                "type": "choice",
                "name": "department",
                "instructions": "Which department?",
                "choices": [{"value": "billing"}, {"value": "other"}],
            }
        ],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/v1/decisions", json=body)
        second = await client.post("/v1/decisions", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["daari_meta"]["tier"] == "decisions"
    assert second.status_code == 200
    assert second.json()["daari_meta"]["tier"] == "L0"
    assert second.json()["daari_meta"]["cache_hit"] is True
    assert calls["n"] == 1


# --- (e) Anthropic streamed cache_creation → spend ---


def _anthropic_sse_with_cache_write(*, write_tokens: int) -> bytes:
    events = [
        {
            "type": "message_start",
            "message": {
                "id": "msg_wave",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-4-5",
                "content": [],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 0,
                    "cache_read_input_tokens": 700,
                    "cache_creation_input_tokens": write_tokens,
                },
            },
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "cached"},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 4},
        },
        {"type": "message_stop"},
    ]
    parts = []
    for event in events:
        parts.append(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n")
    return "".join(parts).encode()


async def _low_confidence(_request: InternalRequest) -> InternalResponse:
    return InternalResponse(
        content="no",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
    )


async def _low_confidence_stream(_request: InternalRequest):
    yield {"message": {"content": "no"}, "done": True}


@pytest.mark.asyncio
async def test_anthropic_stream_cache_creation_hits_spend(
    settings, tmp_path, monkeypatch
):
    """Anthropic stream cache_creation_input_tokens lands on spend + cost header (#1930)."""
    write_tokens = 100
    _enable_spend(settings, tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_anthropic_sse_with_cache_write(write_tokens=write_tokens),
            headers={"content-type": "text/event-stream"},
        )

    app = _app(settings)
    frontier = FrontierExecutor(
        base_url="https://api.anthropic.com",
        default_model="claude-haiku-4-5",
        api_key="sk-ant-test",
        provider="anthropic",
        transport=httpx.MockTransport(handler),
    )
    app.state.ctx.router.frontier = frontier
    app.state.ctx.router.frontier_enabled = True
    # Short local stream ("no") scores confidence 0 → frontier relay (#155).
    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, _low_confidence)
    seen: set[int] = set()
    for attr in ("ollama_l3", "ollama_l4", "ollama_l5", "ollama"):
        executor = getattr(app.state.ctx.router, attr, None)
        if executor is None or id(executor) in seen:
            continue
        seen.add(id(executor))
        monkeypatch.setattr(executor, "stream", _low_confidence_stream)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # OpenAI chat stream path relays Anthropic frontier SSE (same as #1766).
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "claude-haiku-4-5",
                "stream": True,
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
    assert response.status_code == 200, response.text
    assert getattr(frontier, "last_stream_cache_write_tokens", None) == write_tokens
    assert COST_HEADER in response.headers
    rows = _spend_rows(app)
    assert rows
    assert rows[-1]["cache_write_tokens"] == write_tokens
    assert float(response.headers[COST_HEADER]) == pytest.approx(float(rows[-1]["cost_usd"]))


# --- (f) user_rpd isolates two users ---


@pytest.mark.asyncio
async def test_gateway_user_rpd_isolates_two_users(settings, tmp_path, monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    app.state.rate_limiter = RateLimiter(MemoryCounterBackend())

    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.ollama.execute = fake
    created = store.create("shared", user_rpd=1)
    headers = {
        "Authorization": f"Bearer {created.plaintext}",
        "X-Daari-No-Cache": "true",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        alice_ok = await client.post(
            "/v1/chat/completions", json={**CHAT, "user": "alice"}, headers=headers
        )
        alice_denied = await client.post(
            "/v1/chat/completions", json={**CHAT, "user": "alice"}, headers=headers
        )
        bob_ok = await client.post(
            "/v1/chat/completions", json={**CHAT, "user": "bob"}, headers=headers
        )
    assert alice_ok.status_code == 200
    assert alice_denied.status_code == 429
    assert alice_denied.json()["error"]["type"] == "rate_limit_error"
    assert alice_denied.headers.get("x-ratelimit-scope") == "user"
    assert bob_ok.status_code == 200


# --- (g) fleet breaker shared across two app instances ---


@pytest.mark.asyncio
async def test_fleet_breaker_open_visible_on_second_app_instance(settings):
    """Trip on one app instance; a second instance sharing FakeRedis sees open (#1930)."""
    # create_app clears breaker Redis when cache.backend != redis — wire FakeRedis after.
    app_a = _app(settings)
    app_b = _app(settings)
    assert app_a.state.ctx is not None and app_b.state.ctx is not None

    redis = FakeRedis()
    breaker_redis.set_breaker_redis(redis)
    systemone.set_systemone_breaker_redis(redis)

    a = CircuitBreaker(
        failure_threshold=1,
        cooldown_seconds=60.0,
        share_key="frontier:openai",
    )
    a.record_failure()
    assert a.state == "open"

    # Pod B: fresh local breaker, same Redis — must see open without local trip.
    b = CircuitBreaker(
        failure_threshold=1,
        cooldown_seconds=60.0,
        share_key="frontier:openai",
    )
    assert b.state == "open"
    assert b.allow() is False

    # Systemone family: trip on "pod A", observe on wiped local dict ("pod B").
    base = "http://vllm.local:8000"
    breaker = systemone.breaker_for(base)
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 60.0
    systemone._note_failure(base)
    systemone._breakers.clear()
    systemone._breaker_rejects.clear()
    rows = systemone.breaker_snapshot()
    assert rows and rows[0]["state"] == "open"
    with pytest.raises(systemone.SystemOneCircuitOpen):
        systemone._reject_if_open(base)


# --- (h) grouped spend report + bad bucket (#1960 / #1944) ---

SINCE = "2026-01-01T00:00:00+00:00"
DAY_A = "2026-06-15T10:00:00+00:00"


def _spend_seed(ledger: SpendLedger, **overrides) -> None:
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


@pytest.mark.asyncio
async def test_spend_report_group_by_service_tier_and_bad_bucket(settings, tmp_path):
    """GET /v1/daari/spend/report honors group_by+bucket; bad bucket → 400 (#1960)."""
    _enable_spend(settings, tmp_path)
    settings.server.api_key = "master-sekret"
    settings.enterprise.sso.enabled = False
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")

    ledger = SpendLedger(Path(settings.usage.spend.path), enabled=True)
    _spend_seed(ledger, service_tier="default", cost_usd=0.10)
    _spend_seed(
        ledger,
        request_id="req-b",
        service_tier="priority",
        cost_usd=0.20,
        model="claude-haiku-4-5",
    )

    app = _app(settings)
    app.state.ctx.router.spend_ledger = ledger
    headers = {"Authorization": "Bearer master-sekret"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bad = await client.get(
            "/v1/daari/spend/report",
            params={
                "since": SINCE,
                "group_by": "model,service_tier",
                "bucket": "week",
            },
            headers=headers,
        )
        assert bad.status_code == 400
        assert "bucket" in bad.json()["detail"].lower()

        ok = await client.get(
            "/v1/daari/spend/report",
            params={
                "since": SINCE,
                "group_by": "model,service_tier",
                "bucket": "day",
            },
            headers=headers,
        )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["group_by"] == ["model", "service_tier"]
    assert body["bucket"] == "day"
    by_tier = {row["service_tier"]: row for row in body["rows"]}
    assert set(by_tier) == {"default", "priority"}
    assert by_tier["default"]["bucket"] == "2026-06-15"
    assert by_tier["default"]["model"] == "claude-haiku-4-5"
    assert abs(by_tier["default"]["cost_usd"] - 0.10) < 1e-9
    assert abs(by_tier["priority"]["cost_usd"] - 0.20) < 1e-9


# --- (i) per-family breaker inventory + reset (#1960 / #1945) ---


@pytest.mark.asyncio
async def test_fleet_breaker_inventory_and_reset_non_systemone(settings, tmp_path):
    """Frontier open in stats; admin reset closes; non-admin VK → 403 (#1960)."""
    settings.server.api_key = "master-sekret"
    settings.server.virtual_keys.enabled = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = False
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    viewer = store.create("viewer", client_id="viewer")

    frontier_br = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
    frontier_br.record_failure()
    assert frontier_br.state == "open"

    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    app.state.ctx.frontier = SimpleNamespace(
        slots=[SimpleNamespace(id="openai", breaker=frontier_br)]
    )

    admin = {"Authorization": "Bearer master-sekret"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        stats = await client.get("/v1/daari/stats", headers=admin)
        assert stats.status_code == 200, stats.text
        breakers = stats.json()["breakers"]
        assert any(
            row.get("family") == "frontier"
            and row.get("target") == "openai"
            and row.get("state") == "open"
            for row in breakers
        )

        denied = await client.post(
            "/v1/daari/breakers/reset",
            headers={"Authorization": f"Bearer {viewer.plaintext}"},
            json={"family": "frontier", "target": "openai"},
        )
        assert denied.status_code == 403

        reset = await client.post(
            "/v1/daari/breakers/reset",
            headers=admin,
            json={"family": "frontier", "target": "openai"},
        )
    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert body["status"] == "ok"
    assert frontier_br.state == "closed"
    assert all(
        row["state"] == "closed"
        for row in body["breakers"]
        if row.get("family") == "frontier" and row.get("target") == "openai"
    )


# --- (j) Anthropic metadata.user_id shares OpenAI user_rpd fence (#1960 / #1946) ---

ANTHROPIC_MSG = {
    "model": "claude-3-haiku",
    "max_tokens": 16,
    "messages": [{"role": "user", "content": "hi"}],
}


@pytest.mark.asyncio
async def test_anthropic_metadata_user_id_shares_openai_user_rpd(
    settings, tmp_path, monkeypatch
):
    """OpenAI user and Anthropic metadata.user_id share one user_rpd bucket (#1960)."""
    _freeze(monkeypatch, {"now": FROZEN})
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    app.state.rate_limiter = RateLimiter(MemoryCounterBackend())

    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.ollama.execute = fake
    created = store.create("shared", user_rpd=1)
    headers = {
        "Authorization": f"Bearer {created.plaintext}",
        "X-Daari-No-Cache": "true",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openai_ok = await client.post(
            "/v1/chat/completions",
            json={**CHAT, "user": "alice"},
            headers=headers,
        )
        anthropic_denied = await client.post(
            "/v1/messages",
            json={**ANTHROPIC_MSG, "metadata": {"user_id": "alice"}},
            headers={**headers, "anthropic-version": "2023-06-01"},
        )
    assert openai_ok.status_code == 200, openai_ok.text
    assert anthropic_denied.status_code == 429
    assert anthropic_denied.json()["error"]["type"] == "rate_limit_error"
    assert anthropic_denied.headers.get("x-ratelimit-scope") == "user"


# --- (k) AAIF SKILL.md package → system prefix on chat (#1960 / #1950) ---


@pytest.mark.asyncio
async def test_skill_package_loaded_into_chat_system_prefix(
    settings, tmp_path, monkeypatch
):
    """Immediate SKILL.md packages prepend; nested packages are ignored (#1960)."""
    skills = tmp_path / ".daari" / "skills"
    pack = skills / "aaif-pack"
    pack.mkdir(parents=True)
    (pack / "SKILL.md").write_text("AAIF package body.", encoding="utf-8")
    nested = pack / "nested"
    nested.mkdir()
    (nested / "SKILL.md").write_text("Deep skill ignored.", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    settings.skills_system_prefix = _load_skills_system_prefix()
    assert "aaif-pack" in settings.skills_system_prefix
    assert "Deep skill ignored." not in settings.skills_system_prefix

    app = _app(settings)
    seen: list[InternalRequest] = []

    async def fake(request: InternalRequest) -> InternalResponse:
        seen.append(request)
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.ollama.execute = fake
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={**CHAT},
            headers={"X-Daari-No-Cache": "true"},
        )
    assert response.status_code == 200, response.text
    assert seen
    first = seen[0].messages[0]
    assert first.role == "system"
    assert "AAIF package body." in first.content
    assert "## Skill: aaif-pack" in first.content
    assert "Deep skill ignored." not in first.content


# --- (l) Phonon mp3→wav coerce + language-tagged model (#1960 / #1949 / #1956) ---


@pytest.mark.asyncio
async def test_phonon_mp3_coerced_to_wav_and_language_tag_forwarded(
    settings, monkeypatch
):
    """Phonon coerces response_format=mp3→wav and forwards phonon:40m-fr (#1960)."""
    seen: list[httpx.Request] = []
    wav_body = b"RIFFxxxxWAVEfmt "

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/show"):
            return httpx.Response(
                200, json={"voices": ["default", "Zoey", "Easton", "Freya"]}
            )
        seen.append(request)
        return httpx.Response(
            200, content=wav_body, headers={"content-type": "audio/wav"}
        )

    speech._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.speech.httpx.AsyncClient", Patched)

    settings.tts.base_url = "http://127.0.0.1:11434/v1"
    settings.tts.model = "phonon:40m-fr"
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={
                "model": "ignored",
                "input": "bonjour",
                "voice": "alloy",
                "response_format": "mp3",
            },
        )
    assert response.status_code == 200, response.text
    assert response.content == wav_body
    assert "audio/wav" in (response.headers.get("content-type") or "")
    assert seen
    payload = json.loads(seen[0].read())
    assert payload["response_format"] == "wav"
    assert payload["model"] == "phonon:40m-fr"
    await speech.aclose_http()


# --- (m) at-rest sealing through Responses gateway (#1980 / #1971) ---


@pytest.mark.asyncio
async def test_responses_at_rest_sealed_and_wrong_key_refused(
    settings, tmp_path, monkeypatch
):
    """POST /v1/responses seals the row; wrong-key GET fails closed (#1980)."""
    reset_at_rest()
    settings.security.at_rest_key = "wave-fence-right-key"
    secret = "at-rest-secret-payload-never-plaintext"
    app = _app(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content=secret,
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.route = fake_route
    store_path = Path(settings.trace.path).expanduser().parent / "responses.sqlite3"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "seal me"},
        )
        assert created.status_code == 200, created.text
        response_id = created.json()["id"]
        ok = await client.get(f"/v1/responses/{response_id}")
    assert ok.status_code == 200
    assert secret in ok.text

    with sqlite3.connect(store_path) as conn:
        body = conn.execute(
            "SELECT body FROM responses WHERE response_id = ?", (response_id,)
        ).fetchone()[0]
    assert is_sealed(body)
    assert secret not in body
    assert "daari-atr1:" in body

    reset_at_rest()
    settings.security.at_rest_key = "wave-fence-wrong-key"
    wrong_app = _app(settings)
    async with AsyncClient(
        transport=ASGITransport(app=wrong_app), base_url="http://test"
    ) as client:
        with pytest.raises(AtRestDecryptError):
            await client.get(f"/v1/responses/{response_id}")
    reset_at_rest()


# --- (n) gpt-6.1-terra billing base + ≥272K surcharge (#1980 / #1974) ---


@pytest.mark.asyncio
async def test_gpt_61_terra_spend_base_and_threshold(settings, tmp_path, monkeypatch):
    """Terra $1/$5 (+ $0.05 cached) and ≥272K 2×/1.5× via chat + spend (#1980)."""
    _enable_spend(settings, tmp_path)
    app = _app(settings)
    pricing = settings.pricing
    tokens: dict[str, tuple[int, int, int]] = {"use": (1000, 1000, 500)}

    async def fake_local(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="no",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    async def fake_frontier(
        _request: InternalRequest, **_kwargs: object
    ) -> InternalResponse:
        inp, out, cached = tokens["use"]
        return InternalResponse(
            content="terra frontier answer with enough detail",
            model="gpt-6.1-terra",
            daari_meta=DaariMeta(
                tier="L6",
                executor="frontier",
                model="gpt-6.1-terra",
                input_tokens=inp,
                output_tokens=out,
                cached_tokens=cached,
                latency_ms=1,
            ),
        )

    frontier = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-6.1-terra",
        api_key="sk-test",
    )
    frontier.execute = fake_frontier  # type: ignore[method-assign]
    app.state.ctx.router.frontier = frontier
    app.state.ctx.router.frontier_enabled = True
    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_local)

    expected_base = cost_usd(
        "gpt-6.1-terra",
        1000,
        1000,
        pricing,
        fallback_per_1k=0.002,
        cached_input_tokens=500,
    )
    expected_thresh = cost_usd(
        "gpt-6.1-terra",
        272_000,
        1000,
        pricing,
        fallback_per_1k=0.002,
    )
    assert expected_base == pytest.approx(0.005525)
    assert expected_thresh == pytest.approx(0.5515)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        base = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={"X-Daari-No-Cache": "true"},
        )
    assert base.status_code == 200, base.text
    assert float(base.headers[COST_HEADER]) == pytest.approx(expected_base)
    rows = _spend_rows(app)
    assert rows
    assert rows[-1]["model"] == "gpt-6.1-terra"
    assert float(rows[-1]["cost_usd"]) == pytest.approx(expected_base)

    tokens["use"] = (272_000, 1000, 0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thresh = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "long"}],
            },
            headers={"X-Daari-No-Cache": "true"},
        )
    assert thresh.status_code == 200, thresh.text
    assert float(thresh.headers[COST_HEADER]) == pytest.approx(expected_thresh)
    rows = _spend_rows(app)
    assert float(rows[-1]["cost_usd"]) == pytest.approx(expected_thresh)


# --- (o) SEP-2640 skills doors under MCP grant governance (#1980 / #1976) ---


@pytest.mark.asyncio
async def test_mcp_skills_doors_honor_grant_governance(
    settings, tmp_path, monkeypatch
):
    """No-grant VK is refused on initialize; granted VK lists/reads skills (#1980)."""
    skills = tmp_path / ".daari" / "skills"
    skills.mkdir(parents=True)
    (skills / "fence-skill.md").write_text(
        "---\ndescription: Fence skill\n---\n# Fence\nBody.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    settings.integrations.mcp_policy.require_key_access_defined = True
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk-skills.sqlite3")

    store = VirtualKeyStore(settings.virtual_keys_path)
    denied_key = store.create("no-grant", client_id="no-grant")
    granted_key = store.create(
        "with-grant",
        client_id="with-grant",
        metadata={"mcp": {"allow": ["route"]}},
    )
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    init_params = {
        "protocolVersion": "2026-07-28",
        "capabilities": {},
        "clientInfo": {"name": "wave-fence", "version": "0"},
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": init_params},
            headers={"Authorization": f"Bearer {denied_key.plaintext}"},
        )
        granted_headers = {"Authorization": f"Bearer {granted_key.plaintext}"}
        ok_init = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": init_params},
            headers=granted_headers,
        )
        listed = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 3, "method": "skills/list"},
            headers={**granted_headers, **META_HEADERS},
        )
        read = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "resources/read",
                "params": {"uri": "skill://fence-skill/SKILL.md"},
            },
            headers={**granted_headers, **META_HEADERS},
        )

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == TOOL_DENIED
    assert ok_init.status_code == 200
    skills_payload = listed.json()["result"]["skills"]
    assert any(s["frontmatter"]["name"] == "fence-skill" for s in skills_payload)
    assert "Body." in read.json()["result"]["contents"][0]["text"]
