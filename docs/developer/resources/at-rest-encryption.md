# At-rest encryption

Optional AES-GCM envelope encryption for persisted **payload** stores
([#1958](https://github.com/naveenreddyalka/daari/issues/1958)). The operator
holds the key via plaintext config or a [`secret://`
reference](../guides/configuration/auth-and-keys.md#secret-references-secret);
daari never ships a cloud KMS dependency for this path.

## What is covered

When `security.at_rest_key` is set, **new writes** encrypt:

| Store | Fields |
|-------|--------|
| Responses (SQLite / Postgres) | `body`, `conversation` |
| Gateway request log (JSONL / Postgres) | event payload (`_enc` on JSONL) |
| L0 exact disk cache | cached response value (`v`) |
| L1 semantic disk cache | `response_json`, `prompt_text` |
| Files (disk / Postgres) | uploaded file `content` bytes |
| Batches (SQLite / Postgres) | job `payload` (per-item request/response bodies) |

Out of scope: virtual-key hashes, audit chain, usage ledger.

## Setup

```yaml
security:
  at_rest_key: secret://env-file/~/.daari/secrets.env#AT_REST_KEY
```

Or env: `DAARI_SECURITY__AT_REST_KEY=…`. Empty (default) leaves behavior
unchanged — no migration, existing plaintext rows keep working.

On Kubernetes, mount the key from a Secret via the Helm chart
(`security.atRestKeySecret` / `security.atRestKeyPreviousSecret` →
`DAARI_SECURITY__AT_REST_KEY` / `_PREVIOUS`); see
[Capacity and Helm](../guides/operations/capacity-helm.md).

`daari doctor` reports `at_rest_encryption` on/off for those stores.

## Rotation

1. Generate a new key.
2. Set `security.at_rest_key` to the new value and
   `security.at_rest_key_previous` to the old one (mirrors webhook dual-secret
   rotation).
3. Restart the daemon. New writes use the current key; reads try current then
   previous.
4. After old ciphertext is rewritten or aged out, clear
   `at_rest_key_previous`.

Wrong or missing keys on tagged rows **fail closed** — callers see a clear
decrypt error, never raw ciphertext.
