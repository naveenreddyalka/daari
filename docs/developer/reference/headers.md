# Request headers

| Header | Effect |
|--------|--------|
| `Authorization: Bearer` / `x-api-key` | API key or virtual key |
| `X-Daari-Meta: true` | Embed `daari_meta` in JSON responses |
| `X-Daari-No-Cache` | Skip L0/L1 |
| `X-Daari-Tier-Override` | Force a tier |
| `X-Daari-Tier-Cap` | Cap local tier (e.g. `L3`) |
| `X-Daari-No-Frontier` | Forbid L6 |
| `X-Daari-Latency-Budget` | Max local latency (ms) |
| `X-Daari-Client-Id` | Ledger attribution |
| `X-Daari-Project` | Path for `.daari.yaml` discovery |
| `X-Daari-Boundary-Profile` | Named `boundaries.profiles` overlay for this request (browser extension site profiles) |
| `X-Daari-Tools` | Tool-related client hints |
| `X-Daari-Confirm*` / `X-Daari-ReRun-Command` | Lt ask-gate confirmation |

Explicit headers win over project profiles and most config defaults.
