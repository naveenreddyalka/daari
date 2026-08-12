> Install overview: [Get started → Install](../developer/get-started/install.md)

# Homebrew install

> Issue [#160](https://github.com/naveenreddyalka/daari/issues/160) · formula at [`Formula/daari.rb`](https://github.com/naveenreddyalka/daari/blob/main/Formula/daari.rb)

## Not available yet

`brew install daari` does not work, and neither does installing the checked-in
formula directly. Use [Docker Compose or the from-source
install](../developer/get-started/install.md) instead.

Two things are missing, and both need a maintainer:

**A tap repository.** Homebrew 6 refuses to install a formula that is not in a
tap, so a path-based install now fails outright:

```console
$ brew install --formula ./Formula/daari.rb
Error: Homebrew requires formulae to be in a tap, rejecting:
```

Shipping `brew install daari` therefore needs a public
`naveenreddyalka/homebrew-daari` repository holding this formula. That repo does
not exist yet, so `brew tap naveenreddyalka/daari` also fails.

**A PyPI release.** Tracked in [#160](https://github.com/naveenreddyalka/daari/issues/160).

## What is ready

The formula itself is complete. It carries the real sha256 for the v1.2.0 release
tarball and a `resource` block for all 30 transitive runtime dependencies —
required because Homebrew builds without network access, so
`virtualenv_install_with_resources` installs only what is declared. Every checksum
is verified against upstream.

Both the tarball hash and the resource blocks are generated, never hand-edited:

```bash
python scripts/update_formula.py --version X.Y.Z
```

## Validating the formula before a tap exists

A throwaway local tap is enough to check it. `brew fetch` downloads and verifies
every checksum without installing anything:

```bash
brew tap-new --no-git naveenreddyalka/formulatest
cp Formula/daari.rb "$(brew --repository naveenreddyalka/formulatest)/Formula/"
brew fetch --formula --build-from-source naveenreddyalka/formulatest/daari
brew untap naveenreddyalka/formulatest
```

A full `brew install` from that tap additionally compiles the Rust extensions in
`pydantic-core` and `watchfiles`, which is why the formula declares
`depends_on "rust" => :build`. Expect it to pull the Rust toolchain.

## Next

→ [Releasing](../RELEASING.md) for the maintainer steps · [Install options](../developer/get-started/install.md)
