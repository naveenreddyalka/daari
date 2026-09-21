# Local text-to-speech

**Outcome:** `POST /v1/audio/speech` stays on the machine. Point daari at Kokoro, openedai-speech, or any OpenAI-compatible TTS server.

## Config

`tts.base_url` is an OpenAI-compatible API root (it includes `/v1`), the same shape as `asr.base_url`. Point it at a local speech stack that already serves `POST /v1/audio/speech`. No TTS package is installed with daari.

```yaml
tts:
  base_url: http://127.0.0.1:8880/v1
  model: ""    # optional; when set, replaces the client model
  voice: ""    # optional default when the request omits voice
```

Leave `base_url` empty and the route returns **501**. `daari doctor` stays quiet in that case. It warns when `tts.base_url` is set but `GET {base}/models` is unreachable.

Helm fleets can set `tts.baseUrl`. Optional chart values `tts.model` / `tts.voice` mount `DAARI_TTS__MODEL` / `DAARI_TTS__VOICE` so the pod always presents the on-box id (see [Capacity and Helm](../operations/capacity-helm.md)).

## Request

OpenAI JSON body: `model` (required unless `tts.model` is set), `input` (non-empty text), optional `voice` (falls back to `tts.voice`, then `alloy`), and `response_format` (for example `mp3`). The response is raw audio bytes with a matching `Content-Type`.

Auth, virtual-key request budgets, rate limits, model allowlists, and `X-Daari-Deadline-Ms` apply the same way as other gated routes. A key or team model allowlist is checked against the resolved model before any upstream call. Leave `base_url` empty and the route returns **501** without calling a cloud TTS API.

## Verify

```bash
curl -sS http://127.0.0.1:11435/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"model":"tts-1","input":"hello from daari","voice":"alloy"}' \
  -o /tmp/daari-speech.mp3
```

With `tts.base_url` set, the file is non-empty audio. With nothing configured, the same call returns 501.

## Next

→ [Speech-to-text](asr.md) · [Capacity and Helm](../operations/capacity-helm.md) · [Chargeback](../observability/chargeback.md)
