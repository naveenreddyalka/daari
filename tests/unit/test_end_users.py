"""End-user registry: overrides store, enforcement helper, inventory, CLI (#1547)."""

from __future__ import annotations

import uuid

import pytest
from typer.testing import CliRunner

from daari.auth.end_users import EndUserOverride, end_user_blocked_error, end_user_denial
from daari.auth.postgres_virtual_keys import PostgresVirtualKeyStore
from daari.auth.virtual_keys import VirtualKeyStore
from daari.gateway.admin_read import end_users_inventory
from daari.observability.usage import UsageLedger


@pytest.fixture(params=["sqlite", "postgres-memory"])
def store(request, tmp_path):
    if request.param == "sqlite":
        return VirtualKeyStore(tmp_path / "vk.sqlite3")
    return PostgresVirtualKeyStore(f"memory:end-users-{uuid.uuid4().hex}")


def _spend(ledger: UsageLedger, client_id: str, user_id: str, usd: float, *, day=None) -> None:
    ledger.record(
        tier="L6",
        client_id=client_id,
        user_id=user_id,
        model="",
        input_tokens=int(usd / 0.002 * 1000),
        day=day,
    )


def test_store_block_cap_roundtrip(store):
    assert store.get_end_user("alice") is None
    assert store.list_end_users() == []

    blocked = store.set_end_user_blocked("alice", True, reason="abuse")
    assert isinstance(blocked, EndUserOverride)
    assert blocked.user_id == "alice"
    assert blocked.blocked is True
    assert blocked.reason == "abuse"
    assert blocked.user_usd_cap == 0.0
    assert blocked.updated_at

    capped = store.set_end_user_cap("alice", 2.5)
    assert capped.blocked is True, "cap update must not clear the block"
    assert capped.user_usd_cap == 2.5

    fetched = store.get_end_user("alice")
    assert fetched == capped
    assert [row.user_id for row in store.list_end_users()] == ["alice"]

    unblocked = store.set_end_user_blocked("alice", False)
    assert unblocked.blocked is False
    assert unblocked.reason is None
    assert unblocked.user_usd_cap == 2.5

    assert store.set_end_user_cap("alice", 0).user_usd_cap == 0.0
    assert store.delete_end_user("alice") is True
    assert store.delete_end_user("alice") is False
    assert store.get_end_user("alice") is None


def test_store_rejects_blank_user_and_negative_cap(store):
    with pytest.raises(ValueError):
        store.set_end_user_blocked("  ", True)
    with pytest.raises(ValueError):
        store.set_end_user_cap("alice", -1)
    assert store.get_end_user("") is None


