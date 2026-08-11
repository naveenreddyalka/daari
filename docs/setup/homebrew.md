> Install overview: [Get started → Install](../developer/get-started/install.md)

# Homebrew install

> Issue [#123](https://github.com/naveenreddyalka/daari/issues/123) · formula at [`Formula/daari.rb`](https://github.com/naveenreddyalka/daari/blob/main/Formula/daari.rb)

## From this repo (development)

Clone the repo, then install from `HEAD`:

```bash
brew install --HEAD --formula ./Formula/daari.rb
```

Requires Python 3.12 from Homebrew. Then:

```bash
ollama pull llama3.2:3b
daari serve
```

## Not working yet

`brew install --formula ./Formula/daari.rb` (without `--HEAD`) fails: the formula's
`sha256` is a placeholder, so the v1.2.0 tarball fails its checksum. The public tap
below is also unavailable — the tap repo does not exist yet.

```bash
# blocked on a release: needs a hashed tarball pushed to homebrew-daari
brew tap naveenreddyalka/daari
brew install daari
```

Both unblock once a release tarball is published and its hash replaces the
placeholder in `Formula/daari.rb`. Until then use `docker compose up` or the
from-source install — daari is not on PyPI either, so `pip install daari` fails.
