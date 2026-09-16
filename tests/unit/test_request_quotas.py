"""Request-count quotas per key/team window (issue #467).

USD budgets cannot meter $0 local tiers. Request quotas count every non-cache
serve (local + frontier) against a multi-window cap.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.auth.budgets import (
    coalesce_windows,
    merge_windows,
    parse_window_flag,
    parse_window_requests_flag,
)
from daari.auth.virtual_keys import BudgetWindow, VirtualKeyStore
from daari.gateway.budget_headers import (
    QUOTA_REQUESTS_LIMIT_HEADER,
    QUOTA_REQUESTS_REMAINING_HEADER,
    QUOTA_REQUESTS_WARNING_HEADER,
)
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.usage import UsageLedger
from daari.router.router import AppContext
from daari.server.app import create_app

CHAT = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}


def test_parse_window_requests_flag():
    window = parse_window_requests_flag("1d=5000")
    assert window.duration == "1d"
    assert window.max_usd == 0.0
    assert window.max_requests == 5000

    daily = parse_window_requests_flag("day=100")
    assert daily.duration == "day"
    assert daily.max_requests == 100


def test_parse_window_requests_rejects_bad_shape():
    with pytest.raises(ValueError):
        parse_window_requests_flag("1d")
    with pytest.raises(ValueError):
        parse_window_requests_flag("1d=abc")


def test_coalesce_usd_and_request_caps_same_duration():
    merged = coalesce_windows(
        [
            parse_window_flag("day=5"),
            parse_window_requests_flag("day=5000"),
        ]
    )
    assert len(merged) == 1
    assert merged[0].duration == "day"
    assert merged[0].max_usd == 5.0
    assert merged[0].max_requests == 5000


def test_merge_request_quotas_tighter_wins_and_inherits():
    merged = merge_windows(
        [BudgetWindow("day", 0.0, max_requests=9000)],
        [BudgetWindow("day", 0.0, max_requests=1000), BudgetWindow("7d", 0.0, max_requests=50)],
    )
    by_duration = {w.duration: (w.max_requests, scope) for w, scope in merged}
    assert by_duration["day"] == (1000, "team")
    assert by_duration["7d"] == (50, "team")


def test_merge_usd_and_requests_independently_per_duration():
    """Team USD + key requests on the same duration keep both caps."""
    merged = merge_windows(
        [BudgetWindow("day", 0.0, max_requests=5000)],
        [BudgetWindow("day", 10.0)],
    )
    # One window carrying both, or two statuses — coalesce into one BudgetWindow.
    day = next(w for w, _ in merged if w.duration == "day")
    assert day.max_usd == 10.0
    assert day.max_requests == 5000


def test_budget_window_round_trips_max_requests(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    created = store.create(
        "bot",
        client_id="bot",
        budget_windows=[BudgetWindow("day", 2.0, max_requests=100)],
    )
    loaded = store.resolve(created.plaintext)
    assert loaded is not None
    assert len(loaded.budget_windows) == 1
    assert loaded.budget_windows[0].max_usd == 2.0
    assert loaded.budget_windows[0].max_requests == 100


def test_ledger_request_count_excludes_cache_hits(tmp_path):
    ledger = UsageLedger(tmp_path / "u.sqlite3")
    ledger.record(tier="L3", client_id="bot", cache_hit=False)
    ledger.record(tier="L3", client_id="bot", cache_hit=False)
    ledger.record(tier="L0", client_id="bot", cache_hit=True)
    ledger.record(tier="L6", client_id="bot", cache_hit=False, input_tokens=100)

    assert ledger.request_count_for_client("bot") == 3
    assert ledger.request_count_for_client("bot", window="day") == 3


def test_ledger_request_count_counts_local_tiers(tmp_path):
    ledger = UsageLedger(tmp_path / "u.sqlite3")
    ledger.record(tier="L3", client_id="bot", cache_hit=False)
    ledger.record(tier="L5", client_id="bot", cache_hit=False)
    assert ledger.request_count_for_client("bot") == 2


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


def _record_requests(ledger: UsageLedger, client_id: str, n: int, *, cache_hit: bool = False) -> None:
    for _ in range(n):
        ledger.record(tier="L3", client_id=client_id, cache_hit=cache_hit)


@pytest.mark.asyncio
async def test_request_quota_402_shape_and_headers(settings, tmp_path):
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create(
        "a",
        client_id="key-a",
        budget_windows=[BudgetWindow("day", 0.0, max_requests=2)],
    )
    _record_requests(ledger, "key-a", 2)

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
    assert error["quota"] == "requests"
    assert error["window"] == "daily"
    assert error["budget_requests"] == 2
    assert error["spend_requests"] >= 2
    assert error["scope"] == "key"
    assert error["reset_at"]
    assert response.headers[QUOTA_REQUESTS_REMAINING_HEADER] == "0"
    assert response.headers[QUOTA_REQUESTS_LIMIT_HEADER] == "2"
    assert "Retry-After" in response.headers


@pytest.mark.asyncio
async def test_cache_hits_do_not_consume_request_quota(settings, tmp_path):
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create(
        "a",
        client_id="key-a",
        budget_windows=[BudgetWindow("day", 0.0, max_requests=1)],
    )
    _record_requests(ledger, "key-a", 5, cache_hit=True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={
                "Authorization": f"Bearer {key.plaintext}",
                "X-Daari-No-Cache": "true",
            },
        )

    assert response.status_code == 200
    assert int(response.headers[QUOTA_REQUESTS_REMAINING_HEADER]) == 1


@pytest.mark.asyncio
async def test_local_tier_requests_consume_quota(settings, tmp_path):
    """Local tiers cost $0 so USD budgets ignore them — request quotas must not."""
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create(
        "a",
        client_id="key-a",
        budget_windows=[BudgetWindow("day", 100.0, max_requests=1)],
    )
    _record_requests(ledger, "key-a", 1)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )

    assert response.status_code == 402
    assert response.json()["error"]["quota"] == "requests"


@pytest.mark.asyncio
async def test_team_request_quota_tighter_than_key(settings, tmp_path):
    app, store, ledger = _app_with_keys(settings, tmp_path)
    store.create_team(
        "eng",
        budget_windows=[BudgetWindow("day", 0.0, max_requests=1)],
    )
    key = store.create(
        "a",
        client_id="key-a",
        team="eng",
        budget_windows=[BudgetWindow("day", 0.0, max_requests=100)],
    )
    _record_requests(ledger, "key-a", 1)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )

    error = response.json()["error"]
    assert response.status_code == 402
    assert error["quota"] == "requests"
    assert error["scope"] == "team"


@pytest.mark.asyncio
async def test_successful_response_exposes_request_remaining(settings, tmp_path):
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create(
        "a",
        client_id="key-a",
        budget_windows=[BudgetWindow("day", 0.0, max_requests=10)],
    )
    _record_requests(ledger, "key-a", 3)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={
                "Authorization": f"Bearer {key.plaintext}",
                "X-Daari-No-Cache": "true",
            },
        )

    assert response.status_code == 200
    assert response.headers[QUOTA_REQUESTS_REMAINING_HEADER] == "7"
    assert response.headers[QUOTA_REQUESTS_LIMIT_HEADER] == "10"
    assert QUOTA_REQUESTS_WARNING_HEADER not in response.headers


@pytest.mark.asyncio
async def test_request_quota_soft_band_warns_before_402(settings, tmp_path):
    """Crossing soft_budget_ratio surfaces a warning; hard cap still 402s (#498)."""
    settings.frontier.soft_budget_ratio = 0.8
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create(
        "a",
        client_id="key-a",
        budget_windows=[BudgetWindow("day", 0.0, max_requests=10)],
    )
    _record_requests(ledger, "key-a", 8)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        soft = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={
                "Authorization": f"Bearer {key.plaintext}",
                "X-Daari-No-Cache": "true",
                "X-Daari-Meta": "true",
            },
        )
        assert soft.status_code == 200
        assert soft.headers[QUOTA_REQUESTS_WARNING_HEADER] == "soft"
        assert soft.headers[QUOTA_REQUESTS_REMAINING_HEADER] == "2"
        assert soft.json()["daari_meta"]["warning"] == "request_quota_warning"

        _record_requests(ledger, "key-a", 2)  # total 10 → hard
        hard = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )

    assert hard.status_code == 402
    assert hard.json()["error"]["quota"] == "requests"
    assert hard.headers[QUOTA_REQUESTS_REMAINING_HEADER] == "0"
    assert hard.headers[QUOTA_REQUESTS_LIMIT_HEADER] == "10"
    assert "Retry-After" in hard.headers


