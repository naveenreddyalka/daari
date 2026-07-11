from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from daari.enterprise.cache import resolve_org_learning_root, resolve_org_shared_cache_root
from daari.enterprise.config import OrgSettings


class OrgCachePutRequest(BaseModel):
    key: str
    value: str
    tier: str = "L0"
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Issue #6: L1 entries may carry an embedding for similarity lookups.
    embedding: list[float] | None = None
    context_key: str | None = None


class OrgCacheSimilarRequest(BaseModel):
    embedding: list[float]
    context_key: str
    threshold: float = 0.88


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
        entry: dict[str, Any] = {
            "key": payload.key,
            "value": payload.value,
            "tier": payload.tier,
            "metadata": payload.metadata,
            "stored_at": time.time(),
        }
        if payload.embedding:
            entry["embedding"] = payload.embedding
            entry["context_key"] = payload.context_key
        self._store().set(self._entry_key(payload.key, payload.tier), entry)
        self.writes += 1

    def similar(
        self, embedding: list[float], *, context_key: str, threshold: float
    ) -> dict[str, Any] | None:
        """Best L1 entry by cosine similarity within the same context key."""
        from daari.cache.semantic import cosine_similarity

        store = self._store()
        best: dict[str, Any] | None = None
        best_score = 0.0
        for entry_key in store.iterkeys():
            if not isinstance(entry_key, str) or not entry_key.startswith("L1:"):
                continue
            entry = store.get(entry_key)
            if not isinstance(entry, dict):
                continue
            stored = entry.get("embedding")
            if not isinstance(stored, list) or entry.get("context_key") != context_key:
                continue
            score = cosine_similarity(embedding, stored)
            if score > best_score:
                best_score = score
                best = entry
        if best is None or best_score < threshold:
            self.misses += 1
            return None
        self.hits += 1
        return {**best, "similarity": best_score}

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


class OrgLearningFeedbackRequest(BaseModel):
    tier: str
    cache_hit: bool
    latency_ms: int = Field(ge=0)
    rating: int | None = None
    task_class: str | None = None


