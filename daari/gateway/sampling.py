"""Sampling parameters carried from client to backend (issue #161).

`ChatCompletionRequest` declared six fields and set `extra="ignore"`, so everything
else a normal OpenAI client sends — `max_tokens`, `top_p`, `stop`, `seed`,
`response_format` — was accepted with a 200 and dropped. A client asking for
bounded, deterministic, or JSON-shaped output got none of it and no error.

Three rules shape this module:

- **Unset means absent.** Sending `None` for a parameter the client omitted would
  override the backend's own default, so unset keys never appear in a payload.
- **What cannot be honored is reported.** Ollama has no `presence_penalty` and
  returns one choice, so those become a `daari_meta.warning` rather than silence.
- **Only honored parameters split the cache.** A parameter that changed nothing
  about the answer must not fragment the cache; one that did must never collide.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict

# OpenAI centres frequency_penalty on 0 over [-2, 2]; Ollama centres
# repeat_penalty on 1.0. Neither documents an exact correspondence, so this is a
# deliberate approximation: same direction, same "no penalty" point.
_REPEAT_PENALTY_CENTRE = 1.0
_REPEAT_PENALTY_SCALE = 0.5


class SamplingParams(BaseModel):
    """Generation controls, in OpenAI's vocabulary."""

    model_config = ConfigDict(extra="ignore")

    max_tokens: int | None = None
    top_p: float | None = None
    top_k: int | None = None
    stop: list[str] | None = None
    seed: int | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    response_format_json: bool = False
    tool_choice: str | None = None
    n: int | None = None
    logprobs: bool | None = None

    @classmethod
    def from_openai_body(cls, body: dict[str, Any]) -> SamplingParams:
        """Read what a chat-completions body asked for, ignoring the rest."""
        stop = body.get("stop")
        if isinstance(stop, str):
            stop = [stop]
        elif isinstance(stop, list):
            stop = [str(item) for item in stop if item]
        else:
            stop = None

        # max_completion_tokens supersedes max_tokens in newer clients. Both keys
        # are usually present with one set to None, so a `get` default is not
        # enough — it would read the explicit None and stop there.
        raw_max = body.get("max_completion_tokens")
        if raw_max is None:
            raw_max = body.get("max_tokens")
        max_tokens = int(raw_max) if isinstance(raw_max, int) and raw_max > 0 else None

        response_format = body.get("response_format")
        wants_json = (
            isinstance(response_format, dict)
            and response_format.get("type") == "json_object"
        )

        tool_choice = body.get("tool_choice")
        if isinstance(tool_choice, dict):
            # {"type": "function", "function": {...}} forces a specific call.
            tool_choice = "required"
        elif not isinstance(tool_choice, str):
            tool_choice = None

        return cls(
            max_tokens=max_tokens,
            top_p=body.get("top_p"),
            stop=stop or None,
            seed=body.get("seed"),
            frequency_penalty=body.get("frequency_penalty"),
            presence_penalty=body.get("presence_penalty"),
            response_format_json=wants_json,
            tool_choice=tool_choice,
            n=body.get("n"),
            logprobs=body.get("logprobs"),
        )

    @classmethod
    def from_anthropic_body(cls, body: dict[str, Any]) -> SamplingParams:
        """Same controls under Anthropic's names.

        `max_tokens` is required by that API, so Claude Code always sends one — a
        cap daari was ignoring while advertising an Anthropic-compatible endpoint.
        """
        stop = body.get("stop_sequences")
        if isinstance(stop, str):
            stop = [stop]
        elif isinstance(stop, list):
            stop = [str(item) for item in stop if item]
        else:
            stop = None

        raw_max = body.get("max_tokens")
        return cls(
            max_tokens=int(raw_max) if isinstance(raw_max, int) and raw_max > 0 else None,
            top_p=body.get("top_p"),
            top_k=body.get("top_k"),
            stop=stop or None,
        )

    @classmethod
    def from_responses_body(cls, body: dict[str, Any]) -> SamplingParams:
        """The Responses API renames the cap; the rest of the names carry over."""
        cap = body.get("max_output_tokens")
        if cap is None:
            cap = body.get("max_tokens")
        return cls.from_openai_body({**body, "max_tokens": cap, "max_completion_tokens": None})

    @classmethod
    def from_ollama_options(cls, options: dict[str, Any] | None) -> SamplingParams:
        """The facade's clients speak Ollama's own option names."""
        options = options or {}
        stop = options.get("stop")
        if isinstance(stop, str):
            stop = [stop]
        elif isinstance(stop, list):
            stop = [str(item) for item in stop if item]
        else:
            stop = None

        cap = options.get("num_predict")
        return cls(
            # -1 and -2 are Ollama's "unlimited" and "fill context"; leaving them
            # unset means the same thing without pretending it was a request.
            max_tokens=int(cap) if isinstance(cap, int) and cap > 0 else None,
            top_p=options.get("top_p"),
            top_k=options.get("top_k"),
            stop=stop or None,
            seed=options.get("seed"),
        )

    def ollama_options(self) -> dict[str, Any]:
        """The subset Ollama's `options` block understands."""
        options: dict[str, Any] = {}
        if self.max_tokens is not None:
            options["num_predict"] = self.max_tokens
        if self.top_p is not None:
            options["top_p"] = self.top_p
        if self.top_k is not None:
            options["top_k"] = self.top_k
        if self.stop:
            options["stop"] = list(self.stop)
        if self.seed is not None:
            options["seed"] = self.seed
        if self.frequency_penalty is not None:
            options["repeat_penalty"] = max(
                0.0,
                _REPEAT_PENALTY_CENTRE + self.frequency_penalty * _REPEAT_PENALTY_SCALE,
            )
        return options

    def ollama_format(self) -> str | None:
        """Ollama takes JSON mode as a top-level `format`, not an option."""
        return "json" if self.response_format_json else None

    def openai_payload(self) -> dict[str, Any]:
        """Parameters to forward verbatim to an OpenAI-compatible provider.

        `top_k` is left out on purpose: it is not in the chat-completions schema and
        strict providers reject an unknown field with a 400.
        """
        payload: dict[str, Any] = {}
        for name in ("max_tokens", "top_p", "seed", "presence_penalty", "frequency_penalty"):
            value = getattr(self, name)
            if value is not None:
                payload[name] = value
        if self.stop:
            payload["stop"] = list(self.stop)
        if self.response_format_json:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def unsupported_locally(self) -> list[str]:
        """Human-readable notes for parameters a local model cannot honor."""
        notes: list[str] = []
        if self.presence_penalty is not None:
            notes.append("presence_penalty has no local equivalent and was ignored")
        if self.n is not None and self.n > 1:
            notes.append(f"n {self.n} requested; daari returns a single choice")
        if self.logprobs:
            notes.append("logprobs are not available from local models")
        if self.tool_choice == "required":
            notes.append("tool_choice required cannot be forced locally; treated as auto")
        return notes

    def honored_fields(self) -> dict[str, Any]:
        """Only what actually reaches a backend, for cache keying."""
        data: dict[str, Any] = {}
        for name in ("max_tokens", "top_p", "top_k", "seed", "frequency_penalty"):
            value = getattr(self, name)
            if value is not None:
                data[name] = value
        if self.stop:
            data["stop"] = list(self.stop)
        if self.response_format_json:
            data["response_format"] = "json_object"
        if self.tool_choice in {"none"}:
            data["tool_choice"] = self.tool_choice
        return data

    def cache_fingerprint(self) -> str:
        """Stable digest of the parameters that change the answer.

        Empty when nothing was asked for, so requests that set no parameters keep
        hitting entries written before this existed.
        """
        honored = self.honored_fields()
        if not honored:
            return ""
        return hashlib.sha256(
            json.dumps(honored, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
