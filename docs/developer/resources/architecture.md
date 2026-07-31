# Architecture (overview)

daari is a single local daemon: **adapters → optional boundaries/guardrails → Router tiers → ledger/traces**.

- Detailed engineer view: [Internals](../internals/index.md)
- Full historical map: [docs/ARCHITECTURE.md](../../ARCHITECTURE.md) (may lag features — prefer code + this site)
- Decisions: [ADRs](../../adr/README.md)

Default listen address: `127.0.0.1:11435`. Org cache optional on `:11436`.
