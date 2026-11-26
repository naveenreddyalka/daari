"""MCP tool governance: per-key / per-team allow-deny policy and call audit (issue #277).

Tool calls carry the most sensitive payloads a gateway sees (repo contents,
command output), so the policy is evaluated on the developer's machine and the
audit row records only *what* was called and the decision — never the
arguments.

Server-id allowlists (#1201) sit beside tool-name globs: a key may be granted
the `weather` egress server without ever seeing `shell`, even when tool names
collide across servers.

Per-server tool subsets (#1288) narrow a granted server to named tools: the
effective catalog is `server tools ∩ key subset`, and an empty subset fails
closed (no tools from that server).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any

from daari.enterprise.audit import AuditLog

# JSON-RPC server-error range (-32000..-32099) reserved for implementation errors.
TOOL_DENIED = -32003
AUDIT_ACTION = "mcp.tools/call"
KEY_METADATA_FIELD = "mcp"
# Sentinel allow pattern that matches no tool name — used when fail-closed (#1352).
_DENY_ALL_SENTINEL = "__daari_no_mcp_grant__"


def _patterns(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple, set)):
        return ()
    return tuple(item.strip() for item in raw if isinstance(item, str) and item.strip())


def _servers_block(raw: Any) -> Any:
    """Pull the nested `servers` mapping from mcp_policy / metadata.mcp."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw.get("servers")
    return getattr(raw, "servers", None)


def _clients_block(raw: Any) -> Any:
    """Pull the nested `clients` mapping from mcp_policy / metadata.mcp (#1215)."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw.get("clients")
    return getattr(raw, "clients", None)


SERVER_TOOLS_FIELD = "server_tools"


def _server_tools_block(raw: Any) -> Any:
    """Pull the nested `server_tools` mapping from mcp_policy / metadata.mcp (#1288)."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw.get(SERVER_TOOLS_FIELD)
    return getattr(raw, SERVER_TOOLS_FIELD, None)


CLIENT_INFO_META_KEY = "io.modelcontextprotocol/clientInfo"
CLIENT_DENIED = -32004
AUDIT_CLIENT_ACTION = "mcp.client"


@dataclass(frozen=True)
class McpToolPolicy:
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, raw: Any) -> McpToolPolicy:
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raw = {"allow": getattr(raw, "allow", None), "deny": getattr(raw, "deny", None)}
        return cls(allow=_patterns(raw.get("allow")), deny=_patterns(raw.get("deny")))

    def allows(self, tool: str) -> bool:
        name = tool.strip().lower()
        if any(fnmatchcase(name, pattern.lower()) for pattern in self.deny):
            return False
        if not self.allow:
            return True
        return any(fnmatchcase(name, pattern.lower()) for pattern in self.allow)

    def merged_with(self, specific: McpToolPolicy) -> McpToolPolicy:
        """Layer a narrower scope on top: denies accumulate, the narrower allow list wins."""
        deny = self.deny + tuple(item for item in specific.deny if item not in self.deny)
        return McpToolPolicy(allow=specific.allow or self.allow, deny=deny)


# Exclusive allow list that matches nothing → empty catalog / tools/call deny (#1352).
DENY_ALL_TOOLS = McpToolPolicy(allow=(_DENY_ALL_SENTINEL,))


def key_has_mcp_grant(metadata: Any) -> bool:
    """True when virtual-key metadata declares an MCP tool/server grant (#1352).

    A grant is ``metadata.mcp`` containing ``allow``, ``deny``, and/or
    ``servers.allow`` / ``servers.deny``. ``clients`` alone is not a tool grant.
    """
    if not isinstance(metadata, dict):
        return False
    mcp = metadata.get(KEY_METADATA_FIELD)
    if not isinstance(mcp, dict):
        return False
    if "allow" in mcp or "deny" in mcp:
        return True
    servers = mcp.get("servers")
    if isinstance(servers, dict) and ("allow" in servers or "deny" in servers):
        return True
    server_tools = mcp.get(SERVER_TOOLS_FIELD)
    if isinstance(server_tools, dict) and server_tools:
        return True
    return False


def virtual_key_lacks_mcp_grant(claims: Any, settings: Any) -> bool:
    """True when opt-in fail-closed applies to this virtual key (#1352)."""
    integrations = getattr(settings, "integrations", None)
    policy_settings = getattr(integrations, "mcp_policy", None)
    if not bool(getattr(policy_settings, "require_key_access_defined", False)):
        return False
    if claims is None or getattr(claims, "kind", None) != "virtual":
        return False
    key = getattr(claims, "virtual_key", None)
    if key is None:
        return False
    return not key_has_mcp_grant(getattr(key, "metadata", None) or {})


