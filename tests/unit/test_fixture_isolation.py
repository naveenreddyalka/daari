"""The test suite must not touch the developer's real ~/.daari.

Three paths escaped the shared `settings` fixture, and one of them caused a real
intermittent failure: `context.path` pointed at `~/.daari/context/commands`, the
same command-context store a locally running `daari serve` writes to. A CCS entry
left by the daemon changes which tier answers a request, so tests asserting a tier
failed depending on what the daemon had cached — passing in isolation and failing
in a full run for reasons no test controlled.

`virtual_keys.path` was worse than flaky: it pointed at the real virtual-keys
database, so the suite read and wrote actual credential state.
"""

from __future__ import annotations

from pathlib import Path

REAL_DAARI_HOME = Path("~/.daari").expanduser()


def _leaked_paths(model, tmp_path: Path, prefix: str = "") -> list[str]:
    """Every string field that looks like a path outside tmp_path."""
    leaks: list[str] = []
    for name in type(model).model_fields:
        value = getattr(model, name, None)
        label = f"{prefix}{name}"
        if hasattr(type(value), "model_fields"):
            leaks.extend(_leaked_paths(value, tmp_path, prefix=f"{label}."))
            continue
        if not isinstance(value, str) or not value:
            continue
        looks_like_path = value.startswith("~") or value.startswith("/") or ".daari" in value
        if not looks_like_path:
            continue
        resolved = Path(value).expanduser()
        if REAL_DAARI_HOME in resolved.parents or resolved == REAL_DAARI_HOME:
            leaks.append(f"{label} = {value}")
    return leaks


def test_home_is_redirected_away_from_the_real_one():
    """Belt to the `settings` fixture's braces: tests that build their own
    Settings pick up `~/.daari` defaults, so `~` itself must not be real.

    `REAL_DAARI_HOME` is resolved at import time, before the autouse fixture
    patches HOME, so it still names the developer's actual directory.
    """
    assert Path.home() != REAL_DAARI_HOME.parent, (
        "HOME still points at the developer's real home; a running daari serve "
        "would share its cache and databases with the test suite"
    )


def test_default_settings_stay_inside_the_scratch_home():
    """A Settings built with no overrides must not reach the real ~/.daari."""
    from daari.config.settings import Settings

    defaults = Settings()
    for value in (
        defaults.context.path,
        defaults.learning.path,
        defaults.enterprise.audit_path,
        defaults.server.virtual_keys.path,
    ):
        resolved = Path(value).expanduser()
        assert REAL_DAARI_HOME not in resolved.parents, f"{value} escapes to real HOME"


def test_settings_fixture_writes_nothing_under_the_real_daari_home(settings, tmp_path):
    leaks = _leaked_paths(settings, tmp_path)
    assert leaks == [], "fixture paths escaping to the real ~/.daari: " + ", ".join(leaks)


def test_command_context_store_is_isolated(settings, tmp_path):
    """The store a running daemon writes to; sharing it made tier assertions flaky."""
    resolved = Path(settings.context.path).expanduser()
    assert str(tmp_path) in str(resolved)


def test_virtual_key_store_is_isolated(settings, tmp_path):
    """Never read or write the developer's real keys from a test."""
    assert str(tmp_path) in str(settings.virtual_keys_path)


def test_audit_log_is_isolated(settings, tmp_path):
    assert str(tmp_path) in str(Path(settings.enterprise.audit_path).expanduser())


def test_l1_shadow_sampling_is_off_by_default_in_tests(settings):
    """The cause of a real one-in-twenty failure.

    `cache.l1.shadow_sample_rate` ships at 0.05, so one in twenty L1 hits spawns
    a background task that re-executes the request to audit the cached answer.
    Because it runs as a task, whether it has incremented an executor call count
    by the time assertions run is a race — the hit itself always looked correct,
    which is why the failure pointed at a call count rather than the cache.

    Tests that exercise shadow sampling set the rate explicitly.
    """
    assert settings.cache.l1.shadow_sample_rate == 0.0


def test_production_default_for_shadow_sampling_is_unchanged():
    """Disabling it for tests must not quietly disable it for users."""
    from daari.config.settings import Settings

    assert Settings().cache.l1.shadow_sample_rate == 0.05
