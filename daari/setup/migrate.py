"""Operator-facing store migrate dry-run / apply (issue #942).

SQLite stores still migrate on open via their `_migrate` helpers. This module
inspects the same additive column/table expectations without Alembic, and can
open each store explicitly so upgrades are loud and reportable.

Postgres-backed stores (request-log, virtual-keys, audit at minimum) are
inspected the same way when ``observability.postgres_url`` is set (#1655).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from daari.config.settings import Settings


@dataclass
class StoreNote:
    name: str
    path: Path
    status: str  # missing | pending | current | applied | skipped | error
    notes: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)

    @property
    def additive_safe(self) -> bool:
        return self.status != "error"


# Shipped PG schema versions (current vs expected in dry-run reports, #1655).
PG_SCHEMA_VERSIONS: dict[str, int] = {
    "postgres.request-log": 1,
    "postgres.virtual-keys": 1,
    "postgres.audit": 1,
}

# Required columns per table for additive PG migrate probes (#1655).
PG_STORE_COLUMNS: dict[str, dict[str, frozenset[str]]] = {
    "postgres.request-log": {
        "daari_request_log": frozenset({"id", "ts", "event", "payload"}),
    },
    "postgres.virtual-keys": {
        "teams": frozenset(
            {
                "team_id",
                "name",
                "budget_windows_json",
                "created_at",
                "region_pin",
                "rpm",
                "tpm",
                "rpd",
                "allowed_models_json",
                "model_groups_json",
                "cache_scope",
                "priority",
            }
        ),
        "virtual_keys": frozenset(
            {
                "key_hash",
                "key_id",
                "name",
                "prefix",
                "created_at",
                "revoked_at",
                "expires_at",
                "daily_budget_usd",
                "monthly_budget_usd",
                "rpm",
                "tpm",
                "rpd",
                "tier_cap",
                "client_id",
                "team_id",
                "budget_windows_json",
                "metadata_json",
                "user_daily_usd_cap",
                "previous_key_hash",
                "previous_prefix",
                "previous_expires_at",
                "region_pin",
                "allowed_models_json",
                "model_groups_json",
                "cache_scope",
                "priority",
                "last_used_at",
            }
        ),
        "team_members": frozenset({"subject", "team_id"}),
    },
    "postgres.audit": {
        "daari_audit": frozenset(
            {"seq", "ts", "actor", "role", "action", "detail", "prev_hash", "row_hash"}
        ),
    },
}


class PgSchemaInspector(Protocol):
    """Column probe for Postgres migrate dry-run / apply (#1655)."""

    @property
    def reachable(self) -> bool: ...

    @property
    def error(self) -> str | None: ...

    def columns(self, table: str) -> set[str]: ...

    def apply_additive(self, store: str, pending: list[str]) -> list[str]: ...


@dataclass
class DictPgInspector:
    """Hermetic inspector: map of table -> columns; optional apply side-effects."""

    tables: dict[str, set[str]] = field(default_factory=dict)
    reachable: bool = True
    error: str | None = None
    applied: list[str] = field(default_factory=list)

    def columns(self, table: str) -> set[str]:
        return set(self.tables.get(table) or set())

    def apply_additive(self, store: str, pending: list[str]) -> list[str]:
        changed: list[str] = []
        for item in pending:
            if "." not in item:
                table = item.split(":")[0] if ":" in item else item
                expected = PG_STORE_COLUMNS.get(store, {}).get(table)
                if expected is not None:
                    self.tables[table] = set(expected)
                    changed.append(item)
                continue
            table, col = item.split(".", 1)
            cols = self.tables.setdefault(table, set())
            if col not in cols:
                cols.add(col)
                changed.append(item)
        self.applied.extend(changed)
        return changed


class LivePgInspector:
    """information_schema probe against a real (or memory:) DSN."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.reachable = False
        self.error: str | None = None
        self._memory = dsn.startswith("memory:")
        if self._memory:
            self.reachable = True
            return
        try:
            import psycopg

            with psycopg.connect(dsn, connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            self.reachable = True
        except Exception as exc:  # noqa: BLE001 — report, do not raise
            self.reachable = False
            self.error = str(exc)[:200]

    def columns(self, table: str) -> set[str]:
        if self._memory or not self.reachable:
            return set()
        try:
            import psycopg

            with psycopg.connect(self.dsn, connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = %s",
                        (table,),
                    )
                    return {str(row[0]) for row in cur.fetchall()}
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)[:200]
            self.reachable = False
            return set()

    def apply_additive(self, store: str, pending: list[str]) -> list[str]:
        """Open the store (CREATE IF NOT EXISTS) then ALTER missing columns."""
        if self._memory:
            return list(pending)
        if not self.reachable:
            return []
        try:
            import psycopg

            with psycopg.connect(self.dsn, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    for item in pending:
                        if "." not in item:
                            continue
                        table, col = item.split(".", 1)
                        cur.execute(
                            f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{col}" TEXT'
                        )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)[:200]
            return []
        return list(pending)


def responses_sqlite_path(settings: Settings) -> Path:
    return Path(settings.trace.path).expanduser().parent / "responses.sqlite3"


def store_paths(settings: Settings) -> dict[str, Path]:
    return {
        "ledger": Path(settings.usage.path).expanduser(),
        "virtual-keys": Path(settings.server.virtual_keys.path).expanduser(),
        "audit": Path(settings.enterprise.audit_path).expanduser(),
        "responses": responses_sqlite_path(settings),
        "mcp-tasks": Path(settings.integrations.mcp_tasks.path).expanduser(),
    }


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _pending_ledger(conn: sqlite3.Connection) -> list[str]:
    pending: list[str] = []
    for table in ("usage", "client_usage"):
        cols = _cols(conn, table)
        if not cols:
            pending.append(f"{table}: create/migrate")
            continue
        if "model" not in cols:
            pending.append(f"{table}.model")
    # Tables created by _migrate when missing.
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "budget_window_state" not in tables:
        pending.append("budget_window_state: create")
    if "user_usage" not in tables:
        pending.append("user_usage: create")
    return pending


def _pending_virtual_keys(conn: sqlite3.Connection) -> list[str]:
    pending: list[str] = []
    cols = _cols(conn, "virtual_keys")
    if not cols:
        return ["virtual_keys: create/migrate"]
    for col in (
        "tpm",
        "team_id",
        "budget_windows_json",
        "metadata_json",
        "expires_at",
        "previous_key_hash",
        "previous_prefix",
        "previous_expires_at",
        "user_daily_usd_cap",
        "region_pin",
        "allowed_models_json",
        "model_groups_json",
        "rpd",
        "cache_scope",
        "priority",
    ):
        if col not in cols:
            pending.append(f"virtual_keys.{col}")
    team_cols = _cols(conn, "teams")
    if not team_cols:
        pending.append("teams: create/migrate")
    else:
        for col in (
            "region_pin",
            "rpm",
            "tpm",
            "rpd",
            "allowed_models_json",
            "model_groups_json",
            "cache_scope",
            "priority",
            "metadata_json",
        ):
            if col not in team_cols:
                pending.append(f"teams.{col}")
    return pending


def _pending_audit(conn: sqlite3.Connection) -> list[str]:
    cols = _cols(conn, "audit")
    if not cols:
        return ["audit: create/migrate"]
    pending: list[str] = []
    for col in ("prev_hash", "row_hash"):
        if col not in cols:
            pending.append(f"audit.{col}")
    return pending


def _pending_responses(conn: sqlite3.Connection) -> list[str]:
    cols = _cols(conn, "responses")
    if not cols:
        return ["responses: create/migrate"]
    pending: list[str] = []
    for col in ("owner_key_id", "created_at"):
        if col not in cols:
            pending.append(f"responses.{col}")
    return pending


_PENDING: dict[str, Any] = {
    "ledger": _pending_ledger,
    "virtual-keys": _pending_virtual_keys,
    "audit": _pending_audit,
    "responses": _pending_responses,
}


def _inspect_sqlite(name: str, path: Path) -> StoreNote:
    if not path.exists():
        return StoreNote(
            name=name,
            path=path,
            status="missing",
            notes=["file absent — open will create + migrate"],
            pending=["create"],
        )
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return StoreNote(
            name=name,
            path=path,
            status="error",
            notes=[f"cannot open: {exc}"],
        )
    try:
        checker = _PENDING[name]
        pending = checker(conn)
    finally:
        conn.close()
    if pending:
        return StoreNote(
            name=name,
            path=path,
            status="pending",
            notes=["additive migrate pending"],
            pending=pending,
        )
    return StoreNote(
        name=name,
        path=path,
        status="current",
        notes=["schema current"],
    )


def _inspect_mcp_tasks(path: Path) -> StoreNote:
    if not path.exists():
        return StoreNote(
            name="mcp-tasks",
            path=path,
            status="missing",
            notes=["diskcache dir absent — open will create"],
            pending=["create"],
        )
    return StoreNote(
        name="mcp-tasks",
        path=path,
        status="current",
        notes=["diskcache create-if-missing (no SQL migrate)"],
    )


def _pg_url(settings: Settings) -> str:
    return str(getattr(settings.observability, "postgres_url", "") or "").strip()


def _configured_pg_stores(settings: Settings) -> list[str]:
    """Return PG store names that are configured for this settings object."""
    if not _pg_url(settings):
        return []
    stores: list[str] = []
    rl = getattr(settings.observability, "request_log", None)
    if getattr(rl, "backend", "jsonl") == "postgres":
        stores.append("postgres.request-log")
    if getattr(settings.server.virtual_keys, "backend", "sqlite") == "postgres":
        stores.append("postgres.virtual-keys")
    if getattr(settings.enterprise, "audit_backend", "sqlite") == "postgres":
        stores.append("postgres.audit")
    # When only the URL is set (common Helm default), still surface the
    # three core stores so migrate --dry-run is never silent about PG.
    if not stores:
        stores = list(PG_STORE_COLUMNS)
    return stores


def _inspect_pg_store(
    name: str,
    *,
    dsn: str,
    inspector: PgSchemaInspector,
) -> StoreNote:
    path = Path(f"postgres:{name.removeprefix('postgres.')}")
    expected_ver = PG_SCHEMA_VERSIONS.get(name, 1)
    if not inspector.reachable:
        detail = inspector.error or "unreachable"
        return StoreNote(
            name=name,
            path=path,
            status="error",
            notes=[f"postgres unreachable: {detail}"],
            pending=[f"schema v{expected_ver} unreachable"],
        )
    pending: list[str] = []
    for table, required in PG_STORE_COLUMNS.get(name, {}).items():
        cols = inspector.columns(table)
        if not cols:
            pending.append(f"{table}: create/migrate")
            continue
        for col in sorted(required):
            if col not in cols:
                pending.append(f"{table}.{col}")
    if pending:
        return StoreNote(
            name=name,
            path=path,
            status="pending",
            notes=[f"schema v{expected_ver} pending"],
            pending=pending,
        )
    return StoreNote(
        name=name,
        path=path,
        status="current",
        notes=[f"schema v{expected_ver} current"],
    )


def inspect_postgres_stores(
    settings: Settings,
    *,
    inspector: PgSchemaInspector | None = None,
) -> list[StoreNote]:
    """Inspect configured Postgres store schemas (#1655)."""
    dsn = _pg_url(settings)
    if not dsn:
        return []
    stores = _configured_pg_stores(settings)
    if not stores:
        return []
    probe = inspector if inspector is not None else LivePgInspector(dsn)
    return [_inspect_pg_store(name, dsn=dsn, inspector=probe) for name in stores]


def inspect_stores(
    settings: Settings,
    *,
    pg_inspector: PgSchemaInspector | None = None,
) -> list[StoreNote]:
    paths = store_paths(settings)
    notes: list[StoreNote] = []
    for name in ("ledger", "virtual-keys", "audit", "responses"):
        notes.append(_inspect_sqlite(name, paths[name]))
    notes.append(_inspect_mcp_tasks(paths["mcp-tasks"]))
    notes.extend(inspect_postgres_stores(settings, inspector=pg_inspector))
    return notes


def _open_postgres_stores(settings: Settings) -> None:
    """Open PG stores so CREATE TABLE IF NOT EXISTS + additive ALTERs run."""
    dsn = _pg_url(settings)
    if not dsn:
        return
    stores = set(_configured_pg_stores(settings))
    if "postgres.request-log" in stores:
        from daari.gateway.postgres_request_log import PostgresRequestLogStore

        PostgresRequestLogStore(dsn, enabled=True)
    if "postgres.audit" in stores:
        from daari.enterprise.postgres_audit import PostgresAuditLog

        PostgresAuditLog(dsn, enabled=True)
    if "postgres.virtual-keys" in stores:
        from daari.auth.postgres_virtual_keys import virtual_key_store_from_settings

        try:
            virtual_key_store_from_settings(settings)
        except Exception:  # noqa: BLE001 — migrate reports via re-inspect
            pass


def _apply_stores(
    settings: Settings,
    before: list[StoreNote],
    *,
    pg_inspector: PgSchemaInspector | None = None,
) -> list[StoreNote]:
    """Open each store so existing `_migrate` paths run; report what changed."""
    from daari.auth.virtual_keys import VirtualKeyStore
    from daari.enterprise.audit import AuditLog
    from daari.gateway.mcp_tasks import McpTaskStore
    from daari.gateway.response_store import ResponseStore
    from daari.observability.usage import UsageLedger

    paths = store_paths(settings)
    before_by = {n.name: n for n in before}

    UsageLedger(paths["ledger"], enabled=True)
    VirtualKeyStore(paths["virtual-keys"], enabled=True)
    AuditLog(paths["audit"], enabled=True)
    ResponseStore(paths["responses"])
    McpTaskStore(paths["mcp-tasks"])

    if pg_inspector is not None:
        for note in before:
            if note.name.startswith("postgres.") and note.pending:
                pg_inspector.apply_additive(note.name, list(note.pending))
    else:
        _open_postgres_stores(settings)
        dsn = _pg_url(settings)
        if dsn and not dsn.startswith("memory:"):
            live = LivePgInspector(dsn)
            for note in before:
                if note.name.startswith("postgres.") and note.pending and live.reachable:
                    live.apply_additive(note.name, list(note.pending))

    after = inspect_stores(settings, pg_inspector=pg_inspector)
    out: list[StoreNote] = []
    for note in after:
        prev = before_by.get(note.name)
        changed: list[str] = []
        if prev is not None and prev.pending and not note.pending:
            changed = list(prev.pending)
            status = "applied"
            notes = ["opened; _migrate applied"]
        elif note.status == "current":
            status = "current"
            notes = ["opened; already current"]
        else:
            status = note.status
            notes = list(note.notes)
            changed = list(note.pending)
        out.append(
            StoreNote(
                name=note.name,
                path=note.path,
                status=status,
                notes=notes,
                pending=list(note.pending),
                changed=changed,
            )
        )
    return out


def format_notes(notes: list[StoreNote], *, dry_run: bool) -> list[str]:
    lines: list[str] = []
    mode = "dry-run" if dry_run else "migrate"
    lines.append(f"daari migrate ({mode})")
    additive_ok = True
    for note in notes:
        detail = ", ".join(note.pending or note.changed or note.notes) or note.status
        lines.append(f"  {note.name}: {note.status} — {detail} ({note.path})")
        if not note.additive_safe:
            additive_ok = False
    if dry_run:
        if additive_ok:
            lines.append("additive-safe: ok (exit 0)")
        else:
            lines.append("additive-safe: no — fix errors above")
    else:
        changed = [n for n in notes if n.changed]
        if changed:
            lines.append(
                "changed: " + ", ".join(f"{n.name}[{'|'.join(n.changed)}]" for n in changed)
            )
        else:
            lines.append("changed: none")
    return lines


def run_migrate(
    settings: Settings,
    *,
    dry_run: bool = True,
    pg_inspector: PgSchemaInspector | None = None,
) -> list[str]:
    before = inspect_stores(settings, pg_inspector=pg_inspector)
    if dry_run:
        return format_notes(before, dry_run=True)
    after = _apply_stores(settings, before, pg_inspector=pg_inspector)
    return format_notes(after, dry_run=False)


def pending_migrate_summary(
    settings: Settings,
    *,
    pg_inspector: PgSchemaInspector | None = None,
) -> list[str]:
    pending: list[str] = []
    for note in inspect_stores(settings, pg_inspector=pg_inspector):
        if note.pending:
            pending.append(f"{note.name}: {', '.join(note.pending)}")
    return pending
