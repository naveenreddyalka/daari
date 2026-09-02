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

Resolution happens once at daemon startup and shells out — deliberately no
`keyring` dependency (AGENTS.md hard limit on new runtime deps). Failures are
fatal and name the ref, never the value. Resolved values are registered so
gateway logs can redact any accidental echo.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

SECRET_SCHEME = "secret://"
REDACTED = "[redacted]"

Runner = Callable[[list[str]], str]

# Values resolved this process, so logging paths can scrub them (issue #288).
_RESOLVED_SECRETS: set[str] = set()


class SecretRefError(RuntimeError):
    """A secret:// ref failed to resolve. Messages name the ref, never the value."""


def is_secret_ref(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(SECRET_SCHEME)


def register_secret(value: str) -> None:
    if value:
        _RESOLVED_SECRETS.add(value)


def clear_registered_secrets() -> None:
    _RESOLVED_SECRETS.clear()


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


def resolve_secret_ref(
    ref: str,
    *,
    runner: Runner = _default_runner,
    platform: str | None = None,
    register: bool = True,
) -> str:
    """Resolve one secret:// URI to its value. Fatal on any failure.

    `register=False` is for verification passes (doctor) that must not add
    values to the process-wide redaction registry.
    """
    remainder = ref[len(SECRET_SCHEME) :]
    scheme, _, rest = remainder.partition("/")
    if scheme == "env-file":
        value = _resolve_env_file(rest, ref)
    elif scheme == "exec":
        value = _resolve_exec(rest, ref, runner)
    elif scheme == "keychain":
        value = _resolve_keychain(rest, ref, runner, platform or sys.platform)
    else:
        raise SecretRefError(
            f"unknown secret ref scheme in {ref!r} — "
            "supported: env-file, exec, keychain"
        )
    value = value.strip()
    if not value:
        raise SecretRefError(f"{ref!r} resolved to an empty value")
    if register:
        register_secret(value)
    return value


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
