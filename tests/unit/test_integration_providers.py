from __future__ import annotations

import httpx
import pytest

from daari.gateway.internal import InternalRequest, Message
from daari.providers.integrations import GitHubEnterpriseProvider, SourcegraphProvider


def _request(prompt: str = "search auth") -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=prompt)], model="llama3.2:3b")


@pytest.mark.asyncio
async def test_sourcegraph_provider_graphql_query(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/.api/graphql"
        assert request.headers.get("authorization") == "token sg-token"
        body = __import__("json").loads(request.content.decode("utf-8"))
        assert "search(query: $query" in body["query"]
        assert body["variables"]["query"] == "repo:daari auth"
        return httpx.Response(
            200,
            json={
                "data": {
                    "search": {
                        "results": {
                            "resultCount": 2,
                            "results": [
                                {"__typename": "Repository", "name": "acme/daari", "url": "https://sg/acme/daari"},
                                {
                                    "__typename": "FileMatch",
                                    "repository": {"name": "acme/daari"},
                                    "file": {"path": "router.py", "url": "https://sg/acme/daari/-/blob/router.py"},
                                },
                            ],
                        }
                    }
                }
            },
        )

    transport = httpx.MockTransport(handler)

    class TestProvider(SourcegraphProvider):
        async def execute(self, request):  # type: ignore[override]
            token, skipped = self._token_or_skip(request)
            if skipped:
                return skipped
            payload = {"query": "query DaariSearch($query: String!) { search(query: $query, version: V3) { results { resultCount results { __typename } } } }", "variables": {"query": self._extract_query(request) or ""}}
            async with httpx.AsyncClient(base_url=self.base_url, transport=transport, timeout=10.0) as client:
                response = await client.post("/.api/graphql", headers={"Authorization": f"token {token}"}, json=payload)
                response.raise_for_status()
            return self._ok_response(request, self.id, self._format_results(payload["variables"]["query"], response.json()))

    monkeypatch.setenv("DAARI_SOURCEGRAPH_TOKEN", "sg-token")
    provider = TestProvider(base_url="https://sourcegraph.example.com")
    response = await provider.execute(_request("@sourcegraph query: repo:daari auth"))
    assert response.daari_meta.provider_id == "integration:sourcegraph"
    assert "Result count: 2" in response.content


@pytest.mark.asyncio
async def test_ghe_provider_searches_repos_and_issues(monkeypatch):
    seen_paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        assert request.headers.get("authorization") == "Bearer ghe-token"
        if request.url.path == "/search/repositories":
            return httpx.Response(200, json={"total_count": 1, "items": [{"full_name": "acme/daari", "html_url": "https://ghe/acme/daari"}]})
        return httpx.Response(200, json={"total_count": 1, "items": [{"title": "Fix router", "html_url": "https://ghe/acme/daari/issues/1"}]})

    transport = httpx.MockTransport(handler)

    class TestProvider(GitHubEnterpriseProvider):
        async def execute(self, request):  # type: ignore[override]
            token, skipped = self._token_or_skip(request)
            if skipped:
                return skipped
            query = self._extract_query(request) or ""
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
            async with httpx.AsyncClient(base_url=self.base_url, transport=transport, timeout=10.0) as client:
                repos = await client.get("/search/repositories", headers=headers, params={"q": query, "per_page": 5})
                repos.raise_for_status()
                issues = await client.get("/search/issues", headers=headers, params={"q": query, "per_page": 5})
                issues.raise_for_status()
            return self._ok_response(request, self.id, self._format_results(query, repos.json(), issues.json()))

    monkeypatch.setenv("DAARI_GHE_TOKEN", "ghe-token")
    provider = TestProvider(base_url="https://ghe.example.com/api/v3")
    response = await provider.execute(_request("@ghe search: daari router"))
    assert seen_paths == ["/api/v3/search/repositories", "/api/v3/search/issues"]
    assert "Repository matches: 1" in response.content
    assert "Issue matches: 1" in response.content
