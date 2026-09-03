"""Budget-remaining response headers (issue #319).

Sibling of `cost_headers.py`: where those say what *this* response cost, these
say how much frontier budget the caller has left in the window it will hit
first, so clients and FinOps tooling can back off to $0 local tiers before the
402. Budget state is known before the body, so streams carry them too.
"""

from __future__ import annotations

from datetime import datetime, timezone

from daari.auth.budgets import WindowStatus, window_header_label
from daari.gateway.cost_headers import usd_string

BUDGET_REMAINING_HEADER = "x-daari-budget-remaining"
BUDGET_LIMIT_HEADER = "x-daari-budget-limit"
BUDGET_WINDOW_HEADER = "x-daari-budget-window"
BUDGET_RESET_HEADER = "x-daari-budget-reset"
BUDGET_SCOPE_HEADER = "x-daari-budget-scope"


def budget_headers(status: WindowStatus) -> dict[str, str]:
    return {
        BUDGET_REMAINING_HEADER: usd_string(status.remaining),
        BUDGET_LIMIT_HEADER: usd_string(float(status.window.max_usd)),
        BUDGET_WINDOW_HEADER: window_header_label(status.window.duration),
        BUDGET_RESET_HEADER: str(status.reset_epoch),
        BUDGET_SCOPE_HEADER: status.scope,
    }


def retry_after_seconds(status: WindowStatus, *, now: datetime | None = None) -> int:
    """Whole seconds until the window resets; never below 1 so clients back off."""
    moment = now or status.now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(1, status.reset_epoch - int(moment.timestamp()))
