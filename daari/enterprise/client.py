from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, Field

from daari.cache.exact import cache_key
from daari.cache.semantic import extract_embed_text, semantic_context_key
from daari.gateway.internal import InternalRequest, InternalResponse


def org_l0_key(request: InternalRequest) -> str:
    return cache_key(request)


def org_l1_key(request: InternalRequest) -> str:
    payload = f"{semantic_context_key(request)}|{extract_embed_text(request)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class OrgCacheClient:
    base_url: str
    token: str | None = None
    timeout_seconds: float = 1.0
    enabled: bool = True
    transport: httpx.AsyncBaseTransport | None = None

    def _auth_headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    async def _get(self, key: str, *, tier: str) -> str | None:
        if not self.enabled:
            return None
        url = f"{self.base_url.rstrip('/')}/v1/org-cache/get"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = await client.get(
                    url,
                    params={"key": key, "tier": tier},
                    headers=self._auth_headers(),
                )
        except Exception:
            return None
        if response.status_code != 200:
            return None
        payload = response.json()
        if not payload.get("hit"):
            return None
        value = payload.get("value")
        return value if isinstance(value, str) else None

    async def _put(self, key: str, *, value: str, tier: str, metadata: dict[str, Any] | None = None) -> None:
        if not self.enabled:
            return
        url = f"{self.base_url.rstrip('/')}/v1/org-cache/put"
        body = {
            "key": key,
            "value": value,
            "tier": tier,
            "metadata": metadata or {},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
                await client.put(url, json=body, headers=self._auth_headers())
        except Exception:
            return

    async def get_l0(self, request: InternalRequest) -> InternalResponse | None:
        raw = await self._get(org_l0_key(request), tier="L0")
        if raw is None:
            return None
        try:
            return InternalResponse.model_validate_json(raw)
        except Exception:
            return None

    async def get_l1(self, request: InternalRequest) -> InternalResponse | None:
        raw = await self._get(org_l1_key(request), tier="L1")
        if raw is None:
            return None
        try:
            return InternalResponse.model_validate_json(raw)
        except Exception:
            return None

    async def put_l0(self, request: InternalRequest, response: InternalResponse) -> None:
        await self._put(
            org_l0_key(request),
            value=response.model_dump_json(),
            tier="L0",
            metadata={"cache_kind": "exact"},
        )

    async def put_l1(self, request: InternalRequest, response: InternalResponse) -> None:
        await self._put(
            org_l1_key(request),
            value=response.model_dump_json(),
            tier="L1",
            metadata={"cache_kind": "semantic-keyed"},
        )

    async def stats(self) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        url = f"{self.base_url.rstrip('/')}/v1/org-cache/stats"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = await client.get(url, headers=self._auth_headers())
                if response.status_code != 200:
                    return None
                payload = response.json()
                return payload if isinstance(payload, dict) else None
        except Exception:
            return None


class OrgLearningFeedback(BaseModel):
    tier: str
    cache_hit: bool
    latency_ms: int = Field(ge=0)
    rating: int | None = None
    task_class: str | None = None


@dataclass
class OrgLearningClient:
    base_url: str
    token: str | None = None
    timeout_seconds: float = 0.5
    enabled: bool = True
    transport: httpx.AsyncBaseTransport | None = None

    def _auth_headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    async def post_feedback(self, feedback: OrgLearningFeedback) -> None:
        if not self.enabled:
            return
        url = f"{self.base_url.rstrip('/')}/v1/org-learning/feedback"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
                await client.post(url, json=feedback.model_dump(exclude_none=True), headers=self._auth_headers())
        except Exception:
            return

    async def get_profile(self) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        url = f"{self.base_url.rstrip('/')}/v1/org-learning/profile"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = await client.get(url, headers=self._auth_headers())
                if response.status_code != 200:
                    return None
                payload = response.json()
                return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def get_profile_sync(self) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        url = f"{self.base_url.rstrip('/')}/v1/org-learning/profile"
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(url, headers=self._auth_headers())
                if response.status_code != 200:
                    return None
                payload = response.json()
                return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def get_stats_sync(self) -> dict[str, Any] | None:
        profile = self.get_profile_sync()
        if profile is None:
            return None
        metrics = profile.get("metrics")
        if isinstance(metrics, dict):
            return metrics
        return None

    def export_sync(self) -> dict[str, Any] | None:
        profile = self.get_profile_sync()
        if profile is None:
            return None
        return {
            "org_id": profile.get("org_id"),
            "generated_at": profile.get("generated_at"),
            "routing": profile.get("routing", {}),
            "metrics": profile.get("metrics", {}),
        }

    def put_profile_override_sync(self, payload: dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        url = f"{self.base_url.rstrip('/')}/v1/org-learning/profile"
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.put(url, json=payload, headers=self._auth_headers())
                return response.status_code == 200
        except Exception:
            return False
