"""Role-based access helpers for admin / ops surfaces (issues #119, #555).

Roles: admin > analyst > user. Virtual-key / SSO claims may carry a role;
master API key is always treated as admin. Analyst may read stats/traces/
report/audit/config GET; mutating admin routes require admin_min_role
(default admin).
"""

from __future__ import annotations

from typing import Any

ROLE_RANK = {"user": 0, "analyst": 1, "admin": 2}


def normalize_role(role: str | None) -> str:
    value = (role or "user").strip().lower()
    return value if value in ROLE_RANK else "user"


def role_at_least(role: str | None, minimum: str) -> bool:
    return ROLE_RANK[normalize_role(role)] >= ROLE_RANK[normalize_role(minimum)]


def role_from_claims(claims: dict[str, Any] | None, *, role_claim: str = "role") -> str:
    if not claims:
        return "user"
    claim = role_claim or "role"
    value = claims.get(claim)
    if value is None:
        value = claims.get("role") or claims.get("daari_role")
    # Some IdPs put roles in a list.
    if isinstance(value, list) and value:
        value = value[0]
    return normalize_role(str(value or "user"))


def team_id_from_claims(claims: dict[str, Any] | None) -> str | None:
    """Best-effort team id from SSO / JWT claims (#1677)."""
    if not claims:
        return None
    for key in ("team_id", "daari_team_id", "team"):
        value = claims.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def resolve_team_read_filter(
    *,
    role: str,
    caller_team_id: str | None,
    requested: str | None,
) -> str | None:
    """Effective ``team_id`` filter for admin read surfaces (#1677).

    Admin/master may pass any team (or omit for org-wide). Analyst / VK-bound
    callers are restricted to their own ``team_id``: omitting ``?team_id=``
    auto-scopes to that team; requesting another team's id raises
    ``PermissionError``.
    """
    wanted = (requested or "").strip() or None
    own = (caller_team_id or "").strip() or None
    if role_at_least(role, "admin"):
        return wanted
    if own:
        if wanted and wanted != own:
            raise PermissionError("team scope denied")
        return own
    return wanted
