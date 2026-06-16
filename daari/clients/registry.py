from __future__ import annotations

from daari.clients.base import ClientSetupRecipe


class ClientRegistry:
    def __init__(self) -> None:
        self._recipes: dict[str, ClientSetupRecipe] = {}

    def register(self, recipe: ClientSetupRecipe) -> None:
        self._recipes[recipe.id] = recipe

    def get(self, client_id: str) -> ClientSetupRecipe | None:
        return self._recipes.get(client_id)

    def list_ids(self) -> list[str]:
        return sorted(self._recipes.keys())


def default_registry() -> ClientRegistry:
    from daari.clients.cursor.recipe import CursorSetupRecipe

    registry = ClientRegistry()
    registry.register(CursorSetupRecipe())
    return registry
