from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IntegrationProvider(Protocol):
    id: str

    async def health(self) -> bool: ...
