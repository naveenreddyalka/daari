"""Local autodev watchdog helpers (issue #181)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "autodev_local.py"


@pytest.fixture(scope="module")
def autodev_local():
    import sys

    spec = importlib.util.spec_from_file_location("autodev_local", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestDaemonProbe:
    def test_ready_endpoint_success(self, autodev_local):
        seen: list[str] = []

        def probe(url: str) -> bool:
            seen.append(url)
            return url == "http://127.0.0.1:11435/ready"

        assert autodev_local.daemon_ready("http://127.0.0.1:11435", probe=probe) is True
        assert seen == ["http://127.0.0.1:11435/ready"]

    def test_ready_falls_back_to_health(self, autodev_local):
        calls: list[str] = []

        def probe(url: str) -> bool:
            calls.append(url)
            return url.endswith("/health")

        assert autodev_local.daemon_ready("http://127.0.0.1:11435/", probe=probe) is True
        assert calls == [
            "http://127.0.0.1:11435/ready",
            "http://127.0.0.1:11435/health",
        ]

    def test_probe_failure_returns_false(self, autodev_local):
        assert autodev_local.daemon_ready("http://127.0.0.1:11435", probe=lambda _u: False) is False


class TestWaitForDaemon:
    def test_returns_immediately_when_ready(self, autodev_local):
        sleeps: list[float] = []
        assert (
            autodev_local.wait_for_daemon(
                "http://127.0.0.1:11435",
                timeout_seconds=10,
                probe=lambda _u: True,
                sleep=sleeps.append,
                monotonic=lambda: 0.0,
            )
            is True
        )
        assert sleeps == []

    def test_polls_with_backoff_until_ready(self, autodev_local):
        attempts = {"n": 0}
        sleeps: list[float] = []
        clock = iter([0.0, 0.0, 1.0, 1.0, 3.0, 3.0])

        def probe(_url: str) -> bool:
            attempts["n"] += 1
            return attempts["n"] >= 3

        assert (
            autodev_local.wait_for_daemon(
                "http://127.0.0.1:11435",
                timeout_seconds=10,
                initial_backoff_seconds=1.0,
                max_backoff_seconds=4.0,
                probe=probe,
                sleep=sleeps.append,
                monotonic=lambda: next(clock),
            )
            is True
        )
        assert attempts["n"] == 3
        assert sleeps == [1.0, 2.0]

    def test_times_out_when_never_ready(self, autodev_local):
        sleeps: list[float] = []
        clock = iter([0.0, 0.0, 1.0, 1.0, 3.0, 3.0, 9.0, 9.0, 11.0])

        assert (
            autodev_local.wait_for_daemon(
                "http://127.0.0.1:11435",
                timeout_seconds=10,
                initial_backoff_seconds=1.0,
                max_backoff_seconds=4.0,
                probe=lambda _u: False,
                sleep=sleeps.append,
                monotonic=lambda: next(clock),
            )
            is False
        )
        assert sleeps == [1.0, 2.0, 1.0]


class TestFailureDedupe:
    def test_same_failures_skips_regardless_of_sha(self, autodev_local):
        body = (
            "Local watchdog @ `abc123`\n\n## Failures\n"
            "- daemon unreachable\n- cursor-shaped E2E smoke failed\n\n## Log tail\n"
        )
        assert (
            autodev_local.open_issue_has_same_failures(
                [body],
                ["cursor-shaped E2E smoke failed", "daemon unreachable"],
            )
            is True
        )

    def test_different_failures_do_not_skip(self, autodev_local):
        body = "x\n\n## Failures\n- daemon unreachable\n\n## Log\n"
        assert autodev_local.open_issue_has_same_failures([body], ["live integration tests failed"]) is False

    def test_empty_or_closed_style_bodies_do_not_skip(self, autodev_local):
        assert autodev_local.open_issue_has_same_failures([], ["daemon unreachable"]) is False
        assert autodev_local.open_issue_has_same_failures(["no section"], ["daemon unreachable"]) is False

    def test_skip_create_matches_title_or_failures(self, autodev_local):
        nodes = [
            {
                "title": "[autodev] Local E2E regression on main @ abc",
                "body": "## Failures\n- daemon unreachable\n",
            }
        ]
        assert autodev_local.should_skip_regression_create(
            nodes, "[autodev] Local E2E regression on main @ abc", ["live integration tests failed"]
        )
        assert autodev_local.should_skip_regression_create(
            nodes, "[autodev] Local E2E regression on main @ def", ["daemon unreachable"]
        )
        assert not autodev_local.should_skip_regression_create(
            nodes, "[autodev] Local E2E regression on main @ def", ["live integration tests failed"]
        )


_REPO = Path(__file__).resolve().parents[2]
_WATCHDOG_SH = _REPO / "scripts" / "autodev-local.sh"
_SERVE_PLIST = _REPO / "scripts" / "launchd" / "com.daari.serve.plist"


def test_watchdog_serve_plist_permits_weak_or_unset_master_key() -> None:
    """#1320 gate would KeepAlive crash-loop local watchdog serve (#1328)."""
    text = _SERVE_PLIST.read_text(encoding="utf-8")
    assert "EnvironmentVariables" in text
    assert "DAARI_SERVER__DANGEROUSLY_PERMIT_WEAK_OR_UNSET_API_KEY" in text


