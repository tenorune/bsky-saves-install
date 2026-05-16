# bsky-saves-install

Native installers for the `bsky-saves` local helper. The third leg of
the `bsky-saves` / `bsky-saves-gui` / `bsky-saves-install` trio.

## Status

**v0.1 — dogfood milestone.** macOS only, unsigned, intended for the
maintainer's own use. See
`docs/superpowers/specs/2026-05-16-bsky-saves-install-v0.1-design.md`
for the full design.

## Running the unsigned v0.1 build on macOS

Because the `.app` is unsigned, macOS Gatekeeper blocks first launch
with "Bsky Saves can't be opened because Apple cannot check it for
malicious software." Bypass once per install:

1. Right-click (or Control-click) `Bsky Saves.app` in `Applications`.
2. Choose **Open** from the context menu.
3. In the dialog, click **Open** again.

Subsequent launches do not prompt.

## Development

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check
```

## License

MIT