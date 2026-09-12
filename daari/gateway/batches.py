"""OpenAI-compatible Batch API — local sequential drain (#433).

First slice: inline `requests` (chat-completion bodies or JSONL-line objects).
`input_file_id` is accepted for shape parity; file upload is a follow-up.
At most one batch job runs at a time so local GPUs are not stampeded.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

from daari.gateway.request_log import log_gateway_event

STATUS_VALIDATING = "validating"
STATUS_FAILED = "failed"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_CANCELLING = "cancelling"
STATUS_CANCELLED = "cancelled"

ITEM_PENDING = "pending"
ITEM_COMPLETED = "completed"
ITEM_FAILED = "failed"
ITEM_SKIPPED = "skipped"

ExecuteOne = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class BatchItem:
    custom_id: str
    body: dict[str, Any]
    status: str = ITEM_PENDING
    response: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class BatchJob:
    id: str
    endpoint: str = "/v1/chat/completions"
    completion_window: str = "24h"
    status: str = STATUS_VALIDATING
    input_file_id: str | None = None
    created_at: int = field(default_factory=lambda: int(time.time()))
    in_progress_at: int | None = None
    completed_at: int | None = None
    failed_at: int | None = None
    cancelling_at: int | None = None
    cancelled_at: int | None = None
    expires_at: int | None = None
    metadata: dict[str, Any] | None = None
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


class BatchStore:
    """In-process batch registry with a single-slot worker."""

    def __init__(self) -> None:
        self._batches: dict[str, BatchJob] = {}
        self._order: list[str] = []
        self._lock = asyncio.Lock()
        self._worker_sem = asyncio.Semaphore(1)
        self._running: set[str] = set()

    def create(
        self,
        *,
        endpoint: str = "/v1/chat/completions",
        completion_window: str = "24h",
        input_file_id: str | None = None,
        requests: list[Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BatchJob:
        if not input_file_id and not requests:
            raise ValueError("Provide input_file_id or an inline requests array")

        items = _normalize_requests(requests)
        now = int(time.time())
        job = BatchJob(
            id=f"batch_{uuid.uuid4().hex}",
            endpoint=endpoint or "/v1/chat/completions",
            completion_window=completion_window or "24h",
            input_file_id=input_file_id,
            created_at=now,
            expires_at=now + 24 * 3600,
            metadata=metadata,
            items=items,
            status=STATUS_VALIDATING,
        )

        if not items:
            # File upload is a follow-up; accept the field then fail validation.
            job.status = STATUS_FAILED
            job.failed_at = now
            job.errors = {
                "object": "list",
                "data": [
                    {
                        "code": "invalid_request",
                        "message": (
                            "input_file_id without uploaded file content is not "
                            "supported yet; pass an inline requests array"
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
        return job

    def get(self, batch_id: str) -> BatchJob | None:
        return self._batches.get(batch_id)

    def list_batches(self, *, limit: int = 100) -> list[BatchJob]:
        ids = list(reversed(self._order))[: max(1, min(limit, 1000))]
        return [self._batches[batch_id] for batch_id in ids if batch_id in self._batches]

    def cancel(self, batch_id: str) -> BatchJob | None:
        job = self.get(batch_id)
        if job is None:
            return None
        if job.status in {
            STATUS_COMPLETED,
            STATUS_FAILED,
            STATUS_CANCELLED,
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
            "output_file_id": None,
            "error_file_id": None,
            "created_at": job.created_at,
            "in_progress_at": job.in_progress_at,
            "expires_at": job.expires_at,
            "finalizing_at": None,
            "completed_at": job.completed_at,
            "failed_at": job.failed_at,
            "expired_at": None,
            "cancelling_at": job.cancelling_at,
            "cancelled_at": job.cancelled_at,
            "request_counts": {
                "total": len(job.items),
                "completed": completed,
                "failed": failed,
            },
            "metadata": job.metadata,
        }
        # Local convenience: expose inline results (no Files API yet).
        if job.results:
            payload["results"] = job.results
        skipped = sum(1 for item in job.items if item.status == ITEM_SKIPPED)
        if skipped:
            payload["request_counts"]["skipped"] = skipped
        return payload

    def schedule(self, batch_id: str, execute_one: ExecuteOne) -> None:
        """Fire-and-forget worker; safe to call from a request handler."""
        job = self.get(batch_id)
        if job is None or job.status != STATUS_VALIDATING or not job.items:
            return
        asyncio.create_task(self.run_job(batch_id, execute_one))

    async def run_job(self, batch_id: str, execute_one: ExecuteOne) -> None:
        async with self._worker_sem:
            job = self.get(batch_id)
            if job is None:
                return
            if job.status in {STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED}:
                return
            if job.cancel_requested:
                self._mark_remaining_skipped(job)
                now = int(time.time())
                job.status = STATUS_CANCELLED
                job.cancelled_at = job.cancelled_at or now
                job.cancelling_at = job.cancelling_at or now
                return
            if not job.items or job.status == STATUS_FAILED:
                return

            self._running.add(batch_id)
            job.status = STATUS_IN_PROGRESS
            job.in_progress_at = int(time.time())
            log_gateway_event(
                "batch.in_progress",
                {"batch_id": job.id, "total": len(job.items)},
            )
            try:
                for item in job.items:
                    if job.cancel_requested:
                        self._mark_remaining_skipped(job)
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
                                "error": item.error[:200],
                            },
                        )

                now = int(time.time())
                if job.cancel_requested:
                    self._mark_remaining_skipped(job)
                    job.status = STATUS_CANCELLED
                    job.cancelled_at = now
                    log_gateway_event("batch.cancelled", {"batch_id": job.id})
                else:
                    job.status = STATUS_COMPLETED
                    job.completed_at = now
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
                        },
                    )
            finally:
                self._running.discard(batch_id)

    @staticmethod
    def _mark_remaining_skipped(job: BatchJob) -> None:
        for item in job.items:
            if item.status == ITEM_PENDING:
                item.status = ITEM_SKIPPED
