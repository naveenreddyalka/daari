# Extension points

| Extension | How |
|-----------|-----|
| Gateway adapter | Implement adapter; mount in `server/app.py` |
| Integration provider | `IntegrationProvider` + `ProviderRegistry` |
| MCP egress | `providers/mcp_egress.py` config `integrations.mcp_servers` |
| Client setup recipe | `ClientSetupRecipe` in `clients/` |
| Project profile | `.daari.yaml` + `X-Daari-Project` |
| Cache/ledger backend | `cache.backend`, `observability.backend` |
| Org fleet | `enterprise bootstrap`, Helm, org-cache service |

Prefer ADRs before large behavioral changes (`docs/adr/`).
