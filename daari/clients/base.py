from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class SetupChange:
    """A planned change from a setup recipe dry-run."""

    path: str
    action: str
    detail: str


@dataclass
class SetupPlan:
    """Result of detect + dry-run for a client setup recipe."""

    client_id: str
    detected: bool
    settings_paths: list[str] = field(default_factory=list)
    changes: list[SetupChange] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@runtime_checkable
class ClientSetupRecipe(Protocol):
    id: str

    def detect(self) -> bool: ...

    def settings_paths(self) -> list[str]: ...

    def dry_run(self, *, base_url: str, api_key: str, model_name: str) -> SetupPlan: ...
