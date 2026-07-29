"""Compose backends profile exists for Redis + Postgres E2E (issue #142)."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_compose_backends_profile_defines_redis_and_postgres():
    root = Path(__file__).resolve().parents[2]
    raw = (root / "docker-compose.yml").read_text(encoding="utf-8")
    doc = yaml.safe_load(raw)
    services = doc["services"]
    assert "redis" in services
    assert "postgres" in services
    assert "backends" in services["redis"].get("profiles", [])
    assert "backends" in services["postgres"].get("profiles", [])
    assert services["redis"]["image"].startswith("redis:")
    assert services["postgres"]["image"].startswith("postgres:")
