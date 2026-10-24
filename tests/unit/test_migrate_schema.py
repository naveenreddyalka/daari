"""daari migrate dry-run + policy/store schema skew (#942)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daari.cli.app import app as cli_app
from daari.config.settings import Settings
from daari.enterprise.bootstrap import (
    POLICY_SCHEMA,
    PolicySchemaError,
    apply_org_config,
    validate_policy_schema,
)
from daari.enterprise.policy_sync import apply_policy_to_runtime, sync_policy_once
from daari.setup.doctor import CheckResult, doctor_exit_code, run_doctor
from daari.setup.migrate import inspect_stores, run_migrate


def _settings(tmp_path: Path) -> Settings:
    return Settings.model_validate(
        {
            "usage": {"path": str(tmp_path / "ledger.sqlite3")},
            "server": {
                "virtual_keys": {"path": str(tmp_path / "vk.sqlite3")},
            },
            "enterprise": {"audit_path": str(tmp_path / "audit.sqlite3")},
            "trace": {"path": str(tmp_path / "traces" / "traces.sqlite3")},
            "integrations": {"mcp_tasks": {"path": str(tmp_path / "mcp-tasks")}},
        }
    )


def test_validate_policy_schema_accepts_current_and_legacy():
    validate_policy_schema({})
    validate_policy_schema({"schema": POLICY_SCHEMA})
    validate_policy_schema({"schema": 1, "routing": {"prefer": "local"}})


def test_validate_policy_schema_refuses_unknown_major():
    with pytest.raises(PolicySchemaError, match="unknown policy schema"):
        validate_policy_schema({"schema": POLICY_SCHEMA + 1})


def test_apply_org_config_refuses_unknown_schema(tmp_path: Path):
    with pytest.raises(PolicySchemaError):
        apply_org_config(
            {"schema": 99, "org": {"id": "acme"}},
            config_path=tmp_path / "config.yaml",
        )


def test_apply_org_config_accepts_schema_and_ignores_unknown_keys(tmp_path: Path):
    path = apply_org_config(
        {
            "schema": POLICY_SCHEMA,
            "org": {"id": "acme", "enabled": True},
            "future_section": {"x": 1},
            "routing": {"prefer": "local", "unknown_route_key": "x"},
        },
        config_path=tmp_path / "config.yaml",
    )
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "acme" in text


def test_apply_policy_to_runtime_refuses_unknown_schema():
    settings = Settings.model_validate({})
    router = type("R", (), {})()
    with pytest.raises(PolicySchemaError):
        apply_policy_to_runtime(settings, router, {"schema": 99})


def test_dry_run_reports_missing_and_pending(tmp_path: Path):
    settings = _settings(tmp_path)
    # Pre-#156 style ledger missing model column.
    ledger = Path(settings.usage.path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(ledger) as conn:
        conn.execute(
            "CREATE TABLE usage (day TEXT, tier TEXT, requests INTEGER, PRIMARY KEY (day, tier))"
        )
    notes = inspect_stores(settings)
    by_name = {n.name: n for n in notes}
    assert by_name["ledger"].pending
    assert by_name["virtual-keys"].status in {"missing", "pending", "current"}
    assert by_name["mcp-tasks"].name == "mcp-tasks"
    lines = run_migrate(settings, dry_run=True)
    joined = "\n".join(lines)
    assert "ledger" in joined
    assert "dry-run" in joined.lower() or "would" in joined.lower()
    assert "additive-safe" in joined.lower() or "ok" in joined.lower()


def test_migrate_applies_and_reports_changed(tmp_path: Path):
    settings = _settings(tmp_path)
    ledger = Path(settings.usage.path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(ledger) as conn:
        conn.execute(
            "CREATE TABLE usage (day TEXT NOT NULL, tier TEXT NOT NULL, "
            "requests INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, tier))"
        )
        conn.execute(
            "CREATE TABLE client_usage (day TEXT NOT NULL, client_id TEXT NOT NULL, "
            "tier TEXT NOT NULL, requests INTEGER NOT NULL DEFAULT 0, "
            "PRIMARY KEY (day, client_id, tier))"
        )
    lines = run_migrate(settings, dry_run=False)
    joined = "\n".join(lines)
    assert "ledger" in joined
    with sqlite3.connect(ledger) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(usage)")}
    assert "model" in cols
    after = inspect_stores(settings)
    assert not any(n.pending for n in after if n.name == "ledger")


def test_cli_migrate_dry_run(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner()
    result = runner.invoke(cli_app, ["migrate", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "ledger" in result.output
    assert "virtual-keys" in result.output
    assert "audit" in result.output
    assert "responses" in result.output
    assert "mcp-tasks" in result.output


def test_doctor_warns_on_pending_migrate(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path)
    ledger = Path(settings.usage.path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(ledger) as conn:
        conn.execute(
            "CREATE TABLE usage (day TEXT, tier TEXT, requests INTEGER, PRIMARY KEY (day, tier))"
        )

    def _ok_embedding(cfg, client):
        return CheckResult(name="embedding_endpoint", ok=True, detail="stub", optional=True)

    monkeypatch.setattr("daari.setup.doctor._check_embedding_endpoint", _ok_embedding)
    monkeypatch.setattr("daari.setup.doctor._check_ollama", lambda *a, **k: [])
    results = run_doctor(settings, httpx_client=None)
    by_name = {r.name: r for r in results}
    assert "store_migrate" in by_name
    assert by_name["store_migrate"].ok is False
    assert by_name["store_migrate"].optional is True
    assert doctor_exit_code(results) == 0

    results_strict = run_doctor(settings, httpx_client=None, strict=True)
    by_name_s = {r.name: r for r in results_strict}
    assert by_name_s["store_migrate"].optional is False
    assert doctor_exit_code(results_strict) == 1


def test_sync_policy_once_refuses_unknown_schema(monkeypatch):
    settings = Settings.model_validate(
        {
            "enterprise": {
                "policy_sync_url": "https://example.com/policy",
                "config_signing_secret": "s",
            }
        }
    )

    def fake_fetch(url, *, token="", timeout=10.0):
        import json

        body = json.dumps({"schema": 99, "routing": {}}).encode()
        return {"schema": 99, "routing": {}}, body, "deadbeef"

    monkeypatch.setattr("daari.enterprise.policy_sync.fetch_org_config", fake_fetch)
    monkeypatch.setattr("daari.enterprise.policy_sync.verify_signature", lambda *a, **k: True)
    result = sync_policy_once(settings, router=None, insecure=True)
    assert result["ok"] is False
    assert result["reason"] == "unknown_schema"


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
                "postgres_url": "postgresql://migrate-test.invalid/daari",
                "request_log": {"backend": "postgres"},
            },
        }
    )


def test_pg_dry_run_reports_pending_and_version(tmp_path: Path):
    from daari.setup.migrate import DictPgInspector, PG_SCHEMA_VERSIONS

    settings = _pg_settings(tmp_path)
    inspector = DictPgInspector(
        tables={"daari_request_log": {"id", "ts", "event"}},  # missing payload
    )
    lines = run_migrate(settings, dry_run=True, pg_inspector=inspector)
    joined = "\n".join(lines)
    assert "postgres.request-log" in joined
    assert "postgres.virtual-keys" in joined
    assert "postgres.audit" in joined
    assert "pending" in joined
    assert f"v{PG_SCHEMA_VERSIONS['postgres.request-log']}" in joined or "payload" in joined
    notes = inspect_stores(settings, pg_inspector=inspector)
    by_name = {n.name: n for n in notes}
    assert by_name["postgres.request-log"].status == "pending"
    assert any("payload" in p for p in by_name["postgres.request-log"].pending)


def test_pg_dry_run_reports_unreachable(tmp_path: Path):
    from daari.setup.migrate import DictPgInspector

    settings = _pg_settings(tmp_path)
    inspector = DictPgInspector(reachable=False, error="connection refused")
    lines = run_migrate(settings, dry_run=True, pg_inspector=inspector)
    joined = "\n".join(lines)
    assert "postgres.request-log" in joined
    assert "unreachable" in joined.lower() or "error" in joined
    notes = inspect_stores(settings, pg_inspector=inspector)
    assert all(
        n.status == "error"
        for n in notes
        if n.name.startswith("postgres.")
    )


def test_pg_migrate_applies_additive_via_inspector(tmp_path: Path):
    from daari.setup.migrate import DictPgInspector, PG_STORE_COLUMNS

    settings = _pg_settings(tmp_path)
    # Start with empty tables → pending create; apply fills expected columns.
    inspector = DictPgInspector(tables={})
    before = inspect_stores(settings, pg_inspector=inspector)
    assert any(n.status == "pending" for n in before if n.name.startswith("postgres."))
    lines = run_migrate(settings, dry_run=False, pg_inspector=inspector)
    joined = "\n".join(lines)
    assert "postgres.request-log" in joined
    after = inspect_stores(settings, pg_inspector=inspector)
    for name, tables in PG_STORE_COLUMNS.items():
        note = next(n for n in after if n.name == name)
        assert note.status == "current", (name, note.pending)
        for table, cols in tables.items():
            assert cols <= inspector.columns(table)


def test_doctor_warns_on_pg_schema_lag(tmp_path: Path, monkeypatch):
    from daari.setup.doctor import _check_store_migrate
    from daari.setup.migrate import DictPgInspector

    settings = _pg_settings(tmp_path)
    inspector = DictPgInspector(
        tables={"daari_request_log": {"id", "ts", "event"}},
    )
    monkeypatch.setattr(
        "daari.setup.migrate.inspect_stores",
        lambda s, **kw: inspect_stores(s, pg_inspector=inspector),
    )
    result = _check_store_migrate(settings)
    assert result.ok is False
    assert "postgres.request-log" in result.detail
    assert result.optional is True


def test_upgrade_docs_mention_pg_migrate_order():
    text = (
        Path(__file__).resolve().parents[2]
        / "docs/developer/guides/operations/upgrade.md"
    ).read_text(encoding="utf-8")
    assert "postgres.request-log" in text
    assert "daari migrate" in text
    assert "before" in text.lower() and "roll" in text.lower()
    from daari.gateway.postgres_request_log import SCHEMA_VERSION

    assert SCHEMA_VERSION >= 1


def test_pg_downgrade_dry_run_reports_reversible_columns(tmp_path: Path):
    from daari.setup.migrate import (
        DictPgInspector,
        PG_LATEST_ADDITIVE,
        PG_STORE_COLUMNS,
        run_migrate,
    )

    settings = _pg_settings(tmp_path)
    tables: dict[str, set[str]] = {}
    for store_cols in PG_STORE_COLUMNS.values():
        for table, cols in store_cols.items():
            tables[table] = set(cols)
    inspector = DictPgInspector(tables=tables)
    lines = run_migrate(settings, dry_run=True, downgrade=True, pg_inspector=inspector)
    joined = "\n".join(lines)
    assert "downgrade" in joined.lower()
    # At least one store has a reversible latest-additive batch.
    assert any(PG_LATEST_ADDITIVE.values())
    assert "would" in joined.lower() or "drop" in joined.lower() or "reverse" in joined.lower()


def test_pg_downgrade_noop_when_nothing_to_reverse(tmp_path: Path):
    from daari.setup.migrate import DictPgInspector, PG_STORE_COLUMNS, run_migrate

    settings = _pg_settings(tmp_path)
    # Baseline tables without latest-additive columns → nothing to reverse.
    from daari.setup.migrate import PG_LATEST_ADDITIVE

    tables: dict[str, set[str]] = {}
    for store, store_cols in PG_STORE_COLUMNS.items():
        latest = PG_LATEST_ADDITIVE.get(store, {})
        for table, cols in store_cols.items():
            drop = latest.get(table, frozenset())
            tables[table] = set(cols) - set(drop)
    inspector = DictPgInspector(tables=tables)
    lines = run_migrate(settings, dry_run=True, downgrade=True, pg_inspector=inspector)
    joined = "\n".join(lines)
    assert "nothing to reverse" in joined.lower() or "noop" in joined.lower() or "none" in joined.lower()


def test_pg_downgrade_applies_via_inspector(tmp_path: Path):
    from daari.setup.migrate import (
        DictPgInspector,
        PG_LATEST_ADDITIVE,
        PG_STORE_COLUMNS,
        run_migrate,
    )

    settings = _pg_settings(tmp_path)
    tables: dict[str, set[str]] = {}
    for store_cols in PG_STORE_COLUMNS.values():
        for table, cols in store_cols.items():
            tables[table] = set(cols)
    inspector = DictPgInspector(tables=tables)
    lines = run_migrate(settings, dry_run=False, downgrade=True, pg_inspector=inspector)
    joined = "\n".join(lines)
    assert "downgrade" in joined.lower() or "reversed" in joined.lower() or "dropped" in joined.lower()
    for store, latest in PG_LATEST_ADDITIVE.items():
        for table, cols in latest.items():
            for col in cols:
                assert col not in inspector.columns(table), (store, table, col)


def test_cli_migrate_downgrade_dry_run(tmp_path: Path, monkeypatch):
    from daari.setup.migrate import DictPgInspector, PG_STORE_COLUMNS

    settings = _pg_settings(tmp_path)
    tables: dict[str, set[str]] = {}
    for store_cols in PG_STORE_COLUMNS.values():
        for table, cols in store_cols.items():
            tables[table] = set(cols)
    inspector = DictPgInspector(tables=tables)
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    monkeypatch.setattr(
        "daari.setup.migrate.LivePgInspector",
        lambda dsn: inspector,
    )
    runner = CliRunner()
    result = runner.invoke(cli_app, ["migrate", "--downgrade", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "downgrade" in result.output.lower()
