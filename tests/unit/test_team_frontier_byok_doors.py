"""Team/key BYOK signs modality + passthrough L6 doors (#2313).

Images (generations/edits/variations), ASR frontier fallback, OCR, moderations,
rerank, and decisions must resolve their upstream credential through the same
binding chat uses: bound key replaces slot rotation, pool pin filters to the
named slot, unknown pin / unresolvable ref fail closed with 502.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import FrontierProviderConfig
from daari.gateway.l6_passthrough import (
    FrontierBinding,
    FrontierBindingError,
    frontier_binding_from_request,
    resolve_l6_targets,
)
from daari.router.router import AppContext
from daari.security.secret_refs import SecretRefError
from daari.server.app import create_app

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
_AUDIO = b"RIFF"
_DOC = {"type": "image_url", "image_url": "data:image/png;base64,iVBORw0KGgo="}

_OK = {
    "moderations": {
        "id": "modr-1",
        "model": "omni-moderation-latest",
        "results": [{"flagged": False, "categories": {}, "category_scores": {}}],
    },
    "rerank": {"id": "rr-1", "results": [{"index": 0, "relevance_score": 0.9}]},
    "images": {"created": 1, "data": [{"url": "https://cdn.example/x.png"}]},
    "ocr": {
        "object": "ocr",
        "model": "mistral-ocr-latest",
        "pages": [{"index": 0, "markdown": "hi", "dimensions": {}, "images": []}],
        "usage_info": {"pages_processed": 1},
    },
    "transcriptions": {"text": "hello"},
    "decisions": {
        "id": "dec_1",
        "model": "gpt-6-luna",
        "answers": [
            {
                "type": "choice",
                "name": "department",
                "choice": "billing",
                "probabilities": [{"value": "billing", "probability": 0.95}],
                "confidence": 0.93,
            }
        ],
    },
}

_DECISIONS_BODY = {
    "model": "gpt-6-luna",
    "input": "I was charged twice.",
    "questions": [
        {
            "type": "choice",
            "name": "department",
            "instructions": "Which department?",
            "choices": [
                {"value": "billing", "description": "Payments"},
                {"value": "other", "description": "Else"},
            ],
        }
    ],
}

# (door, gateway module, upstream response key)
DOORS = [
    ("moderations", "moderations", "moderations"),
    ("rerank", "rerank", "rerank"),
    ("images_generations", "images", "images"),
    ("images_edits", "images", "images"),
    ("images_variations", "images", "images"),
    ("ocr", "ocr", "ocr"),
    ("transcriptions", "transcriptions", "transcriptions"),
    ("decisions", "decisions", "decisions"),
]


async def _call(client: AsyncClient, door: str, headers: dict[str, str]) -> httpx.Response:
    if door == "moderations":
        return await client.post("/v1/moderations", json={"input": "hello"}, headers=headers)
    if door == "rerank":
        return await client.post(
            "/v1/rerank",
            json={"query": "q", "documents": ["a", "b"], "model": "rerank-english-v3.0"},
            headers=headers,
        )
    if door == "images_generations":
        return await client.post(
            "/v1/images/generations", json={"prompt": "a cat"}, headers=headers
        )
    if door == "images_edits":
        return await client.post(
            "/v1/images/edits",
            data={"prompt": "make it blue", "model": "dall-e-2"},
            files={"image": ("src.png", _PNG, "image/png")},
            headers=headers,
        )
    if door == "images_variations":
        return await client.post(
            "/v1/images/variations",
            data={"model": "dall-e-2", "n": "1"},
            files={"image": ("src.png", _PNG, "image/png")},
            headers=headers,
        )
    if door == "ocr":
        return await client.post(
            "/v1/ocr",
            json={"model": "mistral-ocr-latest", "document": _DOC},
            headers=headers,
        )
    if door == "transcriptions":
        return await client.post(
            "/v1/audio/transcriptions",
            files={"file": ("note.wav", _AUDIO, "audio/wav")},
            data={"model": "whisper-1", "response_format": "json"},
            headers=headers,
        )
    if door == "decisions":
        # Decisions caches by input; vary it per caller so each call reaches upstream.
        body = {**_DECISIONS_BODY, "input": f"{_DECISIONS_BODY['input']} {headers}"}
        return await client.post("/v1/decisions", json=body, headers=headers)
    raise AssertionError(door)


def _patch_upstream(monkeypatch, module_name: str, handler):
    import importlib

    module = importlib.import_module(f"daari.gateway.{module_name}")
    module._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr(f"daari.gateway.{module_name}.httpx.AsyncClient", Patched)


def _configure(settings, tmp_path):
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="primary",
            base_url="https://primary.example/v1",
            model="gpt-4o",
            keys=["sk-global"],
        ),
        FrontierProviderConfig(
            id="openai-byok",
            base_url="https://byok.example/v1",
            model="gpt-4o",
            keys=["sk-slot-byok"],
        ),
    ]
    settings.asr.base_url = ""
    settings.asr.frontier_fallback = True
    settings.ocr.base_url = ""
    settings.ocr.vision_model = ""
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    return app, store


def _seen_handler(seen: list[httpx.Request], payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    return handler


@pytest.mark.asyncio
@pytest.mark.parametrize("door,module,ok_key", DOORS)
async def test_bound_key_signs_modality_upstream(
    settings, tmp_path, monkeypatch, door, module, ok_key
):
    seen: list[httpx.Request] = []
    _patch_upstream(monkeypatch, module, _seen_handler(seen, _OK[ok_key]))
    app, store = _configure(settings, tmp_path)
    bound = store.create("alice", frontier_api_key="sk-team-byok")
    unbound = store.create("bob")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _call(client, door, {"Authorization": f"Bearer {bound.plaintext}"})
        assert response.status_code == 200, response.text
        assert seen[-1].headers["authorization"] == "Bearer sk-team-byok"
        assert seen[-1].url.host == "primary.example"

        response = await _call(client, door, {"Authorization": f"Bearer {unbound.plaintext}"})
        assert response.status_code == 200, response.text
        assert seen[-1].headers["authorization"] == "Bearer sk-global"
        assert seen[-1].url.host == "primary.example"


@pytest.mark.asyncio
@pytest.mark.parametrize("door,module,ok_key", DOORS)
async def test_team_pool_pin_filters_to_named_slot(
    settings, tmp_path, monkeypatch, door, module, ok_key
):
    seen: list[httpx.Request] = []
    _patch_upstream(monkeypatch, module, _seen_handler(seen, _OK[ok_key]))
    app, store = _configure(settings, tmp_path)
    store.create_team("eng", frontier_pool="openai-byok")
    member = store.create("alice", team="eng")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _call(client, door, {"Authorization": f"Bearer {member.plaintext}"})
    assert response.status_code == 200, response.text
    assert len(seen) == 1
    assert seen[0].url.host == "byok.example"
    assert seen[0].headers["authorization"] == "Bearer sk-slot-byok"


@pytest.mark.asyncio
@pytest.mark.parametrize("door,module,ok_key", DOORS)
async def test_unknown_pool_pin_fails_closed_502(
    settings, tmp_path, monkeypatch, door, module, ok_key
):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"must not call {request.url}")

    _patch_upstream(monkeypatch, module, handler)
    app, store = _configure(settings, tmp_path)
    pinned = store.create("alice", frontier_pool="missing-slot")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _call(client, door, {"Authorization": f"Bearer {pinned.plaintext}"})
    assert response.status_code == 502, response.text
    body = response.json()
    assert body["error"]["type"] == "frontier_binding_error"
    assert "missing-slot" in body["error"]["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("door,module,ok_key", DOORS)
async def test_unresolvable_bound_key_fails_closed_502(
    settings, tmp_path, monkeypatch, door, module, ok_key
):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"must not call {request.url}")

    def boom(_ref):
        raise SecretRefError("gone")

    _patch_upstream(monkeypatch, module, handler)
    monkeypatch.setattr("daari.auth.frontier_binding.resolve_secret_ref", boom)
    app, store = _configure(settings, tmp_path)
    bound = store.create("alice", frontier_api_key="secret://env-file/x.env#K")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _call(client, door, {"Authorization": f"Bearer {bound.plaintext}"})
    assert response.status_code == 502, response.text
    assert response.json()["error"]["type"] == "frontier_binding_error"
    assert "secret://" not in response.text


def test_resolve_l6_targets_binding_semantics(settings, monkeypatch):
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="primary", base_url="https://p.example/v1", model="m", keys=["sk-p"]
        ),
        FrontierProviderConfig(
            id="openai-byok", base_url="https://b.example/v1", model="m", keys=["sk-b"]
        ),
    ]
    def shape(targets):
        return [(t.slot_id, t.api_key, t.base_url) for t in targets]

    unbound = resolve_l6_targets(settings, region_pin=None, default_model="m")
    assert shape(unbound) == [
        ("primary", "sk-p", "https://p.example/v1"),
        ("openai-byok", "sk-b", "https://b.example/v1"),
    ]

    explicit_none = resolve_l6_targets(
        settings, region_pin=None, default_model="m", binding=FrontierBinding()
    )
    assert shape(explicit_none) == shape(unbound)

    keyed = resolve_l6_targets(
        settings,
        region_pin=None,
        default_model="m",
        binding=FrontierBinding(api_key="sk-team"),
    )
    assert [t.api_key for t in keyed] == ["sk-team", "sk-team"]

    pinned = resolve_l6_targets(
        settings,
        region_pin=None,
        default_model="m",
        binding=FrontierBinding(pool="openai-byok"),
    )
    assert [(t.slot_id, t.api_key) for t in pinned] == [("openai-byok", "sk-b")]

    with pytest.raises(FrontierBindingError, match="missing-slot"):
        resolve_l6_targets(
            settings,
            region_pin=None,
            default_model="m",
            binding=FrontierBinding(pool="missing-slot"),
        )


def test_frontier_binding_from_request_key_wins_over_team():
    class _VK:
        frontier_api_key = "sk-key"
        frontier_pool = None

    class _Claims:
        kind = "virtual"
        virtual_key = _VK()
        team_frontier_api_key = "sk-team"
        team_frontier_pool = "openai-byok"

    class _State:
        auth_claims = _Claims()

    class _Request:
        state = _State()

    binding = frontier_binding_from_request(_Request())
    assert binding == FrontierBinding(api_key="sk-key", pool="openai-byok")

    class _Anon:
        state = type("S", (), {})()

    assert not frontier_binding_from_request(_Anon())
