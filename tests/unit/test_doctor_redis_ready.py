"""Doctor Redis PING and GET /ready checks (#584)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from daari.config.settings import Settings
from daari.setup.doctor import (
    _check_ready,
    _check_redis,
    doctor_exit_code,
    run_doctor,
)


@pytest.fixture
def settings(tmp_path):
    return Settings.model_validate(
        {
            "server": {"host": "127.0.0.1", "port": 11435},
            "models": {"l3": "llama3.2:3b"},
            "ollama": {"base_url": "http://127.0.0.1:11434"},
            "cache": {"l0": {"enabled": True, "path": str(tmp_path / "l0")}},
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


def _ready_payload(status: str, http_status: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = http_status
    response.json.return_value = {
        "status": status,
        "checks": {"cache": "ok", "model_backend": "ok"},
    }
    return response


class TestDoctorRedis:
    def test_redis_disabled_when_disk_backend(self, settings):
        result = _check_redis(settings)
        assert result.name == "redis"
        assert result.ok is True
        assert result.optional is True
        assert "disabled" in result.detail

    def test_redis_ping_ok(self, settings):
        settings.cache.backend = "redis"
        settings.cache.redis_url = "redis://127.0.0.1:6379/0"
        fake = MagicMock()
        with patch("daari.cache.redis_client.connect_redis", return_value=fake) as connect:
            result = _check_redis(settings)
        connect.assert_called_once()
        fake.ping.assert_called_once()
        assert result.ok is True
        assert "PING ok" in result.detail

    def test_redis_ping_unreachable(self, settings):
        settings.cache.backend = "redis"
        settings.cache.redis_url = "redis://127.0.0.1:6379/0"
        with patch(
            "daari.cache.redis_client.connect_redis",
            side_effect=TimeoutError("timed out"),
        ):
            result = _check_redis(settings)
        assert result.ok is False
        assert result.optional is True
        assert "unreachable" in result.detail
        assert "TimeoutError" in result.detail
        assert doctor_exit_code([result]) == 0


class TestDoctorReady:
    def test_ready_skipped_when_daemon_down(self, settings):
        result = _check_ready(settings, None, daemon_ok=False)
        assert result.ok is True
        assert "skipped" in result.detail

    def test_ready_ok_status(self, settings):
        mock = MagicMock(spec=httpx.Client)
        mock.get.return_value = _ready_payload("ready")
        result = _check_ready(settings, mock, daemon_ok=True)
        assert result.ok is True
        assert "status=ready" in result.detail
        mock.get.assert_called_once()
        assert mock.get.call_args.args[0].endswith("/ready")

    def test_ready_degraded_warns(self, settings):
        mock = MagicMock(spec=httpx.Client)
        mock.get.return_value = _ready_payload("degraded")
        result = _check_ready(settings, mock, daemon_ok=True)
        assert result.ok is False
        assert result.optional is True
        assert "status=degraded" in result.detail

    def test_ready_not_ready_warns(self, settings):
        mock = MagicMock(spec=httpx.Client)
        mock.get.return_value = _ready_payload("not_ready", http_status=503)
        result = _check_ready(settings, mock, daemon_ok=True)
        assert result.ok is False
        assert "status=not_ready" in result.detail

    def test_run_doctor_includes_redis_and_ready(self, settings):
        mock = MagicMock(spec=httpx.Client)

        def get_side_effect(url, **_kwargs):
            if url.endswith("/api/tags"):
                return _tags_ok()
            if url.endswith("/v1/daari/stats"):
                return _stats_ok()
            if url.endswith("/ready"):
                return _ready_payload("ready")
            raise AssertionError(f"unexpected url {url}")

        mock.get.side_effect = get_side_effect
        results = run_doctor(settings, httpx_client=mock)
        by_name = {r.name: r for r in results}
        assert by_name["redis"].ok is True
        assert by_name["ready"].ok is True
        assert "status=ready" in by_name["ready"].detail
        assert doctor_exit_code(results) == 0
