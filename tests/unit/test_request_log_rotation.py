"""Size-based rotation for the gateway request log (issue #44)."""

from __future__ import annotations

import json

from daari.config.settings import Settings
from daari.gateway import request_log
from daari.gateway.request_log import configure_request_log, log_gateway_event


def _configure(tmp_path, *, max_bytes: int, backups: int = 3):
    path = tmp_path / "requests.log"
    configure_request_log(path=path, max_bytes=max_bytes, backups=backups)
    return path


def teardown_function() -> None:
    # Restore module defaults so other tests see the real log location.
    configure_request_log(
        path=request_log.DEFAULT_LOG_PATH,
        max_bytes=request_log.DEFAULT_MAX_BYTES,
        backups=request_log.DEFAULT_BACKUPS,
    )


def test_writes_json_lines(tmp_path):
    path = _configure(tmp_path, max_bytes=10_000)

    log_gateway_event("unit_test", {"key": "value"})

    lines = path.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "unit_test"
    assert record["key"] == "value"


def test_rotates_when_over_max_bytes(tmp_path):
    path = _configure(tmp_path, max_bytes=200, backups=2)

    for i in range(20):
        log_gateway_event("fill", {"n": i, "pad": "x" * 40})

    backup1 = path.with_name(path.name + ".1")
    assert backup1.exists(), "rotation should have produced a .1 backup"
    assert path.stat().st_size <= 200 + 120, "active log stays near the cap"


def test_backup_count_respected(tmp_path):
    path = _configure(tmp_path, max_bytes=120, backups=2)

    for i in range(60):
        log_gateway_event("fill", {"n": i, "pad": "y" * 40})

    assert path.with_name(path.name + ".1").exists()
    assert path.with_name(path.name + ".2").exists()
    assert not path.with_name(path.name + ".3").exists(), "backups beyond the cap must be deleted"


def test_rotation_preserves_recent_events(tmp_path):
    path = _configure(tmp_path, max_bytes=150, backups=1)

    for i in range(30):
        log_gateway_event("seq", {"n": i})

    all_lines = path.read_text().splitlines()
    backup = path.with_name(path.name + ".1")
    if backup.exists():
        all_lines = backup.read_text().splitlines() + all_lines
    last = json.loads(all_lines[-1])
    assert last["n"] == 29, "most recent event is always retained"


def test_zero_max_bytes_disables_rotation(tmp_path):
    path = _configure(tmp_path, max_bytes=0)

    for i in range(50):
        log_gateway_event("fill", {"n": i, "pad": "z" * 40})

    assert len(path.read_text().splitlines()) == 50
    assert not path.with_name(path.name + ".1").exists()


def test_settings_expose_observability_defaults():
    settings = Settings.model_validate({})
    assert settings.observability.request_log_max_bytes == 5 * 1024 * 1024
    assert settings.observability.request_log_backups == 3