@pytest.mark.asyncio
async def test_request_quota_soft_warn_on_anthropic_and_responses(settings, tmp_path):
    """Soft band sets daari_meta.warning on Anthropic + Responses (#509)."""
    settings.frontier.soft_budget_ratio = 0.8
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create(
        "a",
        client_id="key-a",
        budget_windows=[BudgetWindow("day", 0.0, max_requests=10)],
    )
    _record_requests(ledger, "key-a", 8)
    auth = {"Authorization": f"Bearer {key.plaintext}", "X-Daari-No-Cache": "true"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        anthropic = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers=auth,
        )
        assert anthropic.status_code == 200
        assert anthropic.headers[QUOTA_REQUESTS_WARNING_HEADER] == "soft"
        assert anthropic.json()["daari_meta"]["warning"] == "request_quota_warning"

        responses = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "hi"},
            headers={**auth, "X-Daari-Meta": "true"},
        )
        assert responses.status_code == 200
        assert responses.headers[QUOTA_REQUESTS_WARNING_HEADER] == "soft"
        assert responses.json()["daari_meta"]["warning"] == "request_quota_warning"


def test_keys_create_window_requests_cli(tmp_path, monkeypatch):
    from daari.cli.app import app as cli_app
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.virtual_keys.enabled = True
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)

    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        ["keys", "create", "bot", "--window-requests", "1d=5000", "--client-id", "bot"],
    )
    assert result.exit_code == 0, result.output
    store = VirtualKeyStore(settings.virtual_keys_path)
    keys = store.list()
    assert len(keys) == 1
    assert keys[0].budget_windows[0].max_requests == 5000
    assert keys[0].budget_windows[0].duration == "1d"


