"""Input/output guardrails for router requests (Roadmap F2 / issue #110).

Pure functions + a small engine. Actions:
- block: refuse the request / replace the answer with a refusal
- warn: attach daari_meta.warning and continue
- redact: rewrite matching text (PII/secrets) and continue

Builds on daari/gateway/pii.py for PII redaction. Every trip is meant to be
traced (add_step) and counted (Metrics.record_guardrail) by the caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from daari.gateway.internal import InternalRequest, InternalResponse
from daari.gateway.pii import scrub_pii

Action = Literal["block", "warn", "redact"]

# Heuristic phrases that often precede prompt-injection attempts.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)", re.I),
    re.compile(r"you\s+are\s+now\s+(dan|jailbroken|unrestricted)", re.I),
    re.compile(r"system\s*:\s*you\s+must", re.I),
    re.compile(r"<\s*/?\s*system\s*>", re.I),
]

# Secrets we never want echoed in model output.
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    (
        "generic_secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"
        ),
    ),
]


@dataclass
class GuardrailHit:
    stage: str  # input | output
    rule: str
    action: Action
    detail: str = ""


@dataclass
class GuardrailResult:
    hits: list[GuardrailHit] = field(default_factory=list)
    blocked: bool = False
    warning: str | None = None
    # Rewritten request/response content when action=redact.
    request: InternalRequest | None = None
    response: InternalResponse | None = None

    @property
    def tripped(self) -> bool:
        return bool(self.hits)


@dataclass
class GuardrailRule:
    name: str
    pattern: str | None = None
    action: Action = "block"
    # allow rules short-circuit deny when matched (input only).
    kind: Literal["deny", "allow", "max_length", "injection", "secret", "pii"] = "deny"
    max_chars: int | None = None


@dataclass
class GuardrailEngine:
    enabled: bool = False
    input_rules: list[GuardrailRule] = field(default_factory=list)
    output_rules: list[GuardrailRule] = field(default_factory=list)
    max_prompt_chars: int = 0  # 0 = unlimited
    injection_action: Action = "block"
    block_message: str = "Request blocked by daari guardrail."
    # buffered = collect then scan (default); incremental = holdback window (#375).
    stream_mode: Literal["buffered", "incremental"] = "buffered"
    stream_holdback_chars: int = 256
    # When on, scan role=tool messages with output rules before the model hop (#387).
    scan_tool_results: bool = False

    def check_input(self, request: InternalRequest) -> GuardrailResult:
        text = "\n".join(m.content or "" for m in request.messages if m.role != "system")
        result = self.check_input_text(text)
        result.request = request
        return result

    def check_tool_results(self, request: InternalRequest) -> GuardrailResult:
        """Scan OpenAI `role=tool` / Anthropic-converted tool_result messages.

        Opt-in via `scan_tool_results`. Uses output-style rules (secrets/PII/deny)
        so a leaked secret in a tool payload is redacted or blocked before execute
        and before cache keys are computed. System/user/assistant are untouched.
        """
        result = GuardrailResult(request=request)
        if not self.enabled or not self.scan_tool_results:
            return result
        rewritten_any = False
        for index, message in enumerate(request.messages):
            if message.role != "tool":
                continue
            text = message.content or ""
            # Input deny/injection on tool payload (parity with MCP args path).
            inbound = self.check_input_text(text)
            if inbound.hits:
                result.hits.extend(inbound.hits)
                result.warning = result.warning or inbound.warning
            if inbound.blocked:
                result.blocked = True
                return result
            rewritten, outbound = self.check_output_text(text)
            if outbound.hits:
                result.hits.extend(outbound.hits)
                result.warning = result.warning or outbound.warning
            if outbound.blocked:
                result.blocked = True
                return result
            if rewritten != text:
                request.messages[index] = message.model_copy(update={"content": rewritten})
                rewritten_any = True
        if rewritten_any:
            result.request = request
        return result

    def check_input_text(self, text: str) -> GuardrailResult:
        """Run the input rules over raw text (chat prompts, MCP tool arguments)."""
        result = GuardrailResult()
        if not self.enabled:
            return result
        # Allowlist short-circuit: if any allow rule matches, skip denies.
        for rule in self.input_rules:
            if rule.kind == "allow" and rule.pattern and re.search(rule.pattern, text, re.I):
                return result

        if self.max_prompt_chars > 0 and len(text) > self.max_prompt_chars:
            hit = GuardrailHit(
                stage="input",
                rule="max_length",
                action="block",
                detail=f"{len(text)}>{self.max_prompt_chars}",
            )
            result.hits.append(hit)
            result.blocked = True
            return result

        for rule in self.input_rules:
            if rule.kind != "deny" or not rule.pattern:
                continue
            if re.search(rule.pattern, text, re.I):
                hit = GuardrailHit(
                    stage="input", rule=rule.name, action=rule.action, detail=rule.pattern
                )
                result.hits.append(hit)
                if rule.action == "block":
                    result.blocked = True
                    return result
                if rule.action == "warn":
                    result.warning = f"guardrail:{rule.name}"

        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                hit = GuardrailHit(
                    stage="input",
                    rule="prompt_injection",
                    action=self.injection_action,
                    detail=pattern.pattern,
                )
                result.hits.append(hit)
                if self.injection_action == "block":
                    result.blocked = True
                    return result
                if self.injection_action == "warn":
                    result.warning = "guardrail:prompt_injection"
                break
        return result

    def check_output(self, response: InternalResponse) -> GuardrailResult:
        text = response.content or ""
        rewritten, result = self.check_output_text(text)
        result.response = (
            response.model_copy(update={"content": rewritten}) if rewritten != text else response
        )
        return result

    def check_output_text(self, text: str) -> tuple[str, GuardrailResult]:
        """Run the output rules over raw text. Returns (rewritten_text, result);
        a block returns `block_message` as the text."""
        result = GuardrailResult()
        if not self.enabled:
            return text, result
        rewritten = text
        for rule in self.output_rules:
            if rule.kind == "secret" or rule.name == "secrets":
                for kind, pattern in _SECRET_PATTERNS:
                    if pattern.search(rewritten):
                        hit = GuardrailHit(
                            stage="output", rule=f"secret:{kind}", action=rule.action
                        )
                        result.hits.append(hit)
                        if rule.action == "block":
                            result.blocked = True
                            return self.block_message, result
                        if rule.action == "warn":
                            result.warning = f"guardrail:secret:{kind}"
                        if rule.action == "redact":
                            rewritten = pattern.sub(f"<{kind}>", rewritten)
            if rule.kind == "pii" or rule.name == "pii":
                scrubbed, counts = scrub_pii(rewritten)
                if counts:
                    hit = GuardrailHit(
                        stage="output",
                        rule="pii",
                        action=rule.action,
                        detail=",".join(f"{k}:{v}" for k, v in counts.items()),
                    )
                    result.hits.append(hit)
                    if rule.action == "block":
                        result.blocked = True
                        return self.block_message, result
                    if rule.action == "warn":
                        result.warning = "guardrail:pii"
                    if rule.action == "redact":
                        rewritten = scrubbed
            if rule.kind == "deny" and rule.pattern and re.search(rule.pattern, rewritten, re.I):
                hit = GuardrailHit(
                    stage="output", rule=rule.name, action=rule.action, detail=rule.pattern
                )
                result.hits.append(hit)
                if rule.action == "block":
                    result.blocked = True
                    return self.block_message, result
                if rule.action == "warn":
                    result.warning = f"guardrail:{rule.name}"
                if rule.action == "redact":
                    rewritten = re.sub(rule.pattern, "<redacted>", rewritten, flags=re.I)
        return rewritten, result


@dataclass
class StreamScanRelease:
    """Text safe to emit now from an incremental output scan."""

    text: str = ""
    blocked: bool = False
    hits: list[GuardrailHit] = field(default_factory=list)
    warning: str | None = None


@dataclass
class IncrementalOutputScanner:
    """Scan streamed output with a trailing holdback so spans across chunks are caught.

    Holds the last `holdback` characters of the rewritten buffer before release.
    On block, `text` is the engine `block_message` (once) and further pushes stay blocked.
    """

    engine: GuardrailEngine
    holdback: int = 256
    _raw: str = field(default="", init=False, repr=False)
    _emitted_len: int = field(default=0, init=False, repr=False)
    _blocked: bool = field(default=False, init=False, repr=False)
    _hits: list[GuardrailHit] = field(default_factory=list, init=False, repr=False)
    _warning: str | None = field(default=None, init=False, repr=False)
    _scanned: str = field(default="", init=False, repr=False)
    _block_emitted: bool = field(default=False, init=False, repr=False)

    def push(self, chunk: str) -> StreamScanRelease:
        if self._blocked:
            return StreamScanRelease(blocked=True, hits=list(self._hits), warning=self._warning)
        if not chunk:
            return StreamScanRelease(hits=list(self._hits), warning=self._warning)
        self._raw += chunk
        return self._release(final=False)

    def flush(self) -> StreamScanRelease:
        if self._blocked:
            if not self._block_emitted:
                self._block_emitted = True
                return StreamScanRelease(
                    text=self.engine.block_message,
                    blocked=True,
                    hits=list(self._hits),
                    warning=self._warning,
                )
            return StreamScanRelease(blocked=True, hits=list(self._hits), warning=self._warning)
        return self._release(final=True)

    @property
    def scanned_text(self) -> str:
        return self._scanned

    @property
    def hits(self) -> list[GuardrailHit]:
        return list(self._hits)

    @property
    def warning(self) -> str | None:
        return self._warning

    @property
    def blocked(self) -> bool:
        return self._blocked

    def _release(self, *, final: bool) -> StreamScanRelease:
        rewritten, result = self.engine.check_output_text(self._raw)
        if result.hits:
            # Keep first-seen hits; avoid duplicates on every push.
            seen = {(h.stage, h.rule, h.action, h.detail) for h in self._hits}
            for hit in result.hits:
                key = (hit.stage, hit.rule, hit.action, hit.detail)
                if key not in seen:
                    self._hits.append(hit)
                    seen.add(key)
        if result.warning:
            self._warning = result.warning
        if result.blocked:
            self._blocked = True
            self._scanned = rewritten  # block_message
            if self._block_emitted:
                return StreamScanRelease(
                    blocked=True, hits=list(self._hits), warning=self._warning
                )
            self._block_emitted = True
            # Drop any previously released prefix from the client's view of record;
            # cache stores the block message only.
            self._emitted_len = len(rewritten)
            return StreamScanRelease(
                text=rewritten,
                blocked=True,
                hits=list(self._hits),
                warning=self._warning,
            )
        self._scanned = rewritten
        holdback = max(0, int(self.holdback))
        if final:
            safe_len = len(rewritten)
        else:
            safe_len = max(0, len(rewritten) - holdback)
        if safe_len < self._emitted_len:
            # Redaction shortened earlier text; wait for flush to reconcile.
            safe_len = self._emitted_len
        to_emit = rewritten[self._emitted_len : safe_len]
        self._emitted_len = safe_len
        return StreamScanRelease(
            text=to_emit,
            blocked=False,
            hits=list(self._hits),
            warning=self._warning,
        )


def engine_from_settings(settings: Any) -> GuardrailEngine | None:
    return engine_from_block(getattr(settings, "guardrails", None))


def engine_from_block(block: Any) -> GuardrailEngine | None:
    """Build an engine from any `GuardrailSettings`-shaped block (chat or MCP)."""
    if block is None or not getattr(block, "enabled", False):
        return None
    input_rules = [
        GuardrailRule(
            name=r.name,
            pattern=r.pattern,
            action=r.action,  # type: ignore[arg-type]
            kind=r.kind,  # type: ignore[arg-type]
        )
        for r in (block.input_rules or [])
    ]
    output_rules = [
        GuardrailRule(
            name=r.name,
            pattern=r.pattern,
            action=r.action,  # type: ignore[arg-type]
            kind=r.kind,  # type: ignore[arg-type]
        )
        for r in (block.output_rules or [])
    ]
    # Sensible defaults when enabled with empty rule lists.
    if not output_rules:
        output_rules = [
            GuardrailRule(name="secrets", kind="secret", action="redact"),
            GuardrailRule(name="pii", kind="pii", action="redact"),
        ]
    stream_mode = getattr(block, "stream_mode", "buffered") or "buffered"
    holdback = int(getattr(block, "stream_holdback_chars", 256) or 256)
    scan_tool = bool(getattr(block, "scan_tool_results", False))
    return GuardrailEngine(
        enabled=True,
        input_rules=input_rules,
        output_rules=output_rules,
        max_prompt_chars=int(block.max_prompt_chars or 0),
        injection_action=block.injection_action,  # type: ignore[arg-type]
        block_message=block.block_message or GuardrailEngine.block_message,
        stream_mode=stream_mode,  # type: ignore[arg-type]
        stream_holdback_chars=max(0, holdback),
        scan_tool_results=scan_tool,
    )


def blocked_response(request: InternalRequest, message: str) -> InternalResponse:
    from daari.gateway.internal import DaariMeta

    return InternalResponse(
        content=message,
        model=request.model,
        daari_meta=DaariMeta(
            tier="guardrail",
            executor="guardrail",
            provider_id="guardrail",
            latency_ms=0,
            warning="guardrail_blocked",
        ),
    )
