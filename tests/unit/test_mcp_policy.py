"""MCP tool policy resolution (issue #277) and server allowlists (#1201)."""

from __future__ import annotations

from daari.auth.virtual_keys import VirtualKey
from daari.config.settings import Settings
from daari.enterprise.audit import AuditLog
from daari.gateway.mcp_policy import (
    McpClientPolicy,
    McpServerPolicy,
    McpToolPolicy,
    audit_client_decision,
    audit_tool_call,
    resolve_client_identity,
    resolve_client_policy,
    resolve_policy,
    resolve_server_policy,
)
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


class TestMcpServerPolicy:
    def test_empty_policy_allows_every_server(self):
        assert McpServerPolicy().allows("weather")
        assert McpServerPolicy().allows("github")

    def test_allow_only_is_exclusive(self):
        policy = McpServerPolicy(allow=("weather", "finance-*"))
        assert policy.allows("weather")
        assert policy.allows("finance-prod")
        assert not policy.allows("github")
        assert not policy.allows("shell")

    def test_deny_wins_over_allow(self):
        policy = McpServerPolicy(allow=("*",), deny=("shell",))
        assert policy.allows("weather")
        assert not policy.allows("shell")

    def test_merge_key_over_team(self):
        team = McpServerPolicy(allow=("weather", "github"), deny=("shell",))
        key = McpServerPolicy(allow=("weather",), deny=("github",))
        merged = team.merged_with(key)
        assert merged.allow == ("weather",)
        assert set(merged.deny) == {"shell", "github"}
        assert merged.allows("weather")
        assert not merged.allows("github")
        assert not merged.allows("shell")

    def test_from_mapping_reads_servers_block(self):
        assert McpServerPolicy.from_mapping(None) == McpServerPolicy()
        assert McpServerPolicy.from_mapping({"allow": "weather"}) == McpServerPolicy(
            allow=("weather",)
        )
        assert McpServerPolicy.from_mapping({"deny": ["shell", 3, ""]}) == McpServerPolicy(
            deny=("shell",)
        )


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


class TestResolveServerPolicy:
    def test_key_over_team_merge(self):
        settings = Settings.model_validate(
            {
                "integrations": {
                    "mcp_policy": {"servers": {"deny": ["shell"]}},
                    "mcp_team_policies": {
                        "finance": {"servers": {"allow": ["weather", "github"], "deny": []}}
                    },
                }
            }
        )
        policy = resolve_server_policy(
            _claims({"mcp": {"servers": {"allow": ["weather"], "deny": ["github"]}}}, "finance"),
            settings,
        )
        assert policy.allows("weather")
        assert not policy.allows("github")  # key deny
        assert not policy.allows("shell")  # global deny
        assert not policy.allows("slack")  # not in key allow


class TestMcpClientPolicy:
    def test_empty_policy_allows_every_client(self):
        assert McpClientPolicy().allows("claude-code")
        assert McpClientPolicy().allows(None)

    def test_allow_hit_and_deny_miss(self):
        policy = McpClientPolicy(allow=("claude-*", "cursor"))
        assert policy.allows("claude-code")
        assert policy.allows("cursor")
        assert not policy.allows("evil-bot")

    def test_deny_wins(self):
        policy = McpClientPolicy(allow=("*",), deny=("evil-*",))
        assert policy.allows("claude-code")
        assert not policy.allows("evil-bot")

    def test_unset_passthrough_when_not_restrictive(self):
        assert not McpClientPolicy().is_restrictive()
        assert McpClientPolicy(allow=("x",)).is_restrictive()


class TestResolveClientPolicy:
    def test_key_over_team_merge(self):
        settings = Settings.model_validate(
            {
                "integrations": {
                    "mcp_policy": {"clients": {"deny": ["evil-*"]}},
                    "mcp_team_policies": {
                        "eng": {"clients": {"allow": ["claude-*", "cursor"], "deny": []}}
                    },
                }
            }
        )
        policy = resolve_client_policy(
            _claims({"mcp": {"clients": {"allow": ["claude-code"], "deny": []}}}, "eng"),
            settings,
        )
        assert policy.allows("claude-code")
        assert not policy.allows("cursor")  # key allow narrows
        assert not policy.allows("evil-bot")  # global deny


class TestResolveClientIdentity:
    def test_prefers_meta_client_info(self):
        identity = resolve_client_identity(
            {
                "clientInfo": {"name": "params-client"},
                "_meta": {
                    "io.modelcontextprotocol/clientInfo": {"name": "meta-client", "version": "1"}
                },
            },
            claims=_claims(),
            user_agent="ua/1.0",
        )
        assert identity == "meta-client"

    def test_falls_back_to_claim_then_ua(self):
        assert (
            resolve_client_identity({}, claims=_claims(), user_agent="ua/1.0") == "agent"
        )
        assert resolve_client_identity({}, claims=None, user_agent="ua/1.0") == "ua/1.0"


def test_audit_client_decision_records_row(tmp_path):
    audit = AuditLog(tmp_path / "audit.sqlite3")
    audit_client_decision(
        audit,
        _claims(team="eng"),
        client="evil-bot",
        decision="deny",
        method="initialize",
        transport="jsonrpc",
    )
    row = audit.list()[0]
    assert row["action"] == "mcp.client"
    assert row["detail"]["client"] == "evil-bot"
    assert row["detail"]["decision"] == "deny"
    assert row["detail"]["method"] == "initialize"


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


def test_audit_tool_call_records_server_id(tmp_path):
    audit = AuditLog(tmp_path / "audit.sqlite3")
    audit_tool_call(
        audit,
        _claims(team="eng"),
        tool="mcp_shell",
        decision="deny",
        method="tools/call",
        transport="jsonrpc",
        server="shell",
    )
    row = audit.list()[0]
    assert row["detail"]["server"] == "shell"
    assert row["detail"]["tool"] == "mcp_shell"
    assert row["detail"]["decision"] == "deny"


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
