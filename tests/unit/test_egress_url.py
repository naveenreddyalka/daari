"""SSRF / private-network guards for MCP egress URLs (#1214)."""

from __future__ import annotations

import pytest

from daari.security.egress_url import EgressUrlBlocked, validate_egress_url


def test_public_https_allowed():
    validate_egress_url(
        "https://example.com/mcp",
        resolver=lambda _host: ["93.184.216.34"],
    )


def test_metadata_ip_blocked():
    with pytest.raises(EgressUrlBlocked, match="blocked address"):
        validate_egress_url("http://169.254.169.254/latest/meta-data")


def test_rfc1918_blocked():
    with pytest.raises(EgressUrlBlocked, match="blocked address"):
        validate_egress_url("http://10.0.0.1/mcp")


def test_localhost_blocked():
    with pytest.raises(EgressUrlBlocked, match="blocked"):
        validate_egress_url("http://127.0.0.1:8080/mcp")
    with pytest.raises(EgressUrlBlocked, match="blocked"):
        validate_egress_url(
            "http://localhost/mcp",
            resolver=lambda _host: ["127.0.0.1"],
        )


def test_non_http_scheme_blocked():
    with pytest.raises(EgressUrlBlocked, match="scheme"):
        validate_egress_url("file:///etc/passwd")


def test_allow_private_networks_opt_in():
    validate_egress_url("http://10.0.0.1/mcp", allow_private_networks=True)
    validate_egress_url("http://127.0.0.1/mcp", allow_private_networks=True)
    validate_egress_url(
        "http://localhost/mcp",
        allow_private_networks=True,
        resolver=lambda _host: ["127.0.0.1"],
    )


def test_dns_rebinding_blocked_when_any_address_private():
    with pytest.raises(EgressUrlBlocked, match="blocked address"):
        validate_egress_url(
            "https://evil.example/mcp",
            resolver=lambda _host: ["93.184.216.34", "10.0.0.1"],
        )
