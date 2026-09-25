"""Idempotency-Key helpers for chat, Responses, and modality routes (#714, #1065, #1082)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.responses import Response

from daari.gateway.idempotency_store import IdempotencyStore

DEFAULT_TTL_SECONDS = 86400
DEFAULT_WAIT_SECONDS = 60.0
CONFLICT_TYPE = "idempotency_conflict"
_B64_MARKER = "__daari_b64__:"

# In-process waiters for concurrent duplicates (same process).
_WAITERS: dict[tuple[str, str], asyncio.Event] = {}
_WAITERS_LOCK = asyncio.Lock()


def principal_from_request(request: Request) -> str:
    claims = getattr(request.state, "auth_claims", None)
    if claims is None:
        return "anonymous"
    if getattr(claims, "kind", None) == "virtual":
        key_id = getattr(claims, "key_id", None) or "unknown"
        return f"vk:{key_id}"
    return "master"


def request_body_hash(payload: Any) -> str:
    if hasattr(payload, "model_dump"):
        data = payload.model_dump(mode="json")
    elif isinstance(payload, dict):
        data = payload
    else:
        data = json.loads(json.dumps(payload, default=str))
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def multipart_body_hash(
    *,
    fields: dict[str, str],
    file_bytes: bytes,
    filename: str | None = None,
) -> str:
    """Stable digest for multipart ASR uploads (form fields + file sha256)."""
    file_digest = hashlib.sha256(file_bytes).hexdigest()
    return request_body_hash(
        {
            "fields": {str(k): str(v) for k, v in sorted(fields.items())},
            "file_sha256": file_digest,
            "filename": filename or "",
        }
    )


def encode_binary_body(data: bytes) -> str:
    return _B64_MARKER + base64.b64encode(data).decode("ascii")


def extract_idempotency_key(headers: Any) -> str | None:
    raw = None
    try:
        raw = headers.get("idempotency-key") or headers.get("Idempotency-Key")
    except Exception:
        raw = None
    if raw is None:
        return None
    key = str(raw).strip()
    return key or None


def conflict_response() -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "type": CONFLICT_TYPE,
                "message": (
                    "Idempotency-Key was already used with a different request body."
                ),
            }
        },
    )


def store_for(ctx: Any) -> IdempotencyStore | Any:
    """SQLite by default; postgres when idempotency.backend=postgres (#714)."""
    settings = ctx.settings
    cfg = getattr(settings, "idempotency", None)
    ttl = int(getattr(cfg, "ttl_seconds", DEFAULT_TTL_SECONDS) or DEFAULT_TTL_SECONDS)
    backend = getattr(cfg, "backend", "sqlite") if cfg is not None else "sqlite"
    pg_url = (settings.observability.postgres_url or "").strip()
    if backend == "postgres" and pg_url:
        from daari.gateway.postgres_idempotency import PostgresIdempotencyStore

        return PostgresIdempotencyStore(pg_url, ttl_seconds=ttl)
    path = Path(settings.trace.path).expanduser().parent / "idempotency.sqlite3"
    return IdempotencyStore(path, ttl_seconds=ttl)


def replay_response(record: dict[str, Any]) -> Response:
    media_type = record.get("media_type") or "application/json"
    body = record.get("response_body") or ""
    status = int(record.get("status_code") or 200)
    if record.get("stream"):
        async def _chunks() -> AsyncIterator[str]:
            # Re-chunk stored SSE: split on blank lines between events.
            text = body if isinstance(body, str) else body.decode("utf-8")
            for part in text.split("\n\n"):
                if not part.strip():
                    continue
                yield part + "\n\n"
            if "data: [DONE]" not in text:
                yield "data: [DONE]\n\n"

        return StreamingResponse(_chunks(), media_type=media_type, status_code=status)
    if isinstance(body, str) and body.startswith(_B64_MARKER):
        raw = base64.b64decode(body[len(_B64_MARKER) :])
        return Response(content=raw, media_type=media_type, status_code=status)
    if isinstance(body, str):
        try:
            content = json.loads(body)
        except json.JSONDecodeError:
            content = {"raw": body}
    else:
        content = body
    return JSONResponse(content, status_code=status, media_type=media_type)


def complete_json_slot(
    slot: IdempotencySlot | None,
    *,
    status_code: int,
    payload: Any,
    media_type: str = "application/json",
) -> None:
    if slot is None:
        return
    slot.complete(
        status_code=status_code,
        response_body=json.dumps(payload, separators=(",", ":"), default=str),
        media_type=media_type,
        stream=False,
    )


def complete_binary_slot(
    slot: IdempotencySlot | None,
    *,
    status_code: int,
    data: bytes,
    media_type: str,
) -> None:
    if slot is None:
        return
    slot.complete(
        status_code=status_code,
        response_body=encode_binary_body(data),
        media_type=media_type,
        stream=False,
    )


def abandon_slot(slot: IdempotencySlot | None) -> None:
    if slot is not None:
        slot.abandon()


@dataclass
class IdempotencySlot:
    principal: str
    idem_key: str
    body_hash: str
    store: Any

    def complete(
        self,
        *,
        status_code: int,
        response_body: str,
        media_type: str,
        stream: bool = False,
        assistant_text: str | None = None,
    ) -> None:
        self.store.complete(
            self.principal,
            self.idem_key,
            status_code=status_code,
            response_body=response_body,
            media_type=media_type,
            stream=stream,
            assistant_text=assistant_text,
        )
        _signal(self.principal, self.idem_key)

    def abandon(self) -> None:
        self.store.abandon(self.principal, self.idem_key)
        _signal(self.principal, self.idem_key)


OutcomeKind = Literal["noop", "replay", "conflict", "proceed"]


async def resolve_idempotency(
    request: Request,
    ctx: Any,
    payload: Any,
    *,
    wait_seconds: float | None = None,
) -> tuple[OutcomeKind, Response | None, IdempotencySlot | None]:
    """Return (kind, response_or_none, slot_or_none). Missing header is noop."""
    cfg = getattr(ctx.settings, "idempotency", None)
    if cfg is not None and not getattr(cfg, "enabled", True):
        return "noop", None, None
    key = extract_idempotency_key(request.headers)
    if not key:
        return "noop", None, None
    store = store_for(ctx)
    principal = principal_from_request(request)
    body_hash = request_body_hash(payload)
    wait_budget = (
        wait_seconds
        if wait_seconds is not None
        else float(getattr(getattr(ctx.settings, "idempotency", None), "wait_seconds", DEFAULT_WAIT_SECONDS))
    )

    existing = store.get(principal, key)
    if existing is not None:
        if existing.get("body_hash") != body_hash:
            return "conflict", conflict_response(), None
        if existing.get("state") == "complete":
            return "replay", replay_response(existing), None
        # pending: wait for the first request
        waited = await _wait_for_complete(store, principal, key, wait_budget)
        if waited is not None:
            if waited.get("body_hash") != body_hash:
                return "conflict", conflict_response(), None
            if waited.get("state") == "complete":
                return "replay", replay_response(waited), None
        # Timed out or abandoned — try to claim
        store.abandon(principal, key)

    if store.begin(principal, key, body_hash):
        await _register_waiter(principal, key)
        return "proceed", None, IdempotencySlot(principal, key, body_hash, store)

    # Lost the race: re-read
    again = store.get(principal, key)
    if again is None:
        return "noop", None, None
    if again.get("body_hash") != body_hash:
        return "conflict", conflict_response(), None
    if again.get("state") == "complete":
        return "replay", replay_response(again), None
    waited = await _wait_for_complete(store, principal, key, wait_budget)
    if waited is not None and waited.get("state") == "complete":
        if waited.get("body_hash") != body_hash:
            return "conflict", conflict_response(), None
        return "replay", replay_response(waited), None
    return "conflict", conflict_response(), None


def _waiter_key(principal: str, idem_key: str) -> tuple[str, str]:
    return (principal, idem_key)


async def _register_waiter(principal: str, idem_key: str) -> None:
    async with _WAITERS_LOCK:
        _WAITERS.setdefault(_waiter_key(principal, idem_key), asyncio.Event())


def _signal(principal: str, idem_key: str) -> None:
    event = _WAITERS.get(_waiter_key(principal, idem_key))
    if event is not None:
        event.set()


async def _wait_for_complete(
    store: Any,
    principal: str,
    idem_key: str,
    wait_seconds: float,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + max(0.0, float(wait_seconds))
    async with _WAITERS_LOCK:
        event = _WAITERS.setdefault(_waiter_key(principal, idem_key), asyncio.Event())
    while time.monotonic() < deadline:
        row = store.get(principal, idem_key)
        if row is None:
            return None
        if row.get("state") == "complete":
            return row
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        event.clear()
        try:
            await asyncio.wait_for(event.wait(), timeout=min(0.25, remaining))
        except TimeoutError:
            continue
    return store.get(principal, idem_key)


def assemble_assistant_text_from_sse(sse_text: str) -> str:
    """Best-effort extract of assistant text from OpenAI-style chat SSE."""
    parts: list[str] = []
    for line in sse_text.splitlines():
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        choices = obj.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if isinstance(content, str):
                parts.append(content)
            message = choices[0].get("message") or {}
            msg_content = message.get("content")
            if isinstance(msg_content, str):
                parts.append(msg_content)
        # Responses API stream events
        if obj.get("type") == "response.output_text.delta":
            delta = obj.get("delta")
            if isinstance(delta, str):
                parts.append(delta)
    return "".join(parts)
