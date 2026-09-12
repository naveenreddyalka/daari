"""OpenAI Batch API store + worker (#433, #441, #442, #443)."""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from daari.gateway.batches import (
    ITEM_COMPLETED,
    ITEM_FAILED,
    ITEM_SKIPPED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_IN_PROGRESS,
    STATUS_VALIDATING,
    BatchGovernance,
    BatchItemRejected,
    BatchStore,
)


def test_create_requires_input_file_id_or_requests():
    store = BatchStore()
    with pytest.raises(ValueError, match="input_file_id|requests"):
        store.create(endpoint="/v1/chat/completions")


def test_create_inline_requests_starts_validating():
    store = BatchStore()
    job = store.create(
        endpoint="/v1/chat/completions",
        requests=[
            {
                "custom_id": "r1",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": "llama3.2:3b",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            },
            {
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "plain body"}],
            },
        ],
    )
    assert job.id.startswith("batch_")
    assert job.status == STATUS_VALIDATING
    public = store.as_public(job)
    assert public["object"] == "batch"
    assert public["status"] == STATUS_VALIDATING
    assert public["request_counts"]["total"] == 2
    assert public["endpoint"] == "/v1/chat/completions"
    assert len(job.items) == 2
    assert job.items[0].custom_id == "r1"
    assert job.items[1].custom_id.startswith("req_")


def test_create_input_file_id_without_requests_fails_validation():
    store = BatchStore()
    job = store.create(input_file_id="file-abc", endpoint="/v1/chat/completions")
    assert job.status == STATUS_FAILED
    public = store.as_public(job)
    assert public["status"] == STATUS_FAILED
    assert public["input_file_id"] == "file-abc"
    assert public["errors"] is not None


def test_create_from_input_file_jsonl(tmp_path):
    from daari.gateway.files import FileStore

    files = FileStore(tmp_path / "files")
    line = {
        "custom_id": "from-file",
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {"model": "m", "messages": [{"role": "user", "content": "hi"}]},
    }
    uploaded = files.create(
        content=(json.dumps(line) + "\n").encode(),
        filename="in.jsonl",
        purpose="batch",
    )
    store = BatchStore(file_store=files)
    job = store.create(input_file_id=uploaded.id, endpoint="/v1/chat/completions")
    assert job.status == STATUS_VALIDATING
    assert len(job.items) == 1
    assert job.items[0].custom_id == "from-file"


def test_create_from_input_file_reports_bad_line_numbers(tmp_path):
    from daari.gateway.files import FileStore

    files = FileStore(tmp_path / "files")
    content = "{bad\n" + json.dumps({"nope": 1}) + "\n"
    uploaded = files.create(content=content.encode(), filename="bad.jsonl", purpose="batch")
    store = BatchStore(file_store=files)
    job = store.create(input_file_id=uploaded.id)
    assert job.status == STATUS_FAILED
    lines = {err["line"] for err in job.errors["data"]}
    assert lines == {1, 2}


@pytest.mark.asyncio
async def test_completed_batch_writes_output_and_error_files(tmp_path):
    from daari.gateway.files import FileStore

    files = FileStore(tmp_path / "files")
    store = BatchStore(file_store=files)
    job = store.create(
        requests=[
            {"model": "m", "messages": [{"role": "user", "content": "ok"}]},
            {"model": "m", "messages": [{"role": "user", "content": "boom"}]},
        ],
    )

    async def execute_one(body: dict) -> dict:
        if body["messages"][0]["content"] == "boom":
            raise RuntimeError("upstream failed")
        return {"ok": True}

    await store.run_job(job.id, execute_one)
    refreshed = store.get(job.id)
    assert refreshed is not None
    assert refreshed.status == STATUS_COMPLETED
    assert refreshed.output_file_id
    assert refreshed.error_file_id
    public = store.as_public(refreshed)
    assert public["output_file_id"] == refreshed.output_file_id
    assert public["error_file_id"] == refreshed.error_file_id
    out_text = files.read_text(refreshed.output_file_id)
    assert out_text is not None
    assert "ok" in out_text or '"error": null' in out_text
    err_text = files.read_text(refreshed.error_file_id)
    assert err_text is not None
    assert "server_error" in err_text


def test_sqlite_persistence_round_trip(tmp_path):
    path = tmp_path / "batches.sqlite3"
    store = BatchStore(path=path)
    job = store.create(
        requests=[{"model": "m", "messages": [{"role": "user", "content": "persist"}]}],
        governance=BatchGovernance(client_id="c1", tier_cap="L3", kind="virtual"),
    )
    job.status = STATUS_IN_PROGRESS
    job.items[0].status = ITEM_COMPLETED
    job.items[0].response = {"ok": True}
    store._persist(job)

    reloaded = BatchStore(path=path)
    found = reloaded.get(job.id)
    assert found is not None
    assert found.status == STATUS_IN_PROGRESS
    assert found.governance is not None
    assert found.governance.client_id == "c1"
    assert found.items[0].status == ITEM_COMPLETED
    public = reloaded.as_public(found)
    assert public["request_counts"]["completed"] == 1


