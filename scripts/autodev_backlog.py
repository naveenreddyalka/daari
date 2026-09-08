#!/usr/bin/env python3
"""Pick the next auto-dev backlog issue without GitHub's search index (issue #291).

`gh issue list --label ...` routes through GraphQL search, and the search index
can lag the repository: on 2026-08-30 it returned an empty backlog while four
labeled issues were open, so every scheduled dev cycle exited green having done
nothing. The GraphQL *repository connection* is authoritative, so this script
reads only that.

Usage:
  python scripts/autodev_backlog.py --pick   # print next issue number or 'backlog empty'
  python scripts/autodev_backlog.py --list   # print all eligible issues as JSON
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from autodev_pr_watch import (  # noqa: E402 — shared #<n>/branch matching + stall markers
    STALL_MARKER,
    fingerprint_for_blocked_stall,
    latest_blocked_fingerprint,
    pr_references_issue,
)

OWNER = "naveenreddyalka"
REPO = "daari"
BACKLOG_LABEL = "auto-dev"
WORKING_LABEL = "agent:working"
# Lower rank picks first; anything unprioritized trails P3.
PRIORITY_RANK = {"P1": 0, "P2": 1, "P3": 2}
UNPRIORITIZED_RANK = len(PRIORITY_RANK)
_STALL_PR_RE = re.compile(r"PR\s+#(\d+)", re.IGNORECASE)

# Repository connections only — `search(` must never appear here (see module doc).
ISSUES_QUERY = """
query($owner: String!, $name: String!, $labels: [String!]!) {
  repository(owner: $owner, name: $name) {
    issues(states: OPEN, labels: $labels, first: 100) {
      nodes {
        number
        title
        body
        createdAt
        labels(first: 20) { nodes { name } }
      }
    }
  }
}
"""

PRS_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    pullRequests(states: OPEN, first: 100) {
      nodes {
        number
        title
        body
        headRefName
        headRefOid
        state
        mergeStateStatus
        mergeable
        autoMergeRequest { enabledAt }
        statusCheckRollup { __typename }
        createdAt
      }
    }
  }
}
"""

Runner = Callable[[list[str]], str]


def _default_runner(args: list[str]) -> str:
    return subprocess.check_output(["gh", *args], text=True)


def _graphql(query: str, variables: dict[str, Any], runner: Runner) -> dict[str, Any]:
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if isinstance(value, list):
            for item in value:
                args += ["-f", f"{key}[]={item}"]
        else:
            args += ["-F", f"{key}={value}"]
    return json.loads(runner(args))


def fetch_issues(runner: Runner = _default_runner) -> list[dict[str, Any]]:
    data = _graphql(
        ISSUES_QUERY,
        {"owner": OWNER, "name": REPO, "labels": [BACKLOG_LABEL]},
        runner,
    )
    return data["data"]["repository"]["issues"]["nodes"]


def fetch_open_prs(runner: Runner = _default_runner) -> list[dict[str, Any]]:
    data = _graphql(PRS_QUERY, {"owner": OWNER, "name": REPO}, runner)
    return data["data"]["repository"]["pullRequests"]["nodes"]


def fetch_issue_comments(number: int, runner: Runner = _default_runner) -> list[dict[str, Any]]:
    raw = runner(["api", f"repos/{OWNER}/{REPO}/issues/{number}/comments"])
    payload = json.loads(raw) if raw.strip() else []
    return payload if isinstance(payload, list) else []


def fetch_workflow_runs(head_sha: str, runner: Runner = _default_runner) -> list[dict[str, Any]]:
    if not head_sha:
        return []
    raw = runner(
        ["api", f"repos/{OWNER}/{REPO}/actions/runs?head_sha={head_sha}&per_page=20"]
    )
    payload = json.loads(raw) if raw.strip() else {}
    if isinstance(payload, dict):
        return list(payload.get("workflow_runs") or [])
    return []


def _label_names(issue: dict[str, Any]) -> set[str]:
    labels = issue.get("labels") or {}
    return {node.get("name", "") for node in labels.get("nodes") or []}


def _priority(issue: dict[str, Any]) -> int:
    ranks = [PRIORITY_RANK[name] for name in _label_names(issue) if name in PRIORITY_RANK]
    return min(ranks) if ranks else UNPRIORITIZED_RANK


def extract_stall_pr_number(body: str) -> int | None:
    if STALL_MARKER not in (body or ""):
        return None
    match = _STALL_PR_RE.search(body or "")
    return int(match.group(1)) if match else None


def should_skip_human_gated_stall(
    issue: dict[str, Any],
    *,
    comments: list[dict[str, Any]],
    current_fingerprint: str | None,
) -> bool:
    """True when a stall issue is still parked on the same human-gated state (#342)."""
    if STALL_MARKER not in (issue.get("body") or ""):
        return False
    if not current_fingerprint:
        return False
    latest = latest_blocked_fingerprint(comments)
    return latest is not None and latest == current_fingerprint


