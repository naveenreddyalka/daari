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


def test_doctor_reports_at_rest_per_store():
    settings = Settings()
    off = _check_at_rest_encryption(settings)
    assert off.name == "at_rest_encryption"
    assert off.ok
    assert "off" in off.detail.lower()
    settings.security.at_rest_key = "operator-key"
    on = _check_at_rest_encryption(settings)
    assert on.ok
    assert "on" in on.detail.lower()
    assert "response" in on.detail.lower()
    assert "request" in on.detail.lower()
    assert "cache" in on.detail.lower()
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
