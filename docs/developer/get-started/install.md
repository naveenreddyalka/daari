# Install

**Outcome:** daari CLI available and ready to `daari serve`.

## Option A — Docker Compose (recommended)

Bundles Ollama + model pull + daari:

```bash
git clone https://github.com/naveenreddyalka/daari.git
cd daari
docker compose up
```

Daemon: `http://127.0.0.1:11435`. Readiness: `GET /ready`. Image: `ghcr.io/naveenreddyalka/daari`.

Optional profiles:

```bash
docker compose --profile org up          # org-cache on :11436
docker compose --profile backends up -d  # Redis + Postgres
```

## Option B — from source

```bash
git clone https://github.com/naveenreddyalka/daari.git && cd daari
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# optional extras: pip install -e ".[redis,postgres,oidc,otel]"
ollama pull llama3.2:3b
daari serve
```

## Option C — Homebrew

!!! warning "Not published yet"
    There is no `daari` package on PyPI and no Homebrew tap yet, so
    `pip install daari` and `brew install daari` both fail. Use Option A or B.

The formula is checked in at [`Formula/daari.rb`](https://github.com/naveenreddyalka/daari/blob/main/Formula/daari.rb) and works today from a clone:

```bash
brew install --HEAD --formula ./Formula/daari.rb
```

A public tap needs a release tarball to hash — see [Homebrew notes](../../setup/homebrew.md).

## Verify

```bash
curl -fsS http://127.0.0.1:11435/health
curl -fsS http://127.0.0.1:11435/ready
daari doctor
```

## Next

→ [Quickstart](quickstart.md) · [First client](first-client.md)
