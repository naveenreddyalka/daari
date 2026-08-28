"""Local autodev watchdog helpers (issue #181)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "autodev_local.py"


@pytest.fixture(scope="module")
def autodev_local():
    spec = importlib.util.spec_from_file_location("autodev_local", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
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
