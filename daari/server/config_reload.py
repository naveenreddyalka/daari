"""Hot-reload Settings from config.yaml without a process restart (#1234).

`POST /v1/daari/reload-config` and SIGHUP both call `reload_config`. A fresh
`Settings` is loaded from disk; the safe live-tune subset (the same fields
`PATCH /v1/daari/config` owns) is applied in place through
`apply_live_config`, everything else that differs is reported as
`requires_restart`. Loading never touches live settings, so a bad file is a
400 with the previous settings intact.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from daari.config.ownership import (
    _FIELD_PATHS,
    _MISSING,
    _live_leaf,
    _values_equal,
    config_file_path,
    field_key,
    live_config_payload,
)

_SIGHUP = getattr(signal, "SIGHUP", None)

_SETTINGS_PATH_ALIASES: dict[str, str] = {
    "cache.l0_ttl_seconds": "cache.l0.ttl_seconds",
    "cache.l1_ttl_seconds": "cache.l1.ttl_seconds",
    "cache.l1_similarity_threshold": "cache.l1.similarity_threshold",
}
_MCP_SERVERS_KEY = "integrations.mcp_servers"
_SKILLS_KEY = "skills_system_prefix"
_MCP_CEILING_FIELDS = frozenset({"rpm", "tpm"})


class ConfigReloadError(ValueError):
    """config.yaml could not be loaded; live settings were left untouched."""


@dataclass
class SettingsDiff:
    patch: dict[str, Any] = field(default_factory=dict)
    changed_keys: list[str] = field(default_factory=list)
    requires_restart: list[str] = field(default_factory=list)
    skills_system_prefix: str | None = None


def _safe_settings_paths() -> tuple[str, ...]:
    return tuple(
        _SETTINGS_PATH_ALIASES.get(field_key(parts), field_key(parts)) for parts in _FIELD_PATHS
    )


def _flatten(node: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(node, dict) and node:
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict) and value:
                out.update(_flatten(value, path))
            else:
                out[path] = value
        return out
    if prefix:
        out[prefix] = node
    return out


def _under(path: str, roots: tuple[str, ...]) -> bool:
    return any(path == root or path.startswith(root + ".") for root in roots)


def _set_nested(target: dict[str, Any], parts: tuple[str, ...], value: Any) -> None:
    cur = target
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def _mcp_servers_non_ceiling(servers: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for entry in list(servers or []):
        row = dict(entry) if isinstance(entry, dict) else entry.model_dump()
        server_id = str(row.get("id") or "").strip()
        if server_id:
            out[server_id] = {k: v for k, v in row.items() if k not in _MCP_CEILING_FIELDS}
    return out


def diff_settings(current: Any, fresh: Any) -> SettingsDiff:
    """Split `fresh` vs `current` into a live-applicable patch and restart keys."""
    diff = SettingsDiff()
    live_now = live_config_payload(current)
    live_new = live_config_payload(fresh)
    mcp_live_safe = _mcp_servers_non_ceiling(
        current.integrations.mcp_servers
    ) == _mcp_servers_non_ceiling(fresh.integrations.mcp_servers)
    for parts in _FIELD_PATHS:
        key = field_key(parts)
        before = _live_leaf(live_now, parts)
        after = _live_leaf(live_new, parts)
        if before is _MISSING or after is _MISSING or _values_equal(before, after):
            continue
        if key == _MCP_SERVERS_KEY and not mcp_live_safe:
            continue
        _set_nested(diff.patch, parts, after)
        diff.changed_keys.append(key)

    safe_roots = _safe_settings_paths()
    flat_now = _flatten(current.model_dump())
    flat_new = _flatten(fresh.model_dump())
    for path in sorted(set(flat_now) | set(flat_new)):
        before = flat_now.get(path, _MISSING)
        after = flat_new.get(path, _MISSING)
        if before is not _MISSING and after is not _MISSING and _values_equal(before, after):
            continue
        if path == _SKILLS_KEY:
            diff.skills_system_prefix = str(after if after is not _MISSING else "")
            diff.changed_keys.append(_SKILLS_KEY)
            continue
        if path == _MCP_SERVERS_KEY:
            if not mcp_live_safe:
                diff.requires_restart.append(path)
            continue
        if _under(path, safe_roots):
            continue
        diff.requires_restart.append(path)
    diff.changed_keys = sorted(set(diff.changed_keys))
    diff.requires_restart = sorted(set(diff.requires_restart))
    return diff


def _default_loader(ctx: Any) -> Callable[[], Any]:
    from daari.config.settings import Settings

    path = config_file_path(ctx.settings)
    return lambda: Settings.load(path)


def reload_settings_from_disk(app: Any, *, trigger: str = "api") -> dict[str, Any]:
    """Load, diff, and apply. Raises ConfigReloadError before any live mutation."""
    from daari.gateway.request_log import log_gateway_event

    ctx = app.state.ctx
    path = str(config_file_path(ctx.settings))
    loader = getattr(app.state, "settings_loader", None) or _default_loader(ctx)
    try:
        fresh = loader()
        from daari.security.secret_refs import resolve_settings_secrets

        # Same startup contract: a failed secret:// ref keeps the old settings.
        resolve_settings_secrets(fresh)
    except Exception as exc:  # noqa: BLE001 — any load failure keeps prior settings
        log_gateway_event(
            "config_reload_failed",
            {"trigger": trigger, "path": path, "error": str(exc)},
        )
        raise ConfigReloadError(f"config reload failed; prior settings kept: {exc}") from exc

    diff = diff_settings(ctx.settings, fresh)
    new_boundaries = None
    boundaries_patch = diff.patch.get("boundaries")
    if boundaries_patch:
        from daari.config.validate import merged_boundaries

        new_boundaries = merged_boundaries(ctx.settings.boundaries, boundaries_patch)
    from daari.gateway.config_live import apply_live_config

    apply_live_config(
        ctx,
        app_state=app.state,
        routing=diff.patch.get("routing"),
        frontier=diff.patch.get("frontier"),
        cache=diff.patch.get("cache"),
        integrations=diff.patch.get("integrations"),
        observability=diff.patch.get("observability"),
        guardrails=diff.patch.get("guardrails"),
        decisions=diff.patch.get("decisions"),
        systemone=diff.patch.get("systemone"),
        security=diff.patch.get("security"),
        new_boundaries=new_boundaries,
    )
    if diff.skills_system_prefix is not None:
        ctx.settings.skills_system_prefix = diff.skills_system_prefix
        router = getattr(ctx, "router", None)
        if router is not None:
            router.skills_system_prefix = diff.skills_system_prefix.strip()
    overrides = getattr(app.state, "config_runtime_overrides", None)
    if overrides is not None:
        overrides.clear()
    payload = {
        "ok": True,
        "trigger": trigger,
        "path": path,
        "changed_keys": diff.changed_keys,
        "requires_restart": diff.requires_restart,
    }
    log_gateway_event("config_reload", payload)
    return payload


async def reload_config(
    app: Any,
    *,
    trigger: str = "api",
    actor: str = "daari",
    role: str = "system",
) -> dict[str, Any]:
    """Serialized reload; records a `config.reload` audit row on success."""
    lock = getattr(app.state, "config_reload_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        app.state.config_reload_lock = lock
    async with lock:
        payload = reload_settings_from_disk(app, trigger=trigger)
        from daari.enterprise.postgres_audit import audit_log_from_settings

        audit_log_from_settings(app.state.ctx.settings).record(
            actor=actor,
            role=role,
            action="config.reload",
            detail={
                "trigger": trigger,
                "changed_keys": payload["changed_keys"],
                "requires_restart": payload["requires_restart"],
            },
        )
        return payload


def install_sighup_reload(app: Any, *, loop: Any = None) -> Callable[[], None] | None:
    """Route SIGHUP to `reload_config`. Returns the remover, or None when skipped.

    Skipped on platforms without SIGHUP (Windows), when
    `server.sighup_reload` is false, or when the loop refuses signal handlers
    (non-main thread, e.g. test clients).
    """
    from daari.gateway.request_log import log_gateway_event

    if _SIGHUP is None:
        return None
    ctx = getattr(app.state, "ctx", None)
    server = getattr(getattr(ctx, "settings", None), "server", None)
    if not bool(getattr(server, "sighup_reload", True)):
        return None
    active_loop = loop if loop is not None else asyncio.get_running_loop()
    tasks: set[Any] = set()

    async def _run() -> None:
        try:
            await reload_config(app, trigger="sighup")
        except ConfigReloadError:
            return
        except Exception as exc:  # noqa: BLE001 — never let a signal kill the loop
            log_gateway_event("config_reload_failed", {"trigger": "sighup", "error": str(exc)})

    def _on_sighup() -> None:
        task = active_loop.create_task(_run())
        tasks.add(task)
        if hasattr(task, "add_done_callback"):
            task.add_done_callback(tasks.discard)

    try:
        active_loop.add_signal_handler(_SIGHUP, _on_sighup)
    except (NotImplementedError, RuntimeError, ValueError, AttributeError) as exc:
        log_gateway_event("sighup_reload_skipped", {"reason": str(exc)})
        return None

    def _remove() -> None:
        try:
            active_loop.remove_signal_handler(_SIGHUP)
        except (NotImplementedError, RuntimeError, ValueError, AttributeError):
            pass

    return _remove
