"""Backlog picker off GitHub's search index (issue #291).

The 2026-08-30 stall: `gh issue list --label auto-dev` routes through GitHub's
search index, which can lag the repository and return `[]` for a non-empty
backlog. The picker must read the GraphQL repository connection only.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "autodev_backlog", REPO_ROOT / "scripts" / "autodev_backlog.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["autodev_backlog"] = module
    spec.loader.exec_module(module)
    return module


def _issue(number, *, labels=("auto-dev", "P2"), created="2026-08-01T00:00:00Z", title=None):
    return {
        "number": number,
        "title": title or f"issue {number}",
        "createdAt": created,
        "labels": {"nodes": [{"name": name} for name in labels]},
    }


def _pr(number, *, head="", title="", body=""):
    return {"number": number, "headRefName": head, "title": title, "body": body}


def test_queries_use_repository_connection_not_search():
    module = _load_module()
    for query in (module.ISSUES_QUERY, module.PRS_QUERY):
        assert "repository(" in query
        assert "search(" not in query


def test_priority_order_p1_beats_p2_beats_p3():
    module = _load_module()
    issues = [
        _issue(10, labels=("auto-dev", "P3")),
        _issue(11, labels=("auto-dev", "P1")),
        _issue(12, labels=("auto-dev", "P2")),
    ]
    picked = module.pick(issues, open_prs=[])
    assert picked["number"] == 11


def test_oldest_first_within_same_priority():
    module = _load_module()
    issues = [
        _issue(20, created="2026-08-05T00:00:00Z"),
        _issue(21, created="2026-08-01T00:00:00Z"),
        _issue(22, created="2026-08-03T00:00:00Z"),
    ]
    picked = module.pick(issues, open_prs=[])
    assert picked["number"] == 21


def test_unprioritized_issue_sorts_after_p3():
    module = _load_module()
    issues = [
        _issue(30, labels=("auto-dev",)),
        _issue(31, labels=("auto-dev", "P3")),
    ]
    picked = module.pick(issues, open_prs=[])
    assert picked["number"] == 31


def test_agent_working_is_skipped():
    module = _load_module()
    issues = [
        _issue(40, labels=("auto-dev", "P1", "agent:working")),
        _issue(41, labels=("auto-dev", "P2")),
    ]
    picked = module.pick(issues, open_prs=[])
    assert picked["number"] == 41


def test_issue_with_open_linked_pr_is_skipped():
    module = _load_module()
    issues = [
        _issue(50, labels=("auto-dev", "P1")),
        _issue(51, labels=("auto-dev", "P1")),
        _issue(52, labels=("auto-dev", "P1")),
        _issue(53, labels=("auto-dev", "P2")),
    ]
    open_prs = [
        _pr(100, head="autodev/50-something"),
        _pr(101, title="fix: thing (#51)"),
        _pr(102, body="Closes #52"),
    ]
    picked = module.pick(issues, open_prs=open_prs)
    assert picked["number"] == 53


def test_empty_backlog_returns_none():
    module = _load_module()
    assert module.pick([], open_prs=[]) is None
    only_working = [_issue(60, labels=("auto-dev", "agent:working"))]
    assert module.pick(only_working, open_prs=[]) is None


def _fake_runner(issues, prs):
    """Mocked `gh` runner: returns canned GraphQL payloads."""

    def runner(args):
        joined = " ".join(args)
        if "pullRequests" in joined:
            payload = {"data": {"repository": {"pullRequests": {"nodes": prs}}}}
        else:
            payload = {"data": {"repository": {"issues": {"nodes": issues}}}}
        return json.dumps(payload)

    return runner


def test_cli_pick_prints_issue_number(capsys):
    module = _load_module()
    runner = _fake_runner([_issue(70, labels=("auto-dev", "P1"))], [])
    rc = module.main(["--pick"], runner=runner)
    assert rc == 0
    assert capsys.readouterr().out.strip() == "70"


def test_cli_pick_prints_backlog_empty(capsys):
    module = _load_module()
    rc = module.main(["--pick"], runner=_fake_runner([], []))
    assert rc == 0
    assert capsys.readouterr().out.strip() == "backlog empty"


def test_cli_list_prints_eligible_issues_as_json(capsys):
    module = _load_module()
    issues = [
        _issue(80, labels=("auto-dev", "P2")),
        _issue(81, labels=("auto-dev", "P1")),
        _issue(82, labels=("auto-dev", "P1", "agent:working")),
    ]
    rc = module.main(["--list"], runner=_fake_runner(issues, []))
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert [row["number"] for row in rows] == [81, 80]


def test_local_sh_dedupe_no_longer_uses_search():
    text = (REPO_ROOT / "scripts" / "autodev-local.sh").read_text(encoding="utf-8")
    assert "--search" not in text
    assert "repository(" in text or "gh api graphql" in text


def test_workflow_prompt_references_backlog_script():
    text = (REPO_ROOT / ".github" / "workflows" / "autodev.yml").read_text(encoding="utf-8")
    assert "scripts/autodev_backlog.py" in text
    assert "gh issue list --label auto-dev" not in text


def _stall_body(pr_number=340, run_id=33815553913):
    return (
        "<!-- autodev-pr-stall -->\n"
        f"PR #{pr_number} is stalled (classification: awaiting-approval). "
        "The latest workflow run concluded `action_required`.\n"
        f"Fix: Approve and run: https://github.com/o/r/actions/runs/{run_id}."
    )


def test_extract_stall_pr_number():
    module = _load_module()
    assert module.extract_stall_pr_number(_stall_body(340)) == 340
    assert module.extract_stall_pr_number("no stall here") is None


def test_should_skip_human_gated_stall_when_marker_matches():
    module = _load_module()
    issue = _issue(
        341,
        labels=("auto-dev", "P1", "regression"),
        title="[autodev] stalled auto-merge PR #340",
    )
    issue["body"] = _stall_body()
    comments = [
        {
            "body": (
                "<!-- autodev-blocked: awaiting-approval run=33815553913 -->\n"
                "## Findings (blocked — human action required)\n"
            )
        }
    ]
    assert module.should_skip_human_gated_stall(
        issue,
        comments=comments,
        current_fingerprint="awaiting-approval run=33815553913",
    )


def test_should_not_skip_stall_without_blocked_comment():
    module = _load_module()
    issue = _issue(341, labels=("auto-dev", "P1", "regression"))
    issue["body"] = _stall_body()
    assert not module.should_skip_human_gated_stall(
        issue,
        comments=[{"body": "still investigating"}],
        current_fingerprint="awaiting-approval run=33815553913",
    )


def test_should_not_skip_when_fingerprint_changed():
    module = _load_module()
    issue = _issue(341, labels=("auto-dev", "P1", "regression"))
    issue["body"] = _stall_body()
    comments = [
        {
            "body": "<!-- autodev-blocked: awaiting-approval run=33815553913 -->\nfindings"
        }
    ]
    # New CI run → different fingerprint → eligible again
    assert not module.should_skip_human_gated_stall(
        issue,
        comments=comments,
        current_fingerprint="awaiting-approval run=99999999",
    )
    # PR no longer blocked
    assert not module.should_skip_human_gated_stall(
        issue,
        comments=comments,
        current_fingerprint=None,
    )


def test_pick_skips_human_gated_stall_matching_state():
    module = _load_module()
    stall = _issue(341, labels=("auto-dev", "P1", "regression"), created="2026-09-01T00:00:00Z")
    stall["body"] = _stall_body()
    other = _issue(342, labels=("auto-dev", "P1"), created="2026-09-05T00:00:00Z")
    other["body"] = "normal work"

    comments_by_issue = {
        341: [
            {
                "body": "<!-- autodev-blocked: awaiting-approval run=33815553913 -->\nfindings"
            }
        ],
        342: [],
    }
    fingerprints = {341: "awaiting-approval run=33815553913"}

    picked = module.pick(
        [stall, other],
        open_prs=[],
        comments_by_issue=comments_by_issue,
        blocked_fingerprints=fingerprints,
    )
    assert picked["number"] == 342


def test_pick_re_eligible_after_state_change():
    module = _load_module()
    stall = _issue(341, labels=("auto-dev", "P1", "regression"))
    stall["body"] = _stall_body()
    comments_by_issue = {
        341: [
            {
                "body": "<!-- autodev-blocked: awaiting-approval run=33815553913 -->\nfindings"
            }
        ],
    }
    # Same old comment, but PR now has a new run id → pick the stall again
    picked = module.pick(
        [stall],
        open_prs=[],
        comments_by_issue=comments_by_issue,
        blocked_fingerprints={341: "awaiting-approval run=999"},
    )
    assert picked is not None and picked["number"] == 341


def test_non_stall_issues_unaffected_by_blocked_helpers():
    module = _load_module()
    issue = _issue(50, labels=("auto-dev", "P1"))
    issue["body"] = "regular feature work"
    assert not module.should_skip_human_gated_stall(
        issue,
        comments=[
            {"body": "<!-- autodev-blocked: awaiting-approval run=1 -->\nspurious"}
        ],
        current_fingerprint="awaiting-approval run=1",
    )


def test_workflow_uses_user_pat_so_bot_prs_skip_approval_gate():
    text = (REPO_ROOT / ".github" / "workflows" / "autodev.yml").read_text(encoding="utf-8")
    assert "AUTODEV_GH_TOKEN" in text
    assert "secrets.AUTODEV_GH_TOKEN || secrets.GITHUB_TOKEN" in text
