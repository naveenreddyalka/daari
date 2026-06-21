from __future__ import annotations

from fastapi.testclient import TestClient

from daari.enterprise.config import OrgSettings
from daari.enterprise.service import create_org_cache_app


def test_org_cache_put_get_and_stats(tmp_path):
    app = create_org_cache_app(
        OrgSettings.model_validate(
            {
                "enabled": True,
                "org_id": "acme",
                "shared_cache_path": str(tmp_path / "shared-cache"),
            }
        )
    )
    client = TestClient(app)

    put = client.put(
        "/v1/org-cache/put",
        json={"key": "abc", "value": '{"content":"x"}', "tier": "L0", "metadata": {"source": "test"}},
    )
    assert put.status_code == 200

    hit = client.get("/v1/org-cache/get", params={"key": "abc", "tier": "L0"})
    assert hit.status_code == 200
    payload = hit.json()
    assert payload["hit"] is True
    assert payload["tier"] == "L0"
    assert payload["value"] == '{"content":"x"}'

    stats = client.get("/v1/org-cache/stats")
    assert stats.status_code == 200
    stats_payload = stats.json()
    assert stats_payload["entries"] == 1
    assert stats_payload["tiers"]["L0"] == 1


def test_org_cache_token_auth(tmp_path):
    app = create_org_cache_app(
        OrgSettings.model_validate(
            {
                "enabled": True,
                "org_id": "acme",
                "shared_cache_path": str(tmp_path / "shared-cache"),
                "shared_cache_token": "secret-token",
                "shared_cache_require_token": True,
            }
        )
    )
    client = TestClient(app)

    no_auth = client.get("/v1/org-cache/stats")
    assert no_auth.status_code == 401

    wrong_auth = client.get("/v1/org-cache/stats", headers={"Authorization": "Bearer no"})
    assert wrong_auth.status_code == 401

    ok_auth = client.get("/v1/org-cache/stats", headers={"Authorization": "Bearer secret-token"})
    assert ok_auth.status_code == 200


def test_org_learning_feedback_profile_and_override(tmp_path):
    app = create_org_cache_app(
        OrgSettings.model_validate(
            {
                "enabled": True,
                "org_id": "acme",
                "shared_cache_path": str(tmp_path / "shared-cache"),
                "learning_path": str(tmp_path / "learning"),
                "learning_token": "learn-token",
            }
        )
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer learn-token"}
    # Ensure only metadata fields are accepted; no raw prompt/code payload exists in schema.
    feedback = client.post(
        "/v1/org-learning/feedback",
        headers=headers,
        json={
            "tier": "L3",
            "cache_hit": False,
            "latency_ms": 1234,
            "rating": 1,
            "task_class": "git",
            "prompt": "secret raw prompt should be ignored",
        },
    )
    assert feedback.status_code == 200

    profile = client.get("/v1/org-learning/profile", headers=headers)
    assert profile.status_code == 200
    profile_payload = profile.json()
    assert profile_payload["metrics"]["feedback_count"] == 1
    assert profile_payload["metrics"]["tier_counts"]["L3"] == 1
    assert "prompt" not in profile_payload

    no_auth_override = client.put(
        "/v1/org-learning/profile",
        json={"routing": {"prefer": "accuracy"}},
    )
    assert no_auth_override.status_code == 401

    override = client.put(
        "/v1/org-learning/profile",
        headers=headers,
        json={"routing": {"prefer": "accuracy", "confidence_threshold": 0.82}},
    )
    assert override.status_code == 200
    assert override.json()["routing"]["prefer"] == "accuracy"
