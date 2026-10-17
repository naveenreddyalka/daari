"""GET /ready schema_ok and doctor mismatch when SQLite lags the binary (#1727)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.ops.backup import STORE_SCHEMA_VERSIONS, local_sqlite_schema_status
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.setup.doctor import _check_schema_ok


def _stamp(path: Path, version: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(f"PRAGMA user_version = {int(version)}")
        conn.commit()
    finally:
        conn.close()


def test_schema_ok_when_present_store_matches(settings):
    expected = STORE_SCHEMA_VERSIONS["ledger"]
    _stamp(Path(settings.usage.path), expected)
    status = local_sqlite_schema_status(settings)
    assert status.schema_ok is True
    ledger = next(row for row in status.rows if row.name == "ledger")
    assert ledger.state == "match"
    assert ledger.actual == expected


def test_schema_ok_false_when_store_is_behind(settings, monkeypatch):
    monkeypatch.setitem(STORE_SCHEMA_VERSIONS, "ledger", STORE_SCHEMA_VERSIONS["ledger"] + 1)
    expected = STORE_SCHEMA_VERSIONS["ledger"]
    _stamp(Path(settings.usage.path), expected - 1)
    status = local_sqlite_schema_status(settings)
    assert status.schema_ok is False
    ledger = next(row for row in status.rows if row.name == "ledger")
    assert ledger.state == "behind"
    assert ledger.actual == expected - 1
    assert ledger.expected == expected


def test_absent_optional_store_does_not_fail_schema_ok(settings):
    spend = Path(settings.usage.spend.path)
    assert settings.usage.spend.enabled is False
    assert not spend.is_file()
    status = local_sqlite_schema_status(settings)
    assert status.schema_ok is True
    row = next(row for row in status.rows if row.name == "spend")
    assert row.state == "absent"


def test_unstamped_legacy_file_matches_version_one(settings):
    """user_version 0 is the pre-stamp additive schema recorded as 1."""
    assert STORE_SCHEMA_VERSIONS["ledger"] == 1
    _stamp(Path(settings.usage.path), 0)
    status = local_sqlite_schema_status(settings)
    assert status.schema_ok is True


def test_doctor_surfaces_schema_mismatch(settings, monkeypatch):
    monkeypatch.setitem(STORE_SCHEMA_VERSIONS, "ledger", 2)
    _stamp(Path(settings.usage.path), 1)
    result = _check_schema_ok(settings)
    assert result.name == "schema_ok"
    assert result.ok is False
    assert "ledger" in result.detail
    assert "2" in result.detail


@pytest.mark.asyncio
async def test_ready_schema_ok_true_when_store_matches(settings, monkeypatch):
    _stamp(Path(settings.usage.path), STORE_SCHEMA_VERSIONS["ledger"])

    async def backend_ok(probe_url: str, timeout: float = 2.0) -> str:
        return "ok"

    monkeypatch.setattr("daari.gateway.openai.check_model_backend", backend_ok)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
    body = response.json()
    assert body["schema_ok"] is True
    assert response.status_code == 200
    assert body["status"] == "ready"


@pytest.mark.asyncio
async def test_ready_not_healthy_when_store_is_behind(settings, monkeypatch):
    monkeypatch.setitem(STORE_SCHEMA_VERSIONS, "ledger", 2)
    _stamp(Path(settings.usage.path), 1)

    async def backend_ok(probe_url: str, timeout: float = 2.0) -> str:
        return "ok"

    monkeypatch.setattr("daari.gateway.openai.check_model_backend", backend_ok)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
    body = response.json()
    assert body["schema_ok"] is False
    assert not (response.status_code == 200 and body["status"] == "ready")
    assert response.status_code == 503
    assert body["status"] == "not_ready"


def test_doctor_health_docs_mention_schema_ok():
    text = Path("docs/developer/guides/operations/doctor-health.md").read_text()
    assert "schema_ok" in text
