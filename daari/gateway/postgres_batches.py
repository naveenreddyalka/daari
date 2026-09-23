"""Postgres-backed Batch store with cross-replica claim (#465).

Subclass of BatchStore: same job shape, shared via Postgres (or
``memory:<name>`` for unit tests). Only one replica drains a job at a time
via claimed_by + heartbeat TTL reclaim.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any, Callable

from daari.gateway.batches import (
    ITEM_COMPLETED,
    ITEM_FAILED,
    ITEM_PENDING,
    STATUS_CANCELLED,
    STATUS_CANCELLING,
    STATUS_COMPLETED,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_IN_PROGRESS,
    STATUS_VALIDATING,
    BatchItemRejected,
    BatchStore,
    _job_from_payload,
    _job_to_payload,
)
from daari.gateway.request_log import log_gateway_event

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daari_batch_jobs (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    status TEXT NOT NULL,
    claimed_by TEXT,
    claimed_at BIGINT,
    seq BIGSERIAL
);
CREATE INDEX IF NOT EXISTS daari_batch_jobs_status_claim
    ON daari_batch_jobs (status, claimed_at);
"""

_MEMORY_BATCHES: dict[str, dict[str, dict[str, Any]]] = {}
_MEMORY_ORDER: dict[str, list[str]] = {}
_MEMORY_LOCKS: dict[str, threading.Lock] = {}
_MEMORY_META_LOCK = threading.Lock()

DEFAULT_CLAIM_TTL_SECONDS = 90


def _memory_bucket(dsn: str) -> tuple[dict[str, dict[str, Any]], list[str], threading.Lock]:
    with _MEMORY_META_LOCK:
        if dsn not in _MEMORY_BATCHES:
            _MEMORY_BATCHES[dsn] = {}
            _MEMORY_ORDER[dsn] = []
            _MEMORY_LOCKS[dsn] = threading.Lock()
        return _MEMORY_BATCHES[dsn], _MEMORY_ORDER[dsn], _MEMORY_LOCKS[dsn]


