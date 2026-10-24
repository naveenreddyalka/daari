"""Egress TLS trust: exclude eMudhra/emSign roots (LiteLLM 1.106.3 parity, #1907).

Python ``certifi`` still ships emSign Root CA - G1. Outbound httpx clients that
use ``verify=True`` therefore trust it unless we filter the CA bundle. daari
defaults to filtering so frontier / MCP / TTS / org-cache egress match Kong,
Portkey, and LiteLLM distrust without waiting on a cloud image rebuild.
"""

from __future__ import annotations

import hashlib
import os
import re
import ssl
from functools import lru_cache
from pathlib import Path
from typing import Any

# Mozilla cacert.pem labels / subjects for the distrusted eMudhra family.
_DISTRUST_MARKERS = ("emudhra", "emsign")

_PEM_BEGIN = "-----BEGIN CERTIFICATE-----"
_PEM_END = "-----END CERTIFICATE-----"
# Mozilla cacert-style block: # comment lines immediately before BEGIN..END.
_CERT_BLOCK = re.compile(
    r"(?:^|\n)(?:#[^\n]*\n)*"
    + re.escape(_PEM_BEGIN)
    + r".*?"
    + re.escape(_PEM_END),
    re.DOTALL,
)


def _bundle_cache_dir() -> Path:
    override = (os.environ.get("DAARI_TLS_BUNDLE_CACHE") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")) / "daari"


def _source_ca_pem() -> str:
    """Active trust store text: ``SSL_CERT_FILE`` when set, else certifi."""
    ssl_file = (os.environ.get("SSL_CERT_FILE") or "").strip()
    if ssl_file and Path(ssl_file).is_file():
        return Path(ssl_file).read_text(encoding="utf-8")
    import certifi

    return Path(certifi.where()).read_text(encoding="utf-8")


def bundle_contains_distrusted_roots(pem_text: str) -> bool:
    lower = pem_text.lower()
    return any(marker in lower for marker in _DISTRUST_MARKERS)


def filter_ca_bundle(pem_text: str) -> str:
    """Drop PEM certificates whose comment block or body mentions eMudhra/emSign."""

    def _keep(match: re.Match[str]) -> str:
        block = match.group(0)
        if bundle_contains_distrusted_roots(block):
            return "\n" if block.startswith("\n") else ""
        return block

    text = _CERT_BLOCK.sub(_keep, pem_text)
    return re.sub(r"\n{3,}", "\n\n", text)


@lru_cache(maxsize=4)
def _cached_filtered_path(source_digest: str, pem_text: str) -> str:
    cache_dir = _bundle_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"ca-bundle-no-emudhra-{source_digest[:16]}.pem"
    if not path.is_file():
        path.write_text(filter_ca_bundle(pem_text), encoding="utf-8")
    return str(path)


def filtered_ca_bundle_path(*, distrust: bool = True) -> str:
    """Path to a CA bundle suitable for ``httpx`` ``verify=``."""
    pem = _source_ca_pem()
    if not distrust:
        ssl_file = (os.environ.get("SSL_CERT_FILE") or "").strip()
        if ssl_file and Path(ssl_file).is_file():
            return ssl_file
        import certifi

        return certifi.where()
    digest = hashlib.sha256(pem.encode("utf-8")).hexdigest()
    return _cached_filtered_path(digest, pem)


def distrust_emudhra_enabled(settings: Any | None = None) -> bool:
    """Resolve ``upstream.distrust_emudhra_ca`` (default True)."""
    if settings is not None:
        upstream = getattr(settings, "upstream", None)
        if upstream is not None and hasattr(upstream, "distrust_emudhra_ca"):
            return bool(upstream.distrust_emudhra_ca)
    env = os.environ.get("DAARI_UPSTREAM__DISTRUST_EMUDHRA_CA")
    if env is not None and env.strip() != "":
        return env.strip().lower() not in {"0", "false", "no", "off"}
    return True


def resolve_httpx_verify(
    verify: Any = None,
    *,
    distrust: bool | None = None,
    settings: Any | None = None,
) -> Any:
    """httpx ``verify`` value: SSLContext over a filtered CA bundle when distrust is on.

    Explicit ``verify`` that is not ``True``/``None`` (custom path, ``False``,
    or SSLContext) is returned unchanged so callers can override.
    """
    if verify is not None and verify is not True:
        return verify
    if distrust is None:
        distrust = distrust_emudhra_enabled(settings)
    if not distrust:
        return True if verify is None else verify
    cafile = filtered_ca_bundle_path(distrust=True)
    return ssl.create_default_context(cafile=cafile)


def clear_bundle_cache() -> None:
    """Test helper: drop memoized filtered paths."""
    _cached_filtered_path.cache_clear()
