"""SSRF / private-network guards for outbound MCP (and similar) URLs (#1214)."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Sequence
from urllib.parse import urlparse

ALLOWED_SCHEMES = frozenset({"http", "https"})

# Extra cloud metadata / link-local ranges not always covered by is_link_local alone.
_BLOCKED_NETWORKS = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fd00:ec2::/32"),  # AWS IMDS IPv6
)


class EgressUrlBlocked(ValueError):
    """Raised when an egress URL fails SSRF / private-network checks."""


Resolver = Callable[[str], Sequence[str]]


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


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True
    for network in _BLOCKED_NETWORKS:
        if ip in network:
            return True
    return False


def validate_egress_url(
    url: str,
    *,
    allow_private_networks: bool = False,
    resolver: Resolver | None = None,
) -> None:
    """Raise EgressUrlBlocked unless *url* is a safe http(s) egress target.

    By default link-local, loopback, RFC1918, and cloud metadata addresses are
    rejected after DNS resolution (every A/AAAA). Lab setups may pass
    ``allow_private_networks=True``.
    """
    raw = (url or "").strip()
    if not raw:
        raise EgressUrlBlocked("egress URL is empty")
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise EgressUrlBlocked(
            f"egress URL scheme '{scheme or '(none)'}' not allowed (use http or https)"
        )
    host = (parsed.hostname or "").strip()
    if not host:
        raise EgressUrlBlocked("egress URL host is empty")

    resolve = resolver or _default_resolve
    try:
        ipaddress.ip_address(host)
        candidates = [host]
    except ValueError:
        try:
            candidates = list(resolve(host))
        except OSError as exc:
            raise EgressUrlBlocked(f"egress URL host '{host}' could not be resolved: {exc}") from exc
        if not candidates:
            raise EgressUrlBlocked(f"egress URL host '{host}' resolved to no addresses")

    if allow_private_networks:
        return

    for addr in candidates:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError as exc:
            raise EgressUrlBlocked(f"egress URL resolved to invalid address '{addr}'") from exc
        if _is_blocked_ip(ip):
            raise EgressUrlBlocked(
                f"egress URL host '{host}' resolves to blocked address {ip} "
                "(private/loopback/link-local/metadata); set "
                "integrations.mcp_egress.allow_private_networks: true for lab use"
            )
