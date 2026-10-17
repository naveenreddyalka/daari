"""Doctor warns on cleartext remote Postgres/Redis data planes (#1679)."""

from __future__ import annotations

import httpx

from daari.config.settings import Settings
from daari.setup.doctor import (
    _check_postgres_tls,
    _check_redis_tls,
    run_doctor,
)

DOCTOR_HEALTH = "docs/developer/guides/operations/doctor-health.md"
CONFIG_MD = "docs/developer/reference/config.md"


def _down_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_postgres_remote_without_sslmode_warns(settings: Settings) -> None:
    settings.observability.postgres_url = "postgresql://daari:daari@db.example.com:5432/daari"
    result = _check_postgres_tls(settings)
    assert result.name == "postgres_tls"
    assert result.ok is False
    assert result.optional is True
    assert "sslmode" in result.detail.lower()


def test_postgres_remote_with_sslmode_require_ok(settings: Settings) -> None:
    settings.observability.postgres_url = (
        "postgresql://daari:daari@db.example.com:5432/daari?sslmode=require"
    )
    result = _check_postgres_tls(settings)
    assert result.ok is True


def test_postgres_remote_with_verify_full_ok(settings: Settings) -> None:
    settings.observability.postgres_url = (
        "postgresql://daari@db.example.com/daari"
        "?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca.pem"
    )
    result = _check_postgres_tls(settings)
    assert result.ok is True


def test_postgres_localhost_without_sslmode_silent(settings: Settings) -> None:
    settings.observability.postgres_url = "postgresql://daari@127.0.0.1:5432/daari"
    result = _check_postgres_tls(settings)
    assert result.ok is True
    assert "loopback" in result.detail.lower() or "local" in result.detail.lower()


def test_postgres_unix_socket_silent(settings: Settings) -> None:
    settings.observability.postgres_url = "postgresql:///daari?host=/var/run/postgresql"
    result = _check_postgres_tls(settings)
    assert result.ok is True


def test_postgres_empty_url_skipped(settings: Settings) -> None:
    settings.observability.postgres_url = ""
    result = _check_postgres_tls(settings)
    assert result.ok is True
    assert "unset" in result.detail.lower() or "skip" in result.detail.lower()


def test_postgres_prefer_sslmode_warns(settings: Settings) -> None:
    settings.observability.postgres_url = (
        "postgresql://daari@db.example.com/daari?sslmode=prefer"
    )
    result = _check_postgres_tls(settings)
    assert result.ok is False


def test_redis_remote_cleartext_warns(settings: Settings) -> None:
    settings.cache.backend = "redis"
    settings.cache.redis_url = "redis://redis.example.com:6379/0"
    result = _check_redis_tls(settings)
    assert result.name == "redis_tls"
    assert result.ok is False
    assert result.optional is True
    assert "rediss" in result.detail.lower()


def test_redis_remote_rediss_ok(settings: Settings) -> None:
    settings.cache.backend = "redis"
    settings.cache.redis_url = "rediss://redis.example.com:6379/0"
    result = _check_redis_tls(settings)
    assert result.ok is True


def test_redis_localhost_cleartext_silent(settings: Settings) -> None:
    settings.cache.backend = "redis"
    settings.cache.redis_url = "redis://127.0.0.1:6379/0"
    result = _check_redis_tls(settings)
    assert result.ok is True


def test_redis_disabled_skipped(settings: Settings) -> None:
    settings.cache.backend = "disk"
    settings.cache.redis_url = "redis://redis.example.com:6379/0"
    result = _check_redis_tls(settings)
    assert result.ok is True
    assert "disabled" in result.detail.lower() or "skip" in result.detail.lower()


def test_run_doctor_includes_data_plane_tls_checks(settings: Settings) -> None:
    settings.observability.postgres_url = "postgresql://daari@db.example.com/daari"
    settings.cache.backend = "redis"
    settings.cache.redis_url = "redis://redis.example.com:6379/0"
    by_name = {r.name: r for r in run_doctor(settings, httpx_client=_down_client())}
    assert "postgres_tls" in by_name
    assert by_name["postgres_tls"].ok is False
    assert "redis_tls" in by_name
    assert by_name["redis_tls"].ok is False


def test_strict_makes_remote_cleartext_required(settings: Settings) -> None:
    from daari.setup.doctor import doctor_exit_code

    settings.observability.postgres_url = "postgresql://daari@db.example.com/daari"
    settings.cache.backend = "redis"
    settings.cache.redis_url = "redis://redis.example.com:6379/0"
    soft = run_doctor(settings, httpx_client=_down_client(), strict=False)
    soft_by = {r.name: r for r in soft}
    assert soft_by["postgres_tls"].optional is True
    assert soft_by["redis_tls"].optional is True
    assert doctor_exit_code([soft_by["postgres_tls"], soft_by["redis_tls"]]) == 0
    hard = run_doctor(settings, httpx_client=_down_client(), strict=True)
    hard_by = {r.name: r for r in hard}
    assert hard_by["postgres_tls"].optional is False
    assert hard_by["postgres_tls"].ok is False
    assert hard_by["redis_tls"].optional is False
    assert hard_by["redis_tls"].ok is False
    assert doctor_exit_code([hard_by["postgres_tls"], hard_by["redis_tls"]]) == 1


def test_strict_http_webhook_and_otlp_and_mcp(settings: Settings, monkeypatch) -> None:
    from daari.config.settings import McpServerSettings
    from daari.setup.doctor import doctor_exit_code

    settings.alerts.budget_webhook_url = "http://hooks.example.com/budget"
    settings.alerts.key_expiry_webhook_url = "https://hooks.example.com/expiry"
    settings.observability.otlp_logs = True
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel.example.com:4318")
    settings.integrations.mcp_servers = [
        McpServerSettings(id="remote", url="http://mcp.example.com/sse"),
        McpServerSettings(id="local", url="http://127.0.0.1:8080/sse"),
    ]
    soft = run_doctor(settings, httpx_client=_down_client(), strict=False)
    soft_by = {r.name: r for r in soft}
    assert soft_by["egress_https"].ok is False
    assert soft_by["egress_https"].optional is True
    assert doctor_exit_code([soft_by["egress_https"]]) == 0
    hard = run_doctor(settings, httpx_client=_down_client(), strict=True)
    hard_by = {r.name: r for r in hard}
    assert hard_by["egress_https"].ok is False
    assert hard_by["egress_https"].optional is False
    assert "budget_webhook" in hard_by["egress_https"].detail
    assert "otel" in hard_by["egress_https"].detail.lower() or "OTLP" in hard_by["egress_https"].detail
    assert "mcp:remote" in hard_by["egress_https"].detail
    assert "mcp:local" not in hard_by["egress_https"].detail
    assert doctor_exit_code([hard_by["egress_https"]]) == 1


def test_doctor_health_documents_data_plane_tls() -> None:
    from pathlib import Path

    text = Path(DOCTOR_HEALTH).read_text()
    assert "doctor `postgres_tls`" in text
    assert "doctor `redis_tls`" in text
    assert "doctor `egress_https`" in text
    assert "--strict" in text


def test_config_docs_mention_data_plane_tls() -> None:
    from pathlib import Path

    text = Path(CONFIG_MD).read_text()
    assert "sslmode" in text
    assert "rediss://" in text or "rediss" in text
    assert "sslrootcert" in text
