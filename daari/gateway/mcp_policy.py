"""MCP tool governance: per-key / per-team allow-deny policy and call audit (issue #277).

Tool calls carry the most sensitive payloads a gateway sees (repo contents,
command output), so the policy is evaluated on the developer's machine and the
audit row records only *what* was called and the decision — never the
arguments.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any

from daari.enterprise.audit import AuditLog

# JSON-RPC server-error range (-32000..-32099) reserved for implementation errors.
TOOL_DENIED = -32003
AUDIT_ACTION = "mcp.tools/call"
KEY_METADATA_FIELD = "mcp"


def _patterns(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple, set)):
        return ()
    return tuple(item.strip() for item in raw if isinstance(item, str) and item.strip())


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


def resolve_policy(claims: Any, settings: Any) -> McpToolPolicy:
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
) -> None:
    """Record a tools/call decision. `arguments` is accepted only so callers cannot
    forget the contract: it is never persisted."""
    del arguments
    actor, role = _actor(claims)
    audit.record(
        actor=actor,
        role=role,
        action=AUDIT_ACTION,
        detail={"tool": tool, "decision": decision, "method": method, "transport": transport},
    )
