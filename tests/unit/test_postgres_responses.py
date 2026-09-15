"""Cross-replica Postgres Responses store (#481) — memory: fake, no live PG."""

from __future__ import annotations

import uuid

from daari.config.settings import Settings
from daari.gateway.postgres_responses import PostgresResponseStore
from daari.gateway.response_store import ResponseStore, response_visible_to_caller
from daari.gateway.responses import _store_for
from daari.router.router import AppContext


def _dsn() -> str:
    return f"memory:responses-{uuid.uuid4().hex}"


class _Claims:
    def __init__(self, *, kind: str, key_id: str | None = None) -> None:
        self.kind = kind
        self.key_id = key_id


class TestPostgresResponseStoreMemory:
    def test_put_get_across_replicas(self):
        dsn = _dsn()
        a = PostgresResponseStore(dsn)
        b = PostgresResponseStore(dsn)
        a.put(
            "resp_1",
            {"id": "resp_1", "status": "completed", "output": []},
            conversation=[{"role": "user", "content": "hi"}],
            owner_key_id="k1",
        )
        got = b.get("resp_1")
        assert got is not None
        assert got["id"] == "resp_1"
        assert got["_conversation"] == [{"role": "user", "content": "hi"}]
        assert got["_owner_key_id"] == "k1"
        assert response_visible_to_caller(got, _Claims(kind="virtual", key_id="k1"))
        assert not response_visible_to_caller(got, _Claims(kind="virtual", key_id="other"))

    def test_replace_preserves_owner_when_omitted(self):
        dsn = _dsn()
        a = PostgresResponseStore(dsn)
        b = PostgresResponseStore(dsn)
        a.put(
            "resp_bg",
            {"id": "resp_bg", "status": "queued"},
            conversation=[],
            owner_key_id="owner-a",
        )
        # Background poller on another replica omits owner_key_id.
        b.put(
            "resp_bg",
            {"id": "resp_bg", "status": "completed", "output": [{"type": "text"}]},
            conversation=[{"role": "assistant", "content": "done"}],
        )
        got = a.get("resp_bg")
        assert got is not None
        assert got["status"] == "completed"
        assert got["_owner_key_id"] == "owner-a"
        assert got["_conversation"][0]["content"] == "done"

    def test_previous_response_id_chain_visible_on_peer(self):
        dsn = _dsn()
        writer = PostgresResponseStore(dsn)
        reader = PostgresResponseStore(dsn)
        writer.put(
            "resp_prev",
            {"id": "resp_prev", "status": "completed"},
            conversation=[
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "ack"},
            ],
            owner_key_id="k1",
        )
        prev = reader.get("resp_prev")
        assert prev is not None
        chain = list(prev["_conversation"])
        chain.append({"role": "user", "content": "two"})
        writer.put(
            "resp_next",
            {"id": "resp_next", "status": "completed", "previous_response_id": "resp_prev"},
            conversation=chain,
            owner_key_id="k1",
        )
        nxt = reader.get("resp_next")
        assert nxt is not None
        assert nxt["previous_response_id"] == "resp_prev"
        assert [m["content"] for m in nxt["_conversation"]] == ["one", "ack", "two"]


def test_store_for_selects_postgres_when_configured(tmp_path):
    settings = Settings.model_validate(
        {
            "trace": {"path": str(tmp_path / "traces.sqlite3")},
            "observability": {"postgres_url": _dsn()},
            "responses": {"backend": "postgres"},
        }
    )
    ctx = AppContext.from_settings(settings)
    store = _store_for(ctx)
    assert isinstance(store, PostgresResponseStore)


def test_store_for_defaults_to_sqlite(tmp_path):
    settings = Settings.model_validate(
        {
            "trace": {"path": str(tmp_path / "traces.sqlite3")},
            "responses": {"backend": "sqlite"},
        }
    )
    ctx = AppContext.from_settings(settings)
    store = _store_for(ctx)
    assert isinstance(store, ResponseStore)


def test_postgres_response_import_error_message():
    store = PostgresResponseStore("postgresql://x", enabled=False)
    store.enabled = True
    store._memory = False
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "psycopg" or name.startswith("psycopg."):
            raise ImportError("nope")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        import pytest

        with pytest.raises(RuntimeError, match="psycopg"):
            store._connect()
    finally:
        builtins.__import__ = real_import
