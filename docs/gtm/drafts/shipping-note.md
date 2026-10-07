# Shipping note — daari 1.4.0

Apache 2.0, supply chain & enterprise gateway — ~70 commits since v1.3.0: Apache 2.0 relicense, cosign-signed ghcr images with SBOM/provenance, MCP governance/guardrails/Tasks, `secret://` (+ oauth), OpenAI-compat local backends, FinOps headers, fleet upgrade guide. See [RELEASE-v1.4.0.md](https://github.com/naveenreddyalka/daari/blob/main/docs/RELEASE-v1.4.0.md).

- Relicensed the tree back to [Apache 2.0](https://github.com/naveenreddyalka/daari/blob/main/LICENSE) ([#227](https://github.com/naveenreddyalka/daari/issues/227) / [#293](https://github.com/naveenreddyalka/daari/pull/293), [ADR-0016](https://github.com/naveenreddyalka/daari/blob/main/docs/adr/0016-apache-2-relicense.md)). v1.3.0 as tagged remains PolyForm NC.
- Signed ghcr images with cosign (keyless), Syft SBOM, and SLSA provenance ([#311](https://github.com/naveenreddyalka/daari/pull/311)).
- MCP tool governance (#307), guardrails on tools/call (#325), Tasks extension (#315)
- `secret://` refs (#314) and `secret://oauth` (#329); cost-split (#308) and budget-remaining (#327) headers; stream usage counted once (#328)
- OpenAI-compat local backend kind (#303); shadow evals (#326); `reasoning_effort` (#312); SSE keepalive (#304); agent prefix L1 (#299)
- Fleet upgrade guide (#316); retention/prune (#338); virtual key expiry (#337); `daari service` install/restart (#266/#300/#324)

Docs: https://naveenreddyalka.github.io/daari/
Repo: https://github.com/naveenreddyalka/daari

Apache 2.0 — OSI open source.

This file is a draft. A human publishes it. Do not auto-post to HN, Reddit, or X.

## X draft

daari 1.4.0: Apache 2.0, supply chain & enterprise gateway — ~70 commits since v1.3.0: Apache 2.0 relicense, cosign-signed ghcr image https://naveenreddyalka.github.io/daari/ (Apache 2.0)

## LinkedIn draft

Shipped daari 1.4.0. Apache 2.0, supply chain & enterprise gateway — ~70 commits since v1.3.0: Apache 2.0 relicense, cosign-signed ghcr images with SBOM/provenance, MCP governance/guardrails/Tasks, `secret://` (+ oauth), OpenAI-compat local backends, FinOps headers, fleet upgrade guide. See [RELEASE-v1.4.0.md](https://github.com/naveenreddyalka/daari/blob/main/docs/RELEASE-v1.4.0.md). Install: pip install daari. https://naveenreddyalka.github.io/daari/ Apache 2.0 — OSI open source.
