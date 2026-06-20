from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class DevCommandMatch:
    action: str  # execute | ccs_read
    command: str | None = None
    rule_id: str | None = None
    ttl_seconds: int = 300
    needs_rerun: bool = False


def match_dev_command(text: str) -> DevCommandMatch | None:
    normalized = text.strip()

    if re.search(r"(?i)\b(what did|show|last)\b.*\b(test|lint|git status|git diff)\b", normalized):
        return DevCommandMatch(action="ccs_read", rule_id="DEV-06")

    if re.search(r"(?i)\b(re-run|run again)\b.*\b(test|lint)\b", normalized):
        if re.search(r"(?i)\blint|eslint\b", normalized):
            return DevCommandMatch(
                action="execute",
                command="eslint .",
                rule_id="DEV-07",
                ttl_seconds=300,
                needs_rerun=True,
            )
        return DevCommandMatch(
            action="execute",
            command="pytest",
            rule_id="DEV-07",
            ttl_seconds=300,
            needs_rerun=True,
        )

    if re.fullmatch(r"(?i)(run|execute)?\s*git status", normalized):
        return DevCommandMatch(action="execute", command="git status", rule_id="DEV-01", ttl_seconds=60)

    if re.fullmatch(r"(?i)(run|execute)?\s*git diff", normalized):
        return DevCommandMatch(action="execute", command="git diff", rule_id="DEV-02", ttl_seconds=60)

    if re.search(r"(?i)\b(pytest|run tests?|npm test)\b", normalized):
        return DevCommandMatch(action="execute", command="pytest", rule_id="DEV-03", ttl_seconds=300)

    if re.search(r"(?i)\b(run lint|eslint|run linter)\b", normalized):
        return DevCommandMatch(action="execute", command="eslint .", rule_id="DEV-04", ttl_seconds=300)

    return None

