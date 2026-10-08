"""RFC 9728 OAuth protected-resource discovery + local AS token mint for MCP.

Opt-in via ``integrations.mcp_oauth.protected_resource`` (#1262) and
``integrations.mcp_oauth.local_as`` (#1293). When discovery is on, daari serves
``/.well-known/oauth-protected-resource`` and shapes unauthenticated ``/mcp``
401s with a ``WWW-Authenticate`` challenge. When ``local_as`` is on, daari also
exposes a minimal on-box authorization server (AS metadata +
``POST /oauth/token`` client_credentials + ``POST /oauth/revoke`` RFC 7009)
that mints short-lived JWTs usable as Bearer on ``/mcp``, enforces
``scopes_supported``, and denylists revoked ``jti`` values (#1475).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import threading
import time
import uuid
from typing import Any
from urllib.parse import urljoin

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from daari.server.auth import AuthClaims, normalize_master_keys, resolve_auth

_log = logging.getLogger(__name__)

_MCP_OAUTH_ISS = "daari-mcp"
_TOKEN_TYP = "mcp_at"
_REQUIRED_MCP_SCOPE = "mcp"
AUDIT_TOKEN_MINTED = "mcp_oauth.token_minted"
AUDIT_TOKEN_DENIED = "mcp_oauth.token_denied"
AUDIT_TOKEN_REVOKED = "mcp_oauth.token_revoked"

# jti → absolute expiry (unix). Process-local denylist; TTL bounded by remaining exp.
_revoked_jtis: dict[str, int] = {}
_revoked_lock = threading.Lock()


def mcp_oauth_enabled(settings: Any) -> bool:
    integrations = getattr(settings, "integrations", None)
    oauth = getattr(integrations, "mcp_oauth", None)
    return bool(getattr(oauth, "protected_resource", False))


def mcp_oauth_local_as_enabled(settings: Any) -> bool:
    integrations = getattr(settings, "integrations", None)
    oauth = getattr(integrations, "mcp_oauth", None)
    return bool(getattr(oauth, "local_as", False))


def mcp_oauth_routes_enabled(settings: Any) -> bool:
    return mcp_oauth_enabled(settings) or mcp_oauth_local_as_enabled(settings)


def _oauth(settings: Any) -> Any:
    return getattr(getattr(settings, "integrations", None), "mcp_oauth", None)


def _public_base(settings: Any, request: Request | None = None) -> str:
    oauth = _oauth(settings)
    configured = str(getattr(oauth, "resource", "") or "").strip()
    if configured:
        return configured.rstrip("/")
    if request is not None:
        return str(request.base_url).rstrip("/")
    host = getattr(getattr(settings, "server", None), "host", None) or "127.0.0.1"
    port = getattr(getattr(settings, "server", None), "port", None) or 11435
    return f"http://{host}:{port}"


def _local_issuer(settings: Any, request: Request | None = None) -> str:
    return _public_base(settings, request)


def protected_resource_metadata(
    settings: Any, *, request: Request | None = None, path_suffix: str = ""
) -> dict[str, Any]:
    """Build an RFC 9728 protected-resource metadata document."""
    oauth = _oauth(settings)
    base = _public_base(settings, request)
    resource = f"{base}/mcp" if not path_suffix else f"{base}{path_suffix}"
    if not path_suffix:
        resource = f"{base}/mcp"
    auth_servers = list(getattr(oauth, "authorization_servers", None) or [])
    if mcp_oauth_local_as_enabled(settings):
        issuer = _local_issuer(settings, request)
        if issuer not in auth_servers:
            auth_servers = [issuer, *auth_servers]
    scopes = list(getattr(oauth, "scopes_supported", None) or [])
    if not scopes:
        scopes = ["mcp"]
    return {
        "resource": resource,
        "authorization_servers": auth_servers,
        "scopes_supported": scopes,
    }


def _scopes_supported(settings: Any) -> list[str]:
    oauth = _oauth(settings)
    scopes = list(getattr(oauth, "scopes_supported", None) or [])
    return scopes or ["mcp"]


def _parse_scopes(scope: str) -> list[str]:
    return [part for part in str(scope or "").split() if part]


def scope_is_supported(settings: Any, scope: str) -> bool:
    """True when every space-delimited scope token is in ``scopes_supported``."""
    supported = set(_scopes_supported(settings))
    requested = _parse_scopes(scope)
    if not requested:
        return True
    return all(part in supported for part in requested)


def token_has_required_scope(scope: str, required: str = _REQUIRED_MCP_SCOPE) -> bool:
    return required in _parse_scopes(scope)


def authorization_server_metadata(
    settings: Any, *, request: Request | None = None
) -> dict[str, Any]:
    """RFC 8414 AS metadata for the on-box client_credentials mint (#1293, #1475)."""
    issuer = _local_issuer(settings, request)
    scopes = _scopes_supported(settings)
    return {
        "issuer": issuer,
        "token_endpoint": urljoin(f"{issuer}/", "oauth/token"),
        "revocation_endpoint": urljoin(f"{issuer}/", "oauth/revoke"),
        "grant_types_supported": ["client_credentials"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
        ],
        "response_types_supported": [],
        "scopes_supported": scopes,
    }


def _prune_revoked(now: int | None = None) -> None:
    ts = int(time.time()) if now is None else now
    with _revoked_lock:
        stale = [jti for jti, exp in _revoked_jtis.items() if exp < ts]
        for jti in stale:
            _revoked_jtis.pop(jti, None)


def is_jti_revoked(jti: str) -> bool:
    if not jti:
        return False
    _prune_revoked()
    with _revoked_lock:
        return jti in _revoked_jtis


def revoke_jti(jti: str, exp: int) -> None:
    """Denylist ``jti`` until ``exp`` (absolute unix). No-op when already expired."""
    now = int(time.time())
    if not jti or exp < now:
        return
    with _revoked_lock:
        _revoked_jtis[jti] = int(exp)
    _prune_revoked(now)


def clear_revocation_denylist() -> None:
    """Test helper — drop all denylisted jtis."""
    with _revoked_lock:
        _revoked_jtis.clear()


def _decode_token_claims(token: str, settings: Any) -> dict[str, Any] | None:
    """Verify HS256 signature and return payload dict, or None."""
    if not token or token.count(".") != 2:
        return None
    parts = token.split(".")
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    try:
        actual = _b64url_decode(parts[2])
    except Exception:
        return None
    secret = signing_secret_for(settings).encode("utf-8")
    expected = hmac.new(secret, signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, actual):
        return None
    try:
        claims_doc = json.loads(_b64url_decode(parts[1]))
    except Exception:
        return None
    if not isinstance(claims_doc, dict):
        return None
    if claims_doc.get("iss") != _MCP_OAUTH_ISS or claims_doc.get("typ") != _TOKEN_TYP:
        return None
    if claims_doc.get("aud") != "mcp":
        return None
    return claims_doc


def metadata_url(settings: Any, *, request: Request | None = None) -> str:
    base = _public_base(settings, request)
    return urljoin(f"{base}/", ".well-known/oauth-protected-resource")


def www_authenticate_header(settings: Any, *, request: Request | None = None) -> str:
    url = metadata_url(settings, request=request)
    return f'Bearer realm="mcp", resource_metadata="{url}"'


def mcp_oauth_challenge_response(
    settings: Any, *, request: Request | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "type": "authentication_error",
                "message": "Invalid or missing daari API key.",
            }
        },
        headers={"WWW-Authenticate": www_authenticate_header(settings, request=request)},
    )


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def signing_secret_for(settings: Any) -> str:
    oauth = _oauth(settings)
    configured = str(getattr(oauth, "signing_secret", "") or "").strip()
    if configured:
        return configured
    master = ""
    server = getattr(settings, "server", None)
    if server is not None and hasattr(server, "primary_master_key"):
        master = str(server.primary_master_key() or "")
    if not master:
        keys = normalize_master_keys(getattr(server, "api_key", None) if server else None)
        master = keys[0] if keys else ""
    if master:
        return hmac.new(b"daari-mcp-oauth-v1", master.encode("utf-8"), hashlib.sha256).hexdigest()
    # Local-only fallback when no master key (virtual-key installs).
    return hmac.new(b"daari-mcp-oauth-v1", b"local-as", hashlib.sha256).hexdigest()