@pytest.mark.asyncio
async def test_restart_resumes_pending_items(tmp_path):
    path = tmp_path / "batches.sqlite3"
    store = BatchStore(path=path)
    job = store.create(
        requests=[
            {"model": "m", "messages": [{"role": "user", "content": "done"}]},
            {"model": "m", "messages": [{"role": "user", "content": "pending"}]},
        ],
    )
    job.status = STATUS_IN_PROGRESS
    job.items[0].status = ITEM_COMPLETED
    job.items[0].response = {"ok": True}
    job.results.append(
        {
            "id": "batch_req_done",
            "custom_id": job.items[0].custom_id,
            "response": {"status_code": 200, "request_id": None, "body": {"ok": True}},
            "error": None,
        }
    )
    store._persist(job)

    resumed = BatchStore(path=path)
    seen: list[str] = []

    async def execute_one(body: dict) -> dict:
        seen.append(body["messages"][0]["content"])
        return {"echo": body["messages"][0]["content"]}

    count = resumed.resume_incomplete(execute_one)
    assert count == 1
    # Let the scheduled task drain.
    await asyncio.sleep(0.05)
    for _ in range(50):
        refreshed = resumed.get(job.id)
        if refreshed and refreshed.status == STATUS_COMPLETED:
            break
        await asyncio.sleep(0.02)
    refreshed = resumed.get(job.id)
    assert refreshed is not None
    assert refreshed.status == STATUS_COMPLETED
    assert seen == ["pending"]
    assert refreshed.items[1].status == ITEM_COMPLETED


def test_expired_job_skips_pending_on_read(tmp_path):
    from daari.gateway.batches import STATUS_EXPIRED

    path = tmp_path / "batches.sqlite3"
    store = BatchStore(path=path)
    job = store.create(
        requests=[
            {"model": "m", "messages": [{"role": "user", "content": "a"}]},
            {"model": "m", "messages": [{"role": "user", "content": "b"}]},
        ],
    )
    job.expires_at = int(time.time()) - 10
    store._persist(job)
    found = store.get(job.id)
    assert found is not None
    assert found.status == STATUS_EXPIRED
    assert all(item.status == ITEM_SKIPPED for item in found.items)
    assert found.expired_at is not None
    public = store.as_public(found)
    assert public["status"] == STATUS_EXPIRED
    assert public["expired_at"] == found.expired_at



@pytest.mark.asyncio
async def test_worker_runs_items_sequentially_through_executor():
    store = BatchStore()
    job = store.create(
        requests=[
            {"model": "m", "messages": [{"role": "user", "content": "a"}]},
            {"model": "m", "messages": [{"role": "user", "content": "b"}]},
        ],
    )
    order: list[str] = []

    async def execute_one(body: dict) -> dict:
        content = body["messages"][0]["content"]
        order.append(content)
        await asyncio.sleep(0.01)
        return {"id": f"chatcmpl-{content}", "choices": [{"message": {"content": content}}]}

    await store.run_job(job.id, execute_one)
    refreshed = store.get(job.id)
    assert refreshed is not None
    assert refreshed.status == STATUS_COMPLETED
    assert order == ["a", "b"]
    assert all(item.status == ITEM_COMPLETED for item in refreshed.items)
    public = store.as_public(refreshed)
    assert public["request_counts"] == {"total": 2, "completed": 2, "failed": 0}
    assert public["completed_at"] is not None


@pytest.mark.asyncio
async def test_concurrent_batch_jobs_capped_at_one():
    store = BatchStore()
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def execute_one(body: dict) -> dict:
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        async with lock:
            active -= 1
        return {"ok": True}

    jobs = [
        store.create(requests=[{"model": "m", "messages": [{"role": "user", "content": str(i)}]}])
        for i in range(3)
    ]
    await asyncio.gather(*(store.run_job(job.id, execute_one) for job in jobs))
    assert max_active == 1
    assert all(store.get(job.id).status == STATUS_COMPLETED for job in jobs)


