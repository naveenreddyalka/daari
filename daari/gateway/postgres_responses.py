"""Postgres-backed Responses store for cross-replica fleets (issue #481, #497).

Duck-types ResponseStore (put/get + owner_key_id semantics from #453).
DSN is ``observability.postgres_url``. ``memory:<name>`` is an in-process
shared backend for unit tests (no live Postgres required).
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from daari.security.at_rest import loads_json_maybe_sealed, seal_text

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daari_responses (
    response_id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    conversation TEXT NOT NULL,
    stored INTEGER NOT NULL,
    owner_key_id TEXT,
    created_at BIGINT NOT NULL DEFAULT 0,
    job_owner TEXT,
    lease_expires_at BIGINT
);
"""

_MIGRATE_CREATED_AT = """
ALTER TABLE daari_responses ADD COLUMN IF NOT EXISTS created_at BIGINT NOT NULL DEFAULT 0;
"""

_MIGRATE_JOB_OWNER = """
ALTER TABLE daari_responses ADD COLUMN IF NOT EXISTS job_owner TEXT;
"""

_MIGRATE_LEASE = """
ALTER TABLE daari_responses ADD COLUMN IF NOT EXISTS lease_expires_at BIGINT;
"""

# dsn -> {response_id: row_dict} shared across PostgresResponseStore instances.
_MEMORY_RESPONSES: dict[str, dict[str, dict[str, Any]]] = {}
_MEMORY_LOCKS: dict[str, threading.Lock] = {}
_MEMORY_META_LOCK = threading.Lock()


def _memory_bucket(dsn: str) -> tuple[dict[str, dict[str, Any]], threading.Lock]:
    with _MEMORY_META_LOCK:
        if dsn not in _MEMORY_RESPONSES:
            _MEMORY_RESPONSES[dsn] = {}
            _MEMORY_LOCKS[dsn] = threading.Lock()
        return _MEMORY_RESPONSES[dsn], _MEMORY_LOCKS[dsn]


