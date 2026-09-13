"""OpenAI Files API store (#442)."""

from __future__ import annotations

import json

import pytest

from daari.gateway.files import FileStore, parse_batch_jsonl


def test_create_list_get_delete(tmp_path):
    store = FileStore(tmp_path / "files", max_bytes=1024)
    stored = store.create(
        content=b'{"custom_id":"r1"}\n',
        filename="batch.jsonl",
        purpose="batch",
    )
    assert stored.id.startswith("file-")
    assert stored.bytes > 0
    public = stored.as_public()
    assert public["object"] == "file"
    assert public["filename"] == "batch.jsonl"
    assert public["purpose"] == "batch"

    listed = store.list_files(purpose="batch")
    assert len(listed) == 1
    assert listed[0].id == stored.id
    assert store.get(stored.id) is stored
    assert store.read_text(stored.id) == '{"custom_id":"r1"}\n'
    assert store.delete(stored.id) is True
    assert store.get(stored.id) is None
    assert store.delete(stored.id) is False


def test_rejects_oversized_upload(tmp_path):
    store = FileStore(tmp_path / "files", max_bytes=8)
    with pytest.raises(ValueError, match="max size"):
        store.create(content=b"0123456789", filename="big.jsonl", purpose="batch")


def test_parse_batch_jsonl_valid_and_invalid_lines():
    text = "\n".join(
        [
            json.dumps(
                {
                    "custom_id": "ok",
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": {"model": "m", "messages": [{"role": "user", "content": "hi"}]},
                }
            ),
            "{not-json",
            json.dumps({"nope": True}),
            "",
            json.dumps({"model": "m", "messages": [{"role": "user", "content": "plain"}]}),
        ]
    )
    requests, errors = parse_batch_jsonl(text)
    assert len(requests) == 2
    assert requests[0]["custom_id"] == "ok"
    assert "messages" in requests[1]
    assert {err["line"] for err in errors} == {2, 3}
    assert all(err["param"] == "input_file_id" for err in errors)


def test_index_survives_reload(tmp_path):
    root = tmp_path / "files"
    first = FileStore(root)
    stored = first.create(content=b"hello", filename="a.txt", purpose="batch")
    second = FileStore(root)
    reloaded = second.get(stored.id)
    assert reloaded is not None
    assert reloaded.filename == "a.txt"
    assert second.read_bytes(stored.id) == b"hello"


def test_create_records_owner_key_id_and_persists(tmp_path):
    """FileStore.create snapshots owner; index survives reload (#452)."""
    root = tmp_path / "files"
    store = FileStore(root)
    owned = store.create(
        content=b"secret",
        filename="owned.jsonl",
        purpose="batch",
        owner_key_id="vk_alice",
    )
    assert owned.owner_key_id == "vk_alice"
    orphan = store.create(content=b"legacy", filename="orphan.jsonl", purpose="batch")
    assert orphan.owner_key_id is None

    reloaded = FileStore(root)
    assert reloaded.get(owned.id).owner_key_id == "vk_alice"
    assert reloaded.get(orphan.id).owner_key_id is None
    raw = json.loads((root / "index.json").read_text(encoding="utf-8"))
    by_id = {entry["id"]: entry for entry in raw["files"]}
    assert by_id[owned.id]["owner_key_id"] == "vk_alice"
    assert by_id[orphan.id].get("owner_key_id") in (None, "")


def test_list_files_filters_by_owner_key_id(tmp_path):
    store = FileStore(tmp_path / "files")
    a = store.create(content=b"a", filename="a.jsonl", purpose="batch", owner_key_id="vk_a")
    b = store.create(content=b"b", filename="b.jsonl", purpose="batch", owner_key_id="vk_b")
    store.create(content=b"o", filename="o.jsonl", purpose="batch")  # ownerless
    assert {f.id for f in store.list_files(owner_key_id="vk_a")} == {a.id}
    assert {f.id for f in store.list_files(owner_key_id="vk_b")} == {b.id}
    assert len(store.list_files()) == 3


def test_visible_to_caller_scopes_virtual_vs_master(tmp_path):
    """Virtual keys see only their files; ownerless is master-only (#452)."""
    from daari.gateway.files import file_visible_to_caller
    from daari.server.auth import AuthClaims

    store = FileStore(tmp_path / "files")
    mine = store.create(content=b"1", filename="m.jsonl", purpose="batch", owner_key_id="vk_1")
    theirs = store.create(content=b"2", filename="t.jsonl", purpose="batch", owner_key_id="vk_2")
    orphan = store.create(content=b"3", filename="o.jsonl", purpose="batch")

    vk = AuthClaims(kind="virtual", key_id="vk_1")
    master = AuthClaims(kind="master")
    assert file_visible_to_caller(mine, vk) is True
    assert file_visible_to_caller(theirs, vk) is False
    assert file_visible_to_caller(orphan, vk) is False
    assert file_visible_to_caller(mine, master) is True
    assert file_visible_to_caller(orphan, master) is True
    assert file_visible_to_caller(orphan, None) is True
