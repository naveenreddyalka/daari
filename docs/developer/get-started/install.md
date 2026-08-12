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

## Option C — Homebrew or pip

!!! warning "Neither works yet — use Option A or B"
    `pip install daari` fails because nothing is published to PyPI, and
    `brew install daari` fails because there is no tap. Installing the checked-in
    formula by path fails too: Homebrew 6 rejects formulae outside a tap.

The formula at [`Formula/daari.rb`](https://github.com/naveenreddyalka/daari/blob/main/Formula/daari.rb)
is otherwise complete — real tarball hash, all 30 dependency resources, checksums
verified. What remains is publishing, tracked in
[#160](https://github.com/naveenreddyalka/daari/issues/160): a PyPI trusted
publisher and a public tap repo. See [Homebrew notes](../../setup/homebrew.md).

## Verify

```bash
curl -fsS http://127.0.0.1:11435/health
curl -fsS http://127.0.0.1:11435/ready
daari doctor
```

## Next

→ [Quickstart](quickstart.md) · [First client](first-client.md)
