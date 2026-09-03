"""Budget-remaining response headers (issue #319): pure-function contract."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from daari.auth.budgets import (
    WindowStatus,
    budget_status,
    first_exceeded_window,
    reset_epoch,
    tightest_window,
    window_header_label,
)
from daari.auth.virtual_keys import BudgetWindow, Team, VirtualKey
from daari.gateway.budget_headers import (
    BUDGET_LIMIT_HEADER,
    BUDGET_REMAINING_HEADER,
    BUDGET_RESET_HEADER,
    BUDGET_SCOPE_HEADER,
    BUDGET_WINDOW_HEADER,
    budget_headers,
    retry_after_seconds,
)

NOW = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)


class FakeLedger:
    enabled = True

    def __init__(self, spend: dict[str, float]) -> None:
        self.spend = spend

    def frontier_spend_usd_for_client(self, client_id, *, window="day", **_):
        return self.spend.get(f"{client_id}:{window}", 0.0)

    def frontier_spend_usd_for_client_days(self, client_id, *, days, **_):
        return self.spend.get(f"{client_id}:{days}d", 0.0)


def _key(**overrides) -> VirtualKey:
    base = dict(key_id="k1", name="k", prefix="dk", client_id="key-a")
    base.update(overrides)
    return VirtualKey(**base)  # type: ignore[arg-type]


class TestLabels:
    def test_window_header_labels(self):
        assert window_header_label("day") == "1d"
        assert window_header_label("daily") == "1d"
        assert window_header_label("month") == "1mo"
        assert window_header_label("7d") == "7d"
        assert window_header_label("12h") == "12h"

    def test_reset_epoch_matches_reset_at(self):
        # Day window resets at the next UTC midnight.
        assert reset_epoch("day", now=NOW) == int(
            datetime(2026, 9, 3, tzinfo=timezone.utc).timestamp()
        )
        assert reset_epoch("12h", now=NOW) == int(NOW.timestamp()) + 12 * 3600


class TestBudgetStatus:
    def test_no_windows_means_no_status(self):
        assert (
            budget_status(_key(), None, FakeLedger({}), client_id="key-a", team_client_ids=[]) == []
        )

    def test_status_per_window_with_scope_and_remaining(self):
        key = _key(budget_windows=(BudgetWindow("day", 1.0), BudgetWindow("7d", 5.0)))
        ledger = FakeLedger({"key-a:day": 0.25, "key-a:7d": 4.5})
        statuses = budget_status(key, None, ledger, client_id="key-a", team_client_ids=[], now=NOW)
        by_window = {s.window.duration: s for s in statuses}
        assert by_window["day"].remaining == pytest.approx(0.75)
        assert by_window["day"].scope == "key"
        assert by_window["7d"].remaining == pytest.approx(0.5)
        assert not by_window["day"].exceeded

    def test_team_window_sums_team_clients(self):
        key = _key(team_id="t1")
        team = Team(team_id="t1", name="eng", budget_windows=(BudgetWindow("month", 10.0),))
        ledger = FakeLedger({"key-a:month": 1.0, "key-b:month": 2.5})
        (status,) = budget_status(
            key, team, ledger, client_id="key-a", team_client_ids=["key-a", "key-b"], now=NOW
        )
        assert status.scope == "team"
        assert status.spend == pytest.approx(3.5)
        assert status.remaining == pytest.approx(6.5)

    def test_tightest_window_is_least_remaining(self):
        key = _key(budget_windows=(BudgetWindow("day", 1.0), BudgetWindow("month", 20.0)))
        ledger = FakeLedger({"key-a:day": 0.9, "key-a:month": 5.0})
        statuses = budget_status(key, None, ledger, client_id="key-a", team_client_ids=[], now=NOW)
        assert tightest_window(statuses).window.duration == "day"
        assert tightest_window([]) is None

    def test_exceeded_window_clamps_remaining_to_zero(self):
        key = _key(daily_budget_usd=1.0)
        ledger = FakeLedger({"key-a:day": 3.0})
        (status,) = budget_status(key, None, ledger, client_id="key-a", team_client_ids=[], now=NOW)
        assert status.exceeded
        assert status.remaining == 0.0

    def test_first_exceeded_window_still_returns_the_402_body(self):
        key = _key(daily_budget_usd=1.0)
        ledger = FakeLedger({"key-a:day": 3.0})
        error = first_exceeded_window(key, None, ledger, client_id="key-a", team_client_ids=[])
        assert error["type"] == "budget_exceeded"
        assert error["window"] == "daily"


class TestHeaders:
    def test_headers_render_decimal_strings_and_epoch(self):
        status = WindowStatus(window=BudgetWindow("day", 1.0), scope="key", spend=0.2, now=NOW)
        headers = budget_headers(status)
        assert headers == {
            BUDGET_REMAINING_HEADER: "0.8",
            BUDGET_LIMIT_HEADER: "1",
            BUDGET_WINDOW_HEADER: "1d",
            BUDGET_RESET_HEADER: str(int(datetime(2026, 9, 3, tzinfo=timezone.utc).timestamp())),
            BUDGET_SCOPE_HEADER: "key",
        }

    def test_exhausted_headers_read_zero(self):
        status = WindowStatus(window=BudgetWindow("7d", 5.0), scope="team", spend=9.0, now=NOW)
        headers = budget_headers(status)
        assert headers[BUDGET_REMAINING_HEADER] == "0"
        assert headers[BUDGET_LIMIT_HEADER] == "5"
        assert headers[BUDGET_WINDOW_HEADER] == "7d"
        assert headers[BUDGET_SCOPE_HEADER] == "team"

    def test_retry_after_is_seconds_until_reset(self):
        status = WindowStatus(window=BudgetWindow("12h", 1.0), scope="key", spend=2.0, now=NOW)
        assert retry_after_seconds(status, now=NOW) == 12 * 3600
        late = NOW.replace(hour=23, minute=59, second=30)
        status = WindowStatus(window=BudgetWindow("day", 1.0), scope="key", spend=2.0, now=late)
        assert retry_after_seconds(status, now=late) == 30
