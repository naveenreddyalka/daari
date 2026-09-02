"""Resolve `secret://` config references at process start (issue #288).

Supported schemes (no new runtime dependencies — shell out to OS CLIs):

- `secret://env-file/<path>#<KEY>` — KEY=value lines in a root-readable file
- `secret://exec/<command>` — stdout of an operator-supplied command
- `secret://keychain/<service>/<account>` — macOS `security` or Linux `secret-tool`

Plain strings are left unchanged. Resolution failures raise `SecretRefError`
with the URI named and never the secret value.
"""

from __future__ import annotations

import platform
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

SECRET_PREFIX = "secret://"
REDACTED = "***"

# Resolved plaintext values registered for log/trace redaction.
_resolved_secrets: set[str] = set()


class SecretRefError(RuntimeError):
    """A secret:// URI could not be resolved. Message names the ref, never the value."""


def clear_resolved_secrets() -> None:
    """Test helper: drop the redaction registry."""
    _resolved_secrets.clear()


def register_resolved_secret(value: str) -> None:
    if value:
        _resolved_secrets.add(value)


def is_secret_ref(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(SECRET_PREFIX)


def collect_secret_refs(obj: Any, *, path: str = "") -> list[tuple[str, str]]:
    """Return (dotted_path, uri) for every secret:// string in a nested structure."""
    found: list[tuple[str, str]] = []
    if is_secret_ref(obj):
        found.append((path or "<root>", obj))
        return found
    if isinstance(obj, dict):
        for key, child in obj.items():
            child_path = f"{path}.{key}" if path else str(key)
            found.extend(collect_secret_refs(child, path=child_path))
    elif isinstance(obj, list):
        for index, child in enumerate(obj):
            child_path = f"{path}[{index}]"
            found.extend(collect_secret_refs(child, path=child_path))
    return found


def resolve_secret_ref(uri: str) -> str:
    """Resolve one secret:// URI to a plaintext string."""
    if not is_secret_ref(uri):
        raise SecretRefError(f"not a secret:// URI: {uri!r}")
    parsed = urlparse(uri)
    # secret://env-file/... → scheme=secret, netloc=env-file, path=/...
    kind = (parsed.netloc or "").lower()
    if not kind and parsed.path:
        # Fallback when netloc is empty: first path segment is the kind.
        parts = parsed.path.lstrip("/").split("/", 1)
        kind = parts[0].lower() if parts else ""
        remainder = parts[1] if len(parts) > 1 else ""
    else:
        # urlparse yields path="/foo"; absolute env-file URIs use
        # secret://env-file//absolute/path → path="//absolute/path".
        remainder = parsed.path
        if remainder.startswith("//"):
            remainder = remainder[1:]
        elif remainder.startswith("/"):
            remainder = remainder[1:] if kind in {"exec", "keychain"} else remainder

    if kind == "env-file":
        value = _resolve_env_file(uri, remainder, parsed.fragment)
    elif kind == "exec":
        # Command is path + optional query; keep fragment out of the command.
        command = unquote(remainder)
        if parsed.query:
            command = f"{command}?{unquote(parsed.query)}"
        value = _resolve_exec(uri, command)
    elif kind == "keychain":
        value = _resolve_keychain(uri, remainder)
    else:
        raise SecretRefError(
            f"unknown secret:// scheme {kind!r} in {uri} "
            "(expected env-file, exec, or keychain)"
        )
    if not value:
        raise SecretRefError(f"secret:// ref {uri} resolved to an empty value")
    register_resolved_secret(value)
    return value


def _resolve_env_file(uri: str, path_part: str, key: str) -> str:
    if not key:
        raise SecretRefError(f"secret://env-file ref {uri} is missing #<KEY> fragment")
    path = Path(unquote(path_part)).expanduser()
    if not path.is_file():
        raise SecretRefError(f"secret://env-file ref {uri}: file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SecretRefError(f"secret://env-file ref {uri}: cannot read {path}: {exc}") from exc
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            continue
        name, _, raw = stripped.partition("=")
        if name.strip() != key:
            continue
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value
    raise SecretRefError(f"secret://env-file ref {uri}: key {key!r} not found in {path}")


def _resolve_exec(uri: str, command: str) -> str:
    if not command.strip():
        raise SecretRefError(f"secret://exec ref {uri} has an empty command")
    try:
        completed = subprocess.run(
            command,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SecretRefError(f"secret://exec ref {uri} failed to run: {exc}") from exc
    if completed.returncode != 0:
        raise SecretRefError(
            f"secret://exec ref {uri} exited {completed.returncode}"
        )
    return (completed.stdout or "").strip()


def _resolve_keychain(uri: str, remainder: str) -> str:
    parts = [unquote(p) for p in remainder.split("/") if p]
    if len(parts) < 2:
        raise SecretRefError(
            f"secret://keychain ref {uri} needs <service>/<account>"
        )
    service, account = parts[0], parts[1]
    system = platform.system()
    if system == "Darwin":
        command = [
            "security",
            "find-generic-password",
            "-s",
            service,
            "-a",
            account,
            "-w",
        ]
    else:
        # Linux secret-service via libsecret CLI (no Python keyring dep).
        command = [
            "secret-tool",
            "lookup",
            "service",
            service,
            "account",
            account,
        ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SecretRefError(f"secret://keychain ref {uri} failed to run: {exc}") from exc
    if completed.returncode != 0:
        raise SecretRefError(
            f"secret://keychain ref {uri} exited {completed.returncode}"
        )
    return (completed.stdout or "").strip()


def resolve_tree(obj: Any) -> Any:
    """Deep-copy a nested structure, replacing secret:// strings with resolved values."""
    if is_secret_ref(obj):
        return resolve_secret_ref(obj)
    if isinstance(obj, dict):
        return {key: resolve_tree(child) for key, child in obj.items()}
    if isinstance(obj, list):
        return [resolve_tree(child) for child in obj]
    return obj


def redact_secrets(obj: Any) -> Any:
    """Replace known resolved secret values (and secret:// URIs) with ***."""
    if isinstance(obj, str):
        if is_secret_ref(obj):
            return REDACTED
        text = obj
        for secret in _resolved_secrets:
            if secret and secret in text:
                text = text.replace(secret, REDACTED)
        return text
    if isinstance(obj, dict):
        return {key: redact_secrets(child) for key, child in obj.items()}
    if isinstance(obj, list):
        return [redact_secrets(child) for child in obj]
    return obj


_SECRETISH_KEY = re.compile(
    r"(api[_-]?key|password|secret|token|authorization|credential)",
    re.IGNORECASE,
)


def looks_like_secret_field(name: str) -> bool:
    return bool(_SECRETISH_KEY.search(name))
