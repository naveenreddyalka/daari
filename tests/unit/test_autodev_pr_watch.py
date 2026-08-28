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
        "autoMergeRequest": {"enabledAt": "2026-08-27T21:00:00Z"},
        "statusCheckRollup": [],
        "createdAt": "2026-08-27T21:00:00Z",
    }
    base.update(overrides)
    return base


def test_dirty_automerge_is_a_stall(watch):
    assert watch.classify_stall(_pr(), now=NOW, min_age_minutes=15) == "dirty"


def test_no_checks_is_a_stall(watch):
    pr = _pr(mergeStateStatus="UNKNOWN", statusCheckRollup=[])
    assert watch.classify_stall(pr, now=NOW, min_age_minutes=15) == "no_checks"


def test_green_automerge_is_not_a_stall(watch):
    pr = _pr(
        mergeStateStatus="CLEAN",
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
    assert "DIRTY" in commented[0][1]
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
