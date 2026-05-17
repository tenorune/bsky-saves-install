# bsky-saves-install

Native installers for the `bsky-saves` local helper.

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

Requires Python 3.13+ and **pip ≥ 23** (hatchling editable installs use
PEP 660, which older pip versions don't support). Upgrade pip first if
your venv ships an older one — the macOS python.org installer is a
common offender.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
pytest
ruff check
```

## Wheel pinning

The bundled `bsky-saves` version is pinned in two files at the repo
root:

- `wheel-version.txt` — version string (e.g. `0.7.0`).
- `wheel.sha256` — expected SHA-256 of the wheel file.

The release workflow runs `scripts/fetch_wheel.py`, which downloads
`bsky_saves-{version}-py3-none-any.whl` from PyPI and aborts if the
SHA does not match. The all-zero SHA sentinel
(`0000000000000000000000000000000000000000000000000000000000000000`)
is the "pin not yet set" marker — release builds will fail loudly
until both files are updated to point at a real published wheel.

Pin updates arrive via `repository_dispatch` from
`tenorune/bsky-saves` (see
`.github/workflows/wheel-version-bump.yml`) as auto-PRs that need
human review.

## Design

See `docs/superpowers/specs/2026-05-16-bsky-saves-install-v0.1-design.md`
for the full design spec.

## License

MIT
