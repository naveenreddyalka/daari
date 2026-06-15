# ADR-0003: Tool-native execution tier (Lt)

Date: 2026-06-15  
Status: **accepted**

## Context

Not every developer task needs AI. IDEs like IntelliJ already provide rename, refactor, find usages, optimize imports, inspections, and run configurations. Linters, formatters, git, and build tools handle other work deterministically.

Sending these through an LLM wastes tokens, adds latency, and produces worse results than the native tool.

## Decision

Add **Lt (tool-native)** as a first-class routing tier, evaluated **before** local models (after cache and rules):

```
L0 → L1 → L2 → Lt → L3 → L4 → L5 → L6
```

When the router identifies a task mappable to a registered tool backend, daari dispatches to that tool and returns the result — **no model invocation**.

## Examples

| Task intent | Backend | AI needed? |
|-------------|---------|------------|
| Rename symbol across project | IntelliJ refactor CLI | No |
| Format file | prettier / IDE formatter | No |
| Run linter | eslint / IDE inspection | No |
| Create git commit (message aside) | git | No |
| Optimize imports | IntelliJ / IDE | No |
| Explain architecture | — | Yes → L3+ |

## Implementation approach

- **Tool executor registry** — config maps intent patterns → command/API
- **MVP Lt backends:** git, formatter, linter (CLI subprocess)
- **v1 Lt backends:** IntelliJ via `idea` CLI or supported headless APIs
- daari works **with** existing IDEs, not as a replacement

## Consequences

**Positive**
- Maximizes "do locally without AI" — core product goal
- Better results for deterministic operations
- Differentiator vs pure LLM routers

**Negative**
- Intent → tool mapping is hard; needs good classification
- IDE integration varies by platform; IntelliJ first, others later
- Tool failures need clear escalation path to models

## Non-goals

- Building a full IDE plugin in MVP
- Replacing IntelliJ, VS Code, or Cursor
