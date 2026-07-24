"""Role-based access helpers for admin surfaces (issue #119).

Roles: admin > analyst > user. Virtual-key / SSO claims may carry a role;
master API key is always treated as admin.
"""

from __future__ import annotations

from typing import Any

ROLE_RANK = {"user": 0, "analyst": 1, "admin": 2}


def normalize_role(role: str | None) -> str:
    value = (role or "user").strip().lower()
    return value if value in ROLE_RANK else "user"


def role_at_least(role: str | None, minimum: str) -> bool:
    return ROLE_RANK[normalize_role(role)] >= ROLE_RANK[normalize_role(minimum)]


def role_from_claims(claims: dict[str, Any] | None) -> str:
    if not claims:
        return "user"
    return normalize_role(str(claims.get("role") or claims.get("daari_role") or "user"))
