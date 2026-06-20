from __future__ import annotations

from typing import Protocol, runtime_checkable

from daari.gateway.internal import InternalRequest, InternalResponse


@runtime_checkable
class IntegrationProvider(Protocol):
    id: str
    tier: str

    async def health(self) -> bool: ...

    async def execute(self, request: InternalRequest) -> InternalResponse: ...
