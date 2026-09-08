# Release notes — v1.4.0 (Apache 2.0, Supply Chain & Enterprise Gateway)

> Date: 2026-09-03  
> Scope: everything merged since v1.3.0 — ~70 commits: Apache 2.0 relicense, signed ghcr images with SBOM/provenance, MCP governance, `secret://` refs, OpenAI-compat local backends, FinOps headers, and fleet upgrade docs

## Human steps remaining (agent must not run these)

This PR only prepares the tree. A maintainer still needs to:

```bash
git tag v1.4.0 && git push origin v1.4.0
gh release create v1.4.0 \
  --title "v1.4.0 — Apache 2.0, Supply Chain & Enterprise Gateway" \
  --notes-file docs/RELEASE-v1.4.0.md
```

That tag push triggers signed Docker publish (`docker.yml`: cosign keyless + Syft SBOM + SLSA provenance). The GitHub Release publish event triggers PyPI via `publish.yml`. Then:

```bash
python scripts/release_pypi.py verify --version 1.4.0
python scripts/update_formula.py --version 1.4.0   # after the GitHub tarball exists
```

See [RELEASING.md](RELEASING.md). **Do not** have an agent tag, create the release, or publish.

## Summary

daari **1.4.0** is the first release a company can **legally adopt** and **cryptographically verify**:

