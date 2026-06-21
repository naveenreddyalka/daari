from __future__ import annotations

from daari.config.settings import Settings
from daari.router.router import AppContext


def test_app_context_builds_org_cache_client(tmp_path):
    settings = Settings.model_validate(
        {
            "cache": {
                "l0": {"enabled": True, "path": str(tmp_path / "l0")},
                "l1": {"enabled": False, "path": str(tmp_path / "l1")},
            },
            "context": {"enabled": True, "path": str(tmp_path / "ccs")},
            "enterprise": {
                "enabled": True,
                "org_id": "acme",
                "shared_cache_url": "http://127.0.0.1:11436",
                "shared_cache_token": "token",
            },
        }
    )
    ctx = AppContext.from_settings(settings)
    assert ctx.org_cache_client is not None
    assert ctx.org_cache_client.base_url == "http://127.0.0.1:11436"
    assert ctx.org_cache_client.token == "token"
