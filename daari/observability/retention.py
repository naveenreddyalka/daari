"""Retention / prune for traces, ledger, audit, shadow checks, and MCP tasks (#332).

Defaults are 0 (keep forever) so an upgrade never silently deletes data.
Sweep failures are logged and never raised onto the request path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

RETENTION_SWEEP_SECONDS = 86400


@dataclass
class PruneResult:
    store: str
    deleted: int
    skipped: bool
    cutoff: str | None = None


def _now(now: datetime | None) -> datetime:
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _cutoff_iso(days: int, now: datetime) -> str:
    return (now - timedelta(days=days)).isoformat()


def _cutoff_day(days: int, now: datetime) -> str:
    return (now - timedelta(days=days)).strftime("%Y-%m-%d")


def _trace_store(settings: Any):
    if getattr(settings.observability, "backend", "sqlite") == "postgres":
        from daari.observability.postgres_trace import PostgresTraceStore

        return PostgresTraceStore(
            settings.observability.postgres_url,
            enabled=settings.trace.enabled,
            max_entries=settings.trace.max_entries,
        )
    from daari.observability.trace import TraceStore

    return TraceStore(
        settings.trace.path, enabled=settings.trace.enabled, max_entries=settings.trace.max_entries
    )


def _ledger(settings: Any):
    if getattr(settings.observability, "backend", "sqlite") == "postgres":
        from daari.observability.postgres_usage import PostgresUsageLedger

        return PostgresUsageLedger(settings.observability.postgres_url, enabled=settings.usage.enabled)
    from daari.observability.usage import UsageLedger

    return UsageLedger(settings.usage.path, enabled=settings.usage.enabled)


def prune_all(
    settings: Any,
    *,
    dry_run: bool = False,
    now: datetime | None = None,
) -> list[PruneResult]:
    """Prune every store whose retention days > 0. Order leaves the audit
    summary row (written last) inside the kept window."""
    current = _now(now)
    retention = settings.observability.retention
    results: list[PruneResult] = []

    if retention.traces_days:
        cutoff = _cutoff_iso(retention.traces_days, current)
        deleted = _trace_store(settings).prune_before(cutoff, dry_run=dry_run)
        results.append(PruneResult("traces", deleted, False, cutoff))
    else:
        results.append(PruneResult("traces", 0, True))

    if retention.ledger_days:
        cutoff = _cutoff_day(retention.ledger_days, current)
        deleted = _ledger(settings).prune_before_day(cutoff, dry_run=dry_run)
        results.append(PruneResult("ledger", deleted, False, cutoff))
    else:
        results.append(PruneResult("ledger", 0, True))

    if retention.shadow_days:
        from daari.learning.feedback import FeedbackStore

        cutoff = _cutoff_iso(retention.shadow_days, current)
        deleted = FeedbackStore(settings.learning.path, enabled=settings.learning.enabled).prune_shadow_before(
            cutoff, dry_run=dry_run
        )
        results.append(PruneResult("shadow", deleted, False, cutoff))
    else:
        results.append(PruneResult("shadow", 0, True))

    if retention.tasks_days:
        from daari.gateway.mcp_tasks import McpTaskStore

        cutoff_epoch = (current - timedelta(days=retention.tasks_days)).timestamp()
        deleted = McpTaskStore(settings.integrations.mcp_tasks.path).prune_older_than(
            cutoff_epoch, dry_run=dry_run
        )
        results.append(
            PruneResult(
                "tasks",
                deleted,
                False,
                datetime.fromtimestamp(cutoff_epoch, timezone.utc).isoformat(),
            )
        )
    else:
        results.append(PruneResult("tasks", 0, True))

    from daari.enterprise.audit import AuditLog

    audit = AuditLog(settings.enterprise.audit_path)
    if retention.audit_days:
        cutoff = _cutoff_iso(retention.audit_days, current)
        deleted = audit.prune_before(cutoff, dry_run=dry_run)
        results.append(PruneResult("audit", deleted, False, cutoff))
        if not dry_run:
            audit.record(
                actor="daari",
                role="system",
                action="retention.prune",
                detail={
                    row.store: {"deleted": row.deleted, "skipped": row.skipped, "cutoff": row.cutoff}
                    for row in results
                },
            )
    else:
        results.append(PruneResult("audit", 0, True))

    return results


def run_sweep(
    settings: Any,
    *,
    now: datetime | None = None,
    dry_run: bool = False,
) -> list[PruneResult]:
    from daari.gateway.request_log import log_gateway_event

    try:
        results = prune_all(settings, dry_run=dry_run, now=now)
    except Exception as exc:
        log_gateway_event(
            "retention.sweep_failed",
            {"error": f"{type(exc).__name__}: {exc}"},
        )
        return []
    log_gateway_event(
        "retention.sweep",
        {
            "dry_run": dry_run,
            "stores": {
                row.store: {"deleted": row.deleted, "skipped": row.skipped} for row in results
            },
        },
    )
    return results
