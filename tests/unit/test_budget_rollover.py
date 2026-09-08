"""Opt-in budget window rollover of unused headroom (issue #344)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from daari.auth.budgets import (
    WindowStatus,
    budget_error,
    budget_status,
    compute_carry_usd,
    effective_limit,
    first_exceeded_window,
    period_id,
    previous_period_id,
)
from daari.auth.virtual_keys import BudgetWindow, VirtualKey
from daari.gateway.budget_headers import BUDGET_LIMIT_HEADER, BUDGET_REMAINING_HEADER, budget_headers
from daari.observability.budget_alerts import BudgetAlerter, _ratio

NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)


class FakeLedger:
    enabled = True

    def __init__(self) -> None:
        self.spend: dict[str, float] = {}
        self.state: dict[tuple[str, str, str], dict] = {}

    def frontier_spend_usd_for_client(self, client_id, *, window="day", day=None, month=None, **_):
        if window == "month":
            key = f"{client_id}:month:{month or 'current'}"
        else:
            key = f"{client_id}:day:{day or 'current'}"
        return self.spend.get(key, self.spend.get(f"{client_id}:{window}", 0.0))

    def frontier_spend_usd_for_client_days(self, client_id, *, days, **_):
        return self.spend.get(f"{client_id}:{days}d", 0.0)

    def get_budget_window_state(self, scope: str, scope_id: str, duration: str):
        return self.state.get((scope, scope_id, duration))

    def put_budget_window_state(
        self, scope: str, scope_id: str, duration: str, *, period_id: str, carry_usd: float
    ) -> None:
        self.state[(scope, scope_id, duration)] = {
            "period_id": period_id,
            "carry_usd": float(carry_usd),
        }


def _key(**overrides) -> VirtualKey:
    base = dict(key_id="k1", name="k", prefix="dk", client_id="key-a")
    base.update(overrides)
    return VirtualKey(**base)  # type: ignore[arg-type]


def test_budget_window_rollover_defaults_off():
    window = BudgetWindow("day", 10.0)
    assert window.rollover is False
    assert window.rollover_cap_multiple == 2.0
    assert "rollover" not in window.as_dict() or window.as_dict().get("rollover") is False


def test_budget_window_round_trips_rollover_fields():
    window = BudgetWindow("month", 100.0, rollover=True, rollover_cap_multiple=2.5)
    payload = window.as_dict()
    assert payload["rollover"] is True
    assert payload["rollover_cap_multiple"] == 2.5


def test_effective_limit_and_carry_math():
    assert effective_limit(100.0, carry_usd=60.0, cap_multiple=2.0) == 160.0
    assert compute_carry_usd(
        base_limit=100.0, prev_limit=100.0, prev_spent=40.0, cap_multiple=2.0
    ) == 60.0
    assert compute_carry_usd(
        base_limit=100.0, prev_limit=100.0, prev_spent=150.0, cap_multiple=2.0
    ) == 0.0
    # Cap: idle period cannot accumulate beyond 2x base.
    assert compute_carry_usd(
        base_limit=100.0, prev_limit=200.0, prev_spent=0.0, cap_multiple=2.0
    ) == 100.0
    assert effective_limit(100.0, carry_usd=100.0, cap_multiple=2.0) == 200.0


def test_period_ids_for_day_and_month():
    assert period_id("day", now=NOW) == "2026-09-15"
    assert previous_period_id("day", now=NOW) == "2026-09-14"
    assert period_id("month", now=NOW) == "2026-09"
    assert previous_period_id("month", now=NOW) == "2026-08"


def test_default_off_ignores_prior_underspend():
    ledger = FakeLedger()
    ledger.spend["key-a:day:2026-09-14"] = 10.0
    key = _key(budget_windows=(BudgetWindow("day", 100.0),))
    statuses = budget_status(key, None, ledger, client_id="key-a", team_client_ids=[], now=NOW)
    assert statuses[0].limit == 100.0
    assert statuses[0].carry_usd == 0.0


def test_rollover_carries_unused_headroom_into_effective_limit():
    ledger = FakeLedger()
    ledger.spend["key-a:day:2026-09-14"] = 40.0
    key = _key(budget_windows=(BudgetWindow("day", 100.0, rollover=True),))
    statuses = budget_status(key, None, ledger, client_id="key-a", team_client_ids=[], now=NOW)
    status = statuses[0]
    assert status.carry_usd == pytest.approx(60.0)
    assert status.limit == pytest.approx(160.0)
    assert status.remaining == pytest.approx(160.0)  # current spend 0
    # Persisted for multi-replica reuse within the period.
    assert ledger.state[("key", "key-a", "day")]["period_id"] == "2026-09-15"
    assert ledger.state[("key", "key-a", "day")]["carry_usd"] == pytest.approx(60.0)


def test_rollover_cap_prevents_unbounded_accumulation():
    ledger = FakeLedger()
    ledger.spend["key-a:day:2026-09-14"] = 0.0
    key = _key(budget_windows=(BudgetWindow("day", 100.0, rollover=True),))
    status = budget_status(key, None, ledger, client_id="key-a", team_client_ids=[], now=NOW)[0]
    assert status.limit == pytest.approx(200.0)


def test_chained_rollover_uses_prior_effective_limit():
    ledger = FakeLedger()
    ledger.state[("key", "key-a", "day")] = {"period_id": "2026-09-14", "carry_usd": 60.0}
    ledger.spend["key-a:day:2026-09-14"] = 50.0  # prev effective 160, unused 110 → cap to 100
    key = _key(budget_windows=(BudgetWindow("day", 100.0, rollover=True),))
    status = budget_status(key, None, ledger, client_id="key-a", team_client_ids=[], now=NOW)[0]
    assert status.carry_usd == pytest.approx(100.0)
    assert status.limit == pytest.approx(200.0)


def test_same_period_reuses_stored_carry_without_recomputation():
    ledger = FakeLedger()
    ledger.state[("key", "key-a", "day")] = {"period_id": "2026-09-15", "carry_usd": 42.0}
    ledger.spend["key-a:day:2026-09-14"] = 0.0  # would yield 100 if recomputed
    key = _key(budget_windows=(BudgetWindow("day", 100.0, rollover=True),))
    status = budget_status(key, None, ledger, client_id="key-a", team_client_ids=[], now=NOW)[0]
    assert status.carry_usd == pytest.approx(42.0)
    assert status.limit == pytest.approx(142.0)


def test_headers_and_402_use_effective_limit():
    window = BudgetWindow("day", 100.0, rollover=True)
    status = WindowStatus(window=window, scope="key", spend=120.0, carry_usd=60.0, now=NOW)
    assert status.limit == 160.0
    assert status.remaining == pytest.approx(40.0)
    assert not status.exceeded
    headers = budget_headers(status)
    assert headers[BUDGET_LIMIT_HEADER] == "160"
    assert float(headers[BUDGET_REMAINING_HEADER]) == pytest.approx(40.0)

    err = budget_error(client_id="key-a", window=window, spend=160.0, scope="key", limit_usd=160.0)
    assert err["budget_usd"] == 160.0


def test_first_exceeded_reports_effective_limit():
    ledger = FakeLedger()
    ledger.state[("key", "key-a", "day")] = {"period_id": "2026-09-15", "carry_usd": 50.0}
    ledger.spend["key-a:day:current"] = 150.0
    key = _key(budget_windows=(BudgetWindow("day", 100.0, rollover=True),))
    err = first_exceeded_window(key, None, ledger, client_id="key-a", team_client_ids=[], now=NOW)
    assert err is not None
    assert err["budget_usd"] == pytest.approx(150.0)


def test_alert_ratio_uses_effective_limit():
    window = BudgetWindow("day", 100.0, rollover=True)
    status = WindowStatus(window=window, scope="key", spend=128.0, carry_usd=60.0, now=NOW)
    assert _ratio(status) == pytest.approx(128.0 / 160.0)
    alerter = BudgetAlerter(webhook_url="https://example.test/hook")
    payload = alerter.payload(status, 0.8, key=_key(), team=None)
    assert payload["limit_usd"] == 160.0
    assert payload["remaining_usd"] == pytest.approx(32.0)
