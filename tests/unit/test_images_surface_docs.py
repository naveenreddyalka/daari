"""OpenAPI + docs pins for the /v1/images family (#1090, #1097)."""

from __future__ import annotations

from pathlib import Path

from daari.server.app import create_app

ROOT = Path(__file__).resolve().parents[2]
CLIENTS = ROOT / "docs/developer/concepts/clients-and-gateways.md"
HTTP_API = ROOT / "docs/developer/reference/http-api.md"


def test_openapi_images_routes_list_generations_and_edits(settings):
    paths = create_app(settings).openapi()["paths"]
    images = sorted(p for p in paths if p.startswith("/v1/images"))
    assert images == ["/v1/images/edits", "/v1/images/generations"]
    assert "post" in paths["/v1/images/generations"]
    assert "post" in paths["/v1/images/edits"]
    assert "/v1/images/variations" not in paths


def test_clients_docs_state_variations_not_supported() -> None:
    text = CLIENTS.read_text(encoding="utf-8")
    assert "/v1/images/generations" in text
    assert "/v1/images/edits" in text
    assert "variations" in text.lower()
    assert "not supported" in text.lower()


def test_http_api_lists_generations_only() -> None:
    text = HTTP_API.read_text(encoding="utf-8")
    assert "/v1/images/generations" in text
    # http-api.md is generated from OpenAPI — edits appear once regenerator runs;
    # pin that variations stay absent from hand-maintained prose elsewhere.
    assert "/v1/images/variations" not in text
