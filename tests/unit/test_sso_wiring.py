"""Unit tests for SSO wiring helpers (issue #136) — slice 2."""

from __future__ import annotations

from daari.enterprise.rbac import role_from_claims


def test_role_from_claims_custom_claim():
    assert role_from_claims({"groups": ["admin"]}, role_claim="groups") == "admin"
    assert role_from_claims({"role": "analyst"}) == "analyst"
    assert role_from_claims({}) == "user"
