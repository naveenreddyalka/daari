# Homebrew install

> Issue [#123](https://github.com/naveenreddyalka/daari/issues/123) · formula at [`Formula/daari.rb`](../../Formula/daari.rb)

## From this repo (development)

```bash
brew install --formula ./Formula/daari.rb
```

The published `sha256` is a placeholder until a PyPI/GitHub release asset is hashed — for head installs use:

```bash
brew install --HEAD --formula ./Formula/daari.rb
```

## After the public tap

```bash
brew tap naveenreddyalka/daari
brew install daari
```

Requires Python 3.12 from Homebrew. Then:

```bash
ollama pull llama3.2:3b
daari serve
```

Prefer `pip install daari` / `docker compose up` until the tap sha256 is filled in from a real release tarball.
