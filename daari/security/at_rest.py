"""Envelope encryption for persisted payload stores (#1958).

Opt-in via ``security.at_rest_key``. When unset, seal/open are no-ops so
existing plaintext rows keep working. Tagged ciphertext never round-trips
as a successful read — wrong or missing keys raise ``AtRestDecryptError``.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

TAG_PREFIX = "daari-atr1:"
_NONCE_BYTES = 12


class AtRestDecryptError(RuntimeError):
    """Ciphertext present but no usable key, or AEAD authentication failed."""


def _key_material(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _key_id(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8]


def is_sealed(value: str) -> bool:
    return isinstance(value, str) and value.startswith(TAG_PREFIX)


@dataclass(frozen=True)
class AtRestCipher:
    """AES-256-GCM with a key-id tag for rotation."""

    key: str
    previous_key: str = ""

    def _keys(self) -> list[tuple[str, bytes]]:
        keys: list[tuple[str, bytes]] = []
        if self.key:
            keys.append((_key_id(self.key), _key_material(self.key)))
        if self.previous_key:
            kid = _key_id(self.previous_key)
            if not keys or kid != keys[0][0]:
                keys.append((kid, _key_material(self.previous_key)))
        return keys

    def encrypt(self, plaintext: str) -> str:
        if not self.key:
            return plaintext
        kid, material = self._keys()[0]
        nonce = os.urandom(_NONCE_BYTES)
        ct = AESGCM(material).encrypt(nonce, plaintext.encode("utf-8"), None)
        blob = base64.urlsafe_b64encode(nonce + ct).decode("ascii").rstrip("=")
        return f"{TAG_PREFIX}{kid}:{blob}"

    def decrypt(self, value: str) -> str:
        if not is_sealed(value):
            return value
        rest = value[len(TAG_PREFIX) :]
        try:
            kid, blob = rest.split(":", 1)
        except ValueError as exc:
            raise AtRestDecryptError("malformed at-rest ciphertext") from exc
        pad = "=" * (-len(blob) % 4)
        try:
            raw = base64.urlsafe_b64decode(blob + pad)
        except Exception as exc:
            raise AtRestDecryptError("malformed at-rest ciphertext") from exc
        if len(raw) <= _NONCE_BYTES:
            raise AtRestDecryptError("malformed at-rest ciphertext")
        nonce, ct = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        candidates = self._keys()
        if not candidates:
            raise AtRestDecryptError(
                "at-rest ciphertext present but security.at_rest_key is unset"
            )
        # Prefer matching key-id, then try the rest (rotation / id mismatch).
        ordered = [k for k in candidates if k[0] == kid] + [
            k for k in candidates if k[0] != kid
        ]
        for _, material in ordered:
            try:
                return AESGCM(material).decrypt(nonce, ct, None).decode("utf-8")
            except Exception:
                continue
        raise AtRestDecryptError("failed to decrypt at-rest ciphertext")


_cipher: AtRestCipher | None = None


def reset_at_rest() -> None:
    """Clear process-wide cipher (tests / daemon restart)."""
    global _cipher
    _cipher = None


def configure_at_rest(*, key: str = "", previous_key: str = "") -> None:
    """Install the process-wide cipher from resolved settings."""
    global _cipher
    key = (key or "").strip()
    previous_key = (previous_key or "").strip()
    if not key and not previous_key:
        _cipher = None
        return
    _cipher = AtRestCipher(key=key, previous_key=previous_key)


def current_cipher() -> AtRestCipher | None:
    return _cipher


def enabled() -> bool:
    return _cipher is not None and bool(_cipher.key)


def seal_text(plaintext: str) -> str:
    """Encrypt when a key is configured; otherwise return plaintext unchanged."""
    if _cipher is None or not _cipher.key:
        return plaintext
    return _cipher.encrypt(plaintext)


def open_text(value: str) -> str:
    """Decrypt tagged values; pass plaintext through; never return ciphertext."""
    if not is_sealed(value):
        return value
    if _cipher is None:
        raise AtRestDecryptError(
            "at-rest ciphertext present but security.at_rest_key is unset"
        )
    return _cipher.decrypt(value)


def loads_json_maybe_sealed(value: str) -> object:
    """json.loads after transparent decrypt (for sealed JSON blobs)."""
    import json

    return json.loads(open_text(value))
