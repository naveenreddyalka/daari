#!/usr/bin/env python3
"""Flag auto-merge PRs that are DIRTY or have no CI (issue #200).

GitHub will not build a test-merge for a conflicted PR, so required checks
never start and `gh pr merge --auto` waits forever. This watcher comments
on the PR and files a `auto-dev,regression` issue once per stall.

It also sweeps abandoned `agent:working` labels (issue #272): an open issue
untouched for the TTL with no open PR referencing it gets the label removed
so the dev-cycle picker can claim it again.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STALL_MARKER = "autodev-pr-stall"
SWEEP_MARKER = "autodev-stale-working"
ISSUE_LABELS = "auto-dev,regression"
WORKING_LABEL = "agent:working"
DEFAULT_MIN_AGE_MINUTES = 15
DEFAULT_SWEEP_TTL_HOURS = 24


def parse_gh_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def age_minutes(pr: dict[str, Any], *, now: datetime | None = None) -> float:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    created = parse_gh_time(pr.get("createdAt") or pr.get("updatedAt"))
    if created is None:
        return 0.0
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(0.0, (moment - created).total_seconds() / 60.0)


def classify_stall(
    pr: dict[str, Any],
    *,
    now: datetime | None = None,
    min_age_minutes: int = DEFAULT_MIN_AGE_MINUTES,
) -> str | None:
    """Return 'dirty' or 'no_checks' when a PR is silently stuck."""
    if not pr.get("autoMergeRequest"):
        return None
    if (pr.get("state") or "").upper() not in ("OPEN", ""):
        return None
    if age_minutes(pr, now=now) < min_age_minutes:
        return None
    status = (pr.get("mergeStateStatus") or "").upper()
    if status == "DIRTY":
        return "dirty"
    checks = pr.get("statusCheckRollup") or []
    if not checks:
        return "no_checks"
    return None


def already_alerted(comments: list[dict[str, Any]]) -> bool:
    return any(STALL_MARKER in (item.get("body") or "") for item in comments)


def render_comment(pr: dict[str, Any], reason: str) -> str:
    number = pr.get("number")
    status = pr.get("mergeStateStatus") or "unknown"
    if reason == "dirty":
        detail = (
            f"PR #{number} is `mergeStateStatus: DIRTY` (conflicted). "
            "GitHub will not start required checks, so auto-merge waits forever."
        )
    else:
        detail = (
            f"PR #{number} has auto-merge enabled but no check runs "
            f"(mergeStateStatus={status}). Likely a conflict or an out-of-date branch."
        )
    return (
        f"<!-- {STALL_MARKER} -->\n"
        f"{detail}\n\n"
        "Fix: merge `origin/main` into the branch, resolve conflicts "
        "(often `docs/TRACKING.md`), push, and re-enable auto-merge.\n"
        "Filed by `scripts/autodev_pr_watch.py` (#200)."
    )


def render_issue_title(pr: dict[str, Any]) -> str:
    return f"[autodev] stalled auto-merge PR #{pr.get('number')}"


def select_stalled(
    prs: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    min_age_minutes: int = DEFAULT_MIN_AGE_MINUTES,
) -> list[tuple[dict[str, Any], str]]:
    out: list[tuple[dict[str, Any], str]] = []
    for pr in prs:
        reason = classify_stall(pr, now=now, min_age_minutes=min_age_minutes)
        if reason:
            out.append((pr, reason))
    return out


def _label_names(issue: dict[str, Any]) -> set[str]:
    return {label.get("name", "") for label in issue.get("labels") or [] if isinstance(label, dict)}


def pr_references_issue(pr: dict[str, Any], number: int) -> bool:
    if (pr.get("headRefName") or "").startswith(f"autodev/{number}-"):
        return True
    token = f"#{number}"
    return token in (pr.get("title") or "") or token in (pr.get("body") or "")


def classify_stale_working(
    issue: dict[str, Any],
    *,
    open_prs: list[dict[str, Any]],
    now: datetime | None = None,
    ttl_hours: int = DEFAULT_SWEEP_TTL_HOURS,
) -> bool:
    """True when an agent:working label looks abandoned and should be removed."""
    if WORKING_LABEL not in _label_names(issue):
        return False
    if (issue.get("state") or "OPEN").upper() not in ("OPEN", ""):
        return False
    updated = parse_gh_time(issue.get("updatedAt"))
    if updated is None:
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    if (moment - updated).total_seconds() / 3600.0 < ttl_hours:
        return False
    number = int(issue["number"])
    return not any(pr_references_issue(pr, number) for pr in open_prs)


def render_sweep_comment(issue: dict[str, Any], ttl_hours: int) -> str:
    return (
        f"<!-- {SWEEP_MARKER} -->\n"
        f"Removed `{WORKING_LABEL}`: no update on this issue and no open PR "
        f"referencing it for over {ttl_hours}h. The issue is eligible for the "
        "dev-cycle picker again.\n"
        "Swept by `scripts/autodev_pr_watch.py` (#272)."
    )


def apply_sweep(
    issues: list[dict[str, Any]],
    *,
    open_prs: list[dict[str, Any]],
    now: datetime | None = None,
    ttl_hours: int = DEFAULT_SWEEP_TTL_HOURS,
    remove_label: Any = None,
    comment: Any = None,
    list_comments: Any = None,
) -> list[int]:
    """Remove abandoned agent:working labels. Returns swept issue numbers."""
    swept: list[int] = []
    for issue in issues:
        if not classify_stale_working(issue, open_prs=open_prs, now=now, ttl_hours=ttl_hours):
            continue
        number = int(issue["number"])
        comments = list_comments(number) if list_comments else []
        if any(SWEEP_MARKER in (item.get("body") or "") for item in comments):
            continue
        if remove_label:
            remove_label(number)
        if comment:
            comment(number, render_sweep_comment(issue, ttl_hours))
        swept.append(number)
    return swept


def _gh_json(args: list[str]) -> Any:
    raw = subprocess.check_output(["gh", *args], text=True)
    return json.loads(raw) if raw.strip() else None


def fetch_open_prs() -> list[dict[str, Any]]:
    # Audited for #291: plain `gh pr list` (no --search/--label) reads the
    # repository pullRequests connection, not the stale-prone search index.
    return (
        _gh_json(
            [
                "pr",
                "list",
                "--state",
                "open",
                "--limit",
                "50",
                "--json",
                "number,title,state,mergeStateStatus,autoMergeRequest,statusCheckRollup,"
                "createdAt,url,headRefName,body",
            ]
        )
        or []
    )


def fetch_working_issues() -> list[dict[str, Any]]:
    # Audited for #291: `--label` routes through the search index, which can
    # lag. Failure mode here is fail-safe — a stale index only postpones the
    # agent:working sweep until the next 2h run; nothing is removed wrongly.
    return (
        _gh_json(
            [
                "issue",
                "list",
                "--state",
                "open",
                "--label",
                WORKING_LABEL,
                "--limit",
                "50",
                "--json",
                "number,title,state,labels,updatedAt",
            ]
        )
        or []
    )


def apply_alerts(
    prs: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    min_age_minutes: int = DEFAULT_MIN_AGE_MINUTES,
    comment: Any = None,
    list_comments: Any = None,
    create_issue: Any = None,
    list_issues: Any = None,
) -> list[int]:
    """Comment + file a regression issue for each new stall. Returns PR numbers."""
    alerted: list[int] = []
    for pr, reason in select_stalled(prs, now=now, min_age_minutes=min_age_minutes):
        number = int(pr["number"])
        comments = list_comments(number) if list_comments else []
        if already_alerted(comments):
            continue
        body = render_comment(pr, reason)
        if comment:
            comment(number, body)
        title = render_issue_title(pr)
        existing = list_issues(title) if list_issues else []
        if create_issue and not existing:
            create_issue(title, body)
        alerted.append(number)
    return alerted


def _cli_list_comments(number: int) -> list[dict[str, Any]]:
    return _gh_json(["api", f"repos/{{owner}}/{{repo}}/issues/{number}/comments"]) or []


def _cli_comment(number: int, body: str) -> None:
    subprocess.check_call(
        ["gh", "pr", "comment", str(number), "--body", body],
    )


def _cli_list_issues(title: str) -> list[dict[str, Any]]:
    # Audited for #291: `--search` dedupe can miss on a stale index, but the
    # primary dedupe is the PR-comment marker checked before this runs; the
    # worst case is a visible duplicate stall issue, never a silent stall.
    rows = (
        _gh_json(
            [
                "issue",
                "list",
                "--state",
                "open",
                "--search",
                f"in:title {title}",
                "--json",
                "number,title",
            ]
        )
        or []
    )
    return [row for row in rows if row.get("title") == title]


def _cli_create_issue(title: str, body: str) -> None:
    subprocess.check_call(
        [
            "gh",
            "issue",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--label",
            ISSUE_LABELS,
        ]
    )


def _cli_remove_working_label(number: int) -> None:
    subprocess.check_call(
        ["gh", "issue", "edit", str(number), "--remove-label", WORKING_LABEL],
    )


def _cli_issue_comment(number: int, body: str) -> None:
    subprocess.check_call(
        ["gh", "issue", "comment", str(number), "--body", body],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Comment on stalled PRs and file regression issues.",
    )
    parser.add_argument(
        "--min-age-minutes",
        type=int,
        default=DEFAULT_MIN_AGE_MINUTES,
    )
    parser.add_argument(
        "--input-json",
        help="Read PR list from a file instead of `gh pr list`.",
    )
    parser.add_argument(
        "--sweep-ttl-hours",
        type=int,
        default=DEFAULT_SWEEP_TTL_HOURS,
        help="Remove agent:working from issues untouched this long with no open PR.",
    )
    args = parser.parse_args(argv)
    if args.input_json:
        prs = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
        issues = []
    else:
        prs = fetch_open_prs()
        issues = fetch_working_issues()
    stalled = select_stalled(prs, min_age_minutes=args.min_age_minutes)
    for pr, reason in stalled:
        print(f"#{pr.get('number')} {reason} {pr.get('title')}")
    stale = [
        issue
        for issue in issues
        if classify_stale_working(issue, open_prs=prs, ttl_hours=args.sweep_ttl_hours)
    ]
    for issue in stale:
        print(f"#{issue.get('number')} stale_working {issue.get('title')}")
    if not args.apply:
        return 0
    apply_alerts(
        prs,
        min_age_minutes=args.min_age_minutes,
        comment=_cli_comment,
        list_comments=_cli_list_comments,
        create_issue=_cli_create_issue,
        list_issues=_cli_list_issues,
    )
    apply_sweep(
        issues,
        open_prs=prs,
        ttl_hours=args.sweep_ttl_hours,
        remove_label=_cli_remove_working_label,
        comment=_cli_issue_comment,
        list_comments=_cli_list_comments,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
