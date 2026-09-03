"""secret:// reference resolution (issue #288).

Secrets in config (frontier keys, org tokens, Redis/Postgres URLs) may be
written as `secret://` URIs instead of plaintext:

- ``secret://env-file/<path>#<KEY>``    — KEY=VALUE line in a root-only file
- ``secret://exec/<command>``           — stdout of an operator command
                                          (covers `op read`, `vault kv get`,
                                          `aws secretsmanager` without daari
                                          knowing any vault SDK)
- ``secret://keychain/<service>/<account>`` — macOS `security` /
                                          Linux `secret-tool`
- ``secret://oauth/<token-url>?client_id=…&client_secret=<secret-ref>``
                                        — RFC 6749 client-credentials grant
                                          (#321); the access token is cached
                                          until expiry minus a margin and
                                          re-minted lazily on the next read

Resolution happens once at daemon startup and shells out — deliberately no
`keyring` dependency (AGENTS.md hard limit on new runtime deps). Failures are
fatal and name the ref, never the value. Resolved values are registered so
gateway logs can redact any accidental echo.

OAuth tokens expire, so they resolve to a `RefreshableSecret` — a `str` that
remembers its ref. Call sites that hold a credential across requests (frontier
key rotation, org clients) pass it through `current_secret()` right before use
to pick up a fresh token once the cached one nears expiry.
"""

from __future__ import annotations

import base64
import shlex
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
from pydantic import BaseModel

SECRET_SCHEME = "secret://"
REDACTED = "[redacted]"
OAUTH_SCHEME = "oauth"
OAUTH_DEFAULT_REFRESH_MARGIN_SECONDS = 60.0
# RFC 6749 §5.1 only RECOMMENDS `expires_in`; a token server that omits it gets
# a conservative lifetime rather than a token we would never refresh.
OAUTH_DEFAULT_EXPIRES_IN_SECONDS = 3600.0
OAUTH_TIMEOUT_SECONDS = 15.0

Runner = Callable[[list[str]], str]
Clock = Callable[[], float]

# Values resolved this process, so logging paths can scrub them (issue #288).
_RESOLVED_SECRETS: set[str] = set()

# Tests swap these to point the token client at a mock transport / fake clock
# without threading parameters through every call site.
_default_transport: httpx.BaseTransport | None = None
_now: Clock = time.time


class SecretRefError(RuntimeError):
    """A secret:// ref failed to resolve. Messages name the ref, never the value."""


class RefreshableSecret(str):
    """A resolved secret that knows its ref, so it can be re-minted later.

    Behaves as a plain `str` everywhere (headers, f-strings, JSON); only
    `current_secret()` looks at `.ref`. Plain `__dict__` (no slots) keeps
    `copy.deepcopy` / pickle working for pydantic `model_copy(deep=True)`.
    """

    ref: str

    def __new__(cls, value: str, ref: str = "") -> RefreshableSecret:
        instance = super().__new__(cls, value)
        instance.ref = ref
        return instance


