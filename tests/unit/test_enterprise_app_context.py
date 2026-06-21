from __future__ import annotations

from daari.config.settings import Settings
from daari.enterprise.client import OrgLearningClient
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


def test_app_context_merges_org_learning_profile(monkeypatch, tmp_path):
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
                "learning_enabled": True,
                "learning_url": "http://127.0.0.1:11436",
            },
        }
    )

    monkeypatch.setattr(
        OrgLearningClient,
        "get_profile_sync",
        lambda self: {"routing": {"prefer": "accuracy", "confidence_threshold": 0.82}},
    )
    ctx = AppContext.from_settings(settings)
    assert ctx.org_learning_client is not None
    assert ctx.router.model_preference == "accuracy"
    assert ctx.router.confidence_threshold == 0.82
