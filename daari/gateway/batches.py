"""OpenAI-compatible Batch API — local sequential drain (#433, #442, #443).

Inline `requests` or `input_file_id` (JSONL via `/v1/files`). Completed jobs
write `output_file_id` / `error_file_id` JSONL when a FileStore is attached.
Jobs persist to SQLite across restarts when `batches.path` is set.
At most one batch job runs at a time so local GPUs are not stampeded.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable

from daari.gateway.request_log import log_gateway_event

STATUS_VALIDATING = "validating"
STATUS_FAILED = "failed"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_CANCELLING = "cancelling"
STATUS_CANCELLED = "cancelled"
STATUS_EXPIRED = "expired"

ITEM_PENDING = "pending"
ITEM_COMPLETED = "completed"
ITEM_FAILED = "failed"
ITEM_SKIPPED = "skipped"

ExecuteOne = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS batch_jobs (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS batch_order (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL UNIQUE
);
"""


class BatchItemRejected(Exception):
    """Per-item rejection with a structured error body (e.g. 402 budget)."""

    def __init__(self, error: dict[str, Any]) -> None:
        self.error = error
        super().__init__(str(error.get("message") or error.get("type") or "rejected"))


@dataclass
class BatchGovernance:
    """Creating-request identity + policy snapshotted for every item (#441)."""

    key_id: str | None = None
    client_id: str | None = None
    tier_cap: str | None = None
    no_frontier: bool = False
    user: str | None = None
    boundary_profile: str | None = None
    kind: str = "master"  # master | virtual
    latency_budget_ms: int | None = None
    session_id: str | None = None
    user_agent: str | None = None


@dataclass
class BatchItem:
    custom_id: str
    body: dict[str, Any]
    status: str = ITEM_PENDING
    response: dict[str, Any] | None = None
    error: str | dict[str, Any] | None = None


@dataclass
class BatchJob:
    id: str
    endpoint: str = "/v1/chat/completions"
    completion_window: str = "24h"
    status: str = STATUS_VALIDATING
    input_file_id: str | None = None
    output_file_id: str | None = None
    error_file_id: str | None = None
    created_at: int = field(default_factory=lambda: int(time.time()))
    in_progress_at: int | None = None
    completed_at: int | None = None
    failed_at: int | None = None
    cancelling_at: int | None = None
    cancelled_at: int | None = None
    expired_at: int | None = None
    expires_at: int | None = None
    metadata: dict[str, Any] | None = None
    governance: BatchGovernance | None = None
    items: list[BatchItem] = field(default_factory=list)
    errors: dict[str, Any] | None = None
    cancel_requested: bool = False
    results: list[dict[str, Any]] = field(default_factory=list)


def _normalize_requests(raw: Iterable[Any] | None) -> list[BatchItem]:
    items: list[BatchItem] = []
    if not raw:
        return items
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"requests[{index}] must be an object")
        if "body" in entry and isinstance(entry["body"], dict):
            body = dict(entry["body"])
            custom_id = str(entry.get("custom_id") or f"req_{index}")
        elif "messages" in entry:
            body = dict(entry)
            custom_id = str(entry.get("custom_id") or f"req_{uuid.uuid4().hex[:8]}")
        else:
            raise ValueError(
                f"requests[{index}] must be a chat-completion body or "
                "{custom_id, method, url, body}"
            )
        items.append(BatchItem(custom_id=custom_id, body=body))
    return items


def _job_to_payload(job: BatchJob) -> dict[str, Any]:
    gov = asdict(job.governance) if job.governance is not None else None
    return {
        "id": job.id,
        "endpoint": job.endpoint,
        "completion_window": job.completion_window,
        "status": job.status,
        "input_file_id": job.input_file_id,
        "output_file_id": job.output_file_id,
        "error_file_id": job.error_file_id,
        "created_at": job.created_at,
        "in_progress_at": job.in_progress_at,
        "completed_at": job.completed_at,
        "failed_at": job.failed_at,
        "cancelling_at": job.cancelling_at,
        "cancelled_at": job.cancelled_at,
        "expired_at": job.expired_at,
        "expires_at": job.expires_at,
        "metadata": job.metadata,
        "governance": gov,
        "items": [asdict(item) for item in job.items],
        "errors": job.errors,
        "cancel_requested": job.cancel_requested,
        "results": job.results,
    }


