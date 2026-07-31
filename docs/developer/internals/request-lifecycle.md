# Request lifecycle

```mermaid
sequenceDiagram
  participant C as Client
  participant S as server/app
  participant G as gateway adapter
  participant B as boundaries/guardrails
  participant R as Router.route
  participant L as ledger/trace
  C->>S: HTTP
  S->>S: Auth middleware
  S->>G: Parse wire format
  G->>B: InternalRequest
  B->>R: Allowed request
  R->>R: L0 to L6 pipeline
  R->>L: Record meta
  R->>G: InternalResponse
  G->>C: JSON or SSE
```

Key types: `InternalRequest`, `InternalResponse`, `DaariMeta` in `daari/gateway/internal.py`.

`AppContext.from_settings` builds caches, executors, guardrails, and `BoundaryEngine`. Hot reload of boundaries/config editor calls `engine_from_settings` again.
