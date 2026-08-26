# Glossary

| Term | Definition |
|------|------------|
| **daari** | Source-available local execution router (Telugu: path, way) |
| **Tier** | Level in the routing stack (L0–L6, Lt) |
| **L0** | Exact cache — identical prompt → instant hit |
| **L1** | Semantic cache — similar meaning → reused response |
| **L2** | Rules — deterministic transforms, no model |
| **Lt** | Tool-native — CLI/IDE execution without AI |
| **L3 / L4 / L5** | Small / medium / large local models |
| **L6** | Frontier cloud API — last resort |
| **$0 tier** | L0, L1, L2, or Lt — zero marginal inference cost |
| **CCS** | Command context store — reuse command output across turns |
| **PolicyEngine** | Lt allow / deny / ask before shell execution |
| **Boundary** | Product-domain scope gate (in / out / ambiguous) |
| **Guardrail** | Regex/heuristic safety check (injection, PII, secrets) |
| **daari_meta** | Per-response routing metadata (tier, cache_hit, trace_id, …) |
| **Virtual key** | Hashed API key with budgets / RPM / tier caps |
| **Local-first** | Prefer on-machine tiers before cloud |
| **Org cache** | Optional shared L0/L1 for a fleet |
