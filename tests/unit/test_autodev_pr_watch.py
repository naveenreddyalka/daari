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
