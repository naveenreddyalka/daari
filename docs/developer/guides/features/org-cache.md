# Org shared cache

**Outcome:** Run a shared cache/learning service for multiple daari daemons.

## Steps

```bash
docker compose --profile org up
# or
daari org-cache serve --host 0.0.0.0 --port 11436
```

Point clients via enterprise / org settings (cache URL + token). Fleet bootstrap:

```bash
daari enterprise bootstrap --org-config <signed-url>
```

## Verify

`GET http://127.0.0.1:11436/health`; after local L0 miss, traces may show org cache tiers.

## Next

→ [Capacity and Helm](../operations/capacity-helm.md) · [ADR-0014](../../../adr/0014-enterprise-distributed-org-learning.md)
