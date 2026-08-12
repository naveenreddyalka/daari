> Install overview: [Get started → Install](../developer/get-started/install.md)

# Homebrew install

> Tap: [naveenreddyalka/homebrew-daari](https://github.com/naveenreddyalka/homebrew-daari) · formula source at [`Formula/daari.rb`](https://github.com/naveenreddyalka/daari/blob/main/Formula/daari.rb)

## Install

```bash
brew tap naveenreddyalka/daari
brew trust naveenreddyalka/daari
brew install daari
```

Then pull a local model and start the daemon:

```bash
ollama pull llama3.2:3b
daari serve
daari doctor
```

## Why `brew trust` is required

Homebrew 6 refuses to load a formula from a third-party tap until it is trusted:

```console
$ brew info daari
Error: Refusing to load formula naveenreddyalka/daari/daari from untrusted tap naveenreddyalka/daari.
Run `brew trust --formula naveenreddyalka/daari/daari` or `brew trust naveenreddyalka/daari` to trust it.
```

This is a deliberate Homebrew safeguard, not a problem with the tap. Trust is
per-machine, so each new install needs it once.

## What the formula builds

daari itself is pure Python, but two dependencies ship Rust extensions —
`pydantic-core` and `watchfiles` — and the formula builds them from sdist, hence
`depends_on "rust" => :build`. Expect the first install to pull the Rust
toolchain.

The formula declares a `resource` block for all 30 transitive runtime
dependencies. Homebrew builds without network access, so
`virtualenv_install_with_resources` installs only what is declared; a missing
resource produces a `daari` that cannot import its own dependencies.

## Maintaining the formula

Never hand-edit it. Both the release tarball hash and every resource block are
generated:

```bash
python scripts/update_formula.py --version X.Y.Z
```

Then copy the result into the tap repo. The `formula` job in `publish.yml` opens a
PR with the regenerated file after each release.

To validate changes without touching the public tap, use a throwaway local tap —
`brew fetch` verifies every checksum and installs nothing:

```bash
brew tap-new --no-git naveenreddyalka/formulatest
cp Formula/daari.rb "$(brew --repository naveenreddyalka/formulatest)/Formula/"
brew fetch --formula --build-from-source naveenreddyalka/formulatest/daari
brew untap naveenreddyalka/formulatest
```

## Next

→ [Install options](../developer/get-started/install.md) · [Releasing](../RELEASING.md)
