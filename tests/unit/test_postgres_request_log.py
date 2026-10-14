"""Postgres request/event log for fleets (#1631)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from daari.config.settings import Settings
from daari.gateway import request_log
from daari.gateway.postgres_request_log import PostgresRequestLogStore
from daari.gateway.request_log import configure_request_log, log_gateway_event
from daari.observability.retention import prune_all
from daari.ops.backup import catalog_stores


def _dsn() -> str:
    return f"memory:reqlog-{uuid.uuid4().hex}"


@pytest.fixture(autouse=True)
def _reset_request_log():
    configure_request_log(
        path=request_log.DEFAULT_LOG_PATH,
        max_bytes=request_log.DEFAULT_MAX_BYTES,
        backups=request_log.DEFAULT_BACKUPS,
        structured_json_logs=False,
        otlp_logs=False,
        backend="jsonl",
        postgres_url="",
    )
    yield
    configure_request_log(
        path=request_log.DEFAULT_LOG_PATH,
        max_bytes=request_log.DEFAULT_MAX_BYTES,
        backups=request_log.DEFAULT_BACKUPS,
        structured_json_logs=False,
        otlp_logs=False,
        backend="jsonl",
        postgres_url="",
    )


def test_default_request_log_backend_is_jsonl():
    assert Settings().observability.request_log.backend == "jsonl"


def test_two_replicas_share_appended_rows():
    dsn = _dsn()
    a = PostgresRequestLogStore(dsn)
    b = PostgresRequestLogStore(dsn)
    a.append("route", {"model": "l3", "ts": "2026-10-14T00:00:00+00:00"})
    rows = b.list_events()
    assert len(rows) == 1
    assert rows[0]["event"] == "route"
    assert rows[0]["payload"]["model"] == "l3"


def test_log_gateway_event_postgres_best_effort(tmp_path):
    dsn = _dsn()
    configure_request_log(
        path=tmp_path / "unused.log",
        backend="postgres",
        postgres_url=dsn,
    )
    log_gateway_event("chat", {"tier": "local"})
    store = PostgresRequestLogStore(dsn)
    rows = store.list_events()
    assert len(rows) == 1
    assert rows[0]["event"] == "chat"
    assert rows[0]["payload"]["tier"] == "local"
    assert not (tmp_path / "unused.log").exists()


def test_log_gateway_event_postgres_never_raises():
    configure_request_log(
        backend="postgres",
        postgres_url="postgresql://invalid:5432/nope",
    )
    # Fail-open: must not raise into the request path.
    log_gateway_event("chat", {"ok": True})


def test_prune_postgres_request_log():
    dsn = _dsn()
    store = PostgresRequestLogStore(dsn)
    old_ts = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    new_ts = datetime.now(UTC).isoformat()
    store.append("old", {"ts": old_ts})
    store.append("new", {"ts": new_ts})
    cutoff = datetime.now(UTC) - timedelta(days=30)
    deleted = store.prune_before(cutoff, dry_run=False)
    assert deleted == 1
    rows = store.list_events()
    assert len(rows) == 1
    assert rows[0]["event"] == "new"


def test_prune_all_covers_postgres_backend(tmp_path):
    dsn = _dsn()
    settings = Settings()
    settings.observability.request_log.backend = "postgres"
    settings.observability.postgres_url = dsn
    settings.observability.retention.request_log_days = 30
    configure_request_log(backend="postgres", postgres_url=dsn)
    old_ts = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    log_gateway_event("stale", {"ts": old_ts, "n": 1})
    # Override ts inside payload is still stored; prune uses row ts column.
    store = PostgresRequestLogStore(dsn)
    # Force an old row via direct append
    store.append("stale2", {"x": 1}, ts=(datetime.now(UTC) - timedelta(days=40)).isoformat())
    results = prune_all(settings, now=datetime.now(UTC))
    row = next(item for item in results if item.store == "request_log")
    assert row.skipped is False
    assert row.deleted >= 1


def test_backup_catalog_postgres_request_log():
    settings = Settings()
    settings.observability.request_log.backend = "postgres"
    settings.observability.postgres_url = "postgresql://daari:daari@db/daari"
    by_name = {e.name: e for e in catalog_stores(settings)}
    entry = by_name["request-log"]
    assert entry.backend == "postgres"
    assert entry.pg_dump is not None
    assert "daari_request_log" in entry.pg_dump
    assert "request-log.1" not in by_name


def test_backup_catalog_jsonl_default(tmp_path, monkeypatch):
    log = tmp_path / "cursor-requests.log"
    log.write_text("{}\n")
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", log)
    settings = Settings()
    assert settings.observability.request_log.backend == "jsonl"
    by_name = {e.name: e for e in catalog_stores(settings, request_log_path=log)}
    assert by_name["request-log"].backend == "jsonl"
