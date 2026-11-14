"""Opt-in in-flight budget reservation (#2198).

When ``budgets.reserve_in_flight`` is on, admission pre-charges an estimated
cost against active USD windows so a parallel burst cannot blow the cap before
any response settles. Flag off keeps today's settled-only behavior.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.budget_reserve import (
    BudgetReservationLedger,
    estimate_admission_cost_usd,
    is_zero_cost_admission_model,
)
from daari.observability.usage import UsageLedger
from daari.router.router import AppContext
from daari.server.app import create_app

# max_tokens sized so gpt-4o estimate ≈ $0.02 (output $10/1M) — leaves room for
# one/two admits at $0.05 remaining but denies a parallel burst (#2198).
CHAT = {
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 2000,
}
LOCAL_CHAT = {
    "model": "llama3.2:3b",
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 2000,
}


def _spend(ledger: UsageLedger, client_id: str, usd: float) -> None:
    # Empty model → flat fallback_per_1k so usd maps 1:1 (#158 pattern).
    ledger.record(
        tier="L6",
        client_id=client_id,
        model="",
        input_tokens=int(usd / 0.002 * 1000),
        output_tokens=0,
    )


def _mock_execute(app, *, delay_s: float = 0.0, tier: str = "L6"):
    async def fake(request: InternalRequest) -> InternalResponse:
        if delay_s:
            await asyncio.sleep(delay_s)
        return InternalResponse(
            content="ok:" + (request.meta.client_id or ""),
            model=request.model or "gpt-4o",
            daari_meta=DaariMeta(
                tier=tier, executor="openai", provider_id="openai", latency_ms=1
            ),
        )

    app.state.ctx.router.ollama.execute = fake
    # Frontier path for explicit cloud models.
    frontier = getattr(app.state.ctx.router, "frontier", None)
    if frontier is not None and hasattr(frontier, "execute"):
        frontier.execute = fake


def _app(settings: Settings, tmp_path, *, delay_s: float = 0.0, tier: str = "L6"):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    settings.usage.frontier_price_per_1k_tokens = 0.002
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    _mock_execute(app, delay_s=delay_s, tier=tier)
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    app.state.ctx.router.usage_ledger = ledger
    return app, store, ledger


class TestEstimateAndLocalZero:
    def test_estimate_uses_prompt_and_max_tokens(self):
        settings = Settings.model_validate(
            {"usage": {"frontier_price_per_1k_tokens": 0.002}}
        )
        cost = estimate_admission_cost_usd(
            CHAT,
            model="gpt-4o",
            pricing=settings.pricing,
            fallback_per_1k=0.002,
            default_output_tokens=4096,
        )
        assert cost > 0

    def test_local_model_is_zero_cost_admission(self):
        settings = Settings.model_validate({"models": {"l3": "llama3.2:3b"}})
        assert is_zero_cost_admission_model(
            "llama3.2:3b", settings, tier_header=None
        )
        assert is_zero_cost_admission_model(
            "gpt-4o", settings, tier_header="L3"
        )
        assert not is_zero_cost_admission_model(
            "gpt-4o", settings, tier_header=None
        )

    def test_default_output_tokens_when_max_tokens_absent(self):
        settings = Settings.model_validate(
            {"usage": {"frontier_price_per_1k_tokens": 1.0}}
        )
        payload = {"model": "unpriced-x", "messages": [{"role": "user", "content": "ab"}]}
        with_default = estimate_admission_cost_usd(
            payload,
            model="unpriced-x",
            pricing=settings.pricing,
            fallback_per_1k=1.0,
            default_output_tokens=1000,
        )
        # 1 prompt token (chars//4) + 1000 output at $1/1k → ~1.001
        assert with_default == pytest.approx(1.001, abs=1e-6)


class TestReservationLedger:
    def test_parallel_try_reserve_denies_overflow(self):
        ledger = BudgetReservationLedger()
        windows = [("key", "c1", "day", 0.9, 1.0)]
        first = ledger.try_reserve(windows=windows, amount=0.08)
        second = ledger.try_reserve(windows=windows, amount=0.08)
        assert first is not None
        assert second is None
        ledger.release(first.reservation_id)
        third = ledger.try_reserve(windows=windows, amount=0.08)
        assert third is not None
        ledger.release(third.reservation_id)

    def test_release_on_missing_id_is_noop(self):
        ledger = BudgetReservationLedger()
        ledger.release("never-existed")

    def test_zero_amount_does_not_block(self):
        ledger = BudgetReservationLedger()
        windows = [("key", "c1", "day", 1.0, 1.0)]
        a = ledger.try_reserve(windows=windows, amount=0.0)
        b = ledger.try_reserve(windows=windows, amount=0.0)
        assert a is not None and b is not None


@pytest.mark.asyncio
async def test_flag_off_identical_to_settled_only(settings, tmp_path):
    """Near-cap parallel burst is admitted when reservation is off (today)."""
    settings = Settings.model_validate(
        {
            **settings.model_dump(),
            "budgets": {"reserve_in_flight": False},
            "frontier": {"enabled": True, "model": "gpt-4o"},
        }
    )
    app, store, ledger = _app(settings, tmp_path, delay_s=0.05)
    key = store.create("a", client_id="key-a", daily_budget_usd=1.0)
    _spend(ledger, "key-a", 0.95)

    transport = ASGITransport(app=app)
    headers = {
        "Authorization": f"Bearer {key.plaintext}",
        "X-Daari-No-Cache": "true",
        "X-Daari-Tier": "L6",
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        results = await asyncio.gather(
            *[
                client.post("/v1/chat/completions", json=CHAT, headers=headers)
                for _ in range(4)
            ]
        )

    assert all(r.status_code == 200 for r in results)


@pytest.mark.asyncio
async def test_parallel_burst_at_cap_denies_overflow(settings, tmp_path):
    settings = Settings.model_validate(
        {
            **settings.model_dump(),
            "budgets": {"reserve_in_flight": True, "default_output_tokens": 4096},
            "frontier": {"enabled": True, "model": "gpt-4o"},
            "usage": {
                **settings.usage.model_dump(),
                "frontier_price_per_1k_tokens": 0.002,
                "path": str(tmp_path / "usage.sqlite3"),
            },
        }
    )
    app, store, ledger = _app(settings, tmp_path, delay_s=0.08)
    key = store.create("a", client_id="key-a", daily_budget_usd=1.0)
    _spend(ledger, "key-a", 0.95)

    transport = ASGITransport(app=app)
    headers = {
        "Authorization": f"Bearer {key.plaintext}",
        "X-Daari-No-Cache": "true",
        "X-Daari-Tier": "L6",
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        results = await asyncio.gather(
            *[
                client.post("/v1/chat/completions", json=CHAT, headers=headers)
                for _ in range(6)
            ]
        )

    codes = sorted(r.status_code for r in results)
    assert 402 in codes
    assert 200 in codes
    denied = next(r for r in results if r.status_code == 402)
    assert denied.json()["error"]["type"] == "budget_exceeded"
    metrics = app.state.ctx.metrics
    assert int(metrics.rejects.get("budget_reservation", 0)) >= 1
    assert int(metrics.budget_reservation_denied) >= 1


@pytest.mark.asyncio
async def test_local_tier_not_throttled_by_reservation(settings, tmp_path):
    settings = Settings.model_validate(
        {
            **settings.model_dump(),
            "budgets": {"reserve_in_flight": True},
            "models": {"l3": "llama3.2:3b"},
            "frontier": {"enabled": True, "model": "gpt-4o"},
        }
    )
    app, store, ledger = _app(settings, tmp_path, tier="L3")
    key = store.create("a", client_id="key-a", daily_budget_usd=1.0)
    _spend(ledger, "key-a", 0.99)

    transport = ASGITransport(app=app)
    headers = {
        "Authorization": f"Bearer {key.plaintext}",
        "X-Daari-No-Cache": "true",
        "X-Daari-Tier": "L3",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions", json=LOCAL_CHAT, headers=headers
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_reservation_released_on_error(settings, tmp_path):
    settings = Settings.model_validate(
        {
            **settings.model_dump(),
            "budgets": {"reserve_in_flight": True},
            "frontier": {"enabled": True, "model": "gpt-4o"},
        }
    )
    app, store, ledger = _app(settings, tmp_path)
    key = store.create("a", client_id="key-a", daily_budget_usd=1.0)
    _spend(ledger, "key-a", 0.5)

    async def boom(request: InternalRequest) -> InternalResponse:
        raise RuntimeError("upstream down")

    app.state.ctx.router.ollama.execute = boom
    frontier = getattr(app.state.ctx.router, "frontier", None)
    if frontier is not None and hasattr(frontier, "execute"):
        frontier.execute = boom

    transport = ASGITransport(app=app)
    headers = {
        "Authorization": f"Bearer {key.plaintext}",
        "X-Daari-No-Cache": "true",
        "X-Daari-Tier": "L6",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=CHAT, headers=headers)
        # Reservation must not leak — a follow-up near the same spend still admits
        # if settled spend alone is under the cap.
        second = await client.post("/v1/chat/completions", json=CHAT, headers=headers)

    assert first.status_code >= 500
    # After release, settled 0.5 + estimate still fits $1 (no leaked hold).
    assert second.status_code >= 500 or second.status_code == 200
    reserve = getattr(app.state, "budget_reservations", None)
    assert reserve is not None
    assert reserve.reserved("key", "key-a", "day") == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_prometheus_reservation_denied_counter(settings, tmp_path):
    settings = Settings.model_validate(
        {
            **settings.model_dump(),
            "budgets": {"reserve_in_flight": True},
            "frontier": {"enabled": True, "model": "gpt-4o"},
        }
    )
    app, store, ledger = _app(settings, tmp_path, delay_s=0.05)
    key = store.create("a", client_id="key-a", daily_budget_usd=1.0)
    _spend(ledger, "key-a", 0.95)

    transport = ASGITransport(app=app)
    headers = {
        "Authorization": f"Bearer {key.plaintext}",
        "X-Daari-No-Cache": "true",
        "X-Daari-Tier": "L6",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await asyncio.gather(
            *[
                client.post("/v1/chat/completions", json=CHAT, headers=headers)
                for _ in range(6)
            ]
        )
        prom = await client.get(
            "/metrics", headers={"Authorization": "Bearer master"}
        )

    assert prom.status_code == 200
    assert "daari_budget_reservation_denied_total" in prom.text
    assert int(app.state.ctx.metrics.budget_reservation_denied) >= 1
