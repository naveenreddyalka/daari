"""End-user spend attribution and per-user caps (issue #410)."""

from __future__ import annotations

from pathlib import Path

from daari.auth.budgets import user_cap_error, user_daily_cap_exceeded
from daari.auth.virtual_keys import VirtualKey, VirtualKeyStore
from daari.observability.usage import UsageLedger


def test_record_attributes_usage_to_user(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    ledger.record(tier="L3", client_id="key-a", user_id="alice", prompt_chars=40)
    ledger.record(tier="L3", client_id="key-a", user_id="alice", prompt_chars=40)
    ledger.record(tier="L6", client_id="key-a", user_id="bob", input_tokens=500)

    users = {((u["client_id"], u["user_id"])): u for u in ledger.by_user(days=1)}
    assert users[("key-a", "alice")]["requests"] == 2
    assert users[("key-a", "alice")]["local_requests"] == 2
    assert users[("key-a", "bob")]["frontier_requests"] == 1


def test_missing_user_attributes_to_unknown(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    ledger.record(tier="L3", client_id="key-a", prompt_chars=20)
    users = ledger.by_user(days=1)
    assert len(users) == 1
    assert users[0]["user_id"] == "unknown"
    assert users[0]["client_id"] == "key-a"


def test_frontier_spend_for_user_is_isolated(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    ledger.record(tier="L6", client_id="key-a", user_id="alice", input_tokens=1000)
    ledger.record(tier="L6", client_id="key-a", user_id="bob", input_tokens=500)
    # 1000 tokens @ $0.002/1k = $0.002
    assert ledger.frontier_spend_usd_for_user("key-a", "alice") == 0.002
    assert ledger.frontier_spend_usd_for_user("key-a", "bob") == 0.001
    assert ledger.frontier_spend_usd_for_user("key-a", "carol") == 0.0


def test_user_cap_exceeded_only_for_named_users(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    key = VirtualKey(
        key_id="k1",
        name="agent",
        prefix="dk_x",
        client_id="key-a",
        user_daily_usd_cap=0.002,
    )
    ledger.record(tier="L6", client_id="key-a", user_id="alice", input_tokens=1000)
    assert user_daily_cap_exceeded(key, ledger, client_id="key-a", user_id="alice") is not None
    assert user_daily_cap_exceeded(key, ledger, client_id="key-a", user_id="bob") is None
    assert user_daily_cap_exceeded(key, ledger, client_id="key-a", user_id=None) is None
    assert user_daily_cap_exceeded(key, ledger, client_id="key-a", user_id="") is None


def test_user_cap_error_matches_budget_shape():
    key = VirtualKey(
        key_id="k1",
        name="agent",
        prefix="dk_x",
        client_id="key-a",
        user_daily_usd_cap=1.0,
    )
    body = user_cap_error(client_id="key-a", user_id="alice", spend=1.5, cap_usd=1.0)
    assert body["type"] == "budget_exceeded"
    assert body["scope"] == "user"
    assert body["window"] == "daily"
    assert body["user_id"] == "alice"
    assert body["client_id"] == "key-a"
    assert body["budget_usd"] == 1.0
    assert "reset_at" in body
    # unused but documents the key carries the cap
    assert key.user_daily_usd_cap == 1.0


def test_virtual_key_persists_user_daily_cap(tmp_path: Path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    created = store.create("agent", client_id="key-a", user_daily_usd_cap=2.5)
    assert created.key.user_daily_usd_cap == 2.5
    resolved = store.resolve(created.plaintext)
    assert resolved is not None
    assert resolved.user_daily_usd_cap == 2.5
    listed = store.list()
    assert listed[0].user_daily_usd_cap == 2.5
    payload = store.to_dict(listed[0])
    assert payload["user_daily_usd_cap"] == 2.5


def test_old_virtual_key_db_migrates_user_cap_column(tmp_path: Path):
    """Pre-#410 stores lack user_daily_usd_cap; ALTER adds it with default 0."""
    import sqlite3

    path = tmp_path / "vk.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE virtual_keys (
            key_hash TEXT PRIMARY KEY,
            key_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            prefix TEXT NOT NULL,
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            expires_at TEXT,
            daily_budget_usd REAL NOT NULL DEFAULT 0,
            monthly_budget_usd REAL NOT NULL DEFAULT 0,
            rpm INTEGER NOT NULL DEFAULT 0,
            tpm INTEGER NOT NULL DEFAULT 0,
            tier_cap TEXT,
            client_id TEXT,
            team_id TEXT,
            budget_windows_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE teams (team_id TEXT PRIMARY KEY, name TEXT NOT NULL,
            budget_windows_json TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE key_hits (key_id TEXT NOT NULL, ts REAL NOT NULL);
        """
    )
    conn.execute(
        "INSERT INTO virtual_keys (key_hash, key_id, name, prefix, created_at,"
        " daily_budget_usd, monthly_budget_usd, rpm, tpm)"
        " VALUES ('h', 'kid', 'n', 'dk_x', '2026-01-01T00:00:00+00:00', 0, 0, 0, 0)"
    )
    conn.commit()
    conn.close()

    store = VirtualKeyStore(path)
    keys = store.list()
    assert len(keys) == 1
    assert keys[0].user_daily_usd_cap == 0.0


def test_prune_includes_user_usage(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    ledger.record(tier="L3", client_id="key-a", user_id="alice", day="2020-01-01")
    deleted = ledger.prune_before_day("2020-01-02")
    assert deleted >= 1
    assert ledger.by_user(days=3650) == []
