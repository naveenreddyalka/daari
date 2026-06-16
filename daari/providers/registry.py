from __future__ import annotations

from daari.providers.base import IntegrationProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, IntegrationProvider] = {}

    def register(self, provider: IntegrationProvider) -> None:
        self._providers[provider.id] = provider

    def get(self, provider_id: str) -> IntegrationProvider | None:
        return self._providers.get(provider_id)

    def list_ids(self) -> list[str]:
        return sorted(self._providers.keys())