def test_store_schema_is_additive_on_existing_db(tmp_path):
    """A pre-#1547 store opens cleanly and gains the overrides table."""
    import sqlite3

    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "CREATE TABLE virtual_keys (key_hash TEXT PRIMARY KEY, key_id TEXT NOT NULL UNIQUE,"
            " name TEXT NOT NULL, prefix TEXT NOT NULL, created_at TEXT NOT NULL, revoked_at TEXT,"
            " daily_budget_usd REAL NOT NULL DEFAULT 0, monthly_budget_usd REAL NOT NULL DEFAULT 0,"
            " rpm INTEGER NOT NULL DEFAULT 0, tier_cap TEXT, client_id TEXT);"
            "CREATE TABLE teams (team_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,"
            " budget_windows_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL);"
        )
    store = VirtualKeyStore(path)
    assert store.enabled
    assert store.set_end_user_blocked("x", True).blocked is True
    with sqlite3.connect(path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "end_user_overrides" in tables


def test_blocked_error_shape():
    err = end_user_blocked_error("mallory", reason="offboarded")
    assert err["type"] == "end_user_blocked"
    assert err["code"] == "end_user_blocked"
    assert err["user_id"] == "mallory"
    assert err["reason"] == "offboarded"
    assert "mallory" in err["message"]
    assert "reason" not in end_user_blocked_error("m")


def test_denial_blocked_then_cap_override_then_key_cap(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    key = store.create("shared", client_id="key-a", user_daily_usd_cap=1.0).key

    assert end_user_denial(store, ledger, key=key, client_id="key-a", user_id="") is None
    assert end_user_denial(store, ledger, key=key, client_id="key-a", user_id="alice") is None

    # Key cap ($1) still applies when there is no override.
    _spend(ledger, "key-a", "alice", 1.0)
    status, body = end_user_denial(store, ledger, key=key, client_id="key-a", user_id="alice")
    assert status == 402
    assert body["scope"] == "user" and body["budget_usd"] == 1.0

    # Override raises the cap above the key cap: request passes.
    store.set_end_user_cap("alice", 3.0)
    assert end_user_denial(store, ledger, key=key, client_id="key-a", user_id="alice") is None

    # Override cap is cross-key: spend on key-b counts toward alice's cap.
    _spend(ledger, "key-b", "alice", 2.0)
    status, body = end_user_denial(store, ledger, key=key, client_id="key-a", user_id="alice")
    assert status == 402
    assert body["budget_usd"] == 3.0 and body["spend_usd"] == pytest.approx(3.0)

    # Block wins over everything, and applies even without a virtual key.
    store.set_end_user_blocked("alice", True, reason="abuse")
    status, body = end_user_denial(store, ledger, key=key, client_id="key-a", user_id="alice")
    assert status == 403 and body["type"] == "end_user_blocked"
    status, body = end_user_denial(store, ledger, key=None, client_id="", user_id="alice")
    assert status == 403

    # Cap override alone (no key) is enforced too.
    store.set_end_user_blocked("alice", False)
    status, _body = end_user_denial(store, ledger, key=None, client_id="", user_id="alice")
    assert status == 402

    # No store / no ledger / disabled store: fail open.
    assert end_user_denial(None, ledger, key=key, client_id="key-a", user_id="bob") is None
    assert end_user_denial(store, None, key=key, client_id="key-a", user_id="bob") is None


def test_denial_override_keeps_key_lifetime_cap(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    key = store.create(
        "shared",
        client_id="key-a",
        user_daily_usd_cap=0.5,
        metadata={"user_lifetime_usd_cap": 1.0},
    ).key
    store.set_end_user_cap("alice", 10.0)
    _spend(ledger, "key-a", "alice", 0.6, day="2020-01-01")
    _spend(ledger, "key-a", "alice", 0.6)
    status, body = end_user_denial(store, ledger, key=key, client_id="key-a", user_id="alice")
    assert status == 402
    assert body["window"] == "lifetime"


def test_ledger_end_users_and_cross_key_spend(tmp_path):
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    _spend(ledger, "key-a", "alice", 0.5, day="2026-01-01")
    _spend(ledger, "key-b", "alice", 0.25)
    ledger.record(tier="L3", client_id="key-a", user_id="bob", prompt_chars=40)
    ledger.record(tier="L3", client_id="key-a", prompt_chars=40)

    rows = {row["user_id"]: row for row in ledger.end_users()}
    assert set(rows) == {"alice", "bob"}, "unattributed rows never become end-users"
    alice = rows["alice"]
    assert alice["requests"] == 2
    assert alice["frontier_requests"] == 2
    assert alice["first_seen"] == "2026-01-01"
    assert alice["last_seen"] >= alice["first_seen"]
    assert sorted(alice["client_ids"]) == ["key-a", "key-b"]
    assert alice["spend"]["today_usd"] == pytest.approx(0.25)
    assert alice["spend"]["lifetime_usd"] == pytest.approx(0.75)
    assert rows["bob"]["local_requests"] == 1
    assert rows["bob"]["spend"]["lifetime_usd"] == 0.0

    assert ledger.frontier_spend_usd_for_end_user("alice") == pytest.approx(0.25)
    assert ledger.frontier_spend_usd_for_end_user("alice", window="lifetime") == pytest.approx(
        0.75
    )
    assert ledger.frontier_spend_usd_for_end_user("") == 0.0

    disabled = UsageLedger(tmp_path / "off.sqlite3", enabled=False)
    assert disabled.end_users() == []
    assert disabled.frontier_spend_usd_for_end_user("alice") == 0.0


def test_inventory_pagination_and_override_merge(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    for name in ("u1", "u2", "u3"):
        ledger.record(tier="L3", client_id="key-a", user_id=name, prompt_chars=4)
    store.set_end_user_blocked("u2", True, reason="x")
    store.set_end_user_cap("ghost", 1.0)

    page = end_users_inventory(store, ledger=ledger, limit=2, offset=0)
    assert page["total"] == 4
    assert page["has_more"] is True
    assert len(page["users"]) == 2
    tail = end_users_inventory(store, ledger=ledger, limit=2, offset=2)
    assert tail["has_more"] is False
    ids = [row["user_id"] for row in page["users"] + tail["users"]]
    assert ids == sorted(ids), "stable user_id ordering across pages"
    rows = {row["user_id"]: row for row in page["users"] + tail["users"]}
    assert rows["u2"]["blocked"] is True and rows["u2"]["reason"] == "x"
    assert rows["ghost"]["requests"] == 0 and rows["ghost"]["user_usd_cap"] == 1.0
    assert rows["ghost"]["first_seen"] is None
    assert rows["u1"]["blocked"] is False and rows["u1"]["user_usd_cap"] == 0.0

    blocked = end_users_inventory(store, ledger=ledger, blocked=True)
    assert [row["user_id"] for row in blocked["users"]] == ["u2"]
    assert blocked["total"] == 1
    one = end_users_inventory(store, ledger=ledger, user_id="ghost")
    assert [row["user_id"] for row in one["users"]] == ["ghost"]

    empty = end_users_inventory(None, ledger=None)
    assert empty == {"users": [], "total": 0, "limit": 100, "offset": 0, "has_more": False}


def test_cli_users_list_block_cap(settings, tmp_path, monkeypatch):
    from daari.cli import app as cli_app
    from daari.enterprise.audit import AuditLog

    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    monkeypatch.setattr(cli_app, "get_settings", lambda: settings)
    monkeypatch.setenv("USER", "ops-cli")
    ledger = UsageLedger(settings.usage.path)
    _spend(ledger, "key-a", "alice", 0.5)

    runner = CliRunner()
    empty = runner.invoke(cli_app.app, ["users", "list"])
    assert empty.exit_code == 0, empty.output
    assert "alice" in empty.output

    block = runner.invoke(cli_app.app, ["users", "block", "mallory", "--reason", "offboarded"])
    assert block.exit_code == 0, block.output
    assert "blocked" in block.output

    cap = runner.invoke(cli_app.app, ["users", "cap", "alice", "--daily-usd", "1.5"])
    assert cap.exit_code == 0, cap.output
    assert "1.5" in cap.output

    bad = runner.invoke(cli_app.app, ["users", "cap", "alice", "--daily-usd", "-1"])
    assert bad.exit_code != 0

    listed = runner.invoke(cli_app.app, ["users", "list"])
    assert listed.exit_code == 0, listed.output
    assert "mallory" in listed.output and "alice" in listed.output
    assert "0.50" in listed.output

    only_blocked = runner.invoke(cli_app.app, ["users", "list", "--blocked"])
    assert only_blocked.exit_code == 0
    assert "mallory" in only_blocked.output and "alice" not in only_blocked.output

    unblock = runner.invoke(cli_app.app, ["users", "unblock", "mallory"])
    assert unblock.exit_code == 0, unblock.output

    store = VirtualKeyStore(settings.virtual_keys_path)
    assert store.get_end_user("mallory").blocked is False
    assert store.get_end_user("alice").user_usd_cap == 1.5

    actions = [row["action"] for row in AuditLog(settings.enterprise.audit_path).list(limit=20)]
    assert "users.block" in actions
    assert "users.unblock" in actions
    assert "users.cap" in actions
    row = AuditLog(settings.enterprise.audit_path).list(limit=5, action="users.block")[0]
    assert row["actor"] == "ops-cli"
    assert row["detail"]["user_id"] == "mallory"
    assert row["detail"]["reason"] == "offboarded"
