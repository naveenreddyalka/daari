"""Doctor probes the live embed endpoint when L1 is on (#764)."""

from __future__ import annotations

import httpx

from daari.setup.doctor import _check_embedding_endpoint, _check_ollama


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_l1_disabled_skips_probe(settings):
    settings.cache.l1.enabled = False

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"must not probe when L1 is off: {request.url}")

    result = _check_embedding_endpoint(settings, _client(handler))
    assert result.ok
    assert result.optional
    assert "skipped" in result.detail


def test_probe_ok_posts_embeddings(settings):
    settings.cache.l1.enabled = True
    settings.ollama.base_url = "http://ollama.local:11434/"
    settings.cache.l1.embedding_model = "nomic-embed-text"
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"embedding": [0.1, 0.2]})

    result = _check_embedding_endpoint(settings, _client(handler))
    assert result.ok
    assert not result.optional
    assert "http://ollama.local:11434/api/embeddings" in result.detail
    assert len(seen) == 1
    assert seen[0].method == "POST"
    assert str(seen[0].url) == "http://ollama.local:11434/api/embeddings"
    body = seen[0].content
    assert b"nomic-embed-text" in body
    assert b'"prompt":"ok"' in body or b'"prompt": "ok"' in body


def test_probe_http_500_is_not_ok(settings):
    settings.cache.l1.enabled = True
    settings.ollama.base_url = "http://ollama.local:11434"
    result = _check_embedding_endpoint(settings, _client(lambda request: httpx.Response(500)))
    assert not result.ok
    assert "http://ollama.local:11434/api/embeddings" in result.detail
    assert "500" in result.detail


def test_probe_without_vector_is_not_ok(settings):
    settings.cache.l1.enabled = True
    settings.ollama.base_url = "http://ollama.local:11434"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embedding": []})

    result = _check_embedding_endpoint(settings, _client(handler))
    assert not result.ok
    assert "http://ollama.local:11434/api/embeddings" in result.detail
    assert "no vector" in result.detail


def test_tags_check_still_reports_embedding_model(settings):
    settings.cache.l1.enabled = True
    settings.cache.l1.embedding_model = "nomic-embed-text"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "nomic-embed-text"}]})

    rows = _check_ollama(settings, _client(handler))
    embed = next(row for row in rows if row.name == "embedding_model")
    assert embed.ok
    assert "found" in embed.detail
    assert embed.optional is False
