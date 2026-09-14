"""Cross-replica Postgres batches/files (#465) — memory: fake, no live PG."""

from __future__ import annotations

import time
import uuid

import pytest

from daari.gateway.postgres_batches import PostgresBatchStore, _MEMORY_BATCHES
from daari.gateway.postgres_files import PostgresFileStore
from daari.gateway.batches import BatchStore
from daari.gateway.files import FileStore
from daari.router.router import AppContext


def _dsn() -> str:
    return f"memory:test-{uuid.uuid4().hex}"


class TestPostgresFileStoreMemory:
    def test_create_visible_on_second_replica(self):
        dsn = _dsn()
        a = PostgresFileStore(dsn)
        b = PostgresFileStore(dsn)
        stored = a.create(content=b"hello", filename="a.jsonl", purpose="batch", owner_key_id="k1")
        got = b.get(stored.id)
        assert got is not None
        assert got.owner_key_id == "k1"
        assert b.read_bytes(stored.id) == b"hello"
        assert b.read_text(stored.id) == "hello"

    def test_expiry_and_prune(self):
        dsn = _dsn()
        store = PostgresFileStore(dsn, retention_days=0)
        stored = store.create(
            content=b"x",
            filename="x",
            purpose="batch",
            expires_after_seconds=1,
        )
        assert store.get(stored.id, now=stored.created_at) is not None
        assert store.get(stored.id, now=stored.created_at + 2) is None
        again = store.create(
            content=b"y",
            filename="y",
            purpose="batch",
            expires_after_seconds=1,
        )
        assert store.prune_expired(now=again.created_at + 5) == 1


class TestPostgresBatchStoreMemory:
    def test_create_get_cancel_across_replicas(self):
        dsn = _dsn()
        a = PostgresBatchStore(dsn, worker_id="a")
        b = PostgresBatchStore(dsn, worker_id="b")
        job = a.create(
            requests=[{"messages": [{"role": "user", "content": "hi"}]}],
        )
        remote = b.get(job.id)
        assert remote is not None
        assert remote.status == "validating"
        cancelled = b.cancel(job.id)
        assert cancelled is not None
        assert cancelled.status == "cancelled"
        assert a.get(job.id).status == "cancelled"

    def test_only_one_replica_claims(self):
        dsn = _dsn()
        a = PostgresBatchStore(dsn, worker_id="a", claim_ttl_seconds=60)
        b = PostgresBatchStore(dsn, worker_id="b", claim_ttl_seconds=60)
        job = a.create(
            requests=[{"messages": [{"role": "user", "content": "hi"}]}],
        )
        assert a._try_claim(job.id) is True
        assert b._try_claim(job.id) is False
        a._release_claim(job.id)
        assert b._try_claim(job.id) is True

    def test_stale_claim_reclaimed(self):
        dsn = _dsn()
        a = PostgresBatchStore(dsn, worker_id="a", claim_ttl_seconds=5)
        b = PostgresBatchStore(dsn, worker_id="b", claim_ttl_seconds=5)
        job = a.create(
            requests=[{"messages": [{"role": "user", "content": "hi"}]}],
        )
        assert a._try_claim(job.id) is True
        bucket = _MEMORY_BATCHES[dsn]
        bucket[job.id]["claimed_at"] = int(time.time()) - 30
        assert b._try_claim(job.id) is True

    @pytest.mark.asyncio
    async def test_drain_runs_once(self):
        dsn = _dsn()
        store = PostgresBatchStore(dsn, worker_id="w1", yield_to_interactive=False)
        job = store.create(
            requests=[
                {"custom_id": "1", "body": {"messages": [{"role": "user", "content": "a"}]}},
                {"custom_id": "2", "body": {"messages": [{"role": "user", "content": "b"}]}},
            ],
        )
        calls: list[str] = []

        async def execute_one(body: dict) -> dict:
            calls.append(body["messages"][0]["content"])
            return {"ok": True}

        await store.run_job(job.id, execute_one)
        assert calls == ["a", "b"]
        done = store.get(job.id)
        assert done is not None
        assert done.status == "completed"


def test_appcontext_selects_postgres_types(settings):
    settings.files.backend = "postgres"
    settings.batches.backend = "postgres"
    settings.observability.postgres_url = "postgresql://localhost/daari"
    ctx = AppContext.from_settings(settings)
    from daari.gateway.postgres_batches import PostgresBatchStore as PBS
    from daari.gateway.postgres_files import PostgresFileStore as PFS

    assert isinstance(ctx.file_store, PFS)
    assert isinstance(ctx.batch_store, PBS)


def test_appcontext_default_remains_sqlite(settings, tmp_path):
    settings.files.path = str(tmp_path / "files")
    settings.batches.path = str(tmp_path / "batches.sqlite3")
    settings.files.backend = "sqlite"
    settings.batches.backend = "sqlite"
    ctx = AppContext.from_settings(settings)
    assert isinstance(ctx.file_store, FileStore)
    assert isinstance(ctx.batch_store, BatchStore)


def test_postgres_batch_import_error_message():
    store = PostgresBatchStore("postgresql://x", enabled=False)
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
        with pytest.raises(RuntimeError, match="psycopg"):
            store._pg_connect()
    finally:
        builtins.__import__ = real_import


def test_postgres_file_import_error_message():
    store = PostgresFileStore("postgresql://x", enabled=False)
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
        with pytest.raises(RuntimeError, match="psycopg"):
            store._connect()
    finally:
        builtins.__import__ = real_import
