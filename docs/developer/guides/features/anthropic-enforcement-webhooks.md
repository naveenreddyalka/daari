# Anthropic organization enforcement webhooks

**Outcome:** When Anthropic restricts or bans a user profile, daari learns within
seconds (push) instead of waiting for the next `enforcement-sync` poll.

## Enable

1. Create an organization webhook in the Anthropic Admin API
   (`POST /v1/organizations/webhooks`, beta `webhooks-2026-10-07`) pointing at:

   ```text
   https://<your-daari-host>/v1/daari/webhooks/anthropic/org
   ```

   Subscribe to `user_profile.enforcement_action_opened` and
   `user_profile.enforcement_action_resolved`. Store the returned `whsec_…`
   signing secret immediately — Anthropic shows it only once.

2. Configure daari:

   ```yaml
   anthropic:
     user_profiles:
       erin: uprof_011CZkZCu8hGbp5mYRQgUmz9
     org_webhook_signing_secret: whsec_...
     # optional during rotation:
     # org_webhook_signing_secret_previous: whsec_old...
     enforcement_state_path: ~/.daari/anthropic-enforcement.json
   ```

3. Keep a frontier Anthropic Admin API key configured so the ingress handler can
   `GET /v1/user_profiles/{id}` for current `enforcement_status` /
   `enforcement_actions`. Without a key, opened events still cache a conservative
   `restricted` row; resolved events clear the profile from local state.

Empty `org_webhook_signing_secret` disables the route (**404**). Mis-signed
payloads return **401**. Unknown event types are acknowledged (**200**) and
ignored.

The path is auth-open for Anthropic deliveries; authenticity is the Standard
Webhooks signature (`webhook-id`, `webhook-timestamp`, `webhook-signature`).

## Rotate the signing secret

1. Regenerate the secret in the Anthropic Admin API.
2. Set `org_webhook_signing_secret` to the new value and
   `org_webhook_signing_secret_previous` to the old `whsec_…` value.
3. After Anthropic stops signing with the old secret, clear
   `org_webhook_signing_secret_previous`.

## Verify

- `GET /v1/daari/anthropic/enforcement` (analyst+) shows cached profiles.
- Gateway events: `anthropic.enforcement_webhook_ingested`, plus
  `anthropic.enforcement_started` / `anthropic.enforcement_ended` on transitions.
- Prometheus / doctor continue to read the same
  `anthropic.enforcement_state_path` as `daari anthropic enforcement-sync`.

## Next

→ [Config reference](../../reference/config.md) · [HTTP API](../../reference/http-api.md)
· CLI `daari anthropic enforcement-sync` for poll backfill
