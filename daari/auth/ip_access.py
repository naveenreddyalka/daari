"""Per-key and per-team client IP allowlists (#2144).

Unset allowlists (None) keep unrestricted behavior. When a key and/or team sets
a non-empty list, the client IP must match **each** non-empty list (most
restrictive AND of constraints). Uses stdlib ``ipaddress`` only.
"""

from __future__ import annotations

import ipaddress
from typing import Any, Iterable


def normalize_ip_entry(raw: str) -> str:
    """Parse a single IP or CIDR; return canonical network string (host→/32|/128)."""
    text = str(raw).strip()
    if not text:
        raise ValueError("invalid IP allowlist entry: empty")
    try:
        network = ipaddress.ip_network(text, strict=False)
    except ValueError as exc:
        raise ValueError(f"invalid IP allowlist entry: {raw!r}") from exc
    return str(network)


def coerce_ips(raw: list[str] | tuple[str, ...] | None) -> tuple[str, ...] | None:
    """None stays unrestricted. A list (even empty) is an explicit allowlist."""
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)):
        raise ValueError("allowed_ips must be a list of IP or CIDR strings")
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        normalized = normalize_ip_entry(str(item))
        if normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return tuple(out)


def ips_from_meta(metadata: dict[str, Any] | None) -> tuple[str, ...] | None:
    if not isinstance(metadata, dict):
        return None
    if "allowed_ips" not in metadata:
        return None
    raw = metadata.get("allowed_ips")
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        return coerce_ips(list(raw))
    return None


def write_ips_to_meta(
    metadata: dict[str, Any],
    *,
    allowed_ips: list[str] | tuple[str, ...] | None | object = None,
    unset_sentinel: object | None = None,
) -> dict[str, Any]:
    """Mutate and return metadata. Pass ``unset_sentinel`` to leave the field alone."""
    meta = dict(metadata)
    if allowed_ips is unset_sentinel:
        return meta
    ips = coerce_ips(allowed_ips)  # type: ignore[arg-type]
    if ips is None:
        meta.pop("allowed_ips", None)
    else:
        meta["allowed_ips"] = list(ips)
    return meta


def ip_permitted(client_ip: str, *, allowed: Iterable[str] | None) -> bool:
    """True when allowlist is unset, or client_ip is inside any listed network."""
    if allowed is None:
        return True
    networks = tuple(ipaddress.ip_network(item, strict=False) for item in allowed)
    if not networks:
        return False
    text = (client_ip or "").strip()
    if not text or text == "unknown":
        return False
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        return False
    return any(addr in network for network in networks)


def client_ip_allowed(
    client_ip: str,
    *,
    key_ips: Iterable[str] | None,
    team_ips: Iterable[str] | None,
) -> bool:
    """Client must satisfy every non-None allowlist (key and team independently)."""
    key = coerce_ips(list(key_ips) if key_ips is not None else None)
    team = coerce_ips(list(team_ips) if team_ips is not None else None)
    return ip_permitted(client_ip, allowed=key) and ip_permitted(client_ip, allowed=team)


def denial_body(*, client_ip: str = "") -> dict[str, Any]:
    return {
        "error": {
            "type": "ip_not_allowed",
            "code": "ip_not_allowed",
            "message": "Client IP is not permitted for this key.",
            "client_ip": (client_ip or "")[:64],
        }
    }
