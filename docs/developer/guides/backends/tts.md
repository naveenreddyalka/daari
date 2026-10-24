# Local text-to-speech

**Outcome:** `POST /v1/audio/speech` stays on the machine. Point daari at **Ollama 0.40.9+ Phonon**, Kokoro, openedai-speech, or any OpenAI-compatible TTS server.

## Config

`tts.base_url` is an OpenAI-compatible API root (it includes `/v1`), the same shape as `asr.base_url`. Point it at a local speech stack that already serves `POST /v1/audio/speech`. No TTS package is installed with daari.

```yaml
tts:
  base_url: http://127.0.0.1:11434/v1   # Ollama Phonon (0.40.9+); or Kokoro/openedai-speech
  model: ""    # optional; when set, replaces the client model
  voice: ""    # optional default when the request omits voice
```

**Ollama Phonon (local-first):** as of Ollama **0.40.9**, the same daemon that serves chat tiers exposes streaming `POST /v1/audio/speech`. Set `tts.base_url` to `{ollama.base_url}/v1` (for example `http://127.0.0.1:11434/v1`). daari does not auto-wire this — `daari doctor` tips when TTS is empty and Ollama reports a speech-capable version.

Leave `base_url` empty and the route returns **501**. `daari doctor` stays quiet when Ollama is unreachable or older than 0.40.9. It warns when `tts.base_url` is set but `GET {base}/models` is unreachable.

Helm fleets can set `tts.baseUrl`. Optional chart values `tts.model` / `tts.voice` mount `DAARI_TTS__MODEL` / `DAARI_TTS__VOICE` so the pod always presents the on-box id (see [Capacity and Helm](../operations/capacity-helm.md)).

## Request

OpenAI JSON body: `model` (required unless `tts.model` is set), `input` (non-empty text), optional `voice` (falls back to `tts.voice`, then `alloy`), and `response_format` (for example `mp3`). The response is raw audio bytes with a matching `Content-Type`. When the upstream uses chunked transfer (Ollama Phonon), daari **streams** those bytes to the client as they arrive; backends that send a fixed `Content-Length` stay fully buffered.

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
