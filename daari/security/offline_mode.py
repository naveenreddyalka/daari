"""Fail-closed air-gapped egress switch (#2034).

When ``security.offline_mode`` is on, shared outbound httpx clients refuse
connections to non-loopback / non-private hosts unless the hostname is on
``security.offline_allow_hosts``. Local Ollama / RFC1918 backends stay open.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Callable, Sequence
from typing import Any
from urllib.parse import urlparse

Resolver = Callable[[str], Sequence[str]]

_enabled: bool = False
_allow_hosts: frozenset[str] = frozenset()


class OfflineEgressBlocked(RuntimeError):
    """Raised when offline mode refuses an off-box egress attempt."""


def configure_offline_mode(
    *,
    enabled: bool = False,
    allow_hosts: Sequence[str] | None = None,
) -> None:
    """Install process-wide offline mode state (call at daemon startup)."""
    global _enabled, _allow_hosts
    _enabled = bool(enabled)
    hosts = allow_hosts if allow_hosts is not None else ()
    _allow_hosts = frozenset(
        h.strip().lower() for h in hosts if isinstance(h, str) and h.strip()
    )


def configure_offline_mode_from_settings(settings: Any) -> None:
    security = getattr(settings, "security", None)
    configure_offline_mode(
        enabled=bool(getattr(security, "offline_mode", False)),
        allow_hosts=list(getattr(security, "offline_allow_hosts", None) or ()),
    )


def offline_mode_enabled() -> bool:
    return _enabled


def offline_allow_hosts() -> frozenset[str]:
    return _allow_hosts


def _default_resolve(host: str) -> Sequence[str]:
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    addrs: list[str] = []
    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip = str(sockaddr[0])
        if ip not in seen:
            seen.add(ip)
            addrs.append(ip)
    return addrs


def _is_loopback_or_private(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(ip.is_loopback or ip.is_private)


def host_allowed_offline(
    host: str,
    *,
    resolver: Resolver | None = None,
) -> bool:
    """True when *host* may be contacted under offline mode."""
    raw = (host or "").strip().lower().rstrip(".")
    if not raw:
        return False
    if raw in _allow_hosts:
        return True
    if raw in {"localhost", "localhost.localdomain"}:
        return True
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        ip = None
    if ip is not None:
        return _is_loopback_or_private(ip)

    resolve = resolver or _default_resolve
    try:
        candidates = list(resolve(raw))
    except OSError:
        return False
    if not candidates:
        return False
    for addr in candidates:
        try:
            parsed = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if not _is_loopback_or_private(parsed):
            return False
    return True


def url_host(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"http://{raw}"
    return (urlparse(raw).hostname or "").strip().lower()


def assert_offline_url_allowed(
    url: str,
    *,
    resolver: Resolver | None = None,
    surface: str = "",
) -> None:
    """Raise OfflineEgressBlocked when offline mode forbids *url*."""
    if not _enabled:
        return
    host = url_host(url)
    if host_allowed_offline(host, resolver=resolver):
        return
    payload = {
        "host": host or "(empty)",
        "url": (url or "")[:200],
        "surface": surface or "httpx",
    }
    try:
        from daari.gateway.request_log import log_gateway_event

        log_gateway_event("security.offline_egress_refused", payload)
    except Exception:
        pass
    where = f" ({surface})" if surface else ""
    raise OfflineEgressBlocked(
        f"offline_mode refused egress to host '{host or '(empty)'}'{where}; "
        "allow loopback/RFC1918 or add the host to security.offline_allow_hosts"
    )


def _merge_hooks(
    existing: dict[str, list[Any]] | None,
    *,
    sync: bool,
) -> dict[str, list[Any]]:
    hooks: dict[str, list[Any]] = {k: list(v) for k, v in (existing or {}).items()}
    request_hooks = list(hooks.get("request") or [])

    if sync:

        def _sync_hook(request: Any) -> None:
            assert_offline_url_allowed(str(getattr(request, "url", "") or ""))

        request_hooks.append(_sync_hook)
    else:

        async def _async_hook(request: Any) -> None:
            assert_offline_url_allowed(str(getattr(request, "url", "") or ""))

        request_hooks.append(_async_hook)

    hooks["request"] = request_hooks
    return hooks


def apply_offline_event_hooks(
    kwargs: dict[str, Any],
    *,
    sync: bool = False,
) -> dict[str, Any]:
    """Return a copy of client kwargs with offline-mode request hooks merged."""
    out = dict(kwargs)
    out["event_hooks"] = _merge_hooks(out.get("event_hooks"), sync=sync)
    return out


def _url_is_offbox(url: str, *, allow_hosts: Sequence[str]) -> bool:
    """Static config check: treat unresolved public hostnames as off-box."""
    host = url_host(url)
    if not host:
        return False
    allow = {h.strip().lower() for h in allow_hosts if isinstance(h, str) and h.strip()}
    if host in allow or host in {"localhost", "localhost.localdomain"}:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Hostname: assume off-box unless it looks like a private DNS label
        # we can resolve locally; for validate we fail-closed on public-looking
        # names without doing DNS (keeps validate hermetic).
        return True
    return not _is_loopback_or_private(ip)


def offline_mode_findings(settings: Any) -> list[str]:
    """Config surfaces that point off-box while offline mode is enabled."""
    security = getattr(settings, "security", None)
    if not bool(getattr(security, "offline_mode", False)):
        return []
    allow = list(getattr(security, "offline_allow_hosts", None) or ())
    findings: list[str] = []

    def _note(path: str, url: str) -> None:
        raw = (url or "").strip()
        if not raw:
            return
        if _url_is_offbox(raw, allow_hosts=allow):
            findings.append(
                f"security.offline_mode: {path} points off-box ({raw!r}); "
                "refuse at runtime unless listed in security.offline_allow_hosts"
            )

    frontier = getattr(settings, "frontier", None)
    if frontier is not None and bool(getattr(frontier, "enabled", False)):
        _note("frontier.base_url", str(getattr(frontier, "base_url", "") or ""))
        for idx, provider in enumerate(getattr(frontier, "providers", None) or []):
            _note(
                f"frontier.providers[{idx}].base_url",
                str(getattr(provider, "base_url", "") or ""),
            )

    alerts = getattr(settings, "alerts", None)
    if alerts is not None:
        for field in (
            "budget_webhook_url",
            "key_expiry_webhook_url",
            "responses_completion_webhook_url",
        ):
            _note(f"alerts.{field}", str(getattr(alerts, field, "") or ""))

    anthropic = getattr(settings, "anthropic", None)
    if anthropic is not None:
        _note(
            "anthropic.enforcement_webhook_url",
            str(getattr(anthropic, "enforcement_webhook_url", "") or ""),
        )

    tts = getattr(settings, "tts", None)
    if tts is not None:
        _note("tts.base_url", str(getattr(tts, "base_url", "") or ""))

    asr = getattr(settings, "asr", None)
    if asr is not None:
        _note("asr.base_url", str(getattr(asr, "base_url", "") or ""))

    integrations = getattr(settings, "integrations", None)
    for idx, server in enumerate(getattr(integrations, "mcp_servers", None) or []):
        _note(
            f"integrations.mcp_servers[{idx}].url",
            str(getattr(server, "url", "") or ""),
        )

    obs = getattr(settings, "observability", None)
    otel_on = bool(getattr(obs, "otel", False) or getattr(obs, "otlp_logs", False))
    otlp = (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    if otel_on and otlp and _url_is_offbox(otlp, allow_hosts=allow):
        findings.append(
            f"security.offline_mode: OTEL_EXPORTER_OTLP_ENDPOINT points off-box "
            f"({otlp!r}); refuse at runtime unless listed in "
            "security.offline_allow_hosts"
        )

    return findings
