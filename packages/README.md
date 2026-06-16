# packages/

Non-Python daari surfaces live here. Each subfolder is an independent package with its own build tool.

| Package | Language | Phase | Role |
|---------|----------|-------|------|
| `browser-extension/` | TypeScript | C2 | Google search via user browser session |
| `web-ui/` | TypeScript/React | C1+ | Optional localhost stats dashboard |
| `intellij-plugin/` | Kotlin | C2+ | Optional — only if `idea` CLI insufficient |

**Rule:** These packages call the Python daemon over localhost. No routing logic here.

See [ADR-0013](../docs/adr/0013-monorepo-structure.md).

Phase A–B: this directory may be empty except this README.
