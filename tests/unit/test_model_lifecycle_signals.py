"""Retired-model audit, reject metric, and doctor lifecycle check (#1549)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.enterprise.audit import AuditLog
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.model_access import reject_retired_model
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.setup.doctor import _check_model_lifecycle, run_doctor


def _lifecycle_settings(tmp_path) -> Settings:
    settings = Settings()
    settings.server.api_key = ""
    settings.models.lifecycle = {
        "retired-model": {"lifecycle": "retired"},
        "old-model": {
            "lifecycle": "deprecated",
            "deprecated_at": "2026-01-01T00:00:00Z",
        },
    }
    settings.models.reject_retired = True
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    return settings


class TestRetiredDenialAuditAndMetric:
    def test_record_writes_audit_and_reject_counter(self, tmp_path):
        settings = _lifecycle_settings(tmp_path)
        metrics = Metrics()

        class State:
            auth_claims = type(
                "C",
                (),
                {
                    "key_id": "k1",
                    "client_id": "c1",
                    "selected_team_id": "t1",
                    "virtual_key": None,
                },
            )()

        class AppState:
            ctx = type("Ctx", (), {"metrics": metrics})()

        class App:
            state = AppState()

        class Req:
            state = State()
            app = App()
            url = type("U", (), {"path": "/v1/chat/completions"})()

        response = reject_retired_model(Req(), "retired-model", settings)
        assert response is not None
        assert response.status_code == 410
        rows = AuditLog(tmp_path / "audit.sqlite3").list()
        assert rows
        assert rows[0]["action"] == "models.retired_denied"
        assert rows[0]["detail"]["model"] == "retired-model"
        assert rows[0]["detail"]["key_id"] == "k1"
        assert rows[0]["detail"]["team_id"] == "t1"
        assert metrics.snapshot(include_histograms=True)["rejects"].get("retired") == 1
        text = render_prometheus(metrics)
        assert 'daari_rejects_total{kind="retired"} 1' in text

    @pytest.mark.asyncio
    async def test_chat_410_writes_audit(self, tmp_path, monkeypatch):
        settings = _lifecycle_settings(tmp_path)
        app = create_app(settings)
        app.state.ctx = AppContext.from_settings(settings)

        async def fake_route(request: InternalRequest) -> InternalResponse:
            return InternalResponse(
                content="nope",
                model=request.model,
                daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
            )

        monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "retired-model",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
        assert response.status_code == 410
        rows = AuditLog(tmp_path / "audit.sqlite3").list()
        assert any(r["action"] == "models.retired_denied" for r in rows)
        assert (
            app.state.ctx.metrics.snapshot(include_histograms=True)["rejects"].get(
                "retired"
            )
            == 1
        )


class TestDoctorModelLifecycle:
    def _down_client(self):
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_errors_when_tier_model_retired(self, tmp_path):
        settings = _lifecycle_settings(tmp_path)
        settings.models.l3 = "retired-model"
        result = _check_model_lifecycle(settings)
        assert result.ok is False
        assert result.optional is False
        assert "retired-model" in result.detail
        assert "retired" in result.detail

    def test_tips_when_frontier_deprecated(self, tmp_path):
        settings = _lifecycle_settings(tmp_path)
        settings.frontier.enabled = True
        settings.frontier.model = "old-model"
        result = _check_model_lifecycle(settings)
        assert result.ok is False
        assert result.optional is True
        assert "deprecated" in result.detail
        assert "old-model" in result.detail

    def test_quiet_when_no_lifecycle_pressure(self, settings):
        settings.models.lifecycle = {}
        result = _check_model_lifecycle(settings)
        assert result.ok is True

    def test_run_doctor_includes_check(self, tmp_path):
        settings = _lifecycle_settings(tmp_path)
        settings.models.l4 = "retired-model"
        results = run_doctor(settings, httpx_client=self._down_client())
        by_name = {r.name: r for r in results}
        assert "model_lifecycle" in by_name
        assert by_name["model_lifecycle"].ok is False
