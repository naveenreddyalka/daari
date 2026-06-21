from __future__ import annotations

import json

import httpx
import pytest

from daari.enterprise.client import OrgCacheClient
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
