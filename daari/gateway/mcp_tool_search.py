"""Semantic MCP tool search — rank large catalogs with local embeddings (#376).

Default off. When enabled and the catalog exceeds `min_catalog_size`, tools are
ranked by cosine similarity between (name + description) and a query string,
returning the top_k. Governance filters first; embed failures degrade to the
unranked catalog with `mcp_tool_search_degraded`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

from daari.cache.semantic import cosine_similarity
from daari.gateway.mcp_policy import McpToolPolicy


class EmbedderLike(Protocol):
    async def embed(self, text: str, *, model: str | None = None) -> list[float] | None: ...


@dataclass
class ToolSearchSettings:
    enabled: bool = False
    min_catalog_size: int = 40
    top_k: int = 40


@dataclass
class ToolEmbeddingCache:
    """In-process cache keyed by (server, tool name, description hash)."""

    _data: dict[tuple[str, str, str], list[float]] = field(default_factory=dict)

    def get(self, server_id: str, name: str, desc_hash: str) -> list[float] | None:
        hit = self._data.get((server_id, name, desc_hash))
        return list(hit) if hit is not None else None

    def put(self, server_id: str, name: str, desc_hash: str, vector: list[float]) -> None:
        self._data[(server_id, name, desc_hash)] = list(vector)


def tool_document(tool: dict[str, Any]) -> str:
    name = str(tool.get("name") or "").strip()
    description = str(tool.get("description") or "").strip()
    if description:
        return f"{name}\n{description}"
    return name


def description_hash(tool: dict[str, Any]) -> str:
    return hashlib.sha256(tool_document(tool).encode("utf-8")).hexdigest()


def extract_list_query(
    *,
    arg_text: str = "",
    messages: list[Any] | None = None,
) -> str:
    """Heuristic query for ranking at tools/list time.

    Prefer explicit trailing text after `@mcp … tools/list` (arg_text). Else the
    most recent user/tool message content (excluding bare @mcp list commands).
    Empty query → caller should skip ranking.
    """
    if arg_text and arg_text.strip():
        return arg_text.strip()
    if not messages:
        return ""
    for message in reversed(messages):
        role = getattr(message, "role", None) or (
            message.get("role") if isinstance(message, dict) else None
        )
        if role not in {"user", "tool"}:
            continue
        content = getattr(message, "content", None)
        if content is None and isinstance(message, dict):
            content = message.get("content")
        text = (content or "").strip()
        if not text:
            continue
        lowered = text.lower()
        # Skip the list command itself when it has no trailing query.
        if lowered.startswith("@mcp") and (
            "tools/list" in lowered or lowered.rstrip().endswith(" list")
        ):
            # Prefer trailing text after the list token when present.
            for token in ("tools/list", " list"):
                idx = lowered.rfind(token)
                if idx >= 0:
                    tail = text[idx + len(token) :].strip()
                    if tail:
                        return tail
            continue
        return text
    return ""


def apply_governance(
    tools: list[dict[str, Any]], policy: McpToolPolicy | None
) -> list[dict[str, Any]]:
    if policy is None:
        return list(tools)
    return [tool for tool in tools if policy.allows(str(tool.get("name") or ""))]


async def maybe_rank_tools(
    tools: list[dict[str, Any]],
    *,
    query: str,
    settings: ToolSearchSettings | Any | None,
    policy: McpToolPolicy | None = None,
    embedder: EmbedderLike | None = None,
    server_id: str = "",
    cache: ToolEmbeddingCache | None = None,
) -> list[dict[str, Any]]:
    """Governance → optional embedding rank. Never raises to the caller."""
    filtered = apply_governance(tools, policy)
    enabled = bool(getattr(settings, "enabled", False)) if settings is not None else False
    min_size = int(getattr(settings, "min_catalog_size", 40) or 40) if settings else 40
    top_k = int(getattr(settings, "top_k", 40) or 40) if settings else 40
    if not enabled or len(filtered) <= min_size:
        return filtered
    if not query.strip() or embedder is None:
        _log_degraded(server_id, reason="missing_query_or_embedder")
        return filtered
    try:
        ranked = await _rank(
            filtered,
            query=query.strip(),
            embedder=embedder,
            top_k=max(1, top_k),
            server_id=server_id,
            cache=cache or ToolEmbeddingCache(),
        )
        return ranked
    except Exception as exc:  # noqa: BLE001
        _log_degraded(server_id, reason=type(exc).__name__, detail=str(exc)[:200])
        return filtered


async def _rank(
    tools: list[dict[str, Any]],
    *,
    query: str,
    embedder: EmbedderLike,
    top_k: int,
    server_id: str,
    cache: ToolEmbeddingCache,
) -> list[dict[str, Any]]:
    query_vec = await embedder.embed(query)
    if query_vec is None:
        raise RuntimeError("query_embed_failed")
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for index, tool in enumerate(tools):
        name = str(tool.get("name") or "")
        desc_h = description_hash(tool)
        vector = cache.get(server_id, name, desc_h)
        if vector is None:
            vector = await embedder.embed(tool_document(tool))
            if vector is None:
                raise RuntimeError("tool_embed_failed")
            cache.put(server_id, name, desc_h, vector)
        score = cosine_similarity(query_vec, vector)
        scored.append((score, index, tool))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [tool for _score, _index, tool in scored[:top_k]]


def _log_degraded(server_id: str, *, reason: str, detail: str = "") -> None:
    from daari.gateway.request_log import log_gateway_event

    log_gateway_event(
        "mcp_tool_search_degraded",
        {"server_id": server_id, "reason": reason, "detail": detail},
    )


def settings_from_block(block: Any | None) -> ToolSearchSettings:
    if block is None:
        return ToolSearchSettings()
    return ToolSearchSettings(
        enabled=bool(getattr(block, "enabled", False)),
        min_catalog_size=int(getattr(block, "min_catalog_size", 40) or 40),
        top_k=int(getattr(block, "top_k", 40) or 40),
    )