def _job_from_payload(payload: dict[str, Any]) -> BatchJob:
    gov_raw = payload.get("governance")
    governance = BatchGovernance(**gov_raw) if isinstance(gov_raw, dict) else None
    items = [
        BatchItem(
            custom_id=str(item.get("custom_id") or ""),
            body=dict(item.get("body") or {}),
            status=str(item.get("status") or ITEM_PENDING),
            response=item.get("response"),
            error=item.get("error"),
        )
        for item in (payload.get("items") or [])
        if isinstance(item, dict)
    ]
    return BatchJob(
        id=str(payload["id"]),
        endpoint=str(payload.get("endpoint") or "/v1/chat/completions"),
        completion_window=str(payload.get("completion_window") or "24h"),
        status=str(payload.get("status") or STATUS_VALIDATING),
        input_file_id=payload.get("input_file_id"),
        output_file_id=payload.get("output_file_id"),
        error_file_id=payload.get("error_file_id"),
        created_at=int(payload.get("created_at") or time.time()),
        in_progress_at=payload.get("in_progress_at"),
        completed_at=payload.get("completed_at"),
        failed_at=payload.get("failed_at"),
        cancelling_at=payload.get("cancelling_at"),
        cancelled_at=payload.get("cancelled_at"),
        expired_at=payload.get("expired_at"),
        expires_at=payload.get("expires_at"),
        metadata=payload.get("metadata"),
        governance=governance,
        items=items,
        errors=payload.get("errors"),
        cancel_requested=bool(payload.get("cancel_requested")),
        results=list(payload.get("results") or []),
    )


