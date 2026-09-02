"""MCP tool policy resolution (issue #277)."""

from __future__ import annotations

from daari.auth.virtual_keys import VirtualKey
from daari.config.settings import Settings
from daari.enterprise.audit import AuditLog
from daari.gateway.mcp_policy import McpToolPolicy, audit_tool_call, resolve_policy
from daari.server.auth import AuthClaims


def _key(metadata=None, team=None) -> VirtualKey:
    return VirtualKey(
        key_id="k1",
        name="agent",
        prefix="dk_abc",
        team_name=team,
        metadata=metadata or {},
    )


def _claims(metadata=None, team=None) -> AuthClaims:
    key = _key(metadata, team)
    return AuthClaims(kind="virtual", key_id=key.key_id, client_id="agent", virtual_key=key)


class TestMcpToolPolicy:
    def test_empty_policy_allows_everything(self):
        assert McpToolPolicy().allows("route")
        assert McpToolPolicy().allows("mcp_corp")

    def test_deny_wins_over_allow(self):
        policy = McpToolPolicy(allow=("*",), deny=("stats",))
        assert policy.allows("route")
        assert not policy.allows("stats")

    def test_allow_list_is_exclusive_and_glob(self):
        policy = McpToolPolicy(allow=("mcp_*", "route"))
        assert policy.allows("route")
        assert policy.allows("mcp_corp")
        assert not policy.allows("stats")
        assert not policy.allows("sourcegraph")

    def test_matching_is_case_insensitive(self):
        policy = McpToolPolicy(deny=("Stats",))
        assert not policy.allows("STATS")

    def test_from_mapping_tolerates_missing_and_bad_shapes(self):
        assert McpToolPolicy.from_mapping(None) == McpToolPolicy()
        assert McpToolPolicy.from_mapping({"allow": "route"}) == McpToolPolicy(allow=("route",))
        assert McpToolPolicy.from_mapping({"deny": ["a", 3, ""]}) == McpToolPolicy(deny=("a",))

    def test_merge_unions_deny_and_prefers_specific_allow(self):
        base = McpToolPolicy(allow=("route", "stats"), deny=("mcp_prod",))
        specific = McpToolPolicy(allow=("route",), deny=("stats",))
        merged = base.merged_with(specific)
        assert merged.allow == ("route",)
        assert set(merged.deny) == {"mcp_prod", "stats"}
        # A specific policy without an allow list inherits the broader one.
        assert base.merged_with(McpToolPolicy(deny=("x",))).allow == ("route", "stats")


class TestResolvePolicy:
    def test_master_key_gets_global_policy_only(self):
        settings = Settings.model_validate({"integrations": {"mcp_policy": {"deny": ["stats"]}}})
        policy = resolve_policy(AuthClaims(kind="master"), settings)
        assert not policy.allows("stats")
        assert policy.allows("route")

    def test_anonymous_caller_gets_global_policy(self):
        settings = Settings.model_validate({"integrations": {"mcp_policy": {"allow": ["route"]}}})
        policy = resolve_policy(None, settings)
        assert policy.allows("route")
        assert not policy.allows("stats")

    def test_key_metadata_layers_on_team_and_global(self):
        settings = Settings.model_validate(
            {
                "integrations": {
                    "mcp_policy": {"deny": ["mcp_prod"]},
                    "mcp_team_policies": {"eng": {"deny": ["stats"]}},
                }
            }
        )
        policy = resolve_policy(
            _claims({"mcp": {"allow": ["route", "stats", "mcp_*"]}}, "eng"), settings
        )
        assert policy.allows("route")
        assert not policy.allows("stats")  # team deny
        assert not policy.allows("mcp_prod")  # global deny
        assert policy.allows("mcp_dev")
        assert not policy.allows("sourcegraph")  # not in key allow list


def test_audit_tool_call_records_decision_without_arguments(tmp_path):
    audit = AuditLog(tmp_path / "audit.sqlite3")
    audit_tool_call(
        audit,
        _claims(team="eng"),
        tool="route",
        decision="deny",
        method="tools/call",
        transport="jsonrpc",
        arguments={"input": "secret repo contents"},
    )
    rows = audit.list()
    assert len(rows) == 1
    row = rows[0]
    assert row["actor"] == "k1"
    assert row["role"] == "eng"
    assert row["action"] == "mcp.tools/call"
    assert row["detail"]["tool"] == "route"
    assert row["detail"]["decision"] == "deny"
    assert "secret repo contents" not in str(row)
    assert "arguments" not in row["detail"]


def test_audit_tool_call_master_and_anonymous_actors(tmp_path):
    audit = AuditLog(tmp_path / "audit.sqlite3")
    audit_tool_call(
        audit,
        AuthClaims(kind="master"),
        tool="stats",
        decision="allow",
        method="tools/call",
        transport="rest",
    )
    audit_tool_call(
        audit, None, tool="stats", decision="allow", method="tools/call", transport="rest"
    )
    actors = {row["actor"] for row in audit.list()}
    assert actors == {"master", "anonymous"}
