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
