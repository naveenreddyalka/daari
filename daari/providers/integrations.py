from __future__ import annotations

from dataclasses import dataclass

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse


@dataclass
class DeferredIntegrationProvider:
    id: str
    tier: str = "Lt"
    message: str = "Provider is registered but not implemented yet."

    async def health(self) -> bool:
        return False

    async def execute(self, request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content=self.message,
            model=request.model,
            daari_meta=DaariMeta(
                tier=self.tier,
                executor="integration",
                provider_id=self.id,
                task_type="tool",
                warning="provider_deferred",
            ),
        )


class SourcegraphProvider(DeferredIntegrationProvider):
    def __init__(self) -> None:
        super().__init__(
            id="integration:sourcegraph",
            message="Sourcegraph provider is scaffolded and will ship in Phase C3.",
        )


class GitHubEnterpriseProvider(DeferredIntegrationProvider):
    def __init__(self) -> None:
        super().__init__(
            id="integration:ghe",
            message="GitHub Enterprise provider is scaffolded and will ship in Phase C3.",
        )
