"""GET /ready schema_ok when Postgres store schemas lag the binary (#1895)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.setup.doctor import _check_schema_ok
from daari.setup.migrate import (
    DictPgInspector,
    PG_STORE_COLUMNS,
    store_schema_status,
)


def _pg_settings(tmp_path: Path) -> Settings:
    return Settings.model_validate(
        {
            "usage": {"path": str(tmp_path / "ledger.sqlite3")},
            "server": {
                "virtual_keys": {
                    "path": str(tmp_path / "vk.sqlite3"),
                    "backend": "postgres",
                },
            },
            "enterprise": {
                "audit_path": str(tmp_path / "audit.sqlite3"),
                "audit_backend": "postgres",
            },
            "trace": {"path": str(tmp_path / "traces" / "traces.sqlite3")},
            "integrations": {"mcp_tasks": {"path": str(tmp_path / "mcp-tasks")}},
            "observability": {
                "postgres_url": "memory:pg-schema-ok",
                "request_log": {"backend": "postgres"},
            },
        }
    )


def _full_tables() -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {}
    for store_cols in PG_STORE_COLUMNS.values():
        for table, cols in store_cols.items():
            tables[table] = set(cols)
    return tables


def test_store_schema_ok_false_when_pg_columns_missing(tmp_path: Path):
    settings = _pg_settings(tmp_path)
    inspector = DictPgInspector(
        tables={"daari_request_log": {"id", "ts", "event"}},  # missing payload
    )
    status = store_schema_status(settings, pg_inspector=inspector)
    assert status.schema_ok is False
    skewed = [row for row in status.rows if row.state == "behind"]
    assert any(row.name.startswith("postgres.") for row in skewed)


def test_store_schema_ok_true_when_pg_healthy(tmp_path: Path):
    settings = _pg_settings(tmp_path)
    inspector = DictPgInspector(tables=_full_tables())
    status = store_schema_status(settings, pg_inspector=inspector)
    assert status.schema_ok is True
    pg_rows = [row for row in status.rows if row.name.startswith("postgres.")]
    assert pg_rows
    assert all(row.state == "match" for row in pg_rows)


def test_store_schema_ok_ignores_unreachable_pg(tmp_path: Path):
    """Connect failures stay on checks.postgres — not schema skew (#1895)."""
    settings = _pg_settings(tmp_path)
    inspector = DictPgInspector(reachable=False, error="connection refused")
    status = store_schema_status(settings, pg_inspector=inspector)
    assert status.schema_ok is True
    assert any(
        row.name.startswith("postgres.") and row.state == "unreachable" for row in status.rows
    )


def test_doctor_schema_ok_names_lagging_pg_store(tmp_path: Path, monkeypatch):
    settings = _pg_settings(tmp_path)
    inspector = DictPgInspector(
        tables={"daari_request_log": {"id", "ts", "event"}},
    )
    monkeypatch.setattr(
        "daari.setup.migrate.store_schema_status",
        lambda s, **kw: store_schema_status(s, pg_inspector=inspector),
    )
    result = _check_schema_ok(settings)
    assert result.ok is False
    assert "postgres.request-log" in result.detail
    assert "daari migrate" in result.detail


@pytest.mark.asyncio
async def test_ready_not_ready_when_pg_schema_skews(tmp_path: Path, monkeypatch):
    settings = _pg_settings(tmp_path)
    inspector = DictPgInspector(
        tables={"daari_request_log": {"id", "ts", "event"}},
    )

    async def backend_ok(probe_url: str, timeout: float = 2.0) -> str:
        return "ok"

    monkeypatch.setattr("daari.gateway.openai.check_model_backend", backend_ok)
    monkeypatch.setattr(
        "daari.setup.migrate.store_schema_status",
        lambda s, **kw: store_schema_status(s, pg_inspector=inspector),
    )
    monkeypatch.setattr(
        "daari.gateway.openai._probe_postgres_url",
        lambda url: "ok",
    )

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
    body = response.json()
    assert body["schema_ok"] is False
    assert response.status_code == 503
    assert body["status"] == "not_ready"
    assert body["checks"].get("postgres") == "ok"


@pytest.mark.asyncio
async def test_ready_schema_ok_true_when_pg_current(tmp_path: Path, monkeypatch):
    settings = _pg_settings(tmp_path)
    inspector = DictPgInspector(tables=_full_tables())

    async def backend_ok(probe_url: str, timeout: float = 2.0) -> str:
        return "ok"

    monkeypatch.setattr("daari.gateway.openai.check_model_backend", backend_ok)
    monkeypatch.setattr(
        "daari.setup.migrate.store_schema_status",
        lambda s, **kw: store_schema_status(s, pg_inspector=inspector),
    )
    monkeypatch.setattr(
        "daari.gateway.openai._probe_postgres_url",
        lambda url: "ok",
    )

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
    body = response.json()
    assert body["schema_ok"] is True
    assert response.status_code == 200
    assert body["status"] == "ready"


def test_doctor_health_docs_mention_postgres_schema_ok():
    text = Path("docs/developer/guides/operations/doctor-health.md").read_text()
    assert "postgres" in text.lower()
    assert "schema_ok" in text
    assert "daari migrate" in text
