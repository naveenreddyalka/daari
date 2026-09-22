"""TLS / mTLS helpers for ``daari serve`` (#932).

Builds uvicorn SSL kwargs from ``server.tls`` settings. Paths may be plain
filesystem paths or ``secret://`` refs; PEM payloads resolved from refs are
materialized to owner-only temp files so uvicorn can open them.
"""

from __future__ import annotations

import os
import ssl
import tempfile
from pathlib import Path

from daari.config.settings import TlsSettings
from daari.security.secret_refs import is_secret_ref, resolve_secret_ref

_PEM_MARKERS = ("-----BEGIN ",)


def materialize_tls_path(value: str, *, suffix: str = ".pem") -> str:
    """Return a filesystem path for a TLS file setting.

    Plain paths that already exist pass through. ``secret://`` refs are
    resolved; if the result looks like PEM, it is written to a secure temp
    file. A resolved value that is itself an existing path is used as-is.
    """
    raw = (value or "").strip()
    if not raw:
        raise ValueError("TLS path value is empty")
    if is_secret_ref(raw):
        raw = resolve_secret_ref(raw)
    if any(marker in raw for marker in _PEM_MARKERS):
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="daari-tls-",
            suffix=suffix,
            delete=False,
        )
        try:
            with handle as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(handle.name, 0o600)
            return handle.name
        except BaseException:
            Path(handle.name).unlink(missing_ok=True)
            raise
    path = Path(raw).expanduser()
    if not path.is_file():
        raise ValueError(f"TLS file not found: {raw}")
    return str(path)


def build_uvicorn_ssl_kwargs(tls: TlsSettings) -> dict:
    """Map ``server.tls`` to uvicorn ``run()`` / ``Config`` SSL kwargs.

    Returns ``{}`` when TLS is unset. Raises ``ValueError`` when only one of
    cert/key is set. When ``client_ca`` is set, enables mTLS
    (``ssl_cert_reqs=CERT_REQUIRED``).
    """
    cert = (tls.cert_file or "").strip()
    key = (tls.key_file or "").strip()
    client_ca = (tls.client_ca or "").strip()
    if not cert and not key and not client_ca:
        return {}
    if not cert or not key:
        raise ValueError(
            "server.tls requires both cert_file and key_file "
            "(or --tls-cert and --tls-key)"
        )
    kwargs: dict = {
        "ssl_certfile": materialize_tls_path(cert, suffix=".crt"),
        "ssl_keyfile": materialize_tls_path(key, suffix=".key"),
    }
    if client_ca:
        kwargs["ssl_ca_certs"] = materialize_tls_path(client_ca, suffix=".crt")
        kwargs["ssl_cert_reqs"] = ssl.CERT_REQUIRED
    return kwargs
