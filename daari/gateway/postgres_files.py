"""Postgres-backed Files API store for cross-replica fleets (issue #465).

Duck-types FileStore. Content lives in BYTEA (bounded by files.max_bytes).
DSN is ``observability.postgres_url``. ``memory:<name>`` is an in-process
shared backend for unit tests (no live Postgres required).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any, Iterable

from daari.gateway.files import (
    DEFAULT_MAX_BYTES,
    FileStoreFull,
    StoredFile,
    parse_expires_after,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daari_files (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    purpose TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    created_at BIGINT NOT NULL,
    owner_key_id TEXT,
    expires_at BIGINT,
    content BYTEA NOT NULL
);
"""

# dsn -> {file_id: row_dict} shared across PostgresFileStore instances.
_MEMORY_FILES: dict[str, dict[str, dict[str, Any]]] = {}
_MEMORY_LOCKS: dict[str, threading.Lock] = {}
_MEMORY_META_LOCK = threading.Lock()


def _memory_bucket(dsn: str) -> tuple[dict[str, dict[str, Any]], threading.Lock]:
    with _MEMORY_META_LOCK:
        if dsn not in _MEMORY_FILES:
            _MEMORY_FILES[dsn] = {}
            _MEMORY_LOCKS[dsn] = threading.Lock()
        return _MEMORY_FILES[dsn], _MEMORY_LOCKS[dsn]


