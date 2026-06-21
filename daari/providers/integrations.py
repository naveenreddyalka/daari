from __future__ import annotations

from dataclasses import dataclass
import re

import httpx
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse


@dataclass
class HttpIntegrationProvider:
    id: str
    tier: str = "Lt"
    base_url: str = ""
    token_env_var: str = ""
    default_path: str = "/"

    async def health(self) -> bool:
        return bool(__import__("os").environ.get(self.token_env_var))

    async def execute(self, request: InternalRequest) -> InternalResponse:
        token = __import__("os").environ.get(self.token_env_var)
        if not token:
            return InternalResponse(
                content=(
                    f"{self.id} skipped: set {self.token_env_var} to enable "
                    "live integration calls."
                ),
                model=request.model,
                daari_meta=DaariMeta(
                    tier=self.tier,
                    executor="integration",
                    provider_id=self.id,
                    task_type="tool",
                    warning="token_missing",
                ),
            )

        query = self._extract_query(request)
        path = self.default_path
        if query:
            delimiter = "&" if "?" in path else "?"
            path = f"{path}{delimiter}q={httpx.QueryParams({'q': query})['q']}"

        headers = {"Authorization": f"token {token}"}
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=8.0) as client:
                response = await client.get(path, headers=headers)
                response.raise_for_status()
            body = response.text[:1200]
        except Exception as exc:
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

        return InternalResponse(
            content=body,
            model=request.model,
            daari_meta=DaariMeta(
                tier=self.tier,
                executor="integration",
                provider_id=self.id,
                task_type="tool",
            ),
        )

    @staticmethod
    def _extract_query(request: InternalRequest) -> str | None:
        for message in reversed(request.messages):
            if message.role != "user" or not message.content:
                continue
            match = re.search(r"(?i)\b(query|search|find)\s*:?\s*(.+)$", message.content.strip())
            if match:
                return match.group(2).strip()
            return message.content.strip()[:120]
        return None


class SourcegraphProvider(HttpIntegrationProvider):
    def __init__(self) -> None:
        super().__init__(
            id="integration:sourcegraph",
            base_url="https://sourcegraph.com",
            token_env_var="DAARI_SOURCEGRAPH_TOKEN",
            default_path="/.api/graphql",
        )


class GitHubEnterpriseProvider(HttpIntegrationProvider):
    def __init__(self) -> None:
        super().__init__(
            id="integration:ghe",
            base_url="https://api.github.com",
            token_env_var="DAARI_GHE_TOKEN",
            default_path="/user",
        )