def _audit_token_event(
    settings: Any,
    *,
    action: str,
    claims: AuthClaims | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Write mint/deny to the enterprise audit sink — never the raw token (#1468)."""
    try:
        from daari.enterprise.postgres_audit import audit_log_from_settings

        if claims is None:
            actor, role = "anonymous", "anonymous"
        else:
            kind = claims.kind or "anonymous"
            if kind == "virtual" and claims.key_id:
                actor, role = str(claims.key_id), str(claims.client_id or kind)
            else:
                actor, role = kind, kind
        audit_log_from_settings(settings).record(
            actor=actor,
            role=role,
            action=action,
            detail=detail or {},
        )
    except Exception:
        _log.debug("mcp_oauth.audit_failed action=%s", action, exc_info=True)


def mint_access_token(
    settings: Any,
    claims: AuthClaims,
    *,
    scope: str = "mcp",
) -> tuple[str, int]:
    """Return (jwt, expires_in). Never logs the token."""
    oauth = _oauth(settings)
    ttl = int(getattr(oauth, "token_ttl_seconds", 900) or 900)
    ttl = max(60, min(ttl, 86400))
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": _MCP_OAUTH_ISS,
        "aud": "mcp",
        "iat": now,
        "exp": now + ttl,
        "scope": scope or "mcp",
        "typ": _TOKEN_TYP,
        "kind": claims.kind,
        "jti": str(uuid.uuid4()),
    }
    if claims.kind == "virtual" and claims.key_id:
        payload["key_id"] = claims.key_id
        if claims.client_id:
            payload["client_id"] = claims.client_id
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8"))
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header}.{body}".encode("ascii")
    secret = signing_secret_for(settings).encode("utf-8")
    sig = hmac.new(secret, signing_input, hashlib.sha256).digest()
    token = f"{header}.{body}.{_b64url_encode(sig)}"
    return token, ttl


