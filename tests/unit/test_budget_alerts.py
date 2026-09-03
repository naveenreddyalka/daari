"""Budget threshold webhooks (#333)."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from daari.auth.budgets import BudgetWindow, WindowStatus
from daari.auth.virtual_keys import Team, VirtualKey
from daari.config.settings import Settings
from daari.enterprise.audit import AuditLog
from daari.observability.budget_alerts import BudgetAlerter, crossings
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
KEY = VirtualKey(key_id="k1", name="ci-bot", prefix="dk_ci")
TEAM = Team(team_id="t1", name="eng")


def _status(
    spend: float, *, cap: float = 10.0, scope: str = "key", duration: str = "day"
) -> WindowStatus:
    return WindowStatus(
        window=BudgetWindow(duration, cap),
        scope=scope,  # type: ignore[arg-type]
        spend=spend,
        now=NOW,
    )


class TestCrossings:
    def test_fires_when_request_crosses_threshold(self):
        hits = crossings([_status(7.0)], [_status(8.5)], [0.8, 1.0])
        assert [t for _, t in hits] == [0.8]

    def test_jump_crosses_both(self):
        hits = crossings([_status(7.0)], [_status(10.5)], [0.8, 1.0])
        assert [t for _, t in hits] == [0.8, 1.0]

    def test_already_over_does_not_refire(self):
        assert crossings([_status(8.5)], [_status(9.0)], [0.8]) == []

    def test_disabled_thresholds_ignored(self):
        assert crossings([_status(0)], [_status(10)], [0.0, 1.5]) == []


class TestAlerter:
    def test_defaults(self):
        alerts = Settings().alerts
        assert alerts.budget_webhook_url == ""
        assert alerts.budget_thresholds == [0.8, 1.0]
        assert BudgetAlerter(webhook_url="").enabled is False

    def test_payload_has_no_key_material(self, tmp_path):
        posted: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            posted.append(request)
            return httpx.Response(204)

        alerter = BudgetAlerter(
            webhook_url="https://hooks.example/budget",
            transport=httpx.MockTransport(handler),
            audit=AuditLog(tmp_path / "audit.sqlite3"),
            metrics=Metrics(),
        )
        bodies = alerter.notify(
            [_status(7.0)],
            [_status(8.2)],
            key=KEY,
            team=TEAM,
        )
        assert len(bodies) == 1
        body = bodies[0]
        assert body["scope"] == "key"
        assert body["id"] == "k1"
        assert body["name"] == "ci-bot"
        assert body["window"] == "daily"
        assert body["limit_usd"] == 10.0
        assert body["spent_usd"] == 8.2
        assert body["remaining_usd"] == pytest.approx(1.8)
        assert body["threshold"] == 0.8
        assert "dk_" not in str(body)
        assert len(posted) == 1
        assert posted[0].url.path == "/budget"
        rows = AuditLog(tmp_path / "audit.sqlite3").list()
        assert rows[0]["action"] == "budget.alert"
        assert "dk_" not in str(rows[0])
        snap = alerter.metrics.snapshot(include_histograms=True)
        assert snap["budget_alerts"]["key:0.8"] == 1
        text = render_prometheus(alerter.metrics)
        assert 'daari_budget_alerts_total{scope="key",threshold="0.8"} 1' in text

    def test_dedupes_until_window_reset(self):
        hits: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            hits.append(request)
            return httpx.Response(204)

        alerter = BudgetAlerter(
            webhook_url="https://hooks.example/budget",
            transport=httpx.MockTransport(handler),
        )
        alerter.notify([_status(7.0)], [_status(8.2)], key=KEY, team=None)
        alerter.notify([_status(8.2)], [_status(8.4)], key=KEY, team=None)
        assert len(hits) == 1

    def test_webhook_failure_is_logged_not_raised(self, monkeypatch):
        events: list[tuple[str, dict]] = []
        monkeypatch.setattr(
            "daari.gateway.request_log.log_gateway_event",
            lambda name, detail=None: events.append((name, detail or {})),
        )

        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        alerter = BudgetAlerter(
            webhook_url="https://hooks.example/budget",
            transport=httpx.MockTransport(boom),
        )
        alerter.notify([_status(7.0)], [_status(8.2)], key=KEY, team=None)
        assert events[-1][0] == "budget.alert_failed"

    def test_empty_url_never_posts(self):
        alerter = BudgetAlerter(webhook_url="")
        assert alerter.notify([_status(0)], [_status(10)], key=KEY, team=None) == []
