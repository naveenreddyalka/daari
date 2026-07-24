# Capacity guidance (Helm / fleet)

Rough sizing for gateway-heavy deployments (Roadmap F4). Cache-heavy traffic is far cheaper than model traffic.

| Resource | Guidance |
|---|---|
| Gateway replica | ~50–100 req/s when L0/L1 hit rate ≥60%; ~5–15 req/s when mostly L3 |
| Redis memory | ~1–2 KB per L0 entry; ~2–4 KB per L1 entry (embedding + answer) → ~200–400 MB / 100k entries |
| Postgres | Ledger/traces: ~1 KB/row; retain 30–90 days |
| GPU pool | 1× consumer GPU ≈ 1–4 concurrent 7–8B chats; use KEDA on queue depth for Ollama/vLLM |
| HPA | CPU 70% target, min 2 replicas behind any LB; readiness = `/ready` |

See `deploy/helm/daari/` for the chart. Point `orgPool.baseUrl` at a shared Ollama/vLLM service for the L5.5 org-inference step.