@dataclass(frozen=True)
class McpServerPolicy:
    """Allow/deny MCP *egress server ids* (issue #1201). Same merge rules as tools."""

    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, raw: Any) -> McpServerPolicy:
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raw = {"allow": getattr(raw, "allow", None), "deny": getattr(raw, "deny", None)}
        return cls(allow=_patterns(raw.get("allow")), deny=_patterns(raw.get("deny")))

    def allows(self, server: str) -> bool:
        name = server.strip().lower()
        if any(fnmatchcase(name, pattern.lower()) for pattern in self.deny):
            return False
        if not self.allow:
            return True
        return any(fnmatchcase(name, pattern.lower()) for pattern in self.allow)

    def merged_with(self, specific: McpServerPolicy) -> McpServerPolicy:
        deny = self.deny + tuple(item for item in specific.deny if item not in self.deny)
        return McpServerPolicy(allow=specific.allow or self.allow, deny=deny)

    def is_restrictive(self) -> bool:
        return bool(self.allow or self.deny)


@dataclass(frozen=True)
class McpServerToolSubset:
    """Per-egress-server tool-name allowlist (issue #1288).

    ``by_server`` maps a lower-cased server id to glob patterns. A server that
    is absent is unrestricted; a server mapped to an empty tuple exposes no
    tools (fail closed). Layering follows allow lists: the most specific scope
    that names a server wins for that server.
    """

    by_server: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Any) -> McpServerToolSubset:
        if not isinstance(raw, dict):
            return cls()
        by_server: dict[str, tuple[str, ...]] = {}
        for server, patterns in raw.items():
            sid = str(server or "").strip().lower()
            if not sid or patterns is None:
                continue
            by_server[sid] = _patterns(patterns)
        return cls(by_server=by_server)

    def for_server(self, server: str) -> tuple[str, ...] | None:
        return self.by_server.get(server.strip().lower())

    def restricts(self, server: str) -> bool:
        return server.strip().lower() in self.by_server

    def allows(self, server: str, tool: str) -> bool:
        patterns = self.for_server(server)
        if patterns is None:
            return True
        name = tool.strip().lower()
        return any(fnmatchcase(name, pattern.lower()) for pattern in patterns)

    def merged_with(self, specific: McpServerToolSubset) -> McpServerToolSubset:
        return McpServerToolSubset(by_server={**self.by_server, **specific.by_server})

    def is_restrictive(self) -> bool:
        return bool(self.by_server)

    def as_meta(self) -> dict[str, list[str]] | None:
        """Plain mapping for ``RequestMeta.mcp_server_tools``; None when unrestricted."""
        if not self.by_server:
            return None
        return {sid: list(patterns) for sid, patterns in self.by_server.items()}


@dataclass(frozen=True)
class McpClientPolicy:
    """Allow/deny MCP *ingress client identities* (issue #1215). Same merge rules."""

    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, raw: Any) -> McpClientPolicy:
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raw = {"allow": getattr(raw, "allow", None), "deny": getattr(raw, "deny", None)}
        return cls(allow=_patterns(raw.get("allow")), deny=_patterns(raw.get("deny")))

    def allows(self, client: str | None) -> bool:
        """Empty allow+deny = passthrough. Empty allow with deny = deny-only."""
        if not self.allow and not self.deny:
            return True
        name = (client or "").strip().lower()
        if not name:
            return not bool(self.allow)
        if any(fnmatchcase(name, pattern.lower()) for pattern in self.deny):
            return False
        if not self.allow:
            return True
        return any(fnmatchcase(name, pattern.lower()) for pattern in self.allow)

    def merged_with(self, specific: McpClientPolicy) -> McpClientPolicy:
        deny = self.deny + tuple(item for item in specific.deny if item not in self.deny)
        return McpClientPolicy(allow=specific.allow or self.allow, deny=deny)

    def is_restrictive(self) -> bool:
        return bool(self.allow or self.deny)


def resolve_policy(claims: Any, settings: Any) -> McpToolPolicy:
    if virtual_key_lacks_mcp_grant(claims, settings):
        return DENY_ALL_TOOLS
    integrations = getattr(settings, "integrations", None)
    policy = McpToolPolicy.from_mapping(getattr(integrations, "mcp_policy", None))
    key = getattr(claims, "virtual_key", None) if claims is not None else None
    if key is None:
        return policy
    team_policies = getattr(integrations, "mcp_team_policies", None) or {}
    if key.team_name and key.team_name in team_policies:
        policy = policy.merged_with(McpToolPolicy.from_mapping(team_policies[key.team_name]))
    key_policy = (key.metadata or {}).get(KEY_METADATA_FIELD)
    return policy.merged_with(McpToolPolicy.from_mapping(key_policy))


def resolve_server_policy(claims: Any, settings: Any) -> McpServerPolicy:
    """Global → team → key layers for MCP egress server ids (#1201)."""
    integrations = getattr(settings, "integrations", None)
    policy = McpServerPolicy.from_mapping(_servers_block(getattr(integrations, "mcp_policy", None)))
    key = getattr(claims, "virtual_key", None) if claims is not None else None
    if key is None:
        return policy
    team_policies = getattr(integrations, "mcp_team_policies", None) or {}
    if key.team_name and key.team_name in team_policies:
        policy = policy.merged_with(
            McpServerPolicy.from_mapping(_servers_block(team_policies[key.team_name]))
        )
    key_policy = (key.metadata or {}).get(KEY_METADATA_FIELD)
    return policy.merged_with(McpServerPolicy.from_mapping(_servers_block(key_policy)))