def revoke_access_token(token: str, settings: Any) -> bool:
    """Revoke a minted access token by ``jti``. Returns True when denylisted."""
    claims_doc = _decode_token_claims(token, settings)
    if claims_doc is None:
        return False
    jti = str(claims_doc.get("jti") or "").strip()
    if not jti:
        return False
    try:
        exp = int(claims_doc.get("exp", 0))
    except (TypeError, ValueError):
        return False
    if exp < int(time.time()):
        return False
    if is_jti_revoked(jti):
        return True
    revoke_jti(jti, exp)
    return True


def verify_access_token(
    token: str,
    settings: Any,
    *,
    master_key: str | list[str] | None = None,
    store: Any = None,
) -> AuthClaims | None:
    """Verify a local AS JWT and map it to AuthClaims. Never logs the token.

    Returns ``AuthClaims(kind=\"insufficient_scope\")`` when the JWT is
    cryptographically valid but missing the required ``mcp`` scope (#1475).
    Revoked ``jti`` values return ``None``.
    """
    claims_doc = _decode_token_claims(token, settings)
    if claims_doc is None:
        return None
    try:
        exp = int(claims_doc.get("exp", 0))
    except (TypeError, ValueError):
        return None
    if exp < int(time.time()):
        return None
    jti = str(claims_doc.get("jti") or "").strip()
    if jti and is_jti_revoked(jti):
        return None
    scope = str(claims_doc.get("scope") or "")
    if not token_has_required_scope(scope):
        return AuthClaims(kind="insufficient_scope")
    kind = claims_doc.get("kind")
    if kind == "master":
        return AuthClaims(kind="master")
    if kind == "virtual":
        key_id = claims_doc.get("key_id")
        if not key_id or store is None or not getattr(store, "enabled", False):
            return None
        key = store.get_key(key_id) if hasattr(store, "get_key") else None
        if key is None:
            return None
        if hasattr(key, "is_expired") and key.is_expired():
            return AuthClaims(
                kind="expired",
                key_id=key.key_id,
                client_id=key.client_id or key.key_id,
                virtual_key=key,
            )
        from daari.auth.virtual_keys import effective_cache_scope

        region_pin = key.region_pin
        team_allowed = None
        team_groups = None
        team_scope = "global"
        if key.team_id and hasattr(store, "get_team"):
            team = store.get_team(key.team_id)
            if team is not None:
                if not region_pin and team.region_pin:
                    region_pin = team.region_pin
                team_allowed = team.allowed_models
                team_groups = team.model_groups
                team_scope = team.cache_scope
        return AuthClaims(
            kind="virtual",
            key_id=key.key_id,
            client_id=key.client_id or key.key_id,
            tier_cap=key.tier_cap,
            daily_budget_usd=key.daily_budget_usd,
            monthly_budget_usd=key.monthly_budget_usd,
            virtual_key=key,
            boundary_profile=(key.metadata or {}).get("boundary_profile"),
            region_pin=region_pin,
            allowed_models=key.allowed_models,
            model_groups=key.model_groups,
            team_allowed_models=team_allowed,
            team_model_groups=team_groups,
            cache_scope=effective_cache_scope(key.cache_scope, team_scope),
        )
    return None


def _extract_client_secret(request: Request, form: dict[str, Any]) -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(auth[6:].strip()).decode("utf-8")
            if ":" in decoded:
                return decoded.split(":", 1)[1]
        except Exception:
            return ""
    return str(form.get("client_secret") or "").strip()


def _oauth_error(status: int, error: str, description: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": error, "error_description": description},
    )