class BatchStore:
    """Batch registry with optional SQLite durability (#443)."""

    def __init__(
        self,
        file_store: Any | None = None,
        *,
        path: str | Path | None = None,
    ) -> None:
        self._batches: dict[str, BatchJob] = {}
        self._order: list[str] = []
        self._lock = asyncio.Lock()
        self._db_lock = threading.Lock()
        self._worker_sem = asyncio.Semaphore(1)
        self._running: set[str] = set()
        self.file_store = file_store
        self.path = Path(path).expanduser() if path else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.executescript(_SCHEMA)
            self._load_from_db()

    def _connect(self) -> sqlite3.Connection:
        assert self.path is not None
        return sqlite3.connect(self.path, timeout=5.0)

    def _load_from_db(self) -> None:
        if self.path is None:
            return
        try:
            with self._db_lock, self._connect() as conn:
                order_rows = conn.execute(
                    "SELECT batch_id FROM batch_order ORDER BY seq ASC"
                ).fetchall()
                payloads = {
                    row[0]: row[1]
                    for row in conn.execute("SELECT id, payload FROM batch_jobs").fetchall()
                }
        except Exception:
            return
        for (batch_id,) in order_rows:
            raw = payloads.get(batch_id)
            if not raw:
                continue
            try:
                job = _job_from_payload(json.loads(raw))
            except (TypeError, ValueError, json.JSONDecodeError, KeyError):
                continue
            # Mid-flight items stay pending; retry once on resume (#443).
            self._batches[job.id] = job
            self._order.append(job.id)

    def _persist(self, job: BatchJob) -> None:
        if self.path is None:
            return
        payload = json.dumps(_job_to_payload(job), ensure_ascii=False)
        try:
            with self._db_lock, self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO batch_jobs (id, payload, created_at) VALUES (?, ?, ?)",
                    (job.id, payload, int(job.created_at)),
                )
                exists = conn.execute(
                    "SELECT 1 FROM batch_order WHERE batch_id = ?", (job.id,)
                ).fetchone()
                if exists is None:
                    conn.execute(
                        "INSERT INTO batch_order (batch_id) VALUES (?)", (job.id,)
                    )
        except Exception as exc:  # noqa: BLE001
            log_gateway_event(
                "batch.persist_failed",
                {"batch_id": job.id, "error": str(exc)[:200]},
            )

    def create(
        self,
        *,
        endpoint: str = "/v1/chat/completions",
        completion_window: str = "24h",
        input_file_id: str | None = None,
        requests: list[Any] | None = None,
        metadata: dict[str, Any] | None = None,
        governance: BatchGovernance | None = None,
    ) -> BatchJob:
        if not input_file_id and not requests:
            raise ValueError("Provide input_file_id or an inline requests array")

        line_errors: list[dict[str, Any]] = []
        resolved_requests = list(requests or [])
        if input_file_id and not resolved_requests:
            resolved_requests, line_errors = self._load_input_file(input_file_id)

        items = _normalize_requests(resolved_requests) if resolved_requests else []
        now = int(time.time())
        job = BatchJob(
            id=f"batch_{uuid.uuid4().hex}",
            endpoint=endpoint or "/v1/chat/completions",
            completion_window=completion_window or "24h",
            input_file_id=input_file_id,
            created_at=now,
            expires_at=now + 24 * 3600,
            metadata=metadata,
            governance=governance,
            items=items,
            status=STATUS_VALIDATING,
        )

        if line_errors and not items:
            job.status = STATUS_FAILED
            job.failed_at = now
            job.errors = {"object": "list", "data": line_errors}
            log_gateway_event(
                "batch.validation_failed",
                {"batch_id": job.id, "input_file_id": input_file_id, "errors": len(line_errors)},
            )
        elif not items:
            job.status = STATUS_FAILED
            job.failed_at = now
            job.errors = {
                "object": "list",
                "data": [
                    {
                        "code": "invalid_request",
                        "message": (
                            "input_file_id without uploaded file content is not "
                            "supported; upload via POST /v1/files or pass an "
                            "inline requests array"
                        ),
                        "param": "input_file_id",
                        "line": None,
                    }
                ],
            }
            log_gateway_event(
                "batch.validation_failed",
                {"batch_id": job.id, "input_file_id": input_file_id},
            )
        else:
            if line_errors:
                job.errors = {"object": "list", "data": line_errors}
            log_gateway_event(
                "batch.created",
                {
                    "batch_id": job.id,
                    "total": len(items),
                    "endpoint": job.endpoint,
                },
            )

        self._batches[job.id] = job
        self._order.append(job.id)
        self._persist(job)
        return job

    def _load_input_file(
        self, input_file_id: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        store = self.file_store
        if store is None:
            return [], [
                {
                    "code": "invalid_request",
                    "message": "files store is not configured",
                    "param": "input_file_id",
                    "line": None,
                }
            ]
        text = store.read_text(input_file_id)
        if text is None:
            return [], [
                {
                    "code": "invalid_request",
                    "message": f"unknown input_file_id: {input_file_id}",
                    "param": "input_file_id",
                    "line": None,
                }
            ]
        from daari.gateway.files import parse_batch_jsonl

        return parse_batch_jsonl(text)

    def get(self, batch_id: str) -> BatchJob | None:
        job = self._batches.get(batch_id)
        if job is None:
            return None
        if self._maybe_expire(job):
            self._persist(job)
        return job

    def list_batches(self, *, limit: int = 100) -> list[BatchJob]:
        ids = list(reversed(self._order))[: max(1, min(limit, 1000))]
        out: list[BatchJob] = []
        for batch_id in ids:
            job = self.get(batch_id)
            if job is not None:
                out.append(job)
        return out

    def cancel(self, batch_id: str) -> BatchJob | None:
        job = self.get(batch_id)
        if job is None:
            return None
        if job.status in {
            STATUS_COMPLETED,
            STATUS_FAILED,
            STATUS_CANCELLED,
            STATUS_EXPIRED,
        }:
            return job
        now = int(time.time())
        job.cancel_requested = True
        if job.status == STATUS_VALIDATING or batch_id not in self._running:
            self._mark_remaining_skipped(job)
            job.status = STATUS_CANCELLED
            job.cancelling_at = now
            job.cancelled_at = now
        else:
            job.status = STATUS_CANCELLING
            job.cancelling_at = now
        log_gateway_event("batch.cancel_requested", {"batch_id": job.id})
        self._persist(job)
        return job

    def as_public(self, job: BatchJob) -> dict[str, Any]:
        completed = sum(1 for item in job.items if item.status == ITEM_COMPLETED)
        failed = sum(1 for item in job.items if item.status == ITEM_FAILED)
        payload: dict[str, Any] = {
            "id": job.id,
            "object": "batch",
            "endpoint": job.endpoint,
            "errors": job.errors,
            "input_file_id": job.input_file_id,
            "completion_window": job.completion_window,
            "status": job.status,
            "output_file_id": job.output_file_id,
            "error_file_id": job.error_file_id,
            "created_at": job.created_at,
            "in_progress_at": job.in_progress_at,
            "expires_at": job.expires_at,
            "finalizing_at": None,
            "completed_at": job.completed_at,
            "failed_at": job.failed_at,
            "expired_at": job.expired_at,
            "cancelling_at": job.cancelling_at,
            "cancelled_at": job.cancelled_at,
            "request_counts": {
                "total": len(job.items),
                "completed": completed,
                "failed": failed,
            },
            "metadata": job.metadata,
        }
        if job.results:
            payload["results"] = job.results
        skipped = sum(1 for item in job.items if item.status == ITEM_SKIPPED)
        if skipped:
            payload["request_counts"]["skipped"] = skipped
        return payload

    def schedule(self, batch_id: str, execute_one: ExecuteOne) -> None:
        """Fire-and-forget worker; safe to call from a request handler."""
        job = self.get(batch_id)
        if job is None or not job.items:
            return
        if job.status not in {STATUS_VALIDATING, STATUS_IN_PROGRESS}:
            return
        asyncio.create_task(self.run_job(batch_id, execute_one))

    def resume_incomplete(self, execute_one: ExecuteOne) -> int:
        """Re-queue validating/in_progress jobs after a restart (#443)."""
        return self.resume_incomplete_with(lambda _batch_id: execute_one)

    def resume_incomplete_with(
        self, factory: Callable[[str], ExecuteOne]
    ) -> int:
        """Like resume_incomplete but builds a per-job executor (governance)."""
        resumed = 0
        for batch_id in list(self._order):
            job = self.get(batch_id)
            if job is None:
                continue
            if job.status not in {STATUS_VALIDATING, STATUS_IN_PROGRESS}:
                continue
            if not any(item.status == ITEM_PENDING for item in job.items):
                continue
            self.schedule(batch_id, factory(batch_id))
            resumed += 1
        if resumed:
            log_gateway_event("batch.resume", {"count": resumed})
        return resumed

    def _maybe_expire(self, job: BatchJob) -> bool:
        if job.status in {
            STATUS_COMPLETED,
            STATUS_FAILED,
            STATUS_CANCELLED,
            STATUS_EXPIRED,
        }:
            return False
        if job.expires_at is None or int(time.time()) < int(job.expires_at):
            return False
        if not any(item.status == ITEM_PENDING for item in job.items):
            return False
        now = int(time.time())
        self._mark_remaining_skipped(job)
        job.status = STATUS_EXPIRED
        job.expired_at = now
        log_gateway_event("batch.expired", {"batch_id": job.id})
        return True

    async def run_job(self, batch_id: str, execute_one: ExecuteOne) -> None:
        async with self._worker_sem:
            job = self.get(batch_id)
            if job is None:
                return
            if job.status in {
                STATUS_COMPLETED,
                STATUS_FAILED,
                STATUS_CANCELLED,
                STATUS_EXPIRED,
            }:
                return
            if job.cancel_requested:
                self._mark_remaining_skipped(job)
                now = int(time.time())
                job.status = STATUS_CANCELLED
                job.cancelled_at = job.cancelled_at or now
                job.cancelling_at = job.cancelling_at or now
                self._persist(job)
                return
            if not job.items or job.status == STATUS_FAILED:
                return

            self._running.add(batch_id)
            job.status = STATUS_IN_PROGRESS
            job.in_progress_at = job.in_progress_at or int(time.time())
            self._persist(job)
            log_gateway_event(
                "batch.in_progress",
                {"batch_id": job.id, "total": len(job.items)},
            )
            try:
                for item in job.items:
                    if job.cancel_requested:
                        self._mark_remaining_skipped(job)
                        break
                    if self._maybe_expire(job):
                        break
                    if item.status != ITEM_PENDING:
                        continue
                    try:
                        response = await execute_one(item.body)
                        item.response = response
                        item.status = ITEM_COMPLETED
                        job.results.append(
                            {
                                "id": f"batch_req_{uuid.uuid4().hex[:12]}",
                                "custom_id": item.custom_id,
                                "response": {
                                    "status_code": 200,
                                    "request_id": None,
                                    "body": response,
                                },
                                "error": None,
                            }
                        )
                    except BatchItemRejected as exc:
                        item.status = ITEM_FAILED
                        item.error = exc.error
                        status_code = 402 if exc.error.get("type") == "budget_exceeded" else 400
                        job.results.append(
                            {
                                "id": f"batch_req_{uuid.uuid4().hex[:12]}",
                                "custom_id": item.custom_id,
                                "response": {
                                    "status_code": status_code,
                                    "request_id": None,
                                    "body": None,
                                },
                                "error": dict(exc.error),
                            }
                        )
                        log_gateway_event(
                            "batch.item_failed",
                            {
                                "batch_id": job.id,
                                "custom_id": item.custom_id,
                                "error": str(exc.error.get("message") or exc)[:200],
                            },
                        )
                    except Exception as exc:  # noqa: BLE001 — per-item failure
                        item.status = ITEM_FAILED
                        item.error = str(exc)[:500]
                        job.results.append(
                            {
                                "id": f"batch_req_{uuid.uuid4().hex[:12]}",
                                "custom_id": item.custom_id,
                                "response": None,
                                "error": {"code": "server_error", "message": item.error},
                            }
                        )
                        log_gateway_event(
                            "batch.item_failed",
                            {
                                "batch_id": job.id,
                                "custom_id": item.custom_id,
                                "error": str(item.error)[:200],
                            },
                        )
                    self._persist(job)

                now = int(time.time())
                if job.status == STATUS_EXPIRED:
                    self._persist(job)
                elif job.cancel_requested:
                    self._mark_remaining_skipped(job)
                    job.status = STATUS_CANCELLED
                    job.cancelled_at = now
                    self._persist(job)
                    log_gateway_event("batch.cancelled", {"batch_id": job.id})
                else:
                    job.status = STATUS_COMPLETED
                    job.completed_at = now
                    self._write_result_files(job)
                    self._persist(job)
                    log_gateway_event(
                        "batch.completed",
                        {
                            "batch_id": job.id,
                            "completed": sum(
                                1 for i in job.items if i.status == ITEM_COMPLETED
                            ),
                            "failed": sum(
                                1 for i in job.items if i.status == ITEM_FAILED
                            ),
                            "output_file_id": job.output_file_id,
                            "error_file_id": job.error_file_id,
                        },
                    )
            finally:
                self._running.discard(batch_id)

    def _write_result_files(self, job: BatchJob) -> None:
        """Persist OpenAI-shaped JSONL output/error files when a store is wired."""
        store = self.file_store
        if store is None or not job.results:
            return
        try:
            output = store.write_jsonl(
                lines=job.results,
                filename=f"{job.id}_output.jsonl",
                purpose="batch_output",
            )
            job.output_file_id = output.id
            failed_lines = [row for row in job.results if row.get("error") is not None]
            if failed_lines:
                error_file = store.write_jsonl(
                    lines=failed_lines,
                    filename=f"{job.id}_errors.jsonl",
                    purpose="batch_output",
                )
                job.error_file_id = error_file.id
        except Exception as exc:  # noqa: BLE001 — results still available inline
            log_gateway_event(
                "batch.result_files_failed",
                {"batch_id": job.id, "error": str(exc)[:200]},
            )

    @staticmethod
    def _mark_remaining_skipped(job: BatchJob) -> None:
        for item in job.items:
            if item.status == ITEM_PENDING:
                item.status = ITEM_SKIPPED
