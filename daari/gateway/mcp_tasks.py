"""MCP Tasks extension (SEP-2663 / protocol 2026-07-28) — issue #289.

When a client opts in via `_meta["io.modelcontextprotocol/tasks"]` and the tool
is eligible (marked long-running or threshold policy), `tools/call` returns a
task handle and execution continues in the background. Clients that do not
opt in keep the blocking path.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from daari.gateway.request_log import log_gateway_event

TASKS_CAPABILITY = "io.modelcontextprotocol/tasks"
TASKS_META_KEY = "io.modelcontextprotocol/tasks"

STATUS_WORKING = "working"
STATUS_INPUT_REQUIRED = "input_required"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


@dataclass
class McpTask:
    task_id: str
    tool: str
    status: str = STATUS_WORKING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    result: Any = None
    error: str | None = None
    cancel_requested: bool = False


class McpTaskStore:
    """In-process task registry with optional diskcache durability."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._tasks: dict[str, McpTask] = {}
        self._lock = asyncio.Lock()
        self._disk: Any = None
        if path:
            import diskcache

            Path(path).expanduser().mkdir(parents=True, exist_ok=True)
            self._disk = diskcache.Cache(str(Path(path).expanduser()))

    def create(self, *, tool: str) -> McpTask:
        task = McpTask(task_id=f"task_{uuid.uuid4().hex}", tool=tool)
        self._tasks[task.task_id] = task
        self._persist(task)
        log_gateway_event(
            "mcp.task_created",
            {"task_id": task.task_id, "tool": tool, "status": task.status},
        )
        return task

    def get(self, task_id: str) -> McpTask | None:
        task = self._tasks.get(task_id)
        if task is not None:
            return task
        if self._disk is None:
            return None
        raw = self._disk.get(task_id)
        if not isinstance(raw, dict):
            return None
        task = McpTask(
            task_id=raw["task_id"],
            tool=raw.get("tool") or "",
            status=raw.get("status") or STATUS_WORKING,
            created_at=float(raw.get("created_at") or time.time()),
            updated_at=float(raw.get("updated_at") or time.time()),
            result=raw.get("result"),
            error=raw.get("error"),
            cancel_requested=bool(raw.get("cancel_requested")),
        )
        self._tasks[task_id] = task
        return task

    def request_cancel(self, task_id: str) -> McpTask | None:
        task = self.get(task_id)
        if task is None:
            return None
        if task.status in {STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED}:
            return task
        task.cancel_requested = True
        task.status = STATUS_CANCELLED
        task.updated_at = time.time()
        self._persist(task)
        log_gateway_event(
            "mcp.task_cancelled",
            {"task_id": task.task_id, "tool": task.tool},
        )
        return task

    def complete(self, task_id: str, result: Any) -> None:
        task = self.get(task_id)
        if task is None or task.status == STATUS_CANCELLED:
            return
        task.status = STATUS_COMPLETED
        task.result = result
        task.updated_at = time.time()
        self._persist(task)
        log_gateway_event(
            "mcp.task_completed",
            {"task_id": task.task_id, "tool": task.tool},
        )

    def fail(self, task_id: str, error: str) -> None:
        task = self.get(task_id)
        if task is None or task.status == STATUS_CANCELLED:
            return
        task.status = STATUS_FAILED
        task.error = error
        task.updated_at = time.time()
        self._persist(task)
        log_gateway_event(
            "mcp.task_failed",
            {"task_id": task.task_id, "tool": task.tool, "error": error[:200]},
        )

    def as_public(self, task: McpTask) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "taskId": task.task_id,
            "status": task.status,
            "tool": task.tool,
            "createdAt": task.created_at,
            "updatedAt": task.updated_at,
        }
        if task.status == STATUS_COMPLETED:
            payload["result"] = task.result
        if task.status == STATUS_FAILED and task.error:
            payload["error"] = task.error
        if task.status == STATUS_INPUT_REQUIRED:
            payload["status"] = STATUS_INPUT_REQUIRED
        return payload

    def _persist(self, task: McpTask) -> None:
        if self._disk is None:
            return
        self._disk.set(
            task.task_id,
            {
                "task_id": task.task_id,
                "tool": task.tool,
                "status": task.status,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "result": task.result,
                "error": task.error,
                "cancel_requested": task.cancel_requested,
            },
        )


def client_opted_into_tasks(params: dict[str, Any] | None) -> bool:
    if not isinstance(params, dict):
        return False
    meta = params.get("_meta")
    if not isinstance(meta, dict):
        return False
    flag = meta.get(TASKS_META_KEY)
    return flag is True or isinstance(flag, dict)


def tool_should_become_task(
    tool: str,
    *,
    long_running_tools: list[str],
    threshold_ms: int,
) -> bool:
    """Eligible when marked long-running, or threshold_ms > 0 (all tools)."""
    name = tool.strip().lower()
    marked = {item.strip().lower() for item in long_running_tools}
    if name in marked:
        return True
    return threshold_ms > 0


def initialize_capabilities(protocol_version: str) -> dict[str, Any]:
    caps: dict[str, Any] = {"tools": {"listChanged": False}}
    if protocol_version >= "2026-07-28":
        caps[TASKS_CAPABILITY] = {"listChanged": False}
    return caps


def create_task_result(task: McpTask) -> dict[str, Any]:
    return {"taskId": task.task_id, "status": task.status}


async def spawn_tool_task(
    store: McpTaskStore,
    task: McpTask,
    runner: Callable[[], Awaitable[Any]],
) -> None:
    """Run runner in the background and record completion / failure / cancel."""

    async def _wrap() -> None:
        try:
            if task.cancel_requested:
                return
            result = await runner()
            if task.cancel_requested or store.get(task.task_id) is None:
                return
            current = store.get(task.task_id)
            if current is not None and current.status == STATUS_CANCELLED:
                return
            store.complete(task.task_id, result)
        except Exception as exc:  # noqa: BLE001 — surface as task failure
            store.fail(task.task_id, str(exc)[:200])

    asyncio.create_task(_wrap())
