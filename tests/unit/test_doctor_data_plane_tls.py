"""Doctor warns on cleartext remote Postgres/Redis DSNs (#1679)."""

from __future__ import annotations

from pathlib import Path

from daari.config.settings import Settings
from daari.setup.doctor import _check_remote_postgres_tls, _check_remote_redis_tls

DOC = Path("docs/developer/reference/config.md")
HELM = Path("deploy/helm/daari/values.yaml")


def test_local_postgres_dsn_silent(settings):
    settings.observability.postgres_url = "postgresql://daari@127.0.0.1:5432/daari"
    result = _check_remote_postgres_tls(settings)
    assert result.ok
    assert result.name == "postgres_tls"


def test_remote_postgres_without_sslmode_warns(settings):
    settings.observability.postgres_url = "postgresql://daari@db.corp:5432/daari"
    result = _check_remote_postgres_tls(settings)
    assert result.ok is False
    assert "sslmode=require" in result.detail


def test_remote_postgres_with_sslmode_require_ok(settings):
    settings.observability.postgres_url = (
        "postgresql://daari@db.corp:5432/daari?sslmode=require&sslrootcert=/etc/ca.pem"
    )
    result = _check_remote_postgres_tls(settings)
    assert result.ok
    assert "sslmode=require" in result.detail


def test_unset_postgres_skipped(settings):
    settings.observability.postgres_url = ""
    result = _check_remote_postgres_tls(settings)
    assert result.ok
    assert "skipped" in result.detail


def test_local_redis_silent(settings):
    settings.cache.backend = "redis"
    settings.cache.redis_url = "redis://127.0.0.1:6379/0"
    result = _check_remote_redis_tls(settings)
    assert result.ok


def test_remote_redis_plain_warns(settings):
    settings.cache.backend = "redis"
    settings.cache.redis_url = "redis://cache.corp:6379/0"
    result = _check_remote_redis_tls(settings)
    assert result.ok is False
    assert "rediss://" in result.detail


def test_remote_rediss_ok(settings):
    settings.cache.backend = "redis"
    settings.cache.redis_url = "rediss://cache.corp:6379/0"
    result = _check_remote_redis_tls(settings)
    assert result.ok


def test_redis_tls_skipped_when_disk(settings):
    settings.cache.backend = "disk"
    result = _check_remote_redis_tls(settings)
    assert result.ok
    assert "skipped" in result.detail


def test_docs_and_helm_mention_data_plane_tls() -> None:
    doc = DOC.read_text(encoding="utf-8")
    helm = HELM.read_text(encoding="utf-8")
    assert "sslmode=require" in doc
    assert "rediss://" in doc
    assert "sslmode=require" in helm or "sslmode" in helm
    assert "rediss://" in helm
