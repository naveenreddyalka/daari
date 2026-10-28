"""Optional at-rest encryption for payload stores (#1958)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from daari.cache.exact import ExactCache
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.postgres_request_log import PostgresRequestLogStore
from daari.gateway.postgres_responses import PostgresResponseStore
from daari.gateway.request_log import configure_request_log, log_gateway_event
from daari.gateway.response_store import ResponseStore
from daari.security.at_rest import (
    AtRestCipher,
    AtRestDecryptError,
    configure_at_rest,
    is_sealed,
    open_text,
    reset_at_rest,
    seal_text,
)
from daari.setup.doctor import _check_at_rest_encryption, run_doctor


def _resp(content: str, model: str = "m") -> InternalResponse:
    return InternalResponse(
        content=content,
        model=model,
        daari_meta=DaariMeta(tier="L0", executor="cache"),
    )


@pytest.fixture(autouse=True)
def _reset_cipher():
    reset_at_rest()
    yield
    reset_at_rest()


def test_settings_at_rest_defaults_opt_in():
    s = Settings()
    assert s.security.at_rest_key == ""
    assert s.security.at_rest_key_previous == ""


def test_round_trip_and_tag():
    cipher = AtRestCipher(key="test-key-one")
    sealed = cipher.encrypt("hello payload")
    assert is_sealed(sealed)
    assert "hello payload" not in sealed
    assert cipher.decrypt(sealed) == "hello payload"


def test_plaintext_passthrough_when_unset():
    assert seal_text("plain") == "plain"
    assert open_text("plain") == "plain"
    assert open_text('{"a":1}') == '{"a":1}'


def test_rotation_reads_with_previous_key():
    old = AtRestCipher(key="old-key")
    sealed = old.encrypt("rotate-me")
    configure_at_rest(key="new-key", previous_key="old-key")
    assert open_text(sealed) == "rotate-me"
    # New writes use current key.
    fresh = seal_text("fresh")
    assert AtRestCipher(key="new-key").decrypt(fresh) == "fresh"
    with pytest.raises(AtRestDecryptError):
        AtRestCipher(key="old-key").decrypt(fresh)


def test_wrong_key_fails_closed():
    sealed = AtRestCipher(key="right").encrypt("secret")
    with pytest.raises(AtRestDecryptError, match="decrypt"):
        AtRestCipher(key="wrong").decrypt(sealed)
    configure_at_rest(key="wrong")
    with pytest.raises(AtRestDecryptError):
        open_text(sealed)
    # Never return ciphertext.
    try:
        open_text(sealed)
    except AtRestDecryptError as exc:
        assert "daari-atr1:" not in str(exc)
        assert sealed not in str(exc)


def test_missing_key_on_tagged_row_fails_closed():
    sealed = AtRestCipher(key="k").encrypt("x")
    reset_at_rest()
    with pytest.raises(AtRestDecryptError, match="at_rest_key"):
        open_text(sealed)


def test_response_store_sqlite_round_trip_and_plaintext_compat(tmp_path: Path):
    store = ResponseStore(tmp_path / "responses.sqlite3")
    store.put("r-plain", {"id": "r-plain", "output": "open"}, conversation=[{"role": "user"}])
    configure_at_rest(key="store-key")
    store.put("r-enc", {"id": "r-enc", "output": "closed"}, conversation=[{"role": "user"}])

    # Raw DB: encrypted row is tagged; plaintext row is not.
    import sqlite3

    with sqlite3.connect(store.path) as conn:
        rows = {
            rid: body
            for rid, body in conn.execute("SELECT response_id, body FROM responses")
        }
    assert not is_sealed(rows["r-plain"])
    assert is_sealed(rows["r-enc"])
    assert "closed" not in rows["r-enc"]

    got_plain = store.get("r-plain")
    assert got_plain is not None
    assert got_plain["output"] == "open"
    got_enc = store.get("r-enc")
    assert got_enc is not None
    assert got_enc["output"] == "closed"
    assert got_enc["_conversation"] == [{"role": "user"}]


def test_response_store_postgres_memory_round_trip():
    dsn = f"memory:atr-{uuid.uuid4().hex}"
    configure_at_rest(key="pg-key")
    store = PostgresResponseStore(dsn)
    store.put("pg1", {"id": "pg1", "text": "hidden"}, conversation=[])
    from daari.gateway import postgres_responses as pr

    raw_bucket, lock = pr._memory_bucket(dsn)
    with lock:
        raw_body = raw_bucket["pg1"]["body"]
    assert is_sealed(raw_body)
    assert "hidden" not in raw_body
    got = store.get("pg1")
    assert got is not None
    assert got["text"] == "hidden"


def test_response_store_postgres_plaintext_compat():
    dsn = f"memory:atr-plain-{uuid.uuid4().hex}"
    store = PostgresResponseStore(dsn)
    store.put("old", {"id": "old", "text": "legacy"}, conversation=[])
    configure_at_rest(key="later")
    got = store.get("old")
    assert got is not None
    assert got["text"] == "legacy"


def test_exact_cache_encrypts_disk_values(tmp_path: Path):
    configure_at_rest(key="cache-key")
    cache = ExactCache(str(tmp_path / "l0"), enabled=True)
    req = InternalRequest(messages=[Message(role="user", content="hi")], model="m")
    resp = _resp("cached-secret")
    cache.put(req, resp)
    # Peek raw diskcache entry.
    raw = cache._store().get(list(cache._store().iterkeys())[0])
    value = raw["v"] if isinstance(raw, dict) else raw
    assert is_sealed(value)
    assert "cached-secret" not in value
    hit = cache.get(req)
    assert hit is not None
    assert hit.content == "cached-secret"


def test_exact_cache_plaintext_compat(tmp_path: Path):
    cache = ExactCache(str(tmp_path / "l0"), enabled=True)
    req = InternalRequest(messages=[Message(role="user", content="q")], model="m")
    cache.put(req, _resp("legacy"))
    configure_at_rest(key="after")
    hit = cache.get(req)
    assert hit is not None
    assert hit.content == "legacy"


def test_request_log_jsonl_encrypts_payload(tmp_path: Path):
    log_path = tmp_path / "events.log"
    configure_request_log(path=log_path, backend="jsonl", max_bytes=0)
    configure_at_rest(key="log-key")
    log_gateway_event("route", {"prompt": "secret-prompt", "tier": "L3"})
    text = log_path.read_text(encoding="utf-8")
    assert "secret-prompt" not in text
    assert "daari-atr1:" in text
    # Doctor/read helpers decrypt for subject match via open on parse.
    line = text.strip().splitlines()[-1]
    record = json.loads(line)
    assert record["event"] == "route"
    body = open_text(record["_enc"])
    payload = json.loads(body)
    assert payload["prompt"] == "secret-prompt"


def test_request_log_postgres_encrypts_payload():
    dsn = f"memory:atr-log-{uuid.uuid4().hex}"
    configure_at_rest(key="pg-log")
    store = PostgresRequestLogStore(dsn)
    store.append("chat", {"prompt": "hidden-log"})
    rows = store.list_events()
    assert len(rows) == 1
    assert rows[0]["payload"]["prompt"] == "hidden-log"
    # Raw memory keeps sealed string when encryption was on at append.
    from daari.gateway import postgres_request_log as prl

    bucket, lock = prl._memory_bucket(dsn)
    with lock:
        raw = bucket[0]["payload"]
    assert isinstance(raw, str) and is_sealed(raw)


def test_files_store_disk_round_trip_and_plaintext_compat(tmp_path: Path):
    from daari.gateway.files import FileStore

    store = FileStore(tmp_path / "files")
    plain = store.create(content=b"legacy-upload", filename="a.txt")
    configure_at_rest(key="files-key")
    enc = store.create(content=b"secret-bytes\x00\xff", filename="b.bin")

    raw_plain = (tmp_path / "files" / f"{plain.id}.bin").read_bytes()
    raw_enc = (tmp_path / "files" / f"{enc.id}.bin").read_bytes()
    assert raw_plain == b"legacy-upload"
    assert is_sealed(raw_enc.decode("ascii"))
    assert b"secret-bytes" not in raw_enc

    assert store.read_bytes(plain.id) == b"legacy-upload"
    assert store.read_bytes(enc.id) == b"secret-bytes\x00\xff"


def test_files_store_wrong_key_fails_closed(tmp_path: Path):
    from daari.gateway.files import FileStore

    configure_at_rest(key="right-files")
    store = FileStore(tmp_path / "files")
    stored = store.create(content=b"locked", filename="x.bin")
    configure_at_rest(key="wrong-files")
    with pytest.raises(AtRestDecryptError):
        store.read_bytes(stored.id)


def test_files_store_postgres_memory_round_trip():
    from daari.gateway import postgres_files as pf
    from daari.gateway.postgres_files import PostgresFileStore

    dsn = f"memory:atr-files-{uuid.uuid4().hex}"
    configure_at_rest(key="pg-files")
    store = PostgresFileStore(dsn)
    stored = store.create(content=b"hidden-file", filename="h.bin")
    bucket, lock = pf._memory_bucket(dsn)
    with lock:
        raw = bucket[stored.id]["content"]
    assert isinstance(raw, (bytes, bytearray))
    assert is_sealed(bytes(raw).decode("ascii"))
    assert b"hidden-file" not in bytes(raw)
    assert store.read_bytes(stored.id) == b"hidden-file"


def test_files_store_postgres_plaintext_compat():
    from daari.gateway.postgres_files import PostgresFileStore

    dsn = f"memory:atr-files-plain-{uuid.uuid4().hex}"
    store = PostgresFileStore(dsn)
    stored = store.create(content=b"old-file", filename="old.bin")
    configure_at_rest(key="later-files")
    assert store.read_bytes(stored.id) == b"old-file"


def test_batches_store_sqlite_round_trip_and_plaintext_compat(tmp_path: Path):
    from daari.gateway.batches import BatchStore

    db = tmp_path / "batches.sqlite3"
    store = BatchStore(path=db)
    plain = store.create(
        requests=[{"model": "m", "messages": [{"role": "user", "content": "hi"}]}]
    )
    configure_at_rest(key="batch-key")
    enc = store.create(
        requests=[
            {"model": "m", "messages": [{"role": "user", "content": "secret-batch"}]}
        ]
    )

    import sqlite3

    with sqlite3.connect(db) as conn:
        rows = {
            rid: body for rid, body in conn.execute("SELECT id, payload FROM batch_jobs")
        }
    assert not is_sealed(rows[plain.id])
    assert "hi" in rows[plain.id]
    assert is_sealed(rows[enc.id])
    assert "secret-batch" not in rows[enc.id]

    got_plain = store.get(plain.id)
    assert got_plain is not None
    assert got_plain.items[0].body["messages"][0]["content"] == "hi"
    store2 = BatchStore(path=db)
    got_enc = store2.get(enc.id)
    assert got_enc is not None
    assert got_enc.items[0].body["messages"][0]["content"] == "secret-batch"


def test_batches_store_wrong_key_fails_closed(tmp_path: Path):
    from daari.gateway.batches import BatchStore

    configure_at_rest(key="right-batch")
    store = BatchStore(path=tmp_path / "batches.sqlite3")
    store.create(
        requests=[{"model": "m", "messages": [{"role": "user", "content": "x"}]}]
    )
    configure_at_rest(key="wrong-batch")
    with pytest.raises(AtRestDecryptError):
        BatchStore(path=tmp_path / "batches.sqlite3")


def test_batches_store_postgres_memory_round_trip():
    from daari.gateway import postgres_batches as pb
    from daari.gateway.postgres_batches import PostgresBatchStore

    dsn = f"memory:atr-batches-{uuid.uuid4().hex}"
    configure_at_rest(key="pg-batch")
    store = PostgresBatchStore(dsn)
    job = store.create(
        requests=[
            {"model": "m", "messages": [{"role": "user", "content": "hidden-batch"}]}
        ]
    )
    bucket, _order, lock = pb._memory_bucket(dsn)
    with lock:
        raw = bucket[job.id]["payload"]
    assert is_sealed(raw)
    assert "hidden-batch" not in raw
    got = store.get(job.id)
    assert got is not None
    assert got.items[0].body["messages"][0]["content"] == "hidden-batch"


def test_doctor_reports_at_rest_per_store():
    settings = Settings()
    off = _check_at_rest_encryption(settings)
    assert off.name == "at_rest_encryption"
    assert off.ok
    assert "off" in off.detail.lower()
    assert "file" in off.detail.lower()
    assert "batch" in off.detail.lower()
    settings.security.at_rest_key = "operator-key"
    on = _check_at_rest_encryption(settings)
    assert on.ok
    assert "on" in on.detail.lower()
    assert "response" in on.detail.lower()
    assert "request" in on.detail.lower()
    assert "cache" in on.detail.lower()
    assert "file" in on.detail.lower()
    assert "batch" in on.detail.lower()
    names = {r.name for r in run_doctor(settings, httpx_client=None)}
    assert "at_rest_encryption" in names


def test_docs_cover_setup_and_rotation():
    root = Path(__file__).resolve().parents[2]
    doc = root / "docs" / "developer" / "resources" / "at-rest-encryption.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "security.at_rest_key" in text
    assert "at_rest_key_previous" in text
    assert "secret://" in text
    assert "rotation" in text.lower()
    assert "file" in text.lower()
    assert "batch" in text.lower()
