"""Convert InternalRequest to Anthropic's /v1/messages shape (issue #166)."""

from __future__ import annotations

import json
from typing import Any

from daari.gateway.internal import InternalRequest, Message
from daari.observability.trace import add_step

ANTHROPIC_VERSION = "2023-06-01"
# API version that rejects temperature / top_p / top_k (HTTP 400) (#1849).
ANTHROPIC_VERSION_NO_SAMPLING = "2026-10-21"
_ANTHROPIC_SAMPLING_KEYS = ("temperature", "top_p", "top_k")
DEFAULT_MAX_TOKENS = 4096
EFFORT_BETA = "effort-2025-11-24"


def effective_anthropic_version(version: str | None) -> str:
    """Client header when set; otherwise the outbound default."""
    return (version or "").strip() or ANTHROPIC_VERSION


def apply_anthropic_version_sampling_compat(
    payload: dict[str, Any], version: str | None
) -> list[str]:
    """Omit sampling knobs removed under anthropic-version 2026-10-21 (#1849).

    Mutates ``payload`` in place. Returns the names that were dropped.
    """
    if effective_anthropic_version(version) != ANTHROPIC_VERSION_NO_SAMPLING:
        return []
    dropped: list[str] = []
    for name in _ANTHROPIC_SAMPLING_KEYS:
        if name not in payload:
            continue
        del payload[name]
        dropped.append(name)
    return dropped


def apply_anthropic_version_content_compat(
    payload: dict[str, Any], version: str | None
) -> list[str]:
    """Strip assistant ``document`` blocks and user ``citations`` under 2026-10-21 (#1891).

    Mutates ``payload`` in place. Returns soft_warning kinds that fired
    (``anthropic_document_stripped`` / ``anthropic_citations_stripped``).
    Nested documents inside tool/web-fetch results are kept. Document
    ``citations: {enabled: true}`` and assistant-message citations stay.
    """
    if effective_anthropic_version(version) != ANTHROPIC_VERSION_NO_SAMPLING:
        return []
    stripped_docs = False
    stripped_citations = False
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if not isinstance(content, list):
            continue
        if role == "assistant":
            kept: list[Any] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "document":
                    stripped_docs = True
                    continue
                kept.append(block)
            message["content"] = kept
        elif role == "user":
            if _strip_user_text_citations(content):
                stripped_citations = True
    kinds: list[str] = []
    if stripped_docs:
        kinds.append("anthropic_document_stripped")
    if stripped_citations:
        kinds.append("anthropic_citations_stripped")
    return kinds


def _strip_user_text_citations(blocks: list[Any]) -> bool:
    """Remove non-empty citations arrays on user text / search_result text."""
    changed = False
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            citations = block.get("citations")
            if isinstance(citations, list) and citations:
                del block["citations"]
                changed = True
        elif block_type == "search_result":
            nested = block.get("content")
            if isinstance(nested, list) and _strip_user_text_citations(nested):
                changed = True
    return changed


def infer_frontier_kind(provider: str, base_url: str = "") -> str:
    if (provider or "").lower() in {"anthropic", "claude"}:
        return "anthropic"
    if "anthropic.com" in (base_url or "").lower():
        return "anthropic"
    return "openai"


def anthropic_messages_path(base_url: str) -> str:
    stripped = (base_url or "").rstrip("/")
    if stripped.endswith("/v1"):
        return "/messages"
    return "/v1/messages"


def anthropic_headers(
    api_key: str,
    *,
    anthropic_beta: str | None = None,
    anthropic_version: str | None = None,
    anthropic_user_profile_id: str | None = None,
) -> dict[str, str]:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": (anthropic_version or "").strip() or ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    beta = (anthropic_beta or "").strip()
    if beta:
        headers["anthropic-beta"] = beta
    profile = (anthropic_user_profile_id or "").strip()
    if profile:
        headers["anthropic-user-profile-id"] = profile
    return headers


