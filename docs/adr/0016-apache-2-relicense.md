# ADR-0016: Relicense the tree to Apache 2.0

Date: 2026-08-31
Status: accepted

## Context

daari shipped Apache 2.0 from the first commit through v1.2.0. [#202](https://github.com/naveenreddyalka/daari/issues/202) moved `main` to PolyForm Noncommercial 1.0.0 so commercial use needed a separate license. [#227](https://github.com/naveenreddyalka/daari/issues/227) asked whether to keep NC, split daemon vs fleet, or return the whole tree to an OSI license.

Visibility is blocked by distribution, not SPDX — but NC also blocked saying “open source,” and enterprises cannot evaluate the daemon next to MIT LiteLLM. The maintainer chose a full OSI return, not the hybrid.

## Decision

The entire repository is licensed under **Apache License 2.0**.

- Not the hybrid (Apache daemon / commercial fleet).
- Not MIT. Apache matches v1.2.0 and includes the patent grant.
- Public copy may say **open source**. It must not describe the current license as PolyForm Noncommercial or “source-available.”
- v1.3.0 as released remains a PolyForm NC artifact; this ADR applies to `main` after this change.

## Consequences

Anyone may use, modify, and sell daari, including a hosted competitor. Commercial-license revenue from the daemon is off the table unless a later ADR carves features out. CONTRIBUTING grants are Apache 2.0 only. PyPI classifier and Homebrew `license` must stay `Apache-2.0`.