class OrgLearningStore:
    def __init__(self, root: Path, org_id: str) -> None:
        self.root = root
        self.org_id = org_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "feedback.sqlite3"
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tier TEXT NOT NULL,
                    cache_hit INTEGER NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    rating INTEGER,
                    task_class TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS profile_override (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    def add_feedback(self, feedback: OrgLearningFeedbackRequest) -> None:
        rating = feedback.rating
        if rating not in (None, 1, -1):
            rating = None
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                (
                    "INSERT INTO feedback (tier, cache_hit, latency_ms, rating, task_class, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)"
                ),
                (
                    feedback.tier,
                    1 if feedback.cache_hit else 0,
                    feedback.latency_ms,
                    rating,
                    feedback.task_class,
                    now,
                ),
            )
            conn.commit()

    def set_profile_override(self, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                (
                    "INSERT INTO profile_override (id, payload, updated_at) VALUES (1, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at"
                ),
                (json.dumps(payload), time.time()),
            )
            conn.commit()

    def _get_profile_override(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM profile_override WHERE id = 1").fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["payload"])
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _latency_bucket(latency_ms: int) -> str:
        if latency_ms < 200:
            return "<200ms"
        if latency_ms < 500:
            return "200-499ms"
        if latency_ms < 1000:
            return "500-999ms"
        if latency_ms < 2000:
            return "1000-1999ms"
        return "2000ms+"

    def build_profile(self) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute("SELECT tier, cache_hit, latency_ms, rating, task_class FROM feedback").fetchall()
        total = len(rows)
        tier_counts: dict[str, int] = {}
        task_class_counts: dict[str, int] = {}
        latency_buckets = {"<200ms": 0, "200-499ms": 0, "500-999ms": 0, "1000-1999ms": 0, "2000ms+": 0}
        cache_hits = 0
        latency_sum = 0
        upvotes = 0
        downvotes = 0
        for row in rows:
            tier = row["tier"]
            task_class = row["task_class"] or "general"
            latency = int(row["latency_ms"])
            rating = row["rating"]
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            task_class_counts[task_class] = task_class_counts.get(task_class, 0) + 1
            latency_buckets[self._latency_bucket(latency)] += 1
            cache_hits += 1 if row["cache_hit"] else 0
            latency_sum += latency
            if rating == 1:
                upvotes += 1
            elif rating == -1:
                downvotes += 1

        avg_latency_ms = int(latency_sum / total) if total else 0
        cache_hit_rate = round(cache_hits / total, 3) if total else 0.0
        ratings_total = upvotes + downvotes
        rating_score = round((upvotes - downvotes) / ratings_total, 3) if ratings_total else 0.0

        prefer = "balanced"
        if avg_latency_ms > 1800 or cache_hit_rate < 0.2:
            prefer = "latency"
        elif rating_score < -0.2:
            prefer = "accuracy"

        confidence_threshold = 0.7
        if rating_score > 0.3:
            confidence_threshold -= 0.05
        elif rating_score < -0.2:
            confidence_threshold += 0.1
        if cache_hit_rate > 0.6:
            confidence_threshold -= 0.05
        confidence_threshold = max(0.55, min(0.9, round(confidence_threshold, 2)))

        metrics = {
            "feedback_count": total,
            "tier_counts": tier_counts,
            "task_class_counts": task_class_counts,
            "latency_buckets": latency_buckets,
            "cache_hit_rate": cache_hit_rate,
            "avg_latency_ms": avg_latency_ms,
            "ratings": {"up": upvotes, "down": downvotes, "score": rating_score},
        }
        routing_profile = {
            "prefer": prefer,
            "confidence_threshold": confidence_threshold,
        }
        override = self._get_profile_override() or {}
        override_routing = override.get("routing")
        if isinstance(override_routing, dict):
            if isinstance(override_routing.get("prefer"), str):
                routing_profile["prefer"] = override_routing["prefer"]
            threshold = override_routing.get("confidence_threshold")
            if isinstance(threshold, (int, float)):
                routing_profile["confidence_threshold"] = float(threshold)
        return {
            "org_id": self.org_id,
            "generated_at": int(time.time()),
            "routing": routing_profile,
            "metrics": metrics,
            "override": override,
        }


def _expected_token(org: OrgSettings) -> str | None:
    return (
        org.learning_token
        or org.org_token
        or org.shared_cache_token
        or os.environ.get("DAARI_ORG_LEARNING_TOKEN")
        or os.environ.get("DAARI_ORG_TOKEN")
        or os.environ.get("DAARI_ORG_CACHE_TOKEN")
    )


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


def _ensure_admin_authorized(org: OrgSettings, auth_header: str | None) -> None:
    token = _expected_token(org)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="org learning admin token is not configured",
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
    learning_root = resolve_org_learning_root(org)
    if learning_root is None:
        raise ValueError("org learning service requires org id")
    learning_store = OrgLearningStore(learning_root, org.resolved_org_id or "unknown")
    app = FastAPI(title="daari-org-cache", version="0.1.0")

    def _require_auth(authorization: str | None = Header(default=None, alias="Authorization")) -> None:
        _ensure_authorized(org, authorization)

    def _require_admin_auth(authorization: str | None = Header(default=None, alias="Authorization")) -> None:
        _ensure_admin_authorized(org, authorization)

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

    @app.post("/v1/org-cache/similar")
    async def similar_entry(
        body: OrgCacheSimilarRequest,
        _: None = Depends(_require_auth),
    ) -> dict[str, Any]:
        entry = store.similar(body.embedding, context_key=body.context_key, threshold=body.threshold)
        if entry is None:
            return {"hit": False}
        return {"hit": True, "value": entry["value"], "similarity": entry["similarity"]}

    @app.get("/v1/org-cache/stats")
    async def get_stats(_: None = Depends(_require_auth)) -> dict[str, Any]:
        return store.stats()

    @app.post("/v1/org-learning/feedback")
    async def post_feedback(
        body: OrgLearningFeedbackRequest,
        _: None = Depends(_require_auth),
    ) -> dict[str, Any]:
        learning_store.add_feedback(body)
        return {"ok": True}

    @app.get("/v1/org-learning/profile")
    async def get_learning_profile(_: None = Depends(_require_auth)) -> dict[str, Any]:
        return learning_store.build_profile()

    @app.put("/v1/org-learning/profile")
    async def put_learning_profile(
        body: dict[str, Any],
        _: None = Depends(_require_admin_auth),
    ) -> dict[str, Any]:
        learning_store.set_profile_override(body)
        profile = learning_store.build_profile()
        return {"ok": True, "routing": profile["routing"]}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
