"""Local :floor / :nitro model suffixes (G3 / #225)."""

from __future__ import annotations

from typing import Literal


def local_model_alias(model: str) -> Literal["floor", "nitro"] | None:
    name = (model or "").rsplit("/", 1)[-1].lower()
    if name.endswith(":floor") or name == "floor":
        return "floor"
    if name.endswith(":nitro") or name == "nitro":
        return "nitro"
    return None