def is_secret_ref(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(SECRET_SCHEME)


def register_secret(value: str) -> None:
    if value:
        _RESOLVED_SECRETS.add(value)


def clear_registered_secrets() -> None:
    _RESOLVED_SECRETS.clear()
    clear_oauth_cache()


def redact_secrets(text: str) -> str:
    """Scrub every registered secret value out of `text`."""
    for secret in _RESOLVED_SECRETS:
        if secret in text:
            text = text.replace(secret, REDACTED)
    return text


def _default_runner(argv: list[str]) -> str:
    completed = subprocess.run(
        argv, capture_output=True, text=True, check=True, timeout=30
    )
    return completed.stdout


def _resolve_env_file(remainder: str, ref: str) -> str:
    path_part, _, key = remainder.partition("#")
    if not path_part or not key:
        raise SecretRefError(
            f"malformed env-file ref {ref!r} — expected secret://env-file/<path>#<KEY>"
        )
    try:
        with open(path_part, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError as exc:
        raise SecretRefError(f"cannot read env file for {ref!r}: {exc}") from exc
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].lstrip()
        name, sep, value = stripped.partition("=")
        if sep and name.strip() == key:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value
    raise SecretRefError(f"key {key!r} not found in env file for {ref!r}")


def _resolve_exec(remainder: str, ref: str, runner: Runner) -> str:
    argv = shlex.split(remainder)
    if not argv:
        raise SecretRefError(f"malformed exec ref {ref!r} — no command given")
    try:
        output = runner(argv)
    except Exception as exc:
        # Never include exc output — a partially-printed secret must not leak.
        raise SecretRefError(
            f"command for {ref!r} failed ({type(exc).__name__}); "
            "run it manually to diagnose"
        ) from None
    return output


def _resolve_keychain(remainder: str, ref: str, runner: Runner, platform: str) -> str:
    parts = remainder.split("/")
    if len(parts) != 2 or not all(parts):
        raise SecretRefError(
            f"malformed keychain ref {ref!r} — expected secret://keychain/<service>/<account>"
        )
    service, account = parts
    if platform == "darwin":
        argv = ["security", "find-generic-password", "-s", service, "-a", account, "-w"]
    else:
        argv = ["secret-tool", "lookup", "service", service, "account", account]
    try:
        output = runner(argv)
    except Exception as exc:
        raise SecretRefError(
            f"keychain lookup for {ref!r} failed ({type(exc).__name__}); "
            f"check that {argv[0]!r} is installed and the entry exists"
        ) from None
    return output


# --- secret://oauth (#321) ---------------------------------------------------


@dataclass(frozen=True)
class OAuthGrant:
    """Parsed `secret://oauth/<token-url>?…` ref. Never holds the secret value."""

    token_url: str
    client_id: str
    client_secret_ref: str
    scope: str | None
    audience: str | None
    resource: str | None
    auth: str  # "basic" (RFC 6749 §2.3.1 default) or "post" (credentials in body)
    refresh_margin: float

    @property
    def endpoint(self) -> str:
        """Token URL without its query, safe to put in error messages."""
        return self.token_url.split("?", 1)[0]


@dataclass
class _CachedToken:
    value: RefreshableSecret
    expires_at: float


_OAUTH_TOKENS: dict[str, _CachedToken] = {}
_OAUTH_LOCK = threading.Lock()


def clear_oauth_cache() -> None:
    with _OAUTH_LOCK:
        _OAUTH_TOKENS.clear()


def _query_value(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    if not values:
        return None
    value = values[-1].strip()
    return value or None


def parse_oauth_ref(remainder: str, ref: str) -> OAuthGrant:
    """Parse `<token-url>?client_id=…&client_secret=<secret-ref>[&scope=…]
    [&audience=…][&resource=…][&auth=basic|post][&refresh_margin=<s>]`.

    The client secret must itself be a secret:// ref (env-file / exec /
    keychain) so plaintext credentials never sit in config. Percent-encode a
    nested ref that contains `&`, `+` or spaces.
    """
    token_url, _, query_string = remainder.partition("?")
    parts = urlsplit(token_url)
    if parts.scheme not in {"https", "http"} or not parts.netloc:
        raise SecretRefError(
            f"malformed oauth ref {ref!r} — expected "
            "secret://oauth/https://<idp>/token?client_id=<id>&client_secret=<secret-ref>"
        )
    query = parse_qs(query_string, keep_blank_values=True)
    client_id = _query_value(query, "client_id")
    client_secret = _query_value(query, "client_secret")
    if not client_id or not client_secret:
        raise SecretRefError(
            f"oauth ref {ref!r} needs both client_id and client_secret query parameters"
        )
    if not is_secret_ref(client_secret) or client_secret.startswith(f"{SECRET_SCHEME}{OAUTH_SCHEME}/"):
        raise SecretRefError(
            f"oauth ref for {parts.netloc!r} must supply client_secret as a "
            "secret://env-file, secret://exec or secret://keychain ref — never inline"
        )
    auth = (_query_value(query, "auth") or "basic").lower()
    if auth not in {"basic", "post"}:
        raise SecretRefError(f"oauth ref for {parts.netloc!r}: auth must be 'basic' or 'post'")
    margin_raw = _query_value(query, "refresh_margin")
    try:
        refresh_margin = (
            float(margin_raw) if margin_raw is not None else OAUTH_DEFAULT_REFRESH_MARGIN_SECONDS
        )
    except ValueError:
        raise SecretRefError(
            f"oauth ref for {parts.netloc!r}: refresh_margin must be a number of seconds"
        ) from None
    return OAuthGrant(
        token_url=token_url,
        client_id=client_id,
        client_secret_ref=client_secret,
        scope=_query_value(query, "scope"),
        audience=_query_value(query, "audience"),
        resource=_query_value(query, "resource"),
        auth=auth,
        refresh_margin=max(0.0, refresh_margin),
    )


def _mint_oauth_token(
    grant: OAuthGrant,
    ref: str,
    *,
    runner: Runner,
    platform: str | None,
    transport: httpx.BaseTransport | None,
    clock: Clock,
) -> _CachedToken:
    # The client secret resolves through the ordinary resolvers, so its own
    # failures already name the nested ref and never the value.
    client_secret = resolve_secret_ref(
        grant.client_secret_ref, runner=runner, platform=platform, register=True
    )
    form: dict[str, str] = {"grant_type": "client_credentials"}
    if grant.scope:
        form["scope"] = grant.scope
    if grant.audience:
        form["audience"] = grant.audience
    if grant.resource:
        form["resource"] = grant.resource
    headers = {"Accept": "application/json"}
    if grant.auth == "post":
        form["client_id"] = grant.client_id
        form["client_secret"] = client_secret
    else:
        basic = base64.b64encode(f"{grant.client_id}:{client_secret}".encode()).decode()
        headers["Authorization"] = f"Basic {basic}"
    requested_at = clock()
    try:
        with httpx.Client(transport=transport, timeout=OAUTH_TIMEOUT_SECONDS) as client:
            response = client.post(grant.token_url, data=form, headers=headers)
    except Exception as exc:
        raise SecretRefError(
            f"oauth token request to {grant.endpoint} failed ({type(exc).__name__})"
        ) from None
    if response.status_code < 200 or response.status_code >= 300:
        # Bodies can echo the request; only the status is safe to surface.
        raise SecretRefError(
            f"oauth token endpoint {grant.endpoint} returned HTTP {response.status_code}"
        )
    try:
        payload = response.json()
    except ValueError:
        raise SecretRefError(
            f"oauth token endpoint {grant.endpoint} returned a non-JSON body"
        ) from None
    access_token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(access_token, str) or not access_token.strip():
        raise SecretRefError(
            f"oauth token endpoint {grant.endpoint} returned no access_token"
        )
    expires_in = payload.get("expires_in", OAUTH_DEFAULT_EXPIRES_IN_SECONDS)
    try:
        lifetime = float(expires_in)
    except (TypeError, ValueError):
        lifetime = OAUTH_DEFAULT_EXPIRES_IN_SECONDS
    return _CachedToken(
        value=RefreshableSecret(access_token.strip(), ref),
        expires_at=requested_at + max(0.0, lifetime),
    )


def _resolve_oauth(
    remainder: str,
    ref: str,
    *,
    runner: Runner,
    platform: str | None,
    transport: httpx.BaseTransport | None,
    clock: Clock,
) -> RefreshableSecret:
    grant = parse_oauth_ref(remainder, ref)
    with _OAUTH_LOCK:
        cached = _OAUTH_TOKENS.get(ref)
        if cached is not None and clock() < cached.expires_at - grant.refresh_margin:
            return cached.value
        # Minting under the lock serialises concurrent refreshes so a burst of
        # requests at expiry yields one token request, not one per caller.
        minted = _mint_oauth_token(
            grant, ref, runner=runner, platform=platform, transport=transport, clock=clock
        )
        _OAUTH_TOKENS[ref] = minted
        return minted.value


def resolve_secret_ref(
    ref: str,
    *,
    runner: Runner = _default_runner,
    platform: str | None = None,
    register: bool = True,
    transport: httpx.BaseTransport | None = None,
    clock: Clock | None = None,
) -> str:
    """Resolve one secret:// URI to its value. Fatal on any failure.

    `register=False` is for verification passes (doctor) that must not add
    values to the process-wide redaction registry.
    """
    remainder = ref[len(SECRET_SCHEME) :]
    scheme, _, rest = remainder.partition("/")
    value: str
    if scheme == "env-file":
        value = _resolve_env_file(rest, ref)
    elif scheme == "exec":
        value = _resolve_exec(rest, ref, runner)
    elif scheme == "keychain":
        value = _resolve_keychain(rest, ref, runner, platform or sys.platform)
    elif scheme == OAUTH_SCHEME:
        token = _resolve_oauth(
            rest,
            ref,
            runner=runner,
            platform=platform,
            transport=transport if transport is not None else _default_transport,
            clock=clock or _now,
        )
        if register:
            register_secret(token)
        return token
    else:
        raise SecretRefError(
            f"unknown secret ref scheme in {ref!r} — "
            "supported: env-file, exec, keychain, oauth"
        )
    value = value.strip()
    if not value:
        raise SecretRefError(f"{ref!r} resolved to an empty value")
    if register:
        register_secret(value)
    return value


def current_secret(value: str | None) -> str | None:
    """Return the up-to-date value for a resolved secret.

    Plain strings pass through untouched. A `RefreshableSecret` (oauth) is
    re-resolved through the token cache, which only hits the network once the
    cached token is within its refresh margin. Raises SecretRefError if the
    refresh fails — a stale token must not be sent as if it were valid.
    """
    if not isinstance(value, RefreshableSecret) or not value.ref:
        return value
    return resolve_secret_ref(value.ref)


def iter_secret_refs(model: BaseModel) -> list[tuple[str, str]]:
    """All (dotted config path, ref) pairs whose value is a secret:// URI."""
    found: list[tuple[str, str]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, BaseModel):
            for name in type(node).model_fields:
                walk(getattr(node, name), f"{path}.{name}" if path else name)
        elif isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}[{key!r}]")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")
        elif is_secret_ref(node):
            found.append((path, node))

    walk(model, "")
    return found


