"""In-process MCP activity registry for admin list/force-abort (#1231).

Tracks request-scoped ``tools/call`` (and optional task) work — not sticky MCP
sessions. Abort cancels the registered awaitable so operators can kill hung
ingress work without a SaaS control plane.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from daari.gateway.request_log import log_gateway_event

AUDIT_ABORT_ACTION = "mcp.activity.abort"


@dataclass
class McpActivityEntry:
    request_id: str
    key_id: str | None
    principal: str | None
    method: str
    tool_name: str | None
    started_at: float = field(default_factory=time.time)
    task: asyncio.Task[Any] | None = None

    def as_public(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "key_id": self.key_id,
            "principal": self.principal,
            "method": self.method,
            "tool_name": self.tool_name,
            "started_at": self.started_at,
        }


def _rpc_key(rpc_id: Any) -> str:
    """Stable map key for a JSON-RPC request id (int or str)."""
    if rpc_id is None:
        return ""
    return f"rpc:{rpc_id!s}"


class McpActivityRegistry:
    """Thread-safe enough for a single-event-loop process (laptop / one replica)."""

    def __init__(self) -> None:
        self._entries: dict[str, McpActivityEntry] = {}
        self._rpc_index: dict[str, str] = {}  # rpc key -> request_id
        self._lock = asyncio.Lock()
        # Finished ids kept briefly so abort stays idempotent after unregister.
        self._finished: set[str] = set()
        self._finished_rpc: set[str] = set()

    def register(
        self,
        *,
        request_id: str,
        key_id: str | None = None,
        principal: str | None = None,
        method: str = "tools/call",
        tool_name: str | None = None,
        task: asyncio.Task[Any] | None = None,
        rpc_id: Any = None,
    ) -> McpActivityEntry:
        rid = (request_id or "").strip()
        if not rid:
            rid = f"anon-{id(task) if task is not None else id(object())}"
        entry = McpActivityEntry(
            request_id=rid,
            key_id=(key_id.strip() if isinstance(key_id, str) and key_id.strip() else None),
            principal=(
                principal.strip()
                if isinstance(principal, str) and principal.strip()
                else None
            ),
            method=method,
            tool_name=(
                tool_name.strip().lower()
                if isinstance(tool_name, str) and tool_name.strip()
                else None
            ),
            task=task,
        )
        self._finished.discard(rid)
        self._entries[rid] = entry
        rkey = _rpc_key(rpc_id)
        if rkey:
            self._finished_rpc.discard(rkey)
            self._rpc_index[rkey] = rid
        log_gateway_event(
            "mcp.activity_registered",
            {
                "request_id": rid,
                "method": method,
                "tool_name": entry.tool_name or "",
                "rpc_id": rpc_id if rpc_id is not None else "",
            },
        )
        return entry

    def bind_task(self, request_id: str, task: asyncio.Task[Any]) -> None:
        entry = self._entries.get(request_id)
        if entry is not None:
            entry.task = task

    def unregister(self, request_id: str) -> None:
        rid = (request_id or "").strip()
        if not rid:
            return
        if self._entries.pop(rid, None) is not None:
            self._finished.add(rid)
            stale = [k for k, v in self._rpc_index.items() if v == rid]
            for k in stale:
                self._rpc_index.pop(k, None)
                self._finished_rpc.add(k)
            log_gateway_event("mcp.activity_unregistered", {"request_id": rid})

    def list(self) -> list[dict[str, Any]]:
        return [e.as_public() for e in self._entries.values()]

    def get(self, request_id: str) -> McpActivityEntry | None:
        return self._entries.get((request_id or "").strip())

    def get_by_rpc_id(self, rpc_id: Any) -> McpActivityEntry | None:
        rid = self._rpc_index.get(_rpc_key(rpc_id))
        if not rid:
            return None
        return self._entries.get(rid)

    def abort(self, request_id: str) -> bool | None:
        """Cancel in-flight work.

        Returns:
            True — cancelled (or already finished; idempotent success).
            None — unknown request_id (caller should 404).
        """
        rid = (request_id or "").strip()
        if not rid:
            return None
        entry = self._entries.get(rid)
        if entry is None:
            if rid in self._finished:
                return True
            return None
        task = entry.task
        if task is not None and not task.done():
            task.cancel()
            log_gateway_event(
                "mcp.activity_aborted",
                {"request_id": rid, "tool_name": entry.tool_name or ""},
            )
        self._entries.pop(rid, None)
        self._finished.add(rid)
        stale = [k for k, v in self._rpc_index.items() if v == rid]
        for k in stale:
            self._rpc_index.pop(k, None)
            self._finished_rpc.add(k)
        return True

    def abort_by_rpc_id(self, rpc_id: Any) -> bool | None:
        """Cancel via MCP ``notifications/cancelled`` requestId (#2265).

        Returns True if cancelled or already finished; None if unknown.
        """
        rkey = _rpc_key(rpc_id)
        if not rkey:
            return None
        rid = self._rpc_index.get(rkey)
        if rid is None:
            if rkey in self._finished_rpc:
                return True
            return None
        result = self.abort(rid)
        if result is True:
            log_gateway_event(
                "mcp.request_cancelled",
                {"rpc_id": rpc_id, "request_id": rid},
            )
        return result

def principal_from_claims(claims: Any) -> tuple[str | None, str | None]:
    """Return ``(key_id, principal)`` for registry rows."""
    if claims is None:
        return None, None
    kind = getattr(claims, "kind", "") or ""
    key = getattr(claims, "virtual_key", None)
    if kind == "virtual" and key is not None:
        key_id = str(getattr(key, "key_id", "") or "") or None
        return key_id, key_id
    if kind == "master":
        return None, "master"
    client_id = getattr(claims, "client_id", None) or getattr(claims, "key_id", None)
    if client_id:
        return str(client_id), str(client_id)
    return None, (kind or None)


async def track_awaitable(
    registry: McpActivityRegistry,
    awaitable: Any,
    *,
    request_id: str,
    key_id: str | None,
    principal: str | None,
    method: str,
    tool_name: str | None,
    rpc_id: Any = None,
) -> Any:
    """Register *awaitable* as a Task, await it, and always unregister."""
    task: asyncio.Task[Any] = asyncio.ensure_future(awaitable)
    registry.register(
        request_id=request_id,
        key_id=key_id,
        principal=principal,
        method=method,
        tool_name=tool_name,
        task=task,
        rpc_id=rpc_id,
    )
    try:
        return await task
    finally:
        registry.unregister(request_id)
