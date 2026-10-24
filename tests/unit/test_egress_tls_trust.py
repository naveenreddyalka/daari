"""Filter eMudhra/emSign roots from egress CA bundles (#1907)."""

from __future__ import annotations

import ssl
from pathlib import Path

import httpx
import pytest

from daari.config.settings import Settings
from daari.router.http_pool import build_async_client
from daari.security import egress_tls


_SAMPLE_TRUSTED = """\
# Label: "Example Root"
-----BEGIN CERTIFICATE-----
MIIBkTCB+wIJAKHBfLRl7HkAMA0GCSqGSIb3DQEBCwUAMBQxEjAQBgNVBAMMCVRl
c3QgUm9vdDAeFw0yNjAxMDEwMDAwMDBaFw0zNjAxMDEwMDAwMDBaMBQxEjAQBgNV
BAMMCVRlc3QgUm9vdDBcMA0GCSqGSIb3DQEBAQUAA0sAMEgCQQC8n0exampledata
-----END CERTIFICATE-----
"""

_SAMPLE_EMSIGN = """\
# Issuer: CN=emSign Root CA - G1 O=eMudhra Technologies Limited OU=emSign PKI
# Subject: CN=emSign Root CA - G1 O=eMudhra Technologies Limited OU=emSign PKI
# Label: "emSign Root CA - G1"
-----BEGIN CERTIFICATE-----
MIIBkTCB+wIJAKHBfLRl7HkBMA0GCSqGSIb3DQEBCwUAMBQxEjAQBgNVBAMMCVRl
c3QgUm9vdDAeFw0yNjAxMDEwMDAwMDBaFw0zNjAxMDEwMDAwMDBaMBQxEjAQBgNV
BAMMCVRlc3QgUm9vdDBcMA0GCSqGSIb3DQEBAQUAA0sAMEgCQQC8n0exampledata
-----END CERTIFICATE-----
"""


def test_filter_ca_bundle_drops_emsign_keeps_others() -> None:
    filtered = egress_tls.filter_ca_bundle(_SAMPLE_TRUSTED + "\n" + _SAMPLE_EMSIGN)
    assert "emSign" not in filtered
    assert "eMudhra" not in filtered
    assert "Example Root" in filtered
    assert "-----BEGIN CERTIFICATE-----" in filtered


def test_bundle_contains_distrusted_roots() -> None:
    assert egress_tls.bundle_contains_distrusted_roots(_SAMPLE_EMSIGN) is True
    assert egress_tls.bundle_contains_distrusted_roots(_SAMPLE_TRUSTED) is False


def test_filter_certifi_removes_emudhra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import certifi

    src = Path(certifi.where())
    assert egress_tls.bundle_contains_distrusted_roots(src.read_text(encoding="utf-8"))

    egress_tls.clear_bundle_cache()
    monkeypatch.setattr(egress_tls, "_bundle_cache_dir", lambda: tmp_path)
    out = egress_tls.filtered_ca_bundle_path(distrust=True)
    text = Path(out).read_text(encoding="utf-8")
    assert not egress_tls.bundle_contains_distrusted_roots(text)
    assert text.count("-----BEGIN CERTIFICATE-----") == src.read_text(encoding="utf-8").count(
        "-----BEGIN CERTIFICATE-----"
    ) - 1


def test_httpx_verify_path_when_distrust_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    egress_tls.clear_bundle_cache()
    monkeypatch.setattr(egress_tls, "_bundle_cache_dir", lambda: tmp_path)
    verify = egress_tls.resolve_httpx_verify(distrust=True)
    assert isinstance(verify, ssl.SSLContext)
    cafile = egress_tls.filtered_ca_bundle_path(distrust=True)
    assert Path(cafile).is_file()
    assert not egress_tls.bundle_contains_distrusted_roots(
        Path(cafile).read_text(encoding="utf-8")
    )


def test_httpx_verify_true_when_distrust_off() -> None:
    assert egress_tls.resolve_httpx_verify(distrust=False) is True


def test_build_async_client_uses_filtered_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    egress_tls.clear_bundle_cache()
    monkeypatch.setattr(egress_tls, "_bundle_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        egress_tls,
        "distrust_emudhra_enabled",
        lambda settings=None: True,
    )
    captured: dict = {}
    real = httpx.AsyncClient

    def tracking(*args, **kwargs):
        captured.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", tracking)
    client = build_async_client(httpx)
    assert isinstance(captured.get("verify"), ssl.SSLContext)
    cafile = egress_tls.filtered_ca_bundle_path(distrust=True)
    assert not egress_tls.bundle_contains_distrusted_roots(
        Path(cafile).read_text(encoding="utf-8")
    )
    del client


def test_settings_default_distrust_on() -> None:
    assert Settings().upstream.distrust_emudhra_ca is True
