"""Doctor metrics_auth advisory when API key protects /metrics (#596)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from daari.config.settings import Settings
from daari.setup.doctor import (
    _check_metrics_auth,
    doctor_exit_code,
    run_doctor,
)


@pytest.fixture
def settings(tmp_path):
    return Settings.model_validate(
        {
            "server": {"host": "127.0.0.1", "port": 11435, "api_key": ""},
            "models": {"l3": "llama3.2:3b"},
            "ollama": {"base_url": "http://127.0.0.1:11434"},
            "cache": {"l0": {"enabled": True, "path": str(tmp_path / "l0")}},
            "observability": {"prometheus": True},
        }
    )


def _tags_ok() -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "models": [{"name": "llama3.2:3b"}, {"name": "nomic-embed-text:latest"}]
    }
    return response


def _stats_ok() -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"total_requests": 1}
    return response


def _ready_payload(status: str = "ready") -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"status": status, "checks": {}}
    return response


def _metrics_response(status_code: int) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = "unauthorized" if status_code == 401 else "# HELP\n"
    return response


class TestDoctorMetricsAuth:
    def test_skipped_when_daemon_down(self, settings):
        settings.server.api_key = "secret"
        result = _check_metrics_auth(settings, None, daemon_ok=False)
        assert result.name == "metrics_auth"
        assert result.ok is True
        assert result.optional is True
        assert "skipped" in result.detail

    def test_quiet_when_prometheus_off(self, settings):
        settings.observability.prometheus = False
        settings.server.api_key = "secret"
        mock = MagicMock(spec=httpx.Client)
        result = _check_metrics_auth(settings, mock, daemon_ok=True)
        assert result.ok is True
        assert "prometheus" in result.detail.lower() or "disabled" in result.detail
        mock.get.assert_not_called()

    def test_quiet_when_no_api_key(self, settings):
        settings.server.api_key = ""
        mock = MagicMock(spec=httpx.Client)
        result = _check_metrics_auth(settings, mock, daemon_ok=True)
        assert result.ok is True
        assert "api_key" in result.detail.lower() or "open" in result.detail.lower()
        mock.get.assert_not_called()

    def test_quiet_when_scrape_already_open(self, settings):
        settings.server.api_key = "secret"
        mock = MagicMock(spec=httpx.Client)
        mock.get.return_value = _metrics_response(200)
        result = _check_metrics_auth(settings, mock, daemon_ok=True)
        assert result.ok is True
        assert "open" in result.detail.lower() or "ok" in result.detail.lower()
        mock.get.assert_called_once()
        assert mock.get.call_args.args[0].endswith("/metrics")

    def test_warns_when_unauthenticated_metrics_is_401(self, settings):
        settings.server.api_key = "secret"
        mock = MagicMock(spec=httpx.Client)
        mock.get.return_value = _metrics_response(401)
        result = _check_metrics_auth(settings, mock, daemon_ok=True)
        assert result.ok is False
        assert result.optional is True
        assert "401" in result.detail or "Bearer" in result.detail
        assert "bearerTokenSecret" in result.detail or "Bearer" in result.detail
        assert doctor_exit_code([result]) == 0

    def test_run_doctor_includes_metrics_auth(self, settings):
        settings.server.api_key = "secret"
        mock = MagicMock(spec=httpx.Client)

        def get_side_effect(url, **_kwargs):
            if url.endswith("/api/tags"):
                return _tags_ok()
            if url.endswith("/v1/daari/stats"):
                return _stats_ok()
            if url.endswith("/ready"):
                return _ready_payload("ready")
            if url.endswith("/metrics"):
                return _metrics_response(401)
            raise AssertionError(f"unexpected url {url}")

        mock.get.side_effect = get_side_effect
        results = run_doctor(settings, httpx_client=mock)
        by_name = {r.name: r for r in results}
        assert "metrics_auth" in by_name
        assert by_name["metrics_auth"].ok is False
        assert by_name["metrics_auth"].optional is True