@pytest.mark.asyncio
async def test_cancel_marks_remaining_items_skipped():
    store = BatchStore()
    job = store.create(
        requests=[
            {"model": "m", "messages": [{"role": "user", "content": "1"}]},
            {"model": "m", "messages": [{"role": "user", "content": "2"}]},
            {"model": "m", "messages": [{"role": "user", "content": "3"}]},
        ],
    )
    started = asyncio.Event()

    async def execute_one(body: dict) -> dict:
        started.set()
        await asyncio.sleep(0.08)
        return {"ok": body["messages"][0]["content"]}

    task = asyncio.create_task(store.run_job(job.id, execute_one))
    await started.wait()
    # Let first item be in flight, then cancel
    await asyncio.sleep(0.01)
    cancelled = store.cancel(job.id)
    assert cancelled is not None
    assert cancelled.status in {STATUS_CANCELLED, "cancelling", STATUS_IN_PROGRESS}
    await task
    refreshed = store.get(job.id)
    assert refreshed is not None
    assert refreshed.status == STATUS_CANCELLED
    statuses = [item.status for item in refreshed.items]
    assert ITEM_COMPLETED in statuses
    assert ITEM_SKIPPED in statuses
    assert statuses.count(ITEM_SKIPPED) >= 1


@pytest.mark.asyncio
async def test_item_failure_counted_and_batch_can_complete():
    store = BatchStore()
    job = store.create(
        requests=[
            {"model": "m", "messages": [{"role": "user", "content": "ok"}]},
            {"model": "m", "messages": [{"role": "user", "content": "boom"}]},
        ],
    )

    async def execute_one(body: dict) -> dict:
        if body["messages"][0]["content"] == "boom":
            raise RuntimeError("upstream failed")
        return {"ok": True}

    await store.run_job(job.id, execute_one)
    refreshed = store.get(job.id)
    assert refreshed is not None
    assert refreshed.status == STATUS_COMPLETED
    assert refreshed.items[0].status == ITEM_COMPLETED
    assert refreshed.items[1].status == ITEM_FAILED
    public = store.as_public(refreshed)
    assert public["request_counts"] == {"total": 2, "completed": 1, "failed": 1}


def test_list_and_get():
    store = BatchStore()
    a = store.create(requests=[{"model": "m", "messages": [{"role": "user", "content": "a"}]}])
    b = store.create(requests=[{"model": "m", "messages": [{"role": "user", "content": "b"}]}])
    assert store.get(a.id) is a
    listed = store.list_batches()
    assert {job.id for job in listed} == {a.id, b.id}
    assert store.get("batch_missing") is None


def test_create_stores_governance_snapshot():
    """Creating-key identity is snapshotted onto the job (#441)."""
    store = BatchStore()
    gov = BatchGovernance(
        key_id="vk_1",
        client_id="agent-ci",
        tier_cap="L5",
        no_frontier=True,
        user="alice",
        boundary_profile="strict",
        kind="virtual",
    )
    job = store.create(
        requests=[{"model": "m", "messages": [{"role": "user", "content": "hi"}]}],
        governance=gov,
    )
    assert job.governance is not None
    assert job.governance.client_id == "agent-ci"
    assert job.governance.tier_cap == "L5"
    assert job.governance.no_frontier is True
    assert job.governance.user == "alice"
    assert job.governance.boundary_profile == "strict"
    assert job.governance.key_id == "vk_1"


@pytest.mark.asyncio
async def test_budget_rejected_item_records_402_shape_and_continues():
    """Over-budget frontier items fail with a 402 body; siblings still run (#441)."""
    store = BatchStore()
    job = store.create(
        requests=[
            {"model": "m", "messages": [{"role": "user", "content": "ok"}]},
            {"model": "m", "messages": [{"role": "user", "content": "spend"}]},
            {"model": "m", "messages": [{"role": "user", "content": "ok2"}]},
        ],
    )
    budget_err = {
        "type": "budget_exceeded",
        "message": "Virtual key daily frontier budget ($1.0000) exceeded — $2.0000 spent.",
        "client_id": "key-a",
        "window": "daily",
        "budget_usd": 1.0,
        "spend_usd": 2.0,
        "reset_at": "2026-09-13T00:00:00+00:00",
        "scope": "key",
    }

    async def execute_one(body: dict) -> dict:
        if body["messages"][0]["content"] == "spend":
            raise BatchItemRejected(budget_err)
        return {"ok": True, "echo": body["messages"][0]["content"]}

    await store.run_job(job.id, execute_one)
    refreshed = store.get(job.id)
    assert refreshed is not None
    assert refreshed.status == STATUS_COMPLETED
    assert refreshed.items[0].status == ITEM_COMPLETED
    assert refreshed.items[1].status == ITEM_FAILED
    assert refreshed.items[1].error == budget_err
    assert refreshed.items[2].status == ITEM_COMPLETED
    failed = next(r for r in refreshed.results if r["custom_id"] == refreshed.items[1].custom_id)
    assert failed["error"]["type"] == "budget_exceeded"
    assert failed["error"]["client_id"] == "key-a"
