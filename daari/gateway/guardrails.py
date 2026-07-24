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

    def check_input(self, request: InternalRequest) -> GuardrailResult:
        result = GuardrailResult(request=request)
        if not self.enabled:
            return result
        text = "\n".join(m.content or "" for m in request.messages if m.role != "system")
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
        result = GuardrailResult(response=response)
        if not self.enabled:
            return result
        text = response.content or ""
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
                            result.response = response.model_copy(
                                update={"content": self.block_message}
                            )
                            return result
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
                        result.response = response.model_copy(
                            update={"content": self.block_message}
                        )
                        return result
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
                    result.response = response.model_copy(
                        update={"content": self.block_message}
                    )
                    return result
                if rule.action == "warn":
                    result.warning = f"guardrail:{rule.name}"
                if rule.action == "redact":
                    rewritten = re.sub(rule.pattern, "<redacted>", rewritten, flags=re.I)

        if rewritten != text:
            result.response = response.model_copy(update={"content": rewritten})
        return result


def engine_from_settings(settings: Any) -> GuardrailEngine | None:
    block = getattr(settings, "guardrails", None)
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
    return GuardrailEngine(
        enabled=True,
        input_rules=input_rules,
        output_rules=output_rules,
        max_prompt_chars=int(block.max_prompt_chars or 0),
        injection_action=block.injection_action,  # type: ignore[arg-type]
        block_message=block.block_message or GuardrailEngine.block_message,
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
