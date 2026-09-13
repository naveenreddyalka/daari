"""ResponseStore ownership for multi-tenant Responses API (#453)."""

from __future__ import annotations

import sqlite3

from daari.gateway.response_store import ResponseStore, response_visible_to_caller
from daari.server.auth import AuthClaims


def test_put_records_owner_and_get_returns_it(tmp_path):
    store = ResponseStore(tmp_path / "responses.sqlite3")
    store.put(
        "resp_owned",
        {"id": "resp_owned", "status": "completed", "output": []},
        conversation=[{"role": "user", "content": "hi"}],
        owner_key_id="vk_alice",
    )
    stored = store.get("resp_owned")
    assert stored is not None
    assert stored["_owner_key_id"] == "vk_alice"
    assert stored["_conversation"][0]["content"] == "hi"


def test_ownerless_rows_are_master_only_after_migration(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE responses ("
            "response_id TEXT PRIMARY KEY, body TEXT NOT NULL, "
            "conversation TEXT NOT NULL, stored INTEGER NOT NULL)"
        )
        conn.execute(
            "INSERT INTO responses VALUES (?, ?, ?, 1)",
            ("resp_old", '{"id":"resp_old","output":[]}', "[]"),
        )
    store = ResponseStore(path)
    stored = store.get("resp_old")
    assert stored is not None
    assert stored.get("_owner_key_id") in (None, "")
    vk = AuthClaims(kind="virtual", key_id="vk_1")
    master = AuthClaims(kind="master")
    assert response_visible_to_caller(stored, vk) is False
    assert response_visible_to_caller(stored, master) is True


def test_visible_to_caller_scopes_virtual_vs_master(tmp_path):
    store = ResponseStore(tmp_path / "r.sqlite3")
    store.put("resp_a", {"id": "resp_a", "output": []}, owner_key_id="vk_a")
    store.put("resp_b", {"id": "resp_b", "output": []}, owner_key_id="vk_b")
    store.put("resp_m", {"id": "resp_m", "output": []})
    a = store.get("resp_a")
    b = store.get("resp_b")
    m = store.get("resp_m")
    vk = AuthClaims(kind="virtual", key_id="vk_a")
    assert response_visible_to_caller(a, vk) is True
    assert response_visible_to_caller(b, vk) is False
    assert response_visible_to_caller(m, vk) is False
    assert response_visible_to_caller(a, AuthClaims(kind="master")) is True
    assert response_visible_to_caller(m, None) is True


def test_replace_preserves_owner_when_omitted(tmp_path):
    store = ResponseStore(tmp_path / "r.sqlite3")
    store.put("resp_x", {"id": "resp_x", "status": "queued"}, owner_key_id="vk_1")
    store.put("resp_x", {"id": "resp_x", "status": "completed", "output": []})
    assert store.get("resp_x")["_owner_key_id"] == "vk_1"