def apply_anthropic_user_profile(
    meta: Any,
    *,
    client_header: str | None = None,
    user_profiles: dict[str, str] | None = None,
) -> None:
    """Resolve anthropic-user-profile-id onto RequestMeta (#1844).

    Client header wins. Otherwise the first match among user / key_id /
    team_id / client_id in ``user_profiles`` is injected.
    """
    client = (client_header or "").strip() or None
    if client:
        meta.anthropic_user_profile_id = client
        return
    if (getattr(meta, "anthropic_user_profile_id", None) or "").strip():
        return
    profiles = user_profiles or {}
    if not profiles:
        return
    for attr in ("user", "key_id", "team_id", "client_id"):
        key = (getattr(meta, attr, None) or "").strip()
        if not key:
            continue
        mapped = (profiles.get(key) or "").strip()
        if mapped:
            meta.anthropic_user_profile_id = mapped
            return


def anthropic_headers_for_request(
    api_key: str,
    request: InternalRequest,
    *,
    model: str | None = None,
) -> dict[str, str]:
    """Build L6 Anthropic headers, forwarding client beta/version when set (#455).

    When ``output_config`` is present and the L6 model is Opus 4.5, inject
    ``effort-2025-11-24`` if the client did not already send it (#1230).
    Opus 4.6+ does not need the beta. Forwards ``anthropic-user-profile-id`` (#1844).
    """
    meta = request.meta
    beta = (meta.anthropic_beta or "").strip() or None
    effective_model = (model or request.model or "").strip()
    if request.sampling.output_config and _opus_45_needs_effort_beta(effective_model):
        beta = _merge_anthropic_beta(beta, EFFORT_BETA)
    return anthropic_headers(
        api_key,
        anthropic_beta=beta,
        anthropic_version=meta.anthropic_version,
        anthropic_user_profile_id=getattr(meta, "anthropic_user_profile_id", None),
    )


def _opus_45_needs_effort_beta(model: str) -> bool:
    """True for Opus 4.5 family models that still require the effort beta."""
    lowered = (model or "").lower().replace("_", "-")
    if "opus" not in lowered:
        return False
    # 4.6+ ships effort without the beta.
    if "opus-4-6" in lowered or "opus-4.6" in lowered:
        return False
    if "opus-4-5" in lowered or "opus-4.5" in lowered:
        return True
    return False


def _merge_anthropic_beta(existing: str | None, feature: str) -> str:
    parts = [p.strip() for p in (existing or "").split(",") if p.strip()]
    if feature not in parts:
        parts.append(feature)
    return ",".join(parts)


def openai_tools_to_anthropic(tools: list[Any] | None) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function") if tool.get("type") == "function" else tool
        if not isinstance(function, dict) or not function.get("name"):
            continue
        entry: dict[str, Any] = {
            "name": function["name"],
            "description": function.get("description") or "",
            "input_schema": function.get("parameters") or {"type": "object", "properties": {}},
        }
        cache_control = tool.get("cache_control") or function.get("cache_control")
        if isinstance(cache_control, dict):
            entry["cache_control"] = dict(cache_control)
        converted.append(entry)
    return converted


def request_cache_ttl(request: InternalRequest) -> str | None:
    """Highest TTL on the request (OpenAI prompt_cache + Anthropic cache_control).

    OpenAI Responses: ``prompt_cache_options.ttl`` and any
    ``prompt_cache_breakpoint.ttl`` values (longest wins: ``12h`` > ``30m``).
    When options are present without a ttl, default to ``30m`` (#1843).
    Anthropic: ``1h`` wins over ``5m`` on system/tool ``cache_control``.
    """
    openai_ttl = _openai_prompt_cache_ttl(request)
    if openai_ttl:
        return openai_ttl
    found: set[str] = set()
    for message in request.messages:
        ttl = _ttl_from_cache_control(message.cache_control)
        if ttl:
            found.add(ttl)
    for tool in request.tools or []:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function") if isinstance(tool.get("function"), dict) else {}
        ttl = _ttl_from_cache_control(tool.get("cache_control")) or _ttl_from_cache_control(
            function.get("cache_control") if isinstance(function, dict) else None
        )
        if ttl:
            found.add(ttl)
    if "1h" in found:
        return "1h"
    if "5m" in found:
        return "5m"
    return None


