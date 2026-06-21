from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any

import httpx
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse


@dataclass
class HttpIntegrationProvider:
    id: str
    tier: str = "Lt"
    base_url: str = ""
    token_env_var: str = ""

    async def health(self) -> bool:
        return bool(os.environ.get(self.token_env_var))

    @staticmethod
    def _extract_query(request: InternalRequest) -> str | None:
        for message in reversed(request.messages):
            if message.role != "user" or not message.content:
                continue
            cleaned = re.sub(r"(?i)^@(sourcegraph|ghe)\s*", "", message.content.strip(), count=1)
            match = re.search(r"(?i)\b(query|search|find)\s*:?\s*(.+)$", message.content.strip())
            if match:
                return match.group(2).strip()
            return cleaned[:120]
        return None

    def _token_or_skip(self, request: InternalRequest) -> tuple[str | None, InternalResponse | None]:
        token = os.environ.get(self.token_env_var)
        if token:
            return token, None
        return None, InternalResponse(
            content=f"{self.id} skipped: set {self.token_env_var} to enable live integration calls.",
            model=request.model,
            daari_meta=DaariMeta(
                tier=self.tier,
                executor="integration",
                provider_id=self.id,
                task_type="tool",
                warning="token_missing",
            ),
        )

    def _failure(self, request: InternalRequest, exc: Exception) -> InternalResponse:
        return InternalResponse(
            content=f"{self.id} request failed: {exc}",
            model=request.model,
            daari_meta=DaariMeta(
                tier=self.tier,
                executor="integration",
                provider_id=self.id,
                task_type="tool",
                warning="integration_request_failed",
            ),
        )

    @staticmethod
    def _ok_response(request: InternalRequest, provider_id: str, content: str) -> InternalResponse:
        return InternalResponse(
            content=content[:4000],
            model=request.model,
            daari_meta=DaariMeta(
                tier="Lt",
                executor="integration",
                provider_id=provider_id,
                task_type="tool",
            ),
        )


class SourcegraphProvider(HttpIntegrationProvider):
    def __init__(self, base_url: str) -> None:
        super().__init__(
            id="integration:sourcegraph",
            base_url=base_url.rstrip("/"),
            token_env_var="DAARI_SOURCEGRAPH_TOKEN",
        )

    async def execute(self, request: InternalRequest) -> InternalResponse:
        token, skipped = self._token_or_skip(request)
        if skipped is not None:
            return skipped

        query = self._extract_query(request) or "type:repo count:5"
        graphql = """
        query DaariSearch($query: String!) {
          search(query: $query, version: V3) {
            results {
              resultCount
              results {
                __typename
                ... on Repository {
                  name
                  url
                }
                ... on FileMatch {
                  repository { name }
                  file { path url }
                }
              }
            }
          }
        }
        """
        payload = {"query": graphql, "variables": {"query": query}}
        headers = {"Authorization": f"token {token}"}
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
                response = await client.post("/.api/graphql", headers=headers, json=payload)
                response.raise_for_status()
            data = response.json()
            formatted = self._format_results(query, data)
            return self._ok_response(request, self.id, formatted)
        except Exception as exc:
            return self._failure(request, exc)

    @staticmethod
    def _format_results(query: str, payload: dict[str, Any]) -> str:
        results = (((payload.get("data") or {}).get("search") or {}).get("results") or {})
        count = results.get("resultCount", 0)
        items = results.get("results") or []
        lines = [f"Sourcegraph search query: {query}", f"Result count: {count}"]
        for item in items[:10]:
            kind = item.get("__typename", "Unknown")
            if kind == "Repository":
                lines.append(f"- repo: {item.get('name', '?')} ({item.get('url', '')})")
            elif kind == "FileMatch":
                repo = (item.get("repository") or {}).get("name", "?")
                file_info = item.get("file") or {}
                lines.append(f"- code: {repo}/{file_info.get('path', '?')} ({file_info.get('url', '')})")
            else:
                lines.append(f"- {kind}: {json.dumps(item)[:200]}")
        return "\n".join(lines)


class GitHubEnterpriseProvider(HttpIntegrationProvider):
    def __init__(self, base_url: str) -> None:
        super().__init__(
            id="integration:ghe",
            base_url=base_url.rstrip("/"),
            token_env_var="DAARI_GHE_TOKEN",
        )

    async def execute(self, request: InternalRequest) -> InternalResponse:
        token, skipped = self._token_or_skip(request)
        if skipped is not None:
            return skipped

        query = self._extract_query(request) or "language:python"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
                repos = await client.get("/search/repositories", headers=headers, params={"q": query, "per_page": 5})
                repos.raise_for_status()
                issues = await client.get("/search/issues", headers=headers, params={"q": query, "per_page": 5})
                issues.raise_for_status()
            formatted = self._format_results(query, repos.json(), issues.json())
            return self._ok_response(request, self.id, formatted)
        except Exception as exc:
            return self._failure(request, exc)

    @staticmethod
    def _format_results(query: str, repos: dict[str, Any], issues: dict[str, Any]) -> str:
        lines = [
            f"GHE search query: {query}",
            f"Repository matches: {repos.get('total_count', 0)}",
        ]
        for item in (repos.get("items") or [])[:5]:
            lines.append(f"- repo: {item.get('full_name', '?')} ({item.get('html_url', '')})")
        lines.append(f"Issue matches: {issues.get('total_count', 0)}")
        for item in (issues.get("items") or [])[:5]:
            lines.append(f"- issue: {item.get('title', '?')} ({item.get('html_url', '')})")
        return "\n".join(lines)