def _normalize_pr_for_stall(pr: dict[str, Any]) -> dict[str, Any]:
    """GraphQL statusCheckRollup may be typed nodes; classify_stall wants a list."""
    row = dict(pr)
    rollup = row.get("statusCheckRollup")
    if rollup is None:
        row["statusCheckRollup"] = []
    elif isinstance(rollup, dict):
        # Connection-shaped or single typed node — treat non-empty as "has checks".
        nodes = rollup.get("nodes")
        row["statusCheckRollup"] = list(nodes) if nodes is not None else [rollup]
    return row


def resolve_blocked_fingerprint(
    issue: dict[str, Any],
    open_prs: list[dict[str, Any]],
    *,
    fetch_runs: Callable[[str], list[dict[str, Any]]] | None = None,
) -> str | None:
    pr_number = extract_stall_pr_number(issue.get("body") or "")
    if pr_number is None:
        return None
    pr = next((row for row in open_prs if int(row.get("number") or 0) == pr_number), None)
    if pr is None:
        return None
    normalized = _normalize_pr_for_stall(pr)
    sha = normalized.get("headRefOid") or ""
    runs: list[dict[str, Any]] = []
    # Only hit Actions when the rollup is empty (same gate as classify_stall).
    if not (normalized.get("statusCheckRollup") or []) and fetch_runs and sha:
        runs = fetch_runs(sha) or []
    return fingerprint_for_blocked_stall(normalized, workflow_runs=runs)


def eligible_issues(
    issues: list[dict[str, Any]],
    open_prs: list[dict[str, Any]],
    *,
    comments_by_issue: dict[int, list[dict[str, Any]]] | None = None,
    blocked_fingerprints: dict[int, str | None] | None = None,
) -> list[dict[str, Any]]:
    """AGENTS.md pick order: P1 > P2 > P3 then oldest; skip in-progress / gated stalls."""
    comments_by_issue = comments_by_issue or {}
    blocked_fingerprints = blocked_fingerprints or {}
    rows = []
    for issue in issues:
        if WORKING_LABEL in _label_names(issue):
            continue
        number = int(issue["number"])
        if any(pr_references_issue(pr, number) for pr in open_prs):
            continue
        if should_skip_human_gated_stall(
            issue,
            comments=comments_by_issue.get(number, []),
            current_fingerprint=blocked_fingerprints.get(number),
        ):
            continue
        rows.append(issue)
    return sorted(rows, key=lambda issue: (_priority(issue), issue.get("createdAt") or ""))


def pick(
    issues: list[dict[str, Any]],
    open_prs: list[dict[str, Any]],
    *,
    comments_by_issue: dict[int, list[dict[str, Any]]] | None = None,
    blocked_fingerprints: dict[int, str | None] | None = None,
) -> dict[str, Any] | None:
    rows = eligible_issues(
        issues,
        open_prs,
        comments_by_issue=comments_by_issue,
        blocked_fingerprints=blocked_fingerprints,
    )
    return rows[0] if rows else None


def _collect_stall_context(
    issues: list[dict[str, Any]],
    open_prs: list[dict[str, Any]],
    runner: Runner,
) -> tuple[dict[int, list[dict[str, Any]]], dict[int, str | None]]:
    """Fetch comments + fingerprints only for stall-marked issues."""
    comments_by_issue: dict[int, list[dict[str, Any]]] = {}
    fingerprints: dict[int, str | None] = {}
    for issue in issues:
        if STALL_MARKER not in (issue.get("body") or ""):
            continue
        number = int(issue["number"])
        comments_by_issue[number] = fetch_issue_comments(number, runner)
        fingerprints[number] = resolve_blocked_fingerprint(
            issue,
            open_prs,
            fetch_runs=lambda sha, _runner=runner: fetch_workflow_runs(sha, _runner),
        )
    return comments_by_issue, fingerprints


def main(argv: list[str] | None = None, runner: Runner = _default_runner) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--pick", action="store_true", help="Print the next issue number.")
    group.add_argument("--list", action="store_true", help="Print eligible issues as JSON.")
    args = parser.parse_args(argv)

    issues = fetch_issues(runner)
    open_prs = fetch_open_prs(runner)
    comments_by_issue, fingerprints = _collect_stall_context(issues, open_prs, runner)
    if args.list:
        rows = [
            {
                "number": issue["number"],
                "title": issue.get("title", ""),
                "createdAt": issue.get("createdAt", ""),
                "labels": sorted(_label_names(issue)),
            }
            for issue in eligible_issues(
                issues,
                open_prs,
                comments_by_issue=comments_by_issue,
                blocked_fingerprints=fingerprints,
            )
        ]
        print(json.dumps(rows, indent=2))
        return 0

    picked = pick(
        issues,
        open_prs,
        comments_by_issue=comments_by_issue,
        blocked_fingerprints=fingerprints,
    )
    print(picked["number"] if picked else "backlog empty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
