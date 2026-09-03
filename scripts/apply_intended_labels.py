#!/usr/bin/env python3
"""Apply the "**Intended labels:**" line of an issue body as real labels (issue #330).

The prd-cycle automation's token cannot label issues, so every issue it files
opens with a line such as::

    **Intended labels: `auto-dev`, `P2`**

Until a human applied those by hand the autodev picker could not see the
issue. This script runs from `.github/workflows/issue-labeler.yml` with the
repository's own GITHUB_TOKEN and closes that gap at filing time.

Rules:
- Only the first non-empty line of the body is read.
- Only names in ALLOWED_LABELS are applied; anything else is logged and
  skipped. `agent:working` is deliberately absent — it is the agent's own
  claim marker and must never be pre-applied.
- Labels are never created. Idempotent: present labels are no-ops.

Usage:
  python scripts/apply_intended_labels.py --event "$GITHUB_EVENT_PATH"
  python scripts/apply_intended_labels.py --issue 330
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

ALLOWED_LABELS: tuple[str, ...] = (
    "auto-dev",
    "P1",
    "P2",
    "P3",
    "bug",
    "regression",
    "documentation",
    "enhancement",
)

# `**Intended labels: a, b**` and `**Intended labels:** a, b`; tolerant of
# spacing, case, and the colon sitting inside or outside the bold markers.
_INTENDED_RE = re.compile(
    r"^\**\s*intended\s+labels\s*:?\s*\**\s*:?\s*(?P<labels>.*?)\s*\**\s*$",
    re.IGNORECASE,
)


def parse_intended_labels(body: str | None) -> list[str]:
    """Label names from the first non-empty body line, or [] when absent."""
    if not body:
        return []
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    match = _INTENDED_RE.match(first)
    if not match:
        return []
    names: list[str] = []
    for raw in match.group("labels").split(","):
        name = raw.strip().strip("`").strip()
        if name and name not in names:
            names.append(name)
    return names


def select_labels(names: list[str]) -> tuple[list[str], list[str]]:
    """Split into (allowlisted, skipped). Case-sensitive on purpose: label
    names are exact strings on GitHub."""
    wanted = [name for name in names if name in ALLOWED_LABELS]
    skipped = [name for name in names if name not in ALLOWED_LABELS]
    return wanted, skipped


class LabelApi(Protocol):
    def current_labels(self, number: int) -> list[str]: ...

    def add_labels(self, number: int, labels: list[str]) -> None: ...


@dataclass
class ApplyResult:
    applied: list[str] = field(default_factory=list)
    already_present: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def apply_intended_labels(number: int, body: str | None, *, api: LabelApi) -> ApplyResult:
    result = ApplyResult()
    names = parse_intended_labels(body)
    if not names:
        return result
    wanted, result.skipped = select_labels(names)
    if not wanted:
        return result
    present = set(api.current_labels(number))
    result.already_present = [name for name in wanted if name in present]
    result.applied = [name for name in wanted if name not in present]
    if result.applied:
        api.add_labels(number, result.applied)
    return result


class GitHubApi:
    """Thin `gh api` wrapper. Adding labels to an issue is the only mutation;
    there is intentionally no label-creation call."""

    def __init__(self, repo: str | None = None) -> None:
        self.repo = repo or _detect_repo()

    def _api(self, args: list[str], *, payload: dict[str, Any] | None = None) -> Any:
        cmd = ["gh", "api", *args]
        stdin = None
        if payload is not None:
            cmd += ["--method", "POST", "--input", "-"]
            stdin = json.dumps(payload)
        raw = subprocess.check_output(cmd, text=True, input=stdin)
        return json.loads(raw) if raw.strip() else None

    def issue_body(self, number: int) -> str:
        data = self._api([f"repos/{self.repo}/issues/{number}"])
        return (data or {}).get("body") or ""

    def current_labels(self, number: int) -> list[str]:
        data = self._api([f"repos/{self.repo}/issues/{number}/labels", "--paginate"]) or []
        return [entry["name"] for entry in data if isinstance(entry, dict) and "name" in entry]

    def add_labels(self, number: int, labels: list[str]) -> None:
        """POST /issues/{n}/labels — adds existing labels; GitHub rejects
        unknown names instead of creating them, which is the behaviour we want."""
        self._api([f"repos/{self.repo}/issues/{number}/labels"], payload={"labels": labels})


def _detect_repo() -> str:
    import os

    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo:
        return repo
    return subprocess.check_output(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], text=True
    ).strip()


def _issue_from_event(path: str) -> tuple[int, str | None] | None:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    issue = payload.get("issue") if isinstance(payload, dict) else None
    if not isinstance(issue, dict) or "number" not in issue:
        return None
    return int(issue["number"]), issue.get("body")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--event", help="path to the GitHub Actions event payload")
    source.add_argument("--issue", type=int, help="issue number (body fetched via gh)")
    args = parser.parse_args(argv)

    if args.event:
        found = _issue_from_event(args.event)
        if found is None:
            print("apply_intended_labels: event carries no issue; nothing to do")
            return 0
        number, body = found
        api = GitHubApi()
    else:
        number = args.issue
        api = GitHubApi()
        body = api.issue_body(number)

    result = apply_intended_labels(number, body, api=api)
    print(
        f"apply_intended_labels: #{number} applied={result.applied} "
        f"already_present={result.already_present} skipped={result.skipped}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