def test_keys_list_surfaces_request_usage(tmp_path, monkeypatch):
    from daari.cli.app import app as cli_app
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.virtual_keys.enabled = True
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)

    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create(
        "bot",
        client_id="bot",
        daily_budget_usd=5.0,
        budget_windows=[BudgetWindow("day", 5.0, max_requests=100)],
    )
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    _record_requests(ledger, "bot", 4)

    runner = CliRunner()
    result = runner.invoke(cli_app, ["keys", "list"])
    assert result.exit_code == 0, result.output
    assert "4/100" in result.output or "req 4/100" in result.output
    assert "$" in result.output or "0.00/5" in result.output


@pytest.mark.asyncio
async def test_report_includes_request_quota_soft_band(settings, tmp_path):
    """Report surfaces request-quota used/cap and soft flag (#519)."""
    settings.frontier.soft_budget_ratio = 0.8
    app, store, ledger = _app_with_keys(settings, tmp_path)
    store.create(
        "bot",
        client_id="bot",
        budget_windows=[BudgetWindow("day", 0.0, max_requests=10)],
    )
    _record_requests(ledger, "bot", 8)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/daari/report?days=1",
            headers={"Authorization": "Bearer master"},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    quotas = payload.get("request_quotas") or []
    assert len(quotas) == 1
    row = quotas[0]
    assert row["used"] == 8
    assert row["cap"] == 10
    assert row["remaining"] == 2
    assert row["soft"] is True
    assert row["scope"] == "key"
    assert row["window"] in {"1d", "day"}

    from daari.observability.render import report_markdown

    md = report_markdown(payload, days=1)
    assert "Request quotas" in md
    assert "8" in md and "10" in md and "yes" in md


def test_keys_list_marks_request_quota_soft(tmp_path, monkeypatch):
    from daari.cli.app import app as cli_app
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.virtual_keys.enabled = True
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    settings.frontier.soft_budget_ratio = 0.8
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)

    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create(
        "bot",
        client_id="bot",
        budget_windows=[BudgetWindow("day", 0.0, max_requests=10)],
    )
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    _record_requests(ledger, "bot", 8)

    runner = CliRunner()
    result = runner.invoke(cli_app, ["keys", "list"])
    assert result.exit_code == 0, result.output
    assert "req 8/10 soft" in result.output