def _openai_prompt_cache_ttl(request: InternalRequest) -> str | None:
    """Derive OpenAI Responses cache TTL from options / breakpoints (#1843)."""
    options = getattr(request.sampling, "prompt_cache_options", None)
    if not isinstance(options, dict):
        return None
    found: set[str] = set()
    raw = options.get("ttl")
    if isinstance(raw, str) and raw.strip():
        found.add(raw.strip().lower())
    breakpoints = options.get("breakpoints")
    if isinstance(breakpoints, list):
        for item in breakpoints:
            if not isinstance(item, dict):
                continue
            bttl = item.get("ttl")
            if isinstance(bttl, str) and bttl.strip():
                found.add(bttl.strip().lower())
    if "12h" in found or "12hr" in found:
        return "12h"
    if "30m" in found or "30min" in found:
        return "30m"
    # Options object present → OpenAI default TTL semantics.
    return "30m"


def _ttl_from_cache_control(cache_control: Any) -> str | None:
    if not isinstance(cache_control, dict):
        return None
    raw = cache_control.get("ttl")
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if key in {"1h", "1hr", "60m"}:
        return "1h"
    if key in {"5m", "5min"}:
        return "5m"
    return None


def _merge_cache_control(
    existing: dict[str, Any] | None,
    *,
    ensure_ephemeral: bool,
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
    if ensure_ephemeral:
        merged.setdefault("type", "ephemeral")
    elif "type" not in merged:
        merged["type"] = "ephemeral"
    return merged


def openai_tool_choice_to_anthropic(tool_choice: Any) -> dict[str, Any] | None:
    """Map OpenAI ``tool_choice`` to Anthropic's Messages API shape (#934)."""
    if tool_choice is None:
        return None
    if tool_choice == "auto":
        return {"type": "auto"}
    if tool_choice == "none":
        return {"type": "none"}
    if tool_choice == "required":
        return {"type": "any"}
    if isinstance(tool_choice, dict):
        kind = tool_choice.get("type")
        if kind == "function":
            function = tool_choice.get("function") if isinstance(tool_choice.get("function"), dict) else {}
            name = function.get("name")
            if isinstance(name, str) and name:
                return {"type": "tool", "name": name}
        if kind in {"auto", "none", "any", "tool"}:
            return dict(tool_choice)
    return None


def to_anthropic_payload(
    request: InternalRequest,
    *,
    model: str,
    stream: bool = False,
    prompt_cache: bool = False,
) -> dict[str, Any]:
    system_blocks: list[dict[str, Any]] = []
    converted: list[dict[str, Any]] = []
    pending_results: list[dict[str, Any]] = []

    def flush_results() -> None:
        nonlocal pending_results
        if pending_results:
            converted.append({"role": "user", "content": pending_results})
            pending_results = []

    for message in request.messages:
        if message.role == "system":
            if message.content:
                block: dict[str, Any] = {"type": "text", "text": message.content}
                if message.cache_control:
                    block["cache_control"] = _merge_cache_control(
                        message.cache_control, ensure_ephemeral=False
                    )
                system_blocks.append(block)
            continue
        if message.role == "tool":
            pending_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id or "toolu_unknown",
                    "content": message.content or "",
                }
            )
            continue
        flush_results()
        converted.append(_conversation_message(message))

    flush_results()
    if not converted:
        converted = [{"role": "user", "content": " "}]

    if prompt_cache and system_blocks:
        last = system_blocks[-1]
        existing = last.get("cache_control") if isinstance(last.get("cache_control"), dict) else None
        system_blocks[-1] = {
            **last,
            "cache_control": _merge_cache_control(existing, ensure_ephemeral=True),
        }
        add_step("prompt_cache_hint", provider="anthropic", marked_blocks=1)

    payload: dict[str, Any] = {
        "model": model,
        "messages": converted,
        "max_tokens": request.sampling.max_tokens or DEFAULT_MAX_TOKENS,
        "stream": stream,
    }
    if system_blocks:
        payload["system"] = system_blocks
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.tools:
        anthropic_tools = openai_tools_to_anthropic(request.tools)
        if anthropic_tools:
            payload["tools"] = anthropic_tools
    if request.sampling.top_p is not None:
        payload["top_p"] = request.sampling.top_p
    if request.sampling.top_k is not None:
        payload["top_k"] = request.sampling.top_k
    if request.sampling.stop:
        payload["stop_sequences"] = list(request.sampling.stop)
    if request.sampling.service_tier:
        payload["service_tier"] = request.sampling.service_tier
    if request.sampling.speed:
        payload["speed"] = request.sampling.speed
    if request.sampling.thinking:
        payload["thinking"] = dict(request.sampling.thinking)
    if request.sampling.metadata:
        payload["metadata"] = dict(request.sampling.metadata)
    if request.sampling.output_config:
        payload["output_config"] = dict(request.sampling.output_config)
    mapped_choice = openai_tool_choice_to_anthropic(request.sampling.tool_choice)
    if mapped_choice is not None:
        payload["tool_choice"] = mapped_choice
    if request.sampling.json_schema:
        payload["output_format"] = {
            "type": "json_schema",
            "schema": request.sampling.json_schema,
        }
    return payload


