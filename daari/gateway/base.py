from __future__ import annotations

from typing import Protocol, runtime_checkable

from fastapi import APIRouter


@runtime_checkable
class GatewayAdapter(Protocol):
    """Pluggable wire-format adapter mounted as FastAPI routes."""

    id: str

    def router(self) -> APIRouter: ...
