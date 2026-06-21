from __future__ import annotations

import json

import httpx
import pytest

from daari.enterprise.client import OrgCacheClient, OrgLearningClient, OrgLearningFeedback
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message


def _sample_request() -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="hello")],
        model="llama3.2:3b",
    )


def _sample_response() -> InternalResponse:
    return InternalResponse(
        content="cached",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
    )


@pytest.mark.asyncio
async def test_org_cache_client_l0_roundtrip():
    store: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/org-cache/put":
            body = json.loads(request.content.decode("utf-8"))
            store[f"{body['tier']}:{body['key']}"] = body["value"]
            return httpx.Response(200, json={"ok": True})
        if request.url.path == "/v1/org-cache/get":
            key = request.url.params["key"]
            tier = request.url.params["tier"]
            value = store.get(f"{tier}:{key}")
            if value is None:
                return httpx.Response(200, json={"hit": False, "key": key, "tier": tier})
            return httpx.Response(200, json={"hit": True, "key": key, "tier": tier, "value": value})
        if request.url.path == "/v1/org-cache/stats":
            return httpx.Response(200, json={"entries": len(store)})
        return httpx.Response(404)

    client = OrgCacheClient(
        base_url="http://org-cache.test",
        transport=httpx.MockTransport(handler),
    )
    request = _sample_request()
    response = _sample_response()
    await client.put_l0(request, response)
    hit = await client.get_l0(request)
    assert hit is not None
    assert hit.content == "cached"
    stats = await client.stats()
    assert stats is not None
    assert stats["entries"] == 1


@pytest.mark.asyncio
async def test_org_cache_client_sends_bearer_token():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization") != "Bearer test-token":
            return httpx.Response(401, json={"detail": "bad token"})
        return httpx.Response(200, json={"entries": 0})

    client = OrgCacheClient(
        base_url="http://org-cache.test",
        token="test-token",
        transport=httpx.MockTransport(handler),
    )
    stats = await client.stats()
    assert stats is not None
    assert stats["entries"] == 0


@pytest.mark.asyncio
async def test_org_cache_client_retries_on_transient_failure():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ConnectError("temporary network issue", request=request)
        return httpx.Response(200, json={"entries": 0})

    client = OrgCacheClient(
        base_url="http://org-cache.test",
        transport=httpx.MockTransport(handler),
        max_retries=2,
        backoff_seconds=0.0,
    )
    stats = await client.stats()
    assert stats is not None
    assert stats["entries"] == 0
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_org_learning_client_feedback_and_profile():
    seen_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/org-learning/feedback":
            body = json.loads(request.content.decode("utf-8"))
            seen_payloads.append(body)
            return httpx.Response(200, json={"ok": True})
        if request.url.path == "/v1/org-learning/profile":
            return httpx.Response(
                200,
                json={
                    "org_id": "acme",
                    "routing": {"prefer": "latency", "confidence_threshold": 0.75},
                    "metrics": {"feedback_count": 1},
                },
            )
        return httpx.Response(404)

    client = OrgLearningClient(
        base_url="http://org-learning.test",
        token="t",
        transport=httpx.MockTransport(handler),
    )
    await client.post_feedback(
        OrgLearningFeedback(tier="L3", cache_hit=False, latency_ms=320, rating=1, task_class="test")
    )
    profile = await client.get_profile()
    assert profile is not None
    assert profile["routing"]["prefer"] == "latency"
    assert seen_payloads[0]["task_class"] == "test"
