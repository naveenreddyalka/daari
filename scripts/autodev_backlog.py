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
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from autodev_pr_watch import pr_references_issue  # noqa: E402 — shared #<n>/branch matching

OWNER = "naveenreddyalka"
REPO = "daari"
BACKLOG_LABEL = "auto-dev"
WORKING_LABEL = "agent:working"
# Lower rank picks first; anything unprioritized trails P3.
PRIORITY_RANK = {"P1": 0, "P2": 1, "P3": 2}
UNPRIORITIZED_RANK = len(PRIORITY_RANK)

# Repository connections only — `search(` must never appear here (see module doc).
ISSUES_QUERY = """
query($owner: String!, $name: String!, $labels: [String!]!) {
  repository(owner: $owner, name: $name) {
    issues(states: OPEN, labels: $labels, first: 100) {
      nodes {
        number
        title
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
      nodes { number title body headRefName }
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


def _label_names(issue: dict[str, Any]) -> set[str]:
    labels = issue.get("labels") or {}
    return {node.get("name", "") for node in labels.get("nodes") or []}


def _priority(issue: dict[str, Any]) -> int:
    ranks = [PRIORITY_RANK[name] for name in _label_names(issue) if name in PRIORITY_RANK]
    return min(ranks) if ranks else UNPRIORITIZED_RANK


def eligible_issues(
    issues: list[dict[str, Any]], open_prs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """AGENTS.md pick order: P1 > P2 > P3 then oldest; skip in-progress work."""
    rows = [
        issue
        for issue in issues
        if WORKING_LABEL not in _label_names(issue)
        and not any(pr_references_issue(pr, int(issue["number"])) for pr in open_prs)
    ]
    return sorted(rows, key=lambda issue: (_priority(issue), issue.get("createdAt") or ""))


def pick(
    issues: list[dict[str, Any]], open_prs: list[dict[str, Any]]
) -> dict[str, Any] | None:
    rows = eligible_issues(issues, open_prs)
    return rows[0] if rows else None


def main(argv: list[str] | None = None, runner: Runner = _default_runner) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--pick", action="store_true", help="Print the next issue number.")
    group.add_argument("--list", action="store_true", help="Print eligible issues as JSON.")
    args = parser.parse_args(argv)

    issues = fetch_issues(runner)
    open_prs = fetch_open_prs(runner)
    if args.list:
        rows = [
            {
                "number": issue["number"],
                "title": issue.get("title", ""),
                "createdAt": issue.get("createdAt", ""),
                "labels": sorted(_label_names(issue)),
            }
            for issue in eligible_issues(issues, open_prs)
        ]
        print(json.dumps(rows, indent=2))
        return 0

    picked = pick(issues, open_prs)
    print(picked["number"] if picked else "backlog empty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
