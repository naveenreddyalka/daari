"""Opt-in fail-closed when virtual key has no MCP grant (#1352)."""

from __future__ import annotations

from daari.config.settings import Settings
from daari.gateway.mcp_policy import (
    DENY_ALL_TOOLS,
    key_has_mcp_grant,
    resolve_policy,
    virtual_key_lacks_mcp_grant,
)
from daari.auth.virtual_keys import VirtualKey
from daari.server.auth import AuthClaims


def _key(metadata=None) -> VirtualKey:
    return VirtualKey(
        key_id="k1",
        name="agent",
        prefix="dk_abc",
        metadata=metadata or {},
    )


def _claims(metadata=None, *, kind: str = "virtual") -> AuthClaims:
    if kind == "master":
        return AuthClaims(kind="master")
    key = _key(metadata)
    return AuthClaims(kind="virtual", key_id=key.key_id, client_id="agent", virtual_key=key)


class TestKeyHasMcpGrant:
    def test_missing_mcp_block_is_not_a_grant(self):
        assert key_has_mcp_grant({}) is False
        assert key_has_mcp_grant({"other": 1}) is False
        assert key_has_mcp_grant({"mcp": {}}) is False
        assert key_has_mcp_grant({"mcp": "nope"}) is False

    def test_allow_deny_or_servers_count(self):
        assert key_has_mcp_grant({"mcp": {"allow": ["route"]}}) is True
        assert key_has_mcp_grant({"mcp": {"deny": ["stats"]}}) is True
        assert key_has_mcp_grant({"mcp": {"allow": []}}) is True
        assert key_has_mcp_grant({"mcp": {"servers": {"allow": ["weather"]}}}) is True
        assert key_has_mcp_grant({"mcp": {"servers": {"deny": ["shell"]}}}) is True

    def test_clients_alone_is_not_a_tool_grant(self):
        assert key_has_mcp_grant({"mcp": {"clients": {"allow": ["claude-*"]}}}) is False
        assert key_has_mcp_grant({"mcp": {"servers": {}}}) is False


class TestRequireKeyAccessDefined:
    def test_flag_defaults_off(self):
        settings = Settings()
        assert settings.integrations.mcp_policy.require_key_access_defined is False

    def test_flag_off_never_lacks_grant(self):
        settings = Settings()
        assert virtual_key_lacks_mcp_grant(_claims({}), settings) is False

    def test_flag_on_vk_without_grant(self):
        settings = Settings.model_validate(
            {"integrations": {"mcp_policy": {"require_key_access_defined": True}}}
        )
        assert virtual_key_lacks_mcp_grant(_claims({}), settings) is True
        assert virtual_key_lacks_mcp_grant(_claims({"mcp": {}}), settings) is True

    def test_flag_on_vk_with_grant_ok(self):
        settings = Settings.model_validate(
            {"integrations": {"mcp_policy": {"require_key_access_defined": True}}}
        )
        assert (
            virtual_key_lacks_mcp_grant(_claims({"mcp": {"allow": ["route"]}}), settings)
            is False
        )
        assert (
            virtual_key_lacks_mcp_grant(
                _claims({"mcp": {"servers": {"allow": ["weather"]}}}), settings
            )
            is False
        )

    def test_master_and_anonymous_unchanged(self):
        settings = Settings.model_validate(
            {"integrations": {"mcp_policy": {"require_key_access_defined": True}}}
        )
        assert virtual_key_lacks_mcp_grant(_claims(kind="master"), settings) is False
        assert virtual_key_lacks_mcp_grant(None, settings) is False

    def test_resolve_policy_returns_deny_all_when_lacking_grant(self):
        settings = Settings.model_validate(
            {"integrations": {"mcp_policy": {"require_key_access_defined": True}}}
        )
        policy = resolve_policy(_claims({}), settings)
        assert policy == DENY_ALL_TOOLS
        assert not policy.allows("route")
        assert not policy.allows("stats")

    def test_resolve_policy_normal_when_granted(self):
        settings = Settings.model_validate(
            {
                "integrations": {
                    "mcp_policy": {
                        "require_key_access_defined": True,
                    }
                }
            }
        )
        policy = resolve_policy(_claims({"mcp": {"allow": ["route"]}}), settings)
        assert policy.allows("route")
        assert not policy.allows("stats")
