"""Guardrails on MCP tools/call arguments and results (issue #317).

#277 governs *which* tools a caller may invoke; this governs *what flows through
them*. The same `GuardrailEngine` used for chat inspects tool arguments before
execution (input rules) and tool results after (output rules), on the /mcp
ingress, the legacy REST route, and the egress client. Trips are audited as
`mcp.guardrail` rows carrying tool / rule / direction / action — never the
payload, which is the whole point of governing on the developer's machine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from daari.enterprise.audit import AuditLog
from daari.gateway.guardrails import GuardrailEngine, GuardrailResult, engine_from_block
from daari.gateway.mcp_policy import TOOL_DENIED, _actor

AUDIT_ACTION = "mcp.guardrail"
GUARDRAIL_BLOCKED = TOOL_DENIED
LEGACY_ERROR_CODE = "MCP_ERR_GUARDRAIL_BLOCKED"


class GuardrailBlockedError(RuntimeError):
    def __init__(self, tool: str, rule: str, direction: str) -> None:
        super().__init__(f"Tool call blocked by guardrail {rule}: {tool}")
        self.tool = tool
        self.rule = rule
        self.direction = direction


def _leaves(value: Any, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _leaves(item, out)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _leaves(item, out)
    elif value is not None:
        out.append(json.dumps(value, default=str))


def arguments_text(arguments: Any) -> str:
    """Flatten tool arguments to the text the input rules run over. Leaf strings are
    kept verbatim so patterns match the same bytes the tool would see."""
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        return arguments
    leaves: list[str] = []
    _leaves(arguments, leaves)
    return "\n".join(leaves)


@dataclass
class McpGuardrails:
    engine: GuardrailEngine | None = None
    audit: AuditLog | None = None
    claims: Any = None
    transport: str = "jsonrpc"

    @classmethod
    def from_settings(
        cls,
        settings: Any,
        *,
        audit: AuditLog | None = None,
        claims: Any = None,
        transport: str = "jsonrpc",
    ) -> McpGuardrails:
        integrations = getattr(settings, "integrations", None)
        engine = engine_from_block(getattr(integrations, "mcp_guardrails", None))
        return cls(engine=engine, audit=audit, claims=claims, transport=transport)

    @property
    def enabled(self) -> bool:
        return self.engine is not None and self.engine.enabled

    @property
    def block_message(self) -> str:
        return self.engine.block_message if self.engine else GuardrailEngine.block_message

    def _record(self, tool: str, result: GuardrailResult, direction: str) -> None:
        if self.audit is None or not result.hits:
            return
        actor, role = _actor(self.claims)
        for hit in result.hits:
            self.audit.record(
                actor=actor,
                role=role,
                action=AUDIT_ACTION,
                detail={
                    "tool": tool,
                    "rule": hit.rule,
                    "direction": direction,
                    "action": hit.action,
                    "transport": self.transport,
                },
            )

    def check_arguments(self, tool: str, arguments: Any) -> GuardrailResult:
        if not self.enabled:
            return GuardrailResult()
        result = self.engine.check_input_text(arguments_text(arguments))  # type: ignore[union-attr]
        self._record(tool, result, "input")
        return result

    def check_result_text(self, tool: str, text: str) -> tuple[str, GuardrailResult]:
        if not self.enabled:
            return text, GuardrailResult()
        rewritten, result = self.engine.check_output_text(text)  # type: ignore[union-attr]
        self._record(tool, result, "output")
        return rewritten, result

    def check_tool_result(
        self, tool: str, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], GuardrailResult]:
        """Apply output rules to every text item of an MCP `tools/call` result.
        A block collapses the result to a single error text item."""
        if not self.enabled:
            return payload, GuardrailResult()
        items = payload.get("content")
        if not isinstance(items, list):
            return payload, GuardrailResult()
        combined = GuardrailResult()
        rewritten_items: list[Any] = []
        for item in items:
            if not (isinstance(item, dict) and item.get("type") == "text"):
                rewritten_items.append(item)
                continue
            text = str(item.get("text") or "")
            rewritten, result = self.check_result_text(tool, text)
            combined.hits.extend(result.hits)
            combined.warning = combined.warning or result.warning
            if result.blocked:
                combined.blocked = True
                return (
                    {
                        **payload,
                        "content": [{"type": "text", "text": self.block_message}],
                        "isError": True,
                    },
                    combined,
                )
            rewritten_items.append({**item, "text": rewritten} if rewritten != text else item)
        if not combined.hits:
            return payload, combined
        return {**payload, "content": rewritten_items}, combined

    def check_legacy_result(self, tool: str, result: Any) -> tuple[Any, GuardrailResult]:
        """Apply output rules to a legacy /v1/mcp/query result. String `content` is
        rewritten in place; any other shape is checked as JSON and replaced wholesale
        on a trip so nothing tripped can leak through a non-string field."""
        if not self.enabled:
            return result, GuardrailResult()
        if isinstance(result, dict) and isinstance(result.get("content"), str):
            rewritten, outcome = self.check_result_text(tool, result["content"])
            if not outcome.hits:
                return result, outcome
            return {**result, "content": rewritten}, outcome
        serialized = json.dumps(result, default=str)
        rewritten, outcome = self.check_result_text(tool, serialized)
        if not outcome.hits:
            return result, outcome
        if outcome.blocked:
            return {"content": rewritten}, outcome
        try:
            return json.loads(rewritten), outcome
        except json.JSONDecodeError:
            return {"content": rewritten}, outcome


def first_rule(result: GuardrailResult) -> str:
    return result.hits[0].rule if result.hits else "guardrail"