def resolve_server_tool_subset(claims: Any, settings: Any) -> McpServerToolSubset:
    """Global → team → key layers for per-server tool-name subsets (#1288)."""
    integrations = getattr(settings, "integrations", None)
    subset = McpServerToolSubset.from_mapping(
        _server_tools_block(getattr(integrations, "mcp_policy", None))
    )
    key = getattr(claims, "virtual_key", None) if claims is not None else None
    if key is None:
        return subset
    team_policies = getattr(integrations, "mcp_team_policies", None) or {}
    if key.team_name and key.team_name in team_policies:
        subset = subset.merged_with(
            McpServerToolSubset.from_mapping(_server_tools_block(team_policies[key.team_name]))
        )
    key_policy = (key.metadata or {}).get(KEY_METADATA_FIELD)
    return subset.merged_with(McpServerToolSubset.from_mapping(_server_tools_block(key_policy)))


def apply_server_tool_subset_to_meta(meta: Any, claims: Any, settings: Any) -> None:
    """Stamp the resolved subset on RequestMeta so egress enforces it (#1288)."""
    if getattr(meta, "mcp_server_tools", None) is not None:
        return
    resolved = resolve_server_tool_subset(claims, settings).as_meta()
    if resolved is not None:
        meta.mcp_server_tools = resolved


def resolve_client_policy(claims: Any, settings: Any) -> McpClientPolicy:
    """Global → team → key layers for MCP ingress client identities (#1215)."""
    integrations = getattr(settings, "integrations", None)
    policy = McpClientPolicy.from_mapping(_clients_block(getattr(integrations, "mcp_policy", None)))
    key = getattr(claims, "virtual_key", None) if claims is not None else None
    if key is None:
        return policy
    team_policies = getattr(integrations, "mcp_team_policies", None) or {}
    if key.team_name and key.team_name in team_policies:
        policy = policy.merged_with(
            McpClientPolicy.from_mapping(_clients_block(team_policies[key.team_name]))
        )
    key_policy = (key.metadata or {}).get(KEY_METADATA_FIELD)
    return policy.merged_with(McpClientPolicy.from_mapping(_clients_block(key_policy)))


def _client_info_name(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def resolve_client_identity(
    params: dict[str, Any] | None,
    *,
    claims: Any = None,
    user_agent: str | None = None,
) -> str | None:
    """Prefer ``_meta`` clientInfo.name, then OAuth/VK ``client_id``, then User-Agent (#1215)."""
    if isinstance(params, dict):
        meta = params.get("_meta")
        if isinstance(meta, dict):
            from_meta = _client_info_name(meta.get(CLIENT_INFO_META_KEY))
            if from_meta:
                return from_meta
        from_params = _client_info_name(params.get("clientInfo"))
        if from_params:
            return from_params
    if claims is not None:
        claim_id = getattr(claims, "client_id", None)
        if isinstance(claim_id, str) and claim_id.strip():
            return claim_id.strip()
        key = getattr(claims, "virtual_key", None)
        if key is not None:
            key_client = getattr(key, "client_id", None)
            if isinstance(key_client, str) and key_client.strip():
                return key_client.strip()
    if isinstance(user_agent, str) and user_agent.strip():
        return user_agent.strip()
    return None


def server_id_from_provider(provider_id: str | None) -> str | None:
    """`mcp:weather` → `weather`; non-MCP providers return None."""
    if not provider_id or not isinstance(provider_id, str):
        return None
    if not provider_id.startswith("mcp:"):
        return None
    sid = provider_id.split(":", 1)[1].strip()
    return sid or None


def _actor(claims: Any) -> tuple[str, str]:
    if claims is None:
        return "anonymous", "anonymous"
    kind = getattr(claims, "kind", "") or ""
    key = getattr(claims, "virtual_key", None)
    if kind == "virtual" and key is not None:
        return str(key.key_id), str(key.team_name or kind)
    return kind or "anonymous", kind or "anonymous"


def audit_tool_call(
    audit: AuditLog,
    claims: Any,
    *,
    tool: str,
    decision: str,
    method: str,
    transport: str,
    arguments: dict[str, Any] | None = None,
    server: str | None = None,
) -> None:
    """Record a tools/call decision. `arguments` is accepted only so callers cannot
    forget the contract: it is never persisted."""
    del arguments
    actor, role = _actor(claims)
    detail: dict[str, Any] = {
        "tool": tool,
        "decision": decision,
        "method": method,
        "transport": transport,
    }
    if server:
        detail["server"] = server.strip().lower()
    audit.record(
        actor=actor,
        role=role,
        action=AUDIT_ACTION,
        detail=detail,
    )


def audit_client_decision(
    audit: AuditLog,
    claims: Any,
    *,
    client: str | None,
    decision: str,
    method: str,
    transport: str,
) -> None:
    """Record an MCP client allow/deny decision (#1215)."""
    actor, role = _actor(claims)
    audit.record(
        actor=actor,
        role=role,
        action=AUDIT_CLIENT_ACTION,
        detail={
            "client": (client or "").strip() or None,
            "decision": decision,
            "method": method,
            "transport": transport,
        },
    )
