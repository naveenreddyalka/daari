"""Per-key frontier budgets (issue #158).

The middleware compared each key's budget against *global* frontier spend, so one
key's traffic exhausted every other key's allowance and a key could be blocked by
spend it never caused. These tests pin the isolation.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.usage import UsageLedger
from daari.router.router import AppContext
from daari.server.app import create_app

CHAT = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}


def _mock_execute(app):
    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content=f"ok:{request.meta.client_id}",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
            ),
        )

    app.state.ctx.router.ollama.execute = fake


def _spend(ledger: UsageLedger, client_id: str, usd: float, *, day: str | None = None) -> None:
    """Record frontier usage for one client at the flat fallback rate."""
    ledger.record(
        tier="L6",
        client_id=client_id,
        model="",
        input_tokens=int(usd / 0.002 * 1000),
        output_tokens=0,
        day=day,
    )


class TestLedgerPerClientSpend:
    def test_spend_is_attributed_to_the_client_that_caused_it(self, tmp_path):
        ledger = UsageLedger(tmp_path / "u.sqlite3")
        _spend(ledger, "key-a", 1.0)
        _spend(ledger, "key-b", 0.25)

        assert ledger.frontier_spend_usd_for_client("key-a") == pytest.approx(1.0, abs=1e-6)
        assert ledger.frontier_spend_usd_for_client("key-b") == pytest.approx(0.25, abs=1e-6)
        # The global view still sees both.
        assert ledger.frontier_spend_usd() == pytest.approx(1.25, abs=1e-6)

    def test_unknown_client_has_spent_nothing(self, tmp_path):
        ledger = UsageLedger(tmp_path / "u.sqlite3")
        _spend(ledger, "key-a", 1.0)
        assert ledger.frontier_spend_usd_for_client("never-seen") == 0.0

    def test_monthly_window_spans_days_but_stays_per_client(self, tmp_path):
        ledger = UsageLedger(tmp_path / "u.sqlite3")
        _spend(ledger, "key-a", 0.5, day="2026-08-01")
        _spend(ledger, "key-a", 0.5, day="2026-08-09")
        _spend(ledger, "key-b", 2.0, day="2026-08-09")

        month = ledger.frontier_spend_usd_for_client(
            "key-a", window="month", month="2026-08"
        )
        assert month == pytest.approx(1.0, abs=1e-6)
        day = ledger.frontier_spend_usd_for_client("key-a", day="2026-08-09")
        assert day == pytest.approx(0.5, abs=1e-6)

    def test_local_tiers_do_not_count_against_a_frontier_budget(self, tmp_path):
        ledger = UsageLedger(tmp_path / "u.sqlite3")
        ledger.record(tier="L3", client_id="key-a", input_tokens=10_000_000)
        assert ledger.frontier_spend_usd_for_client("key-a") == 0.0

    def test_disabled_ledger_reports_no_spend(self, tmp_path):
        ledger = UsageLedger(tmp_path / "u.sqlite3", enabled=False)
        assert ledger.frontier_spend_usd_for_client("key-a") == 0.0


def _app_with_keys(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    _mock_execute(app)
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    app.state.ctx.router.usage_ledger = ledger
    return app, store, ledger


@pytest.mark.asyncio
async def test_exhausting_one_key_does_not_block_another(settings, tmp_path):
    """The headline bug: key B was blocked by key A's spend."""
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key_a = store.create("a", client_id="key-a", daily_budget_usd=1.0)
    key_b = store.create("b", client_id="key-b", daily_budget_usd=1.0)
    _spend(ledger, "key-a", 5.0)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        blocked = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key_a.plaintext}"},
        )
        allowed = await client.post(
            "/v1/chat/completions",
            json={"model": "daari", "messages": [{"role": "user", "content": "b"}]},
            headers={
                "Authorization": f"Bearer {key_b.plaintext}",
                "X-Daari-No-Cache": "true",
            },
        )

    assert blocked.status_code == 402
    assert allowed.status_code == 200, "key B spent nothing and must not be blocked"


@pytest.mark.asyncio
async def test_402_names_the_key_and_the_window(settings, tmp_path):
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create("a", client_id="key-a", daily_budget_usd=1.0)
    _spend(ledger, "key-a", 2.0)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )

    assert response.status_code == 402
    error = response.json()["error"]
    assert error["type"] == "budget_exceeded"
    assert error["client_id"] == "key-a"
    assert error["window"] == "daily"
    assert error["budget_usd"] == pytest.approx(1.0)
    assert error["spend_usd"] >= 1.0


@pytest.mark.asyncio
async def test_monthly_budget_is_enforced(settings, tmp_path):
    """Only the daily window was ever checked; a monthly cap did nothing."""
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create("a", client_id="key-a", monthly_budget_usd=1.0)
    _spend(ledger, "key-a", 2.0)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )

    assert response.status_code == 402
    assert response.json()["error"]["window"] == "monthly"


@pytest.mark.asyncio
async def test_budget_applies_to_a_key_created_without_a_client_id(settings, tmp_path):
    """`--client-id` is optional, so a key must still be attributable.

    Otherwise spend records under "unknown" while the budget check looks up the
    key's own id, the two never meet, and the cap silently never applies.
    """
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create("no-client-id", daily_budget_usd=1.0)
    assert key.key.client_id is None

    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {key.plaintext}", "X-Daari-No-Cache": "true"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=CHAT, headers=headers)
        assert first.status_code == 200

        _spend(ledger, key.key.key_id, 2.0)
        second = await client.post(
            "/v1/chat/completions",
            json={"model": "daari", "messages": [{"role": "user", "content": "again"}]},
            headers=headers,
        )

    assert second.status_code == 402
    assert second.json()["error"]["client_id"] == key.key.key_id


@pytest.mark.asyncio
async def test_ledger_attributes_usage_to_the_key_when_no_client_id_is_set(
    settings, tmp_path
):
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create("anon", daily_budget_usd=5.0)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
    assert response.status_code == 200

    attributed = {entry["client_id"] for entry in ledger.by_client(days=1)}
    assert key.key.key_id in attributed, "usage recorded as 'unknown' is unbillable"


@pytest.mark.asyncio
async def test_key_within_budget_is_served(settings, tmp_path):
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create("a", client_id="key-a", daily_budget_usd=10.0)
    _spend(ledger, "key-a", 1.0)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )

    assert response.status_code == 200
