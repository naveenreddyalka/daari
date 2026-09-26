"""Pre-auth request-header allow/block policy (#1112).

Screens known-bad User-Agents, missing required custom headers, and blocked
X-* values before ``require_api_key`` spends auth work (Portkey startHooks
parity).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from daari.gateway.request_log import log_gateway_event

OPEN_HEADER_POLICY_PATHS = frozenset(
    {"/health", "/ready", "/v1/messages/health", "/metrics"}
)


@dataclass(frozen=True)
class HeaderPolicyDecision:
    status_code: int
    code: str
    message: str
    header: str = ""


def header_policy_active(policy: Any) -> bool:
    if policy is None or not bool(getattr(policy, "enabled", False)):
        return False
    required = getattr(policy, "required", None) or []
    deny = getattr(policy, "deny", None) or []
    allow = getattr(policy, "allow", None) or {}
    return bool(required or deny or allow)


def evaluate_header_policy(
    policy: Any, headers: Mapping[str, str]
) -> HeaderPolicyDecision | None:
    """Return a deny decision, or None when the request is allowed."""
    if not bool(getattr(policy, "enabled", False)):
        return None

    normalized = {str(k).lower(): str(v) for k, v in headers.items()}

    for name in getattr(policy, "required", None) or []:
        key = str(name).strip().lower()
        if not key:
            continue
        value = (normalized.get(key) or "").strip()
        if not value:
            return HeaderPolicyDecision(
                status_code=400,
                code="header_required",
                message=f"Required header {name!r} is missing or empty.",
                header=key,
            )

    for rule in getattr(policy, "deny", None) or []:
        header = str(getattr(rule, "header", "") or "").strip().lower()
        if not header:
            continue
        value = normalized.get(header, "")
        exact = getattr(rule, "exact", None)
        if exact is not None and str(exact) != "":
            if value == str(exact):
                return HeaderPolicyDecision(
                    status_code=403,
                    code="header_denied",
                    message=f"Header {header!r} is blocked by policy.",
                    header=header,
                )
        pattern = getattr(rule, "regex", None)
        if pattern:
            try:
                if re.search(str(pattern), value):
                    return HeaderPolicyDecision(
                        status_code=403,
                        code="header_denied",
                        message=f"Header {header!r} is blocked by policy.",
                        header=header,
                    )
            except re.error:
                # Malformed patterns are a doctor warning; fail closed only when
                # the rule itself is well-formed and matches.
                continue

    allow = getattr(policy, "allow", None) or {}
    for name, allowed in allow.items():
        key = str(name).strip().lower()
        if not key:
            continue
        if key not in normalized:
            continue
        value = normalized[key]
        allowed_values = {str(item) for item in (allowed or [])}
        if value not in allowed_values:
            return HeaderPolicyDecision(
                status_code=403,
                code="header_not_allowed",
                message=f"Header {key!r} value is not on the allowlist.",
                header=key,
            )

    return None


def header_policy_response(decision: HeaderPolicyDecision) -> JSONResponse:
    return JSONResponse(
        status_code=decision.status_code,
        content={
            "error": {
                "message": decision.message,
                "type": "header_policy_error",
                "code": decision.code,
            }
        },
    )


def record_header_policy_deny(
    app: Any, *, path: str, decision: HeaderPolicyDecision, settings: Any
) -> None:
    metrics = getattr(getattr(app.state, "ctx", None), "metrics", None)
    if metrics is not None and hasattr(metrics, "record_reject"):
        metrics.record_reject("header_policy")
    log_gateway_event(
        "header_policy_deny",
        {
            "path": path,
            "code": decision.code,
            "header": decision.header,
            "status_code": decision.status_code,
        },
    )
    try:
        from daari.enterprise.postgres_audit import audit_log_from_settings

        audit_log_from_settings(settings).record(
            actor="anonymous",
            role="system",
            action="header_policy.deny",
            detail={
                "path": path,
                "code": decision.code,
                "header": decision.header,
            },
        )
    except Exception:
        pass


class HeaderPolicyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, policy: Any, settings: Any) -> None:
        super().__init__(app)
        self.policy = policy
        self.settings = settings

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in OPEN_HEADER_POLICY_PATHS:
            return await call_next(request)
        decision = evaluate_header_policy(self.policy, request.headers)
        if decision is None:
            return await call_next(request)
        record_header_policy_deny(
            request.app, path=path, decision=decision, settings=self.settings
        )
        return header_policy_response(decision)


def install_header_policy(app: Any, settings: Any) -> None:
    """Register header policy outside auth so scrapers never spend VK/SSO work."""
    policy = getattr(getattr(settings, "server", None), "header_policy", None)
    if not header_policy_active(policy):
        return
    app.add_middleware(HeaderPolicyMiddleware, policy=policy, settings=settings)