class PostgresResponseStore:
    """Shared Responses objects for multi-replica gateways (#481)."""

    def __init__(
        self, dsn: str, *, enabled: bool = True, retention_days: int = 0
    ) -> None:
        self.dsn = dsn
        self.path = dsn
        self.enabled = enabled
        self.retention_days = max(0, int(retention_days))
        self._lock = threading.Lock()
        self._memory = dsn.startswith("memory:")
        if self.enabled and not self._memory:
            try:
                with self._connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(_SCHEMA)
                        for stmt in (
                            _MIGRATE_CREATED_AT,
                            _MIGRATE_JOB_OWNER,
                            _MIGRATE_LEASE,
                        ):
                            try:
                                cur.execute(stmt)
                            except Exception:
                                pass
                    conn.commit()
            except Exception:
                self.enabled = False

    def _connect(self) -> Any:
        from daari.gateway.pg_pool import pooled_connection

        return pooled_connection(self.dsn)

    def put(
        self,
        response_id: str,
        body: dict[str, Any],
        *,
        conversation: list[dict[str, Any]] | None = None,
        stored: bool = True,
        owner_key_id: str | None = None,
        job_owner: str | None = None,
        lease_expires_at: int | None = None,
    ) -> None:
        if not stored or not self.enabled:
            return
        body_json = seal_text(json.dumps(body))
        conversation_json = seal_text(json.dumps(conversation or []))
        now = int(time.time())
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                existing = bucket.get(response_id)
                created_at = now
                if existing is not None:
                    if owner_key_id is None:
                        owner_key_id = existing.get("owner_key_id")
                    if existing.get("created_at"):
                        created_at = int(existing["created_at"])
                    if job_owner is None:
                        job_owner = existing.get("job_owner")
                    if lease_expires_at is None:
                        lease_expires_at = existing.get("lease_expires_at")
                bucket[response_id] = {
                    "body": body_json,
                    "conversation": conversation_json,
                    "stored": 1,
                    "owner_key_id": owner_key_id,
                    "created_at": created_at,
                    "job_owner": job_owner,
                    "lease_expires_at": lease_expires_at,
                }
            return
        with self._lock:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT owner_key_id, created_at, job_owner, lease_expires_at"
                        " FROM daari_responses WHERE response_id = %s",
                        (response_id,),
                    )
                    row = cur.fetchone()
                    created_at = now
                    if row is not None:
                        if owner_key_id is None:
                            owner_key_id = row[0]
                        if row[1]:
                            created_at = int(row[1])
                        if job_owner is None:
                            job_owner = row[2]
                        if lease_expires_at is None:
                            lease_expires_at = row[3]
                    cur.execute(
                        "INSERT INTO daari_responses"
                        " (response_id, body, conversation, stored, owner_key_id,"
                        "  created_at, job_owner, lease_expires_at)"
                        " VALUES (%s, %s, %s, 1, %s, %s, %s, %s)"
                        " ON CONFLICT (response_id) DO UPDATE SET"
                        " body = EXCLUDED.body,"
                        " conversation = EXCLUDED.conversation,"
                        " stored = 1,"
                        " owner_key_id = EXCLUDED.owner_key_id,"
                        " created_at = daari_responses.created_at,"
                        " job_owner = EXCLUDED.job_owner,"
                        " lease_expires_at = EXCLUDED.lease_expires_at",
                        (
                            response_id,
                            body_json,
                            conversation_json,
                            owner_key_id,
                            created_at,
                            job_owner,
                            lease_expires_at,
                        ),
                    )
                conn.commit()

    def get(self, response_id: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                row = bucket.get(response_id)
                if row is None:
                    return None
                body = loads_json_maybe_sealed(row["body"])
                if not isinstance(body, dict):
                    body = {}
                conversation = loads_json_maybe_sealed(row["conversation"])
                body["_conversation"] = (
                    conversation if isinstance(conversation, list) else []
                )
                body["_owner_key_id"] = row.get("owner_key_id")
                body["_job_owner"] = row.get("job_owner")
                body["_lease_expires_at"] = row.get("lease_expires_at")
                return body
        with self._lock:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT body, conversation, owner_key_id, job_owner,"
                        " lease_expires_at FROM daari_responses"
                        " WHERE response_id = %s",
                        (response_id,),
                    )
                    row = cur.fetchone()
        if row is None:
            return None
        body = loads_json_maybe_sealed(row[0])
        if not isinstance(body, dict):
            body = {}
        conversation = loads_json_maybe_sealed(row[1])
        body["_conversation"] = conversation if isinstance(conversation, list) else []
        body["_owner_key_id"] = row[2]
        body["_job_owner"] = row[3]
        body["_lease_expires_at"] = row[4]
        return body

    def delete(self, response_id: str) -> bool:
        if not self.enabled:
            return False
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                return bucket.pop(response_id, None) is not None
        with self._lock:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM daari_responses WHERE response_id = %s",
                        (response_id,),
                    )
                    deleted = cur.rowcount > 0
                conn.commit()
                return deleted

    def erase_owner_keys(self, owner_key_ids: list[str], *, dry_run: bool = False) -> int:
        ids = [str(i).strip() for i in owner_key_ids if str(i).strip()]
        if not ids or not self.enabled:
            return 0
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                doomed = [
                    rid
                    for rid, row in bucket.items()
                    if (row.get("owner_key_id") or "") in ids
                ]
                if dry_run:
                    return len(doomed)
                for rid in doomed:
                    bucket.pop(rid, None)
                return len(doomed)
        placeholders = ",".join("%s" for _ in ids)
        with self._lock:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"SELECT COUNT(*) FROM daari_responses WHERE owner_key_id IN ({placeholders})",
                        ids,
                    )
                    count = int(cur.fetchone()[0] or 0)
                    if dry_run or count == 0:
                        return count
                    cur.execute(
                        f"DELETE FROM daari_responses WHERE owner_key_id IN ({placeholders})",
                        ids,
                    )
                conn.commit()
                return count

    def prune_older_than(self, cutoff_epoch: float, *, dry_run: bool = False) -> int:
        """Delete (or count) responses with created_at <= cutoff (#497)."""
        if not self.enabled:
            return 0
        cutoff = int(cutoff_epoch)
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                doomed = [
                    rid
                    for rid, row in bucket.items()
                    if int(row.get("created_at") or 0) > 0
                    and int(row.get("created_at") or 0) <= cutoff
                ]
                if dry_run:
                    return len(doomed)
                for rid in doomed:
                    del bucket[rid]
                return len(doomed)
        with self._lock:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM daari_responses"
                        " WHERE created_at > 0 AND created_at <= %s",
                        (cutoff,),
                    )
                    count = int(cur.fetchone()[0])
                    if dry_run or count == 0:
                        conn.commit()
                        return count
                    cur.execute(
                        "DELETE FROM daari_responses"
                        " WHERE created_at > 0 AND created_at <= %s",
                        (cutoff,),
                    )
                conn.commit()
                return count
