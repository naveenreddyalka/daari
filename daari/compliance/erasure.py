"""Subject erasure across durable stores (#1130).

``daari erase --key|--team|--user`` deletes matching rows. Audit rows are never
rewritten; a new ``compliance.erase`` event records the sweep.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

SubjectKind = Literal["key", "team", "user"]


@dataclass(frozen=True)
class ErasureSubject:
    kind: SubjectKind
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", (self.value or "").strip())
        if not self.value:
            raise ValueError(f"empty {self.kind} id")


@dataclass
class ErasureStoreResult:
    store: str
    matched: int
    deleted: int


@dataclass
class ErasureResult:
    subject: ErasureSubject
    dry_run: bool
    stores: list[ErasureStoreResult] = field(default_factory=list)

    def as_counts(self) -> dict[str, int]:
        return {row.store: row.deleted if not self.dry_run else row.matched for row in self.stores}


def erase_subject(
    settings: Any,
    subject: ErasureSubject,
    *,
    dry_run: bool = False,
    actor: str = "cli",
) -> ErasureResult:
    """Erase (or dry-run count) every store that holds data for ``subject``."""
    result = ErasureResult(subject=subject, dry_run=dry_run)
    result.stores.append(_erase_spend(settings, subject, dry_run=dry_run))
    result.stores.append(_erase_usage(settings, subject, dry_run=dry_run))
    result.stores.append(_erase_request_log(settings, subject, dry_run=dry_run))
    result.stores.append(_erase_responses(settings, subject, dry_run=dry_run))
    result.stores.append(_erase_files(settings, subject, dry_run=dry_run))
    result.stores.append(_erase_batches(settings, subject, dry_run=dry_run))
    result.stores.append(_erase_idempotency(settings, subject, dry_run=dry_run))
    result.stores.append(_erase_cache(settings, subject, dry_run=dry_run))

    if not dry_run:
        _record_audit(settings, subject, result, actor=actor)
    return result


def _record_audit(
    settings: Any,
    subject: ErasureSubject,
    result: ErasureResult,
    *,
    actor: str,
) -> None:
    try:
        from daari.enterprise.postgres_audit import audit_log_from_settings

        audit = audit_log_from_settings(settings)
    except Exception:
        return
    if audit is None or not getattr(audit, "enabled", False):
        return
    audit.record(
        actor=actor,
        role="admin",
        action="compliance.erase",
        detail={
            "subject_kind": subject.kind,
            "subject_id": subject.value,
            "stores": {
                row.store: {"matched": row.matched, "deleted": row.deleted}
                for row in result.stores
            },
        },
    )


def _erase_spend(settings: Any, subject: ErasureSubject, *, dry_run: bool) -> ErasureStoreResult:
    from daari.observability.spend import spend_ledger_from_settings

    spend = spend_ledger_from_settings(settings)
    if spend is None or not getattr(spend, "enabled", False):
        return ErasureStoreResult("spend", 0, 0)
    erase = getattr(spend, "erase_subject", None)
    if erase is None:
        return ErasureStoreResult("spend", 0, 0)
    matched = int(
        erase(
            key_id=subject.value if subject.kind == "key" else None,
            team_id=subject.value if subject.kind == "team" else None,
            client_id=subject.value if subject.kind == "user" else None,
            dry_run=dry_run,
        )
    )
    return ErasureStoreResult("spend", matched, 0 if dry_run else matched)


def _erase_usage(settings: Any, subject: ErasureSubject, *, dry_run: bool) -> ErasureStoreResult:
    from daari.observability.retention import _ledger

    ledger = _ledger(settings)
    if ledger is None or not getattr(ledger, "enabled", False):
        return ErasureStoreResult("ledger", 0, 0)
    erase = getattr(ledger, "erase_subject", None)
    if erase is None:
        return ErasureStoreResult("ledger", 0, 0)
    client_ids: list[str] | None = None
    user_id: str | None = None
    if subject.kind == "key":
        client_ids = [subject.value]
        # Also erase rows attributed via the key's client_id when known.
        extra = _client_ids_for_key(settings, subject.value)
        for cid in extra:
            if cid not in client_ids:
                client_ids.append(cid)
    elif subject.kind == "team":
        client_ids = _client_ids_for_team(settings, subject.value) or []
    else:
        user_id = subject.value
    matched = int(erase(client_ids=client_ids, user_id=user_id, dry_run=dry_run))
    return ErasureStoreResult("ledger", matched, 0 if dry_run else matched)


def _client_ids_for_key(settings: Any, key_id: str) -> list[str]:
    store = _vk_store(settings)
    if store is None:
        return []
    try:
        key = store.get_key(key_id)
    except Exception:
        return []
    if key is None:
        return []
    client = (getattr(key, "client_id", None) or "").strip()
    return [client] if client and client != key_id else []


def _client_ids_for_team(settings: Any, team_id: str) -> list[str]:
    store = _vk_store(settings)
    if store is None:
        return []
    try:
        return list(store.team_client_ids(team_id) or [])
    except Exception:
        return []


def _vk_store(settings: Any) -> Any | None:
    try:
        from daari.auth.postgres_virtual_keys import virtual_key_store_from_settings

        if not getattr(settings.server.virtual_keys, "enabled", False):
            return None
        return virtual_key_store_from_settings(settings)
    except Exception:
        return None


def _owner_key_ids(settings: Any, subject: ErasureSubject) -> list[str] | None:
    """Owner key ids to match for files/responses/idempotency, or None = skip."""
    if subject.kind == "key":
        return [subject.value]
    if subject.kind == "team":
        store = _vk_store(settings)
        if store is None:
            return []
        try:
            keys = [
                k.key_id
                for k in store.list()
                if getattr(k, "team_id", None) == subject.value
            ]
            return keys
        except Exception:
            return []
    return None  # user: no owner_key_id column


def _erase_request_log(
    settings: Any, subject: ErasureSubject, *, dry_run: bool
) -> ErasureStoreResult:
    from daari.gateway import request_log as rl

    path = Path(getattr(rl, "LOG_PATH", rl.DEFAULT_LOG_PATH))
    matched = rl.erase_subject_from_logs(
        path,
        kind=subject.kind,
        value=subject.value,
        dry_run=dry_run,
    )
    return ErasureStoreResult("request_log", matched, 0 if dry_run else matched)


def _erase_responses(
    settings: Any, subject: ErasureSubject, *, dry_run: bool
) -> ErasureStoreResult:
    owners = _owner_key_ids(settings, subject)
    if owners is None:
        return ErasureStoreResult("responses", 0, 0)
    if not owners and subject.kind == "team":
        return ErasureStoreResult("responses", 0, 0)
    store = _response_store(settings)
    if store is None:
        return ErasureStoreResult("responses", 0, 0)
    erase = getattr(store, "erase_owner_keys", None)
    if erase is None:
        return ErasureStoreResult("responses", 0, 0)
    matched = int(erase(owners, dry_run=dry_run))
    return ErasureStoreResult("responses", matched, 0 if dry_run else matched)


def _response_store(settings: Any) -> Any | None:
    responses_cfg = getattr(settings, "responses", None)
    if responses_cfg is None:
        return None
    pg_url = (getattr(settings.observability, "postgres_url", "") or "").strip()
    if getattr(responses_cfg, "backend", "sqlite") == "postgres" and pg_url:
        from daari.gateway.postgres_responses import PostgresResponseStore

        return PostgresResponseStore(
            pg_url, retention_days=getattr(responses_cfg, "retention_days", 0) or 0
        )
    from daari.gateway.response_store import ResponseStore

    traces_path = Path(settings.trace.path).expanduser()
    return ResponseStore(
        traces_path.parent / "responses.sqlite3",
        retention_days=getattr(responses_cfg, "retention_days", 0) or 0,
    )


def _erase_files(settings: Any, subject: ErasureSubject, *, dry_run: bool) -> ErasureStoreResult:
    owners = _owner_key_ids(settings, subject)
    if owners is None:
        return ErasureStoreResult("files", 0, 0)
    files_cfg = getattr(settings, "files", None)
    if files_cfg is None or not getattr(files_cfg, "enabled", True):
        return ErasureStoreResult("files", 0, 0)
    store = _file_store(settings)
    if store is None:
        return ErasureStoreResult("files", 0, 0)
    erase = getattr(store, "erase_owner_keys", None)
    if erase is None:
        return ErasureStoreResult("files", 0, 0)
    matched = int(erase(owners, dry_run=dry_run))
    return ErasureStoreResult("files", matched, 0 if dry_run else matched)


def _file_store(settings: Any) -> Any | None:
    files_cfg = getattr(settings, "files", None)
    if files_cfg is None:
        return None
    pg_url = (getattr(settings.observability, "postgres_url", "") or "").strip()
    if getattr(files_cfg, "backend", "sqlite") == "postgres" and pg_url:
        from daari.gateway.postgres_files import PostgresFileStore

        return PostgresFileStore(
            pg_url,
            max_bytes=files_cfg.max_bytes,
            retention_days=files_cfg.retention_days,
            max_total_bytes=files_cfg.max_total_bytes,
        )
    from daari.gateway.files import FileStore

    return FileStore(
        settings.files_store_path,
        max_bytes=files_cfg.max_bytes,
        retention_days=files_cfg.retention_days,
        max_total_bytes=files_cfg.max_total_bytes,
    )


def _erase_batches(settings: Any, subject: ErasureSubject, *, dry_run: bool) -> ErasureStoreResult:
    batches_cfg = getattr(settings, "batches", None)
    if batches_cfg is None or not getattr(batches_cfg, "enabled", True):
        return ErasureStoreResult("batches", 0, 0)
    from daari.gateway.batches import BatchStore

    path = getattr(settings, "batches_store_path", None)
    store = BatchStore(path=path)
    erase = getattr(store, "erase_subject", None)
    if erase is None:
        return ErasureStoreResult("batches", 0, 0)
    matched = int(
        erase(
            key_id=subject.value if subject.kind == "key" else None,
            team_id=subject.value if subject.kind == "team" else None,
            user=subject.value if subject.kind == "user" else None,
            dry_run=dry_run,
        )
    )
    return ErasureStoreResult("batches", matched, 0 if dry_run else matched)


def _erase_idempotency(
    settings: Any, subject: ErasureSubject, *, dry_run: bool
) -> ErasureStoreResult:
    owners = _owner_key_ids(settings, subject)
    if owners is None:
        return ErasureStoreResult("idempotency", 0, 0)
    store = _idem_store(settings)
    if store is None:
        return ErasureStoreResult("idempotency", 0, 0)
    erase = getattr(store, "erase_principals", None)
    if erase is None:
        return ErasureStoreResult("idempotency", 0, 0)
    principals = [f"vk:{oid}" for oid in owners]
    matched = int(erase(principals, dry_run=dry_run))
    return ErasureStoreResult("idempotency", matched, 0 if dry_run else matched)


def _idem_store(settings: Any) -> Any | None:
    cfg = getattr(settings, "idempotency", None)
    if cfg is None:
        return None
    ttl = int(getattr(cfg, "ttl_seconds", 86400) or 86400)
    pg_url = (getattr(settings.observability, "postgres_url", "") or "").strip()
    if getattr(cfg, "backend", "sqlite") == "postgres" and pg_url:
        from daari.gateway.postgres_idempotency import PostgresIdempotencyStore

        return PostgresIdempotencyStore(pg_url, ttl_seconds=ttl)
    from daari.gateway.idempotency_store import IdempotencyStore

    traces_path = Path(settings.trace.path).expanduser()
    return IdempotencyStore(traces_path.parent / "idempotency.sqlite3", ttl_seconds=ttl)


def _erase_cache(settings: Any, subject: ErasureSubject, *, dry_run: bool) -> ErasureStoreResult:
    if subject.kind == "user":
        return ErasureStoreResult("cache", 0, 0)
    if dry_run:
        return ErasureStoreResult("cache", 0, 0)
    removed = 0
    try:
        from daari.cache.exact import ExactCache

        l0 = ExactCache(
            settings.cache.l0.path,
            enabled=settings.cache.l0.enabled,
            ttl_seconds=settings.cache.l0.ttl_seconds,
        )
        if subject.kind == "key":
            removed += int(l0.invalidate(key_id=subject.value))
        else:
            removed += int(l0.invalidate(team_id=subject.value))
    except Exception:
        pass
    try:
        from daari.cache.semantic import SemanticCache

        class _NullEmbedder:
            model = "null"

            def embed(self, texts: list[str]) -> list[list[float]]:
                return [[0.0] for _ in texts]

        l1 = SemanticCache(
            settings.cache.l1.path,
            _NullEmbedder(),
            enabled=settings.cache.l1.enabled,
            similarity_threshold=settings.cache.l1.similarity_threshold,
            max_entries=settings.cache.l1.max_entries,
            ttl_seconds=settings.cache.l1.ttl_seconds,
        )
        if subject.kind == "key":
            removed += int(l1.invalidate(key_id=subject.value))
        else:
            removed += int(l1.invalidate(team_id=subject.value))
    except Exception:
        pass
    return ErasureStoreResult("cache", removed, removed)