def build_mcp_oauth_router(settings: Any) -> APIRouter:
    router = APIRouter(tags=["mcp-oauth"])

    if mcp_oauth_enabled(settings) or mcp_oauth_local_as_enabled(settings):

        @router.get("/.well-known/oauth-protected-resource")
        async def oauth_protected_resource(request: Request) -> dict[str, Any]:
            return protected_resource_metadata(settings, request=request)

        @router.get("/.well-known/oauth-protected-resource/mcp")
        async def oauth_protected_resource_mcp(request: Request) -> dict[str, Any]:
            return protected_resource_metadata(settings, request=request, path_suffix="/mcp")

    if mcp_oauth_local_as_enabled(settings):

        @router.get("/.well-known/oauth-authorization-server")
        async def oauth_authorization_server(request: Request) -> dict[str, Any]:
            return authorization_server_metadata(settings, request=request)

        @router.post("/oauth/token")
        async def oauth_token(request: Request) -> JSONResponse:
            content_type = (request.headers.get("content-type") or "").lower()
            form: dict[str, Any] = {}
            if "application/json" in content_type:
                try:
                    payload = await request.json()
                    if isinstance(payload, dict):
                        form = payload
                except Exception:
                    form = {}
            else:
                try:
                    raw = await request.form()
                    form = {str(k): raw.get(k) for k in raw}
                except Exception:
                    form = {}
            grant = str(form.get("grant_type") or "").strip()
            if grant != "client_credentials":
                _audit_token_event(
                    settings,
                    action=AUDIT_TOKEN_DENIED,
                    detail={"reason": "unsupported_grant_type", "grant_type": grant},
                )
                return _oauth_error(
                    400,
                    "unsupported_grant_type",
                    "Only client_credentials is supported.",
                )
            client_secret = _extract_client_secret(request, form)
            if not client_secret:
                _audit_token_event(
                    settings,
                    action=AUDIT_TOKEN_DENIED,
                    detail={"reason": "invalid_client", "cause": "missing_client_secret"},
                )
                return _oauth_error(401, "invalid_client", "Missing client_secret.")
            store = getattr(getattr(request.app, "state", None), "virtual_key_store", None)
            server = getattr(settings, "server", None)
            master = getattr(server, "api_key", None) if server is not None else None
            claims = resolve_auth(client_secret, master_key=master, store=store)
            if claims is None or claims.kind == "expired":
                _log.info("mcp_oauth.token_denied reason=invalid_client")
                _audit_token_event(
                    settings,
                    action=AUDIT_TOKEN_DENIED,
                    claims=claims,
                    detail={"reason": "invalid_client"},
                )
                return _oauth_error(401, "invalid_client", "Invalid client credentials.")
            scope = str(form.get("scope") or "mcp").strip() or "mcp"
            if not scope_is_supported(settings, scope):
                _audit_token_event(
                    settings,
                    action=AUDIT_TOKEN_DENIED,
                    claims=claims,
                    detail={
                        "reason": "invalid_scope",
                        "scope": scope,
                        "scopes_supported": _scopes_supported(settings),
                    },
                )
                return _oauth_error(
                    400,
                    "invalid_scope",
                    "Requested scope is not in scopes_supported.",
                )
            token, expires_in = mint_access_token(settings, claims, scope=scope)
            # Log only a non-reversible fingerprint — never the token or secret.
            token_fp = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
            _log.info(
                "mcp_oauth.token_minted kind=%s expires_in=%s fp=%s",
                claims.kind,
                expires_in,
                token_fp,
            )
            _audit_token_event(
                settings,
                action=AUDIT_TOKEN_MINTED,
                claims=claims,
                detail={
                    "kind": claims.kind,
                    "expires_in": expires_in,
                    "scope": scope,
                    "token_fp": token_fp,
                },
            )
            return JSONResponse(
                status_code=200,
                content={
                    "access_token": token,
                    "token_type": "Bearer",
                    "expires_in": expires_in,
                    "scope": scope,
                },
            )

        @router.post("/oauth/revoke")
        async def oauth_revoke(request: Request) -> JSONResponse:
            """RFC 7009 token revocation — denylist by jti until remaining exp."""
            content_type = (request.headers.get("content-type") or "").lower()
            form: dict[str, Any] = {}
            if "application/json" in content_type:
                try:
                    payload = await request.json()
                    if isinstance(payload, dict):
                        form = payload
                except Exception:
                    form = {}
            else:
                try:
                    raw = await request.form()
                    form = {str(k): raw.get(k) for k in raw}
                except Exception:
                    form = {}
            token = str(form.get("token") or "").strip()
            # RFC 7009: always 200 for well-formed requests, even unknown tokens.
            if token:
                revoked = revoke_access_token(token, settings)
                if revoked:
                    token_fp = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
                    _log.info("mcp_oauth.token_revoked fp=%s", token_fp)
                    _audit_token_event(
                        settings,
                        action=AUDIT_TOKEN_REVOKED,
                        detail={"token_fp": token_fp},
                    )
            return JSONResponse(status_code=200, content={})

    return router
