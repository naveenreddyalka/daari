from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch


@dataclass
class PolicyResult:
    outcome: str  # allow | deny | ask
    reason: str


class PolicyEngine:
    def __init__(
        self,
        *,
        allow_patterns: list[str] | None = None,
        block_patterns: list[str] | None = None,
        unknown: str = "deny",
    ) -> None:
        self.allow_patterns = allow_patterns or []
        self.block_patterns = block_patterns or []
        self.unknown = unknown

    def evaluate(self, command: str, *, confirmed: bool = False) -> PolicyResult:
        lowered = command.lower()
        for pattern in self.block_patterns:
            if fnmatch(lowered, pattern.lower()):
                return PolicyResult(outcome="deny", reason=f"blocked by pattern: {pattern}")

        for pattern in self.allow_patterns:
            if fnmatch(lowered, pattern.lower()):
                return PolicyResult(outcome="allow", reason=f"allowlist pattern: {pattern}")

        if confirmed:
            return PolicyResult(outcome="allow", reason="request confirmed by header")
        if self.unknown == "ask":
            return PolicyResult(outcome="ask", reason="unknown command requires confirmation")
        return PolicyResult(outcome="deny", reason="unknown command denied")

