"""Stalled auto-merge detector (issue #200)."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "autodev_pr_watch.py"


@pytest.fixture(scope="module")
def watch():
    spec = importlib.util.spec_from_file_location("autodev_pr_watch", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NOW = datetime(2026, 8, 27, 22, 0, tzinfo=timezone.utc)


def _pr(**overrides):
    base = {
        "number": 250,
        "title": "feat(extension): intercept",
        "state": "OPEN",
        "mergeStateStatus": "DIRTY",
        "mergeable": "CONFLICTING",
        "autoMergeRequest": {"enabledAt": "2026-08-27T21:00:00Z"},
        "statusCheckRollup": [],
        "createdAt": "2026-08-27T21:00:00Z",
        "headRefOid": "abc123deadbeef",
        "url": "https://github.com/naveenreddyalka/daari/pull/250",
    }
    base.update(overrides)
    return base


def test_conflict_automerge_is_a_stall(watch):
    assert watch.classify_stall(_pr(), now=NOW, min_age_minutes=15) == "conflict"


def test_conflict_via_mergeable_field(watch):
    pr = _pr(mergeStateStatus="UNKNOWN", mergeable="CONFLICTING", statusCheckRollup=[])
    assert watch.classify_stall(pr, now=NOW, min_age_minutes=15) == "conflict"


def test_awaiting_approval_classification(watch):
    pr = _pr(mergeStateStatus="UNKNOWN", mergeable="MERGEABLE", statusCheckRollup=[])
    runs = [
        {
            "id": 1,
            "conclusion": "action_required",
            "created_at": "2026-08-27T21:10:00Z",
            "html_url": "https://github.com/naveenreddyalka/daari/actions/runs/1",
        }
    ]
    assert (
        watch.classify_stall(pr, now=NOW, min_age_minutes=15, workflow_runs=runs)
        == "awaiting-approval"
    )


def test_no_ci_triggered_classification(watch):
    pr = _pr(mergeStateStatus="UNKNOWN", mergeable="MERGEABLE", statusCheckRollup=[])
    assert (
        watch.classify_stall(pr, now=NOW, min_age_minutes=15, workflow_runs=[])
        == "no-ci-triggered"
    )


def test_unknown_classification_when_runs_exist_but_not_action_required(watch):
    pr = _pr(mergeStateStatus="UNKNOWN", mergeable="MERGEABLE", statusCheckRollup=[])
    runs = [
        {
            "id": 2,
            "conclusion": "cancelled",
            "created_at": "2026-08-27T21:10:00Z",
            "html_url": "https://github.com/naveenreddyalka/daari/actions/runs/2",
        }
    ]
    assert (
        watch.classify_stall(pr, now=NOW, min_age_minutes=15, workflow_runs=runs)
        == "unknown"
    )


def test_classify_workflow_stall_picks_latest_run(watch):
    runs = [
        {
            "id": 1,
            "conclusion": "success",
            "created_at": "2026-08-27T21:00:00Z",
            "html_url": "https://github.com/o/r/actions/runs/1",
        },
        {
            "id": 2,
            "conclusion": "action_required",
            "created_at": "2026-08-27T21:30:00Z",
            "html_url": "https://github.com/o/r/actions/runs/2",
        },
    ]
    assert watch.classify_workflow_stall(runs) == "awaiting-approval"


def test_green_automerge_is_not_a_stall(watch):
    pr = _pr(
        mergeStateStatus="CLEAN",
        mergeable="MERGEABLE",
        statusCheckRollup=[{"name": "test", "status": "COMPLETED"}],
    )
    assert watch.classify_stall(pr, now=NOW) is None


def test_fresh_pr_is_ignored(watch):
    pr = _pr(createdAt="2026-08-27T21:55:00Z")
    assert watch.classify_stall(pr, now=NOW, min_age_minutes=15) is None


def test_without_automerge_is_ignored(watch):
    assert watch.classify_stall(_pr(autoMergeRequest=None), now=NOW) is None


def test_already_alerted(watch):
    assert watch.already_alerted([{"body": "<!-- autodev-pr-stall --> once"}])
    assert not watch.already_alerted([{"body": "lgtm"}])


def test_render_comment_conflict_keeps_merge_main_remedy(watch):
    body = watch.render_comment(_pr(), "conflict")
    assert watch.STALL_MARKER in body
    assert "classification: conflict" in body
    assert "merge `origin/main`" in body


def test_render_comment_awaiting_approval(watch):
    runs = [
        {
            "id": 9,
            "conclusion": "action_required",
            "created_at": "2026-08-27T21:10:00Z",
            "html_url": "https://github.com/naveenreddyalka/daari/actions/runs/9",
        }
    ]
    body = watch.render_comment(
        _pr(mergeStateStatus="UNKNOWN", mergeable="MERGEABLE"),
        "awaiting-approval",
        workflow_runs=runs,
    )
    assert watch.STALL_MARKER in body
    assert "classification: awaiting-approval" in body
    assert "Approve and run" in body
    assert "actions/runs/9" in body


def test_render_comment_no_ci_triggered(watch):
    body = watch.render_comment(
        _pr(mergeStateStatus="UNKNOWN", mergeable="MERGEABLE"),
        "no-ci-triggered",
        workflow_runs=[],
    )
    assert "classification: no-ci-triggered" in body
    assert "GITHUB_TOKEN" in body
    assert "close/reopen" in body


def test_render_comment_unknown(watch):
    body = watch.render_comment(
        _pr(mergeStateStatus="UNKNOWN", mergeable="MERGEABLE"),
        "unknown",
        workflow_runs=[
            {
                "id": 3,
                "conclusion": "failure",
                "created_at": "2026-08-27T21:10:00Z",
                "html_url": "https://github.com/o/r/actions/runs/3",
            }
        ],
    )
    assert "classification: unknown" in body


def _issue(**overrides):
    base = {
        "number": 176,
        "title": "Mint virtual keys from IdP claims",
        "state": "OPEN",
        "labels": [{"name": "auto-dev"}, {"name": "agent:working"}],
        "updatedAt": "2026-08-26T20:00:00Z",
    }
    base.update(overrides)
    return base


def test_stale_unlinked_issue_is_swept(watch):
    assert watch.classify_stale_working(_issue(), open_prs=[], now=NOW, ttl_hours=24)


def test_fresh_working_issue_is_not_swept(watch):
    issue = _issue(updatedAt="2026-08-27T21:30:00Z")
    assert not watch.classify_stale_working(issue, open_prs=[], now=NOW, ttl_hours=24)


def test_issue_with_open_pr_branch_is_not_swept(watch):
    pr = _pr(number=260, headRefName="autodev/176-idp-keys")
    assert not watch.classify_stale_working(_issue(), open_prs=[pr], now=NOW, ttl_hours=24)


def test_issue_referenced_in_pr_title_is_not_swept(watch):
    pr = _pr(number=260, headRefName="feature/x", title="fix: mint keys (#176)")
    assert not watch.classify_stale_working(_issue(), open_prs=[pr], now=NOW, ttl_hours=24)


def test_issue_without_working_label_is_ignored(watch):
    issue = _issue(labels=[{"name": "auto-dev"}])
    assert not watch.classify_stale_working(issue, open_prs=[], now=NOW, ttl_hours=24)


def test_apply_sweep_removes_label_once(watch):
    removed: list[int] = []
    commented: list[tuple[int, str]] = []

    swept = watch.apply_sweep(
        [_issue()],
        open_prs=[],
        now=NOW,
        ttl_hours=24,
        remove_label=lambda n: removed.append(n),
        comment=lambda n, body: commented.append((n, body)),
        list_comments=lambda _n: [],
    )
    assert swept == [176]
    assert removed == [176]
    assert commented[0][0] == 176
    assert watch.SWEEP_MARKER in commented[0][1]

    again = watch.apply_sweep(
        [_issue()],
        open_prs=[],
        now=NOW,
        ttl_hours=24,
        remove_label=lambda n: removed.append(n),
        comment=lambda n, body: commented.append((n, body)),
        list_comments=lambda _n: [{"body": commented[0][1]}],
    )
    assert again == []
    assert removed == [176]
    assert len(commented) == 1


def test_apply_alerts_once(watch):
    commented: list[tuple[int, str]] = []
    issues: list[str] = []

    def comment(number, body):
        commented.append((number, body))

    alerted = watch.apply_alerts(
        [_pr()],
        now=NOW,
        min_age_minutes=15,
        comment=comment,
        list_comments=lambda _n: [],
        create_issue=lambda title, body: issues.append(title),
        list_issues=lambda _title: [],
    )
    assert alerted == [250]
    assert commented[0][0] == 250
    assert "classification: conflict" in commented[0][1]
    assert "DIRTY" in commented[0][1] or "CONFLICTING" in commented[0][1]
    assert issues == ["[autodev] stalled auto-merge PR #250"]

    again = watch.apply_alerts(
        [_pr()],
        now=NOW,
        min_age_minutes=15,
        comment=comment,
        list_comments=lambda _n: [{"body": commented[0][1]}],
        create_issue=lambda title, body: issues.append(title),
        list_issues=lambda _title: [{"title": issues[0]}],
    )
    assert again == []
    assert len(commented) == 1
    assert len(issues) == 1


def test_apply_alerts_fetches_runs_for_empty_rollup(watch):
    commented: list[tuple[int, str]] = []
    fetched: list[str] = []
    pr = _pr(mergeStateStatus="UNKNOWN", mergeable="MERGEABLE", statusCheckRollup=[])

    def fetch_runs(sha: str):
        fetched.append(sha)
        return [
            {
                "id": 42,
                "conclusion": "action_required",
                "created_at": "2026-08-27T21:10:00Z",
                "html_url": "https://github.com/naveenreddyalka/daari/actions/runs/42",
            }
        ]

    alerted = watch.apply_alerts(
        [pr],
        now=NOW,
        min_age_minutes=15,
        comment=lambda n, body: commented.append((n, body)),
        list_comments=lambda _n: [],
        create_issue=lambda _t, _b: None,
        list_issues=lambda _t: [],
        fetch_workflow_runs=fetch_runs,
    )
    assert alerted == [250]
    assert fetched == ["abc123deadbeef"]
    assert "classification: awaiting-approval" in commented[0][1]
    assert "actions/runs/42" in commented[0][1]