class PostgresBatchStore(BatchStore):
    """Fleet-shared batch jobs with claim/heartbeat drain (#465)."""

    def __init__(
        self,
        dsn: str,
        file_store: Any | None = None,
        *,
        idle_probe: Callable[[], int] | None = None,
        yield_to_interactive: bool = True,
        idle_poll_seconds: float = 0.25,
        claim_ttl_seconds: int = DEFAULT_CLAIM_TTL_SECONDS,
        worker_id: str | None = None,
        enabled: bool = True,
    ) -> None:
        super().__init__(
            file_store=file_store,
            path=None,
            idle_probe=idle_probe,
            yield_to_interactive=yield_to_interactive,
            idle_poll_seconds=idle_poll_seconds,
        )
        self.dsn = dsn
        self.enabled = enabled
        self.claim_ttl_seconds = max(5, int(claim_ttl_seconds))
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:12]}"
        self._memory = dsn.startswith("memory:")
        self._pg_lock = threading.Lock()
        if self.enabled and not self._memory:
            try:
                with self._pg_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(_SCHEMA)
                    conn.commit()
            except Exception:
                self.enabled = False
        if self.enabled or self._memory:
            self._load_from_db()

    def _pg_connect(self) -> Any:
        from daari.gateway.pg_pool import pooled_connection

        try:
            import psycopg  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "batches.backend=postgres requires psycopg — "
                "pip install 'psycopg[binary,pool]>=3' (or daari[postgres])"
            ) from exc
        return pooled_connection(self.dsn)

    def _load_from_db(self) -> None:
        self._batches.clear()
        self._order.clear()
        if self._memory:
            bucket, order, lock = _memory_bucket(self.dsn)
            with lock:
                for batch_id in list(order):
                    row = bucket.get(batch_id)
                    if not row:
                        continue
                    try:
                        job = _job_from_payload(json.loads(row["payload"]))
                    except (TypeError, ValueError, json.JSONDecodeError, KeyError):
                        continue
                    self._batches[job.id] = job
                    self._order.append(job.id)
            return
        if not self.enabled:
            return
        try:
            with self._pg_lock, self._pg_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, payload FROM daari_batch_jobs ORDER BY seq ASC"
                    )
                    rows = cur.fetchall()
            for batch_id, raw in rows:
                try:
                    job = _job_from_payload(json.loads(raw))
                except (TypeError, ValueError, json.JSONDecodeError, KeyError):
                    continue
                self._batches[job.id] = job
                self._order.append(job.id)
        except Exception:
            return

    def _persist(self, job: Any) -> None:
        payload = json.dumps(_job_to_payload(job), ensure_ascii=False)
        if self._memory:
            bucket, order, lock = _memory_bucket(self.dsn)
            with lock:
                existing = bucket.get(job.id)
                claimed_by = existing.get("claimed_by") if existing else None
                claimed_at = existing.get("claimed_at") if existing else None
                bucket[job.id] = {
                    "id": job.id,
                    "payload": payload,
                    "created_at": int(job.created_at),
                    "status": job.status,
                    "claimed_by": claimed_by,
                    "claimed_at": claimed_at,
                }
                if job.id not in order:
                    order.append(job.id)
            self._batches[job.id] = job
            if job.id not in self._order:
                self._order.append(job.id)
            return
        if not self.enabled:
            self._batches[job.id] = job
            if job.id not in self._order:
                self._order.append(job.id)
            return
        try:
            with self._pg_lock, self._pg_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO daari_batch_jobs (id, payload, created_at, status)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            payload = EXCLUDED.payload,
                            status = EXCLUDED.status
                        """,
                        (job.id, payload, int(job.created_at), job.status),
                    )
                conn.commit()
            self._batches[job.id] = job
            if job.id not in self._order:
                self._order.append(job.id)
        except Exception as exc:  # noqa: BLE001
            log_gateway_event(
                "batch.persist_failed",
                {"batch_id": job.id, "error": str(exc)[:200]},
            )

    def list_batches(
        self, *, limit: int = 100, owner_key_id: str | None = None
    ) -> list[Any]:
        self._load_from_db()
        return super().list_batches(limit=limit, owner_key_id=owner_key_id)

    def get(self, batch_id: str) -> Any | None:
        job = self._fetch(batch_id)
        if job is None:
            return None
        if self._maybe_expire(job):
            self._persist(job)
        return job

    def _fetch(self, batch_id: str) -> Any | None:
        if self._memory:
            bucket, _order, lock = _memory_bucket(self.dsn)
            with lock:
                row = bucket.get(batch_id)
            if row is None:
                return None
            try:
                job = _job_from_payload(json.loads(row["payload"]))
            except (TypeError, ValueError, json.JSONDecodeError, KeyError):
                return None
            self._batches[job.id] = job
            return job
        if not self.enabled:
            return self._batches.get(batch_id)
        try:
            with self._pg_lock, self._pg_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT payload FROM daari_batch_jobs WHERE id = %s",
                        (batch_id,),
                    )
                    found = cur.fetchone()
            if found is None:
                return None
            job = _job_from_payload(json.loads(found[0]))
            self._batches[job.id] = job
            return job
        except Exception:
            return self._batches.get(batch_id)

    def _try_claim(self, batch_id: str) -> bool:
        now = int(time.time())
        stale_before = now - self.claim_ttl_seconds
        if self._memory:
            bucket, _order, lock = _memory_bucket(self.dsn)
            with lock:
                row = bucket.get(batch_id)
                if row is None:
                    return False
                owner = row.get("claimed_by")
                claimed_at = int(row.get("claimed_at") or 0)
                if owner and owner != self.worker_id and claimed_at >= stale_before:
                    return False
                row["claimed_by"] = self.worker_id
                row["claimed_at"] = now
            return True
        if not self.enabled:
            return True
        try:
            with self._pg_lock, self._pg_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE daari_batch_jobs
                        SET claimed_by = %s, claimed_at = %s
                        WHERE id = %s
                          AND status IN (%s, %s)
                          AND (
                            claimed_by IS NULL
                            OR claimed_by = %s
                            OR claimed_at IS NULL
                            OR claimed_at < %s
                          )
                        RETURNING id
                        """,
                        (
                            self.worker_id,
                            now,
                            batch_id,
                            STATUS_VALIDATING,
                            STATUS_IN_PROGRESS,
                            self.worker_id,
                            stale_before,
                        ),
                    )
                    won = cur.fetchone() is not None
                conn.commit()
            return won
        except Exception:
            return False

    def _heartbeat(self, batch_id: str) -> None:
        now = int(time.time())
        if self._memory:
            bucket, _order, lock = _memory_bucket(self.dsn)
            with lock:
                row = bucket.get(batch_id)
                if row is not None and row.get("claimed_by") == self.worker_id:
                    row["claimed_at"] = now
            return
        if not self.enabled:
            return
        try:
            with self._pg_lock, self._pg_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE daari_batch_jobs
                        SET claimed_at = %s
                        WHERE id = %s AND claimed_by = %s
                        """,
                        (now, batch_id, self.worker_id),
                    )
                conn.commit()
        except Exception:
            return

    def _release_claim(self, batch_id: str) -> None:
        if self._memory:
            bucket, _order, lock = _memory_bucket(self.dsn)
            with lock:
                row = bucket.get(batch_id)
                if row is not None and row.get("claimed_by") == self.worker_id:
                    row["claimed_by"] = None
                    row["claimed_at"] = None
            return
        if not self.enabled:
            return
        try:
            with self._pg_lock, self._pg_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE daari_batch_jobs
                        SET claimed_by = NULL, claimed_at = NULL
                        WHERE id = %s AND claimed_by = %s
                        """,
                        (batch_id, self.worker_id),
                    )
                conn.commit()
        except Exception:
            return

    async def run_job(self, batch_id: str, execute_one: Any) -> None:
        async with self._worker_sem:
            if not self._try_claim(batch_id):
                log_gateway_event(
                    "batch.claim_skipped",
                    {"batch_id": batch_id, "worker_id": self.worker_id},
                )
                return
            try:
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
                    {
                        "batch_id": job.id,
                        "total": len(job.items),
                        "worker_id": self.worker_id,
                    },
                )
                try:
                    for index in range(len(job.items)):
                        job = self.get(batch_id) or job
                        self._heartbeat(batch_id)
                        if job.cancel_requested:
                            self._mark_remaining_skipped(job)
                            break
                        if self._maybe_expire(job):
                            break
                        item = job.items[index]
                        if item.status != ITEM_PENDING:
                            continue
                        if not await self._wait_for_idle(job):
                            break
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
                            error_type = str(exc.error.get("type") or exc.error.get("code") or "")
                            if error_type == "budget_exceeded":
                                status_code = 402
                            elif error_type in {"rate_limit_error", "rate_limit"}:
                                status_code = 429
                            elif error_type == "model_not_allowed":
                                status_code = 403
                            else:
                                status_code = 400
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
                        except Exception as exc:  # noqa: BLE001
                            item.status = ITEM_FAILED
                            item.error = str(exc)[:500]
                            job.results.append(
                                {
                                    "id": f"batch_req_{uuid.uuid4().hex[:12]}",
                                    "custom_id": item.custom_id,
                                    "response": None,
                                    "error": {"message": str(exc)[:500]},
                                }
                            )
                        self._persist(job)

                    job = self.get(batch_id) or job
                    now = int(time.time())
                    if job.cancel_requested or job.status == STATUS_CANCELLING:
                        self._mark_remaining_skipped(job)
                        job.status = STATUS_CANCELLED
                        job.cancelled_at = now
                        job.cancelling_at = job.cancelling_at or now
                    elif job.status != STATUS_EXPIRED:
                        job.status = STATUS_COMPLETED
                        job.completed_at = now
                    self._write_result_files(job)
                    self._persist(job)
                    log_gateway_event(
                        "batch.finished",
                        {"batch_id": job.id, "status": job.status},
                    )
                finally:
                    self._running.discard(batch_id)
            finally:
                self._release_claim(batch_id)