def test_watchdog_skips_cursor_smoke_when_daemon_unreachable() -> None:
    text = _WATCHDOG_SH.read_text(encoding="utf-8")
    assert "SKIP: cursor smoke" in text
    assert "daemon_unreachable" in text


def test_watchdog_skips_live_integration_when_daemon_unreachable() -> None:
    text = _WATCHDOG_SH.read_text(encoding="utf-8")
    assert "SKIP: live integration (daemon unreachable)" in text
    assert "daemon_unreachable" in text


def test_watchdog_issue_body_includes_serve_stderr_tail() -> None:
    text = _WATCHDOG_SH.read_text(encoding="utf-8")
    assert "serve.err.log" in text


def test_watchdog_dedupes_open_issues_by_failure_list() -> None:
    text = _WATCHDOG_SH.read_text(encoding="utf-8")
    assert "skip-create" in text
    assert "body" in text


# Sample serve.err.log tails from the 2026-10-05 KeepAlive crash loop (#1453).
_SAMPLE_MASTER_KEY_REFUSE = """
INFO:     Waiting for application startup.
  ✗ master_key: refusing to serve: server.api_key unset
"""

_SAMPLE_WEAK_KEY_REFUSE = """
  ✗ master_key: refusing to serve: server.api_key matches weak denylist ('changeme') — choose a unique secret, or set server.dangerously_permit_weak_or_unset_api_key: true for local sandboxes
"""

_SAMPLE_BOOTING = """
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
"""


class TestClassifyFatalServeConfig:
    def test_master_key_unset_refuse(self, autodev_local):
        hit = autodev_local.classify_fatal_serve_config(_SAMPLE_MASTER_KEY_REFUSE)
        assert hit is not None
        assert hit.reason == "master_key_refuse"
        assert "refusing to serve" in hit.matched.lower()

    def test_weak_denylist_refuse(self, autodev_local):
        hit = autodev_local.classify_fatal_serve_config(_SAMPLE_WEAK_KEY_REFUSE)
        assert hit is not None
        assert hit.reason == "master_key_refuse"

    def test_booting_stderr_is_not_fatal(self, autodev_local):
        assert autodev_local.classify_fatal_serve_config(_SAMPLE_BOOTING) is None

    def test_empty_stderr_is_not_fatal(self, autodev_local):
        assert autodev_local.classify_fatal_serve_config("") is None
        assert autodev_local.classify_fatal_serve_config(None) is None

    def test_should_skip_kickstart_on_fatal(self, autodev_local):
        hit = autodev_local.classify_fatal_serve_config(_SAMPLE_MASTER_KEY_REFUSE)
        assert autodev_local.should_skip_serve_kickstart(hit) is True
        assert autodev_local.should_skip_serve_kickstart(None) is False

    def test_failure_bullet_includes_classified_reason(self, autodev_local):
        hit = autodev_local.classify_fatal_serve_config(_SAMPLE_MASTER_KEY_REFUSE)
        bullet = autodev_local.daemon_unreachable_failure_bullet(hit)
        assert bullet.startswith("daemon unreachable")
        assert "master_key_refuse" in bullet


def test_watchdog_classifies_fatal_config_before_kickstart() -> None:
    text = _WATCHDOG_SH.read_text(encoding="utf-8")
    assert "classify-fatal" in text
    assert "FATAL_SERVE_CONFIG" in text
    assert "skip kickstart" in text.lower() or "Skipping kickstart" in text
