# Glossary — daari

| Term | Definition |
|------|------------|
| **daari** | Open-source local execution router (Telugu: path, way) |
| **Tier** | A level in the routing stack (L0–L6, Lt) |
| **Path** | The tier chosen for a specific request |
| **L0** | Exact cache — identical prompt → instant hit |
| **L1** | Semantic cache — similar meaning → reused response |
| **L2** | Rules — deterministic transforms, no model |
| **Lt** | Tool-native — IDE/CLI execution without AI |
| **L3** | Small local model (SLM) |
| **L4** | Medium local model |
| **L5** | Large local model |
| **L6** | Frontier cloud API (OpenAI/Anthropic) — last resort |
| **$0 tier** | L0, L1, L2, or Lt — zero marginal inference cost |
| **CCS** | Command context store — reuse command output across turns |
| **L2-dev** | Developer command rule profile (detect run/test/script) |
| **Router** | Classifies requests and selects tier |
| **Executor** | Runs the work at a tier (tool, Ollama, frontier) |
| **Frontier** | Cloud LLM providers (OpenAI, Anthropic) |
| **Local-first** | Prefer on-machine tiers before cloud |
| **Tracer bullet MVP** | Smallest shippable proof of cost/latency wins |
