"""OpenAPI + docs pins for the /v1/images family (#1090, #1097, #1098)."""

from __future__ import annotations

from pathlib import Path

from daari.server.app import create_app

ROOT = Path(__file__).resolve().parents[2]
CLIENTS = ROOT / "docs/developer/concepts/clients-and-gateways.md"
HTTP_API = ROOT / "docs/developer/reference/http-api.md"


def test_openapi_images_routes_list_generations_edits_variations(settings):
    paths = create_app(settings).openapi()["paths"]
    images = sorted(p for p in paths if p.startswith("/v1/images"))
    assert images == [
        "/v1/images/edits",
        "/v1/images/generations",
        "/v1/images/variations",
    ]
    assert "post" in paths["/v1/images/generations"]
    assert "post" in paths["/v1/images/edits"]
    assert "post" in paths["/v1/images/variations"]


def test_clients_docs_cover_images_family() -> None:
    text = CLIENTS.read_text(encoding="utf-8")
    assert "/v1/images/generations" in text
    assert "/v1/images/edits" in text
    assert "/v1/images/variations" in text
    for line in text.splitlines():
        if "variations" in line.lower():
            assert "not supported" not in line.lower(), line


def test_http_api_lists_images_family() -> None:
    text = HTTP_API.read_text(encoding="utf-8")
    assert "/v1/images/generations" in text
    assert "/v1/images/edits" in text
    assert "/v1/images/variations" in text
