from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from daari.enterprise.cache import resolve_org_shared_cache_root
from daari.enterprise.config import OrgSettings


class OrgCachePutRequest(BaseModel):
    key: str
    value: str
    tier: str = "L0"
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrgCacheStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._cache = None
        self.hits = 0
        self.misses = 0
        self.writes = 0

    def _store(self) -> Any:
        if self._cache is None:
            import diskcache

            self._cache = diskcache.Cache(str(self.root))
        return self._cache

    @staticmethod
    def _entry_key(key: str, tier: str) -> str:
        return f"{tier}:{key}"

    def get(self, key: str, *, tier: str) -> dict[str, Any] | None:
        entry = self._store().get(self._entry_key(key, tier))
        if entry is None:
            self.misses += 1
            return None
        self.hits += 1
        return entry if isinstance(entry, dict) else None

    def put(self, payload: OrgCachePutRequest) -> None:
        self._store().set(
            self._entry_key(payload.key, payload.tier),
            {
                "key": payload.key,
                "value": payload.value,
                "tier": payload.tier,
                "metadata": payload.metadata,
                "stored_at": time.time(),
            },
        )
        self.writes += 1

    def stats(self) -> dict[str, Any]:
        tiers: dict[str, int] = {"L0": 0, "L1": 0}
        count = 0
        for entry_key in self._store().iterkeys():
            if not isinstance(entry_key, str):
                continue
            count += 1
            if entry_key.startswith("L0:"):
                tiers["L0"] += 1
            elif entry_key.startswith("L1:"):
                tiers["L1"] += 1
        return {
            "entries": count,
            "tiers": tiers,
            "hits": self.hits,
            "misses": self.misses,
            "writes": self.writes,
            "root": str(self.root),
        }


def _expected_token(org: OrgSettings) -> str | None:
    return org.shared_cache_token or os.environ.get("DAARI_ORG_CACHE_TOKEN")


def _auth_required(org: OrgSettings) -> bool:
    return org.shared_cache_require_token or _expected_token(org) is not None


def _ensure_authorized(org: OrgSettings, auth_header: str | None) -> None:
    if not _auth_required(org):
        return
    token = _expected_token(org)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="org cache auth required but DAARI_ORG_CACHE_TOKEN not configured",
        )
    provided = (auth_header or "").strip()
    if not provided.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    if provided.split(" ", 1)[1] != token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")


def create_org_cache_app(org: OrgSettings) -> FastAPI:
    root = resolve_org_shared_cache_root(org)
    if root is None:
        raise ValueError("org cache service requires org id")
    store = OrgCacheStore(root)
    app = FastAPI(title="daari-org-cache", version="0.1.0")

    def _require_auth(authorization: str | None = Header(default=None, alias="Authorization")) -> None:
        _ensure_authorized(org, authorization)

    @app.get("/v1/org-cache/get")
    async def get_entry(
        key: str,
        tier: str = "L0",
        _: None = Depends(_require_auth),
    ) -> dict[str, Any]:
        entry = store.get(key, tier=tier)
        if entry is None:
            return {"hit": False, "key": key, "tier": tier}
        return {"hit": True, **entry}

    @app.put("/v1/org-cache/put")
    async def put_entry(
        body: OrgCachePutRequest,
        _: None = Depends(_require_auth),
    ) -> dict[str, Any]:
        store.put(body)
        return {"ok": True, "key": body.key, "tier": body.tier}

    @app.get("/v1/org-cache/stats")
    async def get_stats(_: None = Depends(_require_auth)) -> dict[str, Any]:
        return store.stats()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
