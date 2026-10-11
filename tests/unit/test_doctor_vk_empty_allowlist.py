"""Doctor tip when VK allowlists match zero catalog cards (#1582)."""

from __future__ import annotations

from pathlib import Path

from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import Settings
from daari.setup.doctor import _check_vk_empty_allowlist, run_doctor

ROOT = Path(__file__).resolve().parents[2]
DOCTOR_HEALTH = ROOT / "docs/developer/guides/operations/doctor-health.md"


def _stub_settings(tmp_path) -> Settings:
    settings = Settings.model_validate(
        {
            "server": {
                "api_key": "master",
                "virtual_keys": {
                    "enabled": True,
                    "path": str(tmp_path / "vk.sqlite3"),
                },
            },
            "frontier": {
                "enabled": True,
                "providers": [
                    {"id": "anthropic", "model": "claude-sonnet-5-5"},
                ],
            },
            "model_groups": {"anthropic": ["claude-sonnet-*"]},
        }
    )
    return settings


class TestVkEmptyAllowlistDoctor:
    def _down_client(self):
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_tips_when_patterns_match_zero_cards(self, tmp_path):
        settings = _stub_settings(tmp_path)
        store = VirtualKeyStore(settings.virtual_keys_path)
        stale = store.create("stale", allowed_models=["claude-opus-99"])
        store.create("ok", allowed_models=["claude-sonnet-*"])
        store.create("open")  # unrestricted — ignored

        result = _check_vk_empty_allowlist(settings)
        assert result.ok is False
        assert result.optional is True
        assert result.name == "vk_empty_allowlist"
        assert stale.key.key_id in result.detail
        assert "claude-opus-99" in result.detail
        # unrestricted and matching keys omitted
        open_keys = [k for k in store.list() if k.name == "open"]
        assert open_keys
        assert open_keys[0].key_id not in result.detail

    def test_tips_for_stale_model_group(self, tmp_path):
        settings = _stub_settings(tmp_path)
        store = VirtualKeyStore(settings.virtual_keys_path)
        created = store.create("ghost-group", model_groups=["missing-group"])
        result = _check_vk_empty_allowlist(settings)
        assert result.ok is False
        assert created.key.key_id in result.detail
        assert "missing-group" in result.detail or "groups=" in result.detail

    def test_quiet_when_allowlists_match_catalog(self, tmp_path):
        settings = _stub_settings(tmp_path)
        store = VirtualKeyStore(settings.virtual_keys_path)
        store.create("good", allowed_models=["claude-sonnet-*"], model_groups=["anthropic"])
        store.create("open")
        result = _check_vk_empty_allowlist(settings)
        assert result.ok is True
        assert result.optional is True

    def test_quiet_when_virtual_keys_disabled(self, tmp_path):
        settings = _stub_settings(tmp_path)
        settings.server.virtual_keys.enabled = False
        result = _check_vk_empty_allowlist(settings)
        assert result.ok is True
        assert "disabled" in result.detail.lower()

    def test_ignores_revoked_keys(self, tmp_path):
        settings = _stub_settings(tmp_path)
        store = VirtualKeyStore(settings.virtual_keys_path)
        created = store.create("gone", allowed_models=["claude-opus-99"])
        store.revoke(created.key.key_id)
        result = _check_vk_empty_allowlist(settings)
        assert result.ok is True
        assert created.key.key_id not in result.detail

    def test_run_doctor_includes_check(self, tmp_path):
        settings = _stub_settings(tmp_path)
        VirtualKeyStore(settings.virtual_keys_path).create(
            "stale", allowed_models=["claude-opus-99"]
        )
        results = run_doctor(settings, httpx_client=self._down_client())
        by_name = {r.name: r for r in results}
        assert "vk_empty_allowlist" in by_name
        assert by_name["vk_empty_allowlist"].ok is False
        assert by_name["vk_empty_allowlist"].optional is True

    def test_doctor_health_documents_check(self) -> None:
        text = DOCTOR_HEALTH.read_text(encoding="utf-8")
        assert "doctor `vk_empty_allowlist`" in text