def _conversation_message(message: Message) -> dict[str, Any]:
    role = message.role if message.role in {"user", "assistant"} else "user"
    if message.tool_calls:
        return {"role": "assistant", "content": _assistant_tool_content(message)}
    return {"role": role, "content": _parts(message)}


def _thinking_prefix(message: Message) -> list[dict[str, Any]]:
    """Replay signed thinking blocks ahead of text/tool_use on assistant turns."""
    if message.role != "assistant" or not message.thinking_blocks:
        return []
    return [dict(block) for block in message.thinking_blocks]


def _assistant_tool_content(message: Message) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = list(_thinking_prefix(message))
    if message.content:
        blocks.append({"type": "text", "text": message.content})
    for call in message.tool_calls or []:
        if not isinstance(call, dict):
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
        blocks.append(
            {
                "type": "tool_use",
                "id": call.get("id") or "toolu_unknown",
                "name": function.get("name") or "",
                "input": arguments if isinstance(arguments, dict) else {},
            }
        )
    return blocks or [{"type": "text", "text": ""}]


def _parts(message: Message) -> str | list[dict[str, Any]]:
    thinking = _thinking_prefix(message)
    if not message.images and not thinking:
        return message.content or ""
    parts: list[dict[str, Any]] = list(thinking)
    if message.content:
        parts.append({"type": "text", "text": message.content})
    for image in message.images:
        data = image.as_base64()
        if not data:
            continue
        parts.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image.media_type or "image/png",
                    "data": data,
                },
            }
        )
    return parts or (message.content or "")


def text_from_anthropic_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    return "".join(parts)


def text_delta_from_sse_data(data: str) -> str | None:
    try:
        payload = json.loads(data)
    except ValueError:
        return None
    if payload.get("type") != "content_block_delta":
        return None
    delta = payload.get("delta") or {}
    if delta.get("type") == "text_delta" and isinstance(delta.get("text"), str):
        return delta["text"]
    return None


def anthropic_tool_event_from_sse_data(data: str) -> dict[str, Any] | None:
    """Return tool-related Anthropic SSE payloads for L6 relay (#934)."""
    try:
        payload = json.loads(data)
    except ValueError:
        return None
    event_type = payload.get("type")
    if event_type == "content_block_start":
        block = payload.get("content_block") or {}
        if isinstance(block, dict) and block.get("type") == "tool_use":
            return payload
    if event_type == "content_block_delta":
        delta = payload.get("delta") or {}
        if isinstance(delta, dict) and delta.get("type") == "input_json_delta":
            return payload
    if event_type == "content_block_stop":
        # Callers decide whether this stop closes a tool_use block.
        return payload
    return None