class PostgresFileStore:
    """Shared file registry + content for multi-replica gateways (#465)."""

    def __init__(
        self,
        dsn: str,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        retention_days: int = 0,
        max_total_bytes: int = 0,
        enabled: bool = True,
    ) -> None:
        self.dsn = dsn
        self.path = dsn  # compatibility with loggers that read store.path
        self.max_bytes = max(1, int(max_bytes))
        self.retention_days = max(0, int(retention_days))
        self.max_total_bytes = max(0, int(max_total_bytes))
        self.enabled = enabled
        self._lock = threading.Lock()
        self._memory = dsn.startswith("memory:")
        if self.enabled and not self._memory:
            try:
                with self._connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(_SCHEMA)
                    conn.commit()
            except Exception:
                self.enabled = False

    def _connect(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "files.backend=postgres requires psycopg — "
                "pip install 'psycopg[binary]>=3' (or daari[postgres])"
            ) from exc
        return psycopg.connect(self.dsn)

    def _resolve_expires_at(
        self,
        *,
        created_at: int,
        expires_after_seconds: int | None,
    ) -> int | None:
        if expires_after_seconds is not None:
            return int(created_at) + int(expires_after_seconds)
        if self.retention_days > 0:
            return int(created_at) + self.retention_days * 86400
        return None

    def _row_to_stored(self, row: dict[str, Any]) -> StoredFile:
        return StoredFile(
            id=str(row["id"]),
            filename=str(row["filename"]),
            purpose=str(row["purpose"]),
            bytes=int(row["bytes"]),
            created_at=int(row["created_at"]),
            path=None,
            owner_key_id=row.get("owner_key_id"),
            expires_at=row.get("expires_at"),
        )

    def total_bytes(self) -> int:
        if not self.enabled:
            return 0
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                return sum(int(row["bytes"]) for row in bucket.values())
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COALESCE(SUM(bytes), 0) FROM daari_files")
                    row = cur.fetchone()
                    return int(row[0] if row else 0)
        except Exception:
            return 0

    def create(
        self,
        *,
        content: bytes,
        filename: str,
        purpose: str = "batch",
        owner_key_id: str | None = None,
        expires_after: Any | None = None,
        expires_after_seconds: int | None = None,
    ) -> StoredFile:
        if not self.enabled and not self._memory:
            raise RuntimeError("postgres file store is disabled")
        if len(content) > self.max_bytes:
            raise ValueError(
                f"file exceeds max size of {self.max_bytes} bytes "
                f"({len(content)} bytes uploaded)"
            )
        if expires_after_seconds is None and expires_after is not None:
            expires_after_seconds = parse_expires_after(expires_after)
        current = self.total_bytes()
        if self.max_total_bytes > 0 and current + len(content) > self.max_total_bytes:
            raise FileStoreFull(
                max_total_bytes=self.max_total_bytes,
                current_bytes=current,
                incoming_bytes=len(content),
            )
        file_id = f"file-{uuid.uuid4().hex}"
        created_at = int(time.time())
        expires_at = self._resolve_expires_at(
            created_at=created_at,
            expires_after_seconds=expires_after_seconds,
        )
        row = {
            "id": file_id,
            "filename": filename or "upload",
            "purpose": purpose or "batch",
            "bytes": len(content),
            "created_at": created_at,
            "owner_key_id": owner_key_id,
            "expires_at": expires_at,
            "content": bytes(content),
        }
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                bucket[file_id] = row
            return self._row_to_stored(row)
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO daari_files
                      (id, filename, purpose, bytes, created_at, owner_key_id, expires_at, content)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        file_id,
                        row["filename"],
                        row["purpose"],
                        row["bytes"],
                        created_at,
                        owner_key_id,
                        expires_at,
                        content,
                    ),
                )
            conn.commit()
        return self._row_to_stored(row)

    def get(self, file_id: str, *, now: int | None = None) -> StoredFile | None:
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                row = bucket.get(file_id)
            if row is None:
                return None
            stored = self._row_to_stored(row)
            if stored.is_expired(now=now):
                self.delete(file_id)
                return None
            return stored
        if not self.enabled:
            return None
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, filename, purpose, bytes, created_at,
                               owner_key_id, expires_at
                        FROM daari_files WHERE id = %s
                        """,
                        (file_id,),
                    )
                    found = cur.fetchone()
            if found is None:
                return None
            stored = StoredFile(
                id=found[0],
                filename=found[1],
                purpose=found[2],
                bytes=int(found[3]),
                created_at=int(found[4]),
                path=None,
                owner_key_id=found[5],
                expires_at=found[6],
            )
            if stored.is_expired(now=now):
                self.delete(file_id)
                return None
            return stored
        except Exception:
            return None

    def list_files(
        self,
        *,
        purpose: str | None = None,
        limit: int = 10000,
        owner_key_id: str | None = None,
        now: int | None = None,
    ) -> list[StoredFile]:
        self.prune_expired(now=now)
        limit_n = max(1, min(limit, 10000))
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                rows = sorted(bucket.values(), key=lambda r: int(r["created_at"]), reverse=True)
            out: list[StoredFile] = []
            for row in rows:
                stored = self._row_to_stored(row)
                if purpose and stored.purpose != purpose:
                    continue
                if owner_key_id is not None and stored.owner_key_id != owner_key_id:
                    continue
                out.append(stored)
                if len(out) >= limit_n:
                    break
            return out
        if not self.enabled:
            return []
        try:
            clauses = ["1=1"]
            params: list[Any] = []
            if purpose:
                clauses.append("purpose = %s")
                params.append(purpose)
            if owner_key_id is not None:
                clauses.append("owner_key_id = %s")
                params.append(owner_key_id)
            params.append(limit_n)
            sql = (
                "SELECT id, filename, purpose, bytes, created_at, owner_key_id, expires_at"
                f" FROM daari_files WHERE {' AND '.join(clauses)}"
                " ORDER BY created_at DESC LIMIT %s"
            )
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    found = cur.fetchall()
            return [
                StoredFile(
                    id=row[0],
                    filename=row[1],
                    purpose=row[2],
                    bytes=int(row[3]),
                    created_at=int(row[4]),
                    path=None,
                    owner_key_id=row[5],
                    expires_at=row[6],
                )
                for row in found
            ]
        except Exception:
            return []

    def read_bytes(self, file_id: str, *, now: int | None = None) -> bytes | None:
        stored = self.get(file_id, now=now)
        if stored is None:
            return None
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                row = bucket.get(file_id)
            return None if row is None else bytes(row["content"])
        if not self.enabled:
            return None
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT content FROM daari_files WHERE id = %s", (file_id,))
                    found = cur.fetchone()
            if found is None:
                return None
            return bytes(found[0])
        except Exception:
            return None

    def read_text(self, file_id: str, *, now: int | None = None) -> str | None:
        raw = self.read_bytes(file_id, now=now)
        if raw is None:
            return None
        return raw.decode("utf-8")

    def delete(self, file_id: str) -> bool:
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                return bucket.pop(file_id, None) is not None
        if not self.enabled:
            return False
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM daari_files WHERE id = %s", (file_id,))
                    deleted = cur.rowcount > 0
                conn.commit()
            return deleted
        except Exception:
            return False

    def prune_expired(self, *, now: int | None = None, dry_run: bool = False) -> int:
        stamp = int(now if now is not None else time.time())
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                expired = [
                    fid
                    for fid, row in list(bucket.items())
                    if row.get("expires_at") is not None and int(row["expires_at"]) <= stamp
                ]
            if dry_run:
                return len(expired)
            for fid in expired:
                self.delete(fid)
            return len(expired)
        if not self.enabled:
            return 0
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id FROM daari_files WHERE expires_at IS NOT NULL AND expires_at <= %s",
                        (stamp,),
                    )
                    expired = [row[0] for row in cur.fetchall()]
                    if dry_run:
                        return len(expired)
                    if expired:
                        cur.execute(
                            "DELETE FROM daari_files WHERE expires_at IS NOT NULL AND expires_at <= %s",
                            (stamp,),
                        )
                conn.commit()
            return len(expired)
        except Exception:
            return 0

    def write_jsonl(
        self,
        *,
        lines: Iterable[dict[str, Any]],
        filename: str,
        purpose: str,
        owner_key_id: str | None = None,
        expires_after_seconds: int | None = None,
    ) -> StoredFile:
        body = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
        return self.create(
            content=body.encode("utf-8"),
            filename=filename,
            purpose=purpose,
            owner_key_id=owner_key_id,
            expires_after_seconds=expires_after_seconds,
        )