def resolve_settings_secrets(
    settings: BaseModel,
    *,
    runner: Runner = _default_runner,
    platform: str | None = None,
) -> list[str]:
    """Resolve every secret:// value in `settings` in place, once, at startup.

    Returns the list of resolved refs. Raises SecretRefError naming the config
    path and ref on the first failure — a daemon must not start half-keyed.
    """
    resolved: list[str] = []

    def resolve(ref: str, path: str) -> str:
        try:
            value = resolve_secret_ref(ref, runner=runner, platform=platform)
        except SecretRefError as exc:
            raise SecretRefError(f"config {path}: {exc}") from None
        resolved.append(ref)
        return value

    def walk(node: Any, path: str) -> None:
        if isinstance(node, BaseModel):
            for name in type(node).model_fields:
                child_path = f"{path}.{name}" if path else name
                value = getattr(node, name)
                if is_secret_ref(value):
                    object.__setattr__(node, name, resolve(value, child_path))
                else:
                    walk(value, child_path)
        elif isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{path}[{key!r}]"
                if is_secret_ref(value):
                    node[key] = resolve(value, child_path)
                else:
                    walk(value, child_path)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                child_path = f"{path}[{index}]"
                if is_secret_ref(value):
                    node[index] = resolve(value, child_path)
                else:
                    walk(value, child_path)

    walk(settings, "")
    return resolved
