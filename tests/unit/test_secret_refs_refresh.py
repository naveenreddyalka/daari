"""Refreshable non-oauth secret:// resolution (issue #1204).

env-file / exec / keychain refs re-resolve on TTL (and env-file mtime)
without a process restart. TTL 0 keeps boot-only plain-string behavior.
"""

from __future__ import annotations

import os
import time

import pytest

from daari.config.settings import Settings
from daari.security import secret_refs
from daari.security.secret_refs import (
    RefreshableSecret,
    SecretRefError,
    clear_registered_secrets,
    current_secret,
    resolve_secret_ref,
    resolve_settings_secrets,
    set_static_refresh_ttl,
)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    clear_registered_secrets()
    set_static_refresh_ttl(300.0)
    monkeypatch.setattr(secret_refs, "_now", time.time)
    yield
    clear_registered_secrets()
    set_static_refresh_ttl(300.0)


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class TestBootOnlyTtlZero:
    def test_ttl_zero_resolves_to_plain_str(self, tmp_path):
        set_static_refresh_ttl(0.0)
        env = tmp_path / "secrets.env"
        env.write_text("K=boot-value\n", encoding="utf-8")
        ref = f"secret://env-file/{env}#K"
        value = resolve_secret_ref(ref)
        assert value == "boot-value"
        assert type(value) is str
        assert not isinstance(value, RefreshableSecret)

    def test_ttl_zero_settings_stay_frozen_after_rotation(self, tmp_path):
        env = tmp_path / "secrets.env"
        env.write_text("K=v1\n", encoding="utf-8")
        ref = f"secret://env-file/{env}#K"
        settings = Settings.model_validate(
            {
                "secrets": {"refresh_ttl_seconds": 0},
                "frontier": {"providers": [{"id": "openai", "keys": [ref]}]},
            }
        )
        resolve_settings_secrets(settings)
        key = settings.frontier.providers[0].keys[0]
        assert key == "v1" and type(key) is str
        env.write_text("K=v2\n", encoding="utf-8")
        assert current_secret(key) == "v1"


class TestTtlRefresh:
    def test_env_file_refresh_after_ttl(self, tmp_path, monkeypatch):
        clock = FakeClock()
        monkeypatch.setattr(secret_refs, "_now", clock)
        env = tmp_path / "secrets.env"
        env.write_text("K=v1\n", encoding="utf-8")
        ref = f"secret://env-file/{env}#K"
        first = resolve_secret_ref(ref)
        assert first == "v1" and isinstance(first, RefreshableSecret)
        env.write_text("K=v2\n", encoding="utf-8")
        os.utime(env, (clock() + 1, clock() + 1))
        # Within TTL: mtime change alone should refresh.
        assert current_secret(first) == "v2"

    def test_exec_refresh_after_ttl_only(self, monkeypatch):
        clock = FakeClock()
        monkeypatch.setattr(secret_refs, "_now", clock)
        values = iter(["tok-1", "tok-2", "tok-3"])

        def runner(argv):
            return next(values)

        monkeypatch.setattr(secret_refs, "_default_runner", runner)
        ref = "secret://exec/op read op://vault/item/key"
        first = resolve_secret_ref(ref)
        assert first == "tok-1" and isinstance(first, RefreshableSecret)
        assert current_secret(first) == "tok-1"  # still within TTL
        clock.advance(301)
        assert current_secret(first) == "tok-2"

    def test_settings_frontier_key_rotation_without_restart(self, tmp_path, monkeypatch):
        clock = FakeClock()
        monkeypatch.setattr(secret_refs, "_now", clock)
        env = tmp_path / "secrets.env"
        env.write_text("API_KEY=sk-old\n", encoding="utf-8")
        ref = f"secret://env-file/{env}#API_KEY"
        settings = Settings.model_validate(
            {
                "secrets": {"refresh_ttl_seconds": 60.0},
                "frontier": {"providers": [{"id": "openai", "keys": [ref]}]},
            }
        )
        resolve_settings_secrets(settings)
        key = settings.frontier.providers[0].keys[0]
        assert key == "sk-old" and isinstance(key, RefreshableSecret)

        from daari.router.frontier import FrontierExecutor
        from daari.router.frontier_pool import ProviderSlot

        slot = ProviderSlot(
            id="openai",
            executor=FrontierExecutor(
                base_url="https://api.openai.com/v1",
                api_key=key,
                default_model="gpt-4o-mini",
                provider="openai",
            ),
            keys=[key],
        )
        assert slot.pick_key() == "sk-old"
        env.write_text("API_KEY=sk-rotated\n", encoding="utf-8")
        os.utime(env, (clock(), clock()))
        assert slot.pick_key() == "sk-rotated"

    def test_boot_failure_still_fatal(self, tmp_path):
        ref = f"secret://env-file/{tmp_path}/absent.env#K"
        settings = Settings.model_validate(
            {"frontier": {"providers": [{"id": "openai", "keys": [ref]}]}}
        )
        with pytest.raises(SecretRefError) as excinfo:
            resolve_settings_secrets(settings)
        assert ref in str(excinfo.value)
        assert "frontier.providers[0].keys[0]" in str(excinfo.value)

    def test_settings_ttl_zero_from_config(self, tmp_path):
        env = tmp_path / "secrets.env"
        env.write_text("K=v1\n", encoding="utf-8")
        ref = f"secret://env-file/{env}#K"
        settings = Settings.model_validate(
            {
                "secrets": {"refresh_ttl_seconds": 0},
                "enterprise": {"shared_cache_token": ref},
            }
        )
        resolve_settings_secrets(settings)
        token = settings.enterprise.shared_cache_token
        assert type(token) is str
        env.write_text("K=v2\n", encoding="utf-8")
        assert current_secret(token) == "v1"
