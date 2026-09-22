"""Operator-facing store migrate dry-run / apply (issue #942).

SQLite stores still migrate on open via their `_migrate` helpers. This module
inspects the same additive column/table expectations without Alembic, and can
open each store explicitly so upgrades are loud and reportable.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
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


def inspect_stores(settings: Settings) -> list[StoreNote]:
    paths = store_paths(settings)
    notes: list[StoreNote] = []
    for name in ("ledger", "virtual-keys", "audit", "responses"):
        notes.append(_inspect_sqlite(name, paths[name]))
    notes.append(_inspect_mcp_tasks(paths["mcp-tasks"]))
    return notes


def _apply_stores(settings: Settings, before: list[StoreNote]) -> list[StoreNote]:
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

    after = inspect_stores(settings)
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


def run_migrate(settings: Settings, *, dry_run: bool = True) -> list[str]:
    before = inspect_stores(settings)
    if dry_run:
        return format_notes(before, dry_run=True)
    after = _apply_stores(settings, before)
    return format_notes(after, dry_run=False)


def pending_migrate_summary(settings: Settings) -> list[str]:
    pending: list[str] = []
    for note in inspect_stores(settings):
        if note.pending:
            pending.append(f"{note.name}: {', '.join(note.pending)}")
    return pending