- **License:** the whole tree is **Apache 2.0** again ([ADR-0016](adr/0016-apache-2-relicense.md), #293). v1.3.0 as tagged remains PolyForm Noncommercial; this tag is the first Apache 2.0 ship since the NC experiment.
- **Supply chain:** ghcr images are **cosign-signed** (keyless OIDC) with **Syft SBOM** and **SLSA provenance** attestations attached on every main/tag push (#311).

On top of that, the gateway gained MCP tool governance and guardrails, `secret://` (and `secret://oauth`) for provider credentials, an OpenAI-compatible local backend kind (vLLM / llama.cpp), shadow evals for tier decisions, cost-split and budget-remaining response headers, and a fleet upgrade / config-migration guide.

## Highlights

### License & supply chain

| Feature | Detail |
|---------|--------|
| Apache 2.0 relicense (#293) | Tree-wide Apache 2.0; ADR-0016. First shippable OSI release after the PolyForm NC experiment at v1.3.0 |
| Signed images + SBOM + provenance (#311) | `docker.yml`: cosign keyless sign of the image digest; `sbom: true` + `provenance: true` on build-push |

### MCP & agent surface

| Feature | Detail |
|---------|--------|
| MCP tool governance (#307) | Per-key / per-team allow/deny with audit rows on `tools/call` |
| MCP guardrails (#325) | Guardrails on tool arguments and results; `mcp.guardrail` audit |
| MCP Tasks extension (#315) | Long-running `tools/call` via the Tasks extension |
| Agent prefix L1 (#299) | Cache the stable tool/system prefix; miss on the user suffix |
| `reasoning_effort` (#312) | Honored on chat completions; optional local-tier escalation |
| SSE keepalive (#304) | Heartbeat on all streaming routes (`server.sse_keepalive_seconds`) |

### Secrets, auth & FinOps

| Feature | Detail |
|---------|--------|
| `secret://` refs (#314) | `env-file` / `keychain` / `exec` for provider and org keys |
| `secret://oauth` (#329) | Client-credentials upstream token fetch |
| Cost-split headers (#308) | `x-daari-response-cost-*` savings breakdown |
| Budget-remaining headers (#327) | Remaining budget on responses and budget 402s |
| Stream usage once (#328) | Streamed usage counted exactly once on every stream path |
| Virtual key expiry (#337) | `expires_at` + SSO `key_ttl`; 401 `key_expired` |
| Multi-window budgets / team keys (#252) | Hierarchy and windowed spend caps |
| SSO key minting (#253) | Virtual keys from IdP claim mappings |

### Routing & local backends

| Feature | Detail |
|---------|--------|
| OpenAI-compat local kind (#303) | `routing.local_pool.backends[].kind: openai` for vLLM / llama.cpp |
| Shadow evals (#326) | `routing.shadow_compare_tier` / `shadow_daily_usd` for tier divergence |
| Context-length failover (#247) | Capability-tagged models and length-aware failover |
| OpenRouter L6 (#241, #242) | First-class OpenRouter slot; honor `provider` object |

### Ops, clients & observability

| Feature | Detail |
|---------|--------|
| Fleet upgrade guide (#316) | [Upgrade and config migration](developer/guides/operations/upgrade.md) |
| Retention + prune (#338) | `observability.retention.*_days` + `daari prune` |
| `daari service` (#266, #300, #324) | User systemd/launchd install, `--now`, `restart` |
| Onboard / Cursor tunnel (#262, #265, #271) | First-run onboard, tunnel one-liner, `--serve` |
| Claude Desktop recipe (#309) | One-click Desktop setup |
| OTel GenAI conventions (#205) | Semantic conventions for GenAI spans |

### Also in this release

- Boundaries B2 quorum / B3 budget / embed B0 (#251); L0 identical agent turns (#235); L1 synonym retention (#249) and serve-path verifier (#209)
- Extension site profiles for in-page chat widgets (#250); eval CI floors (#248); competitive / load / LiteLLM benches (#207, #210, #216, #218, #245)
- GTM scoreboard, shipping-note drafts, vs LiteLLM/Ollama/OpenRouter pages, Discussions templates (#230–#240, #246)
- Config runtime setattr validation (#221); OIDC ES256 JWKS (#219); Windows-via-WSL2 setup honesty (#267)
- Autodev reliability: backlog picker off search index, abandoned `agent:working` sweep, DIRTY/auto-merge stall detection, intended-labels workflow (#254, #255, #273, #305/#306, #310, #330/#336)
- PRD gap-scan cycles and enterprise ENTERPRISE.md (#274, #280, #290–#298, #322, #335)

## Validation

- Default suite: **1480 passed** (`pytest -m "not integration and not benchmark" -q`) on this branch
- Supply-chain path: `docker.yml` cosign + SBOM + provenance steps present; verified against [RELEASING.md](RELEASING.md)
- No tag / GitHub release / PyPI / ghcr publish from the preparing agent

## Upgrade notes

Follow the fleet guide: **[Upgrade and config migration](developer/guides/operations/upgrade.md)** (#316). Summary for operators coming from v1.3.0:

- **License:** v1.4.0 is Apache 2.0. v1.3.0 artifacts remain PolyForm NC; switch install pins / legal review accordingly.
- **Images:** prefer `ghcr.io/naveenreddyalka/daari:v1.4.0` and verify the cosign signature / SBOM when your policy requires it.
- **New / notable config keys** (all nested → ignored by older daari; safe to leave when rolling back):
  - `server.sse_keepalive_seconds` (default `10`; `0` disables)
  - `routing.reasoning_effort_escalation` (default `false`)
  - `routing.shadow_compare_tier`, `routing.shadow_daily_usd`, `routing.shadow_sample_rate`
  - `routing.local_pool.backends[].kind: openai` (OpenAI-compat local backends)
  - `observability.retention.{traces,ledger,audit,shadow,tasks}_days` (default `0` = keep forever)
  - `mcp` / Tasks settings (`mcp_tasks`) and MCP tool governance / guardrail policy
  - Provider and org secret fields may use `secret://…` / `secret://oauth/…` instead of plaintext
- **CLI:** `daari service install [--now]`, `daari service restart`, `daari onboard`, `daari prune`
- **Helm:** bump `image.tag` to `1.4.0` with `--atomic` as in the upgrade guide
- Nested additions are downgrade-safe; do not introduce a **new top-level** config section if you may roll back to v1.3.0 without restoring `config.yaml`
