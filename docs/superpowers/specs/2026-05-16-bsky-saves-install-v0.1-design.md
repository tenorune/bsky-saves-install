# `bsky-saves-install` v0.1 — design spec

**Status:** approved (brainstorming session, 2026-05-16)
**Milestone:** dogfood (v0.1.0)
**Authors:** Claude (drafting), tenorune (decisions)

## 1. Scope & milestones

### Repo purpose

`tenorune/bsky-saves-install` produces native installers that bundle
`bsky-saves` (the helper daemon, which in turn already vendors
`bsky-saves-gui` inside its wheel) so non-Python users can run the
local helper. It is the third leg of the trio described in the
bootstrap briefs (`docs/bootstrap-from-gui.md`,
`docs/bootstrap-from-core.md`) and sits one hop downstream of
`bsky-saves`.

### Dogfood milestone (this spec — installer v0.1.0)

- **Single platform: macOS.** Apple Silicon + Intel universal, or
  arm64-only if simpler — to be settled at build time, not in this
  spec.
- **Unsigned `.app` wrapped in a `.dmg`.** Documented
  right-click → Open Gatekeeper bypass.
- **Full launcher present from day one:** pystray menu-bar icon +
  Tkinter status window opened from the tray. The *surfaces* are in
  place in v0.1; the *contents* of the status window are deferred to
  a follow-up spec.
- **Tray menu (v0.1):** "Open GUI" (opens
  `http://127.0.0.1:47826/`, the wheel's bundled pre-paired local
  GUI), "Quit" (terminates the helper subprocess, exits the
  launcher).
- **Bundled helper:** a pinned `bsky-saves` wheel; target version
  `bsky-saves v0.7.0` (reserved by the helper team for this
  milestone). If v0.7.0 is not on PyPI at build time, pin to the
  latest available and bump on release.
- **Distribution:** artifact attached to a GitHub Release on this
  repo. No external channels (brew/winget/AUR/AppImage stores) yet.
- **Audience:** pure dogfood — the user (tenorune) is the only
  intended consumer of v0.1.

### Public-release milestone (later spec, not in v0.1)

Widen to Windows + Linux, add Apple Developer ID + Authenticode
signing, add autostart toggle, add update notification, add the
"Open hosted version" tray item that opens `saves.lightseed.net`,
add external distribution channels, target the non-technical user
segment from the fleet table in
`docs/bootstrap-from-gui.md` §3.

**Apple Developer Program enrollment** is a tracked parallel human
action item so certs are ready when we transition from dogfood to
public-release. See § 6.

## 2. Architecture

### Process tree at runtime

```
[user opens Bsky Saves.app]
└─ launcher process (Python, frozen by Briefcase)
   ├─ pystray thread          → macOS menu-bar icon + menu (Open GUI, Quit)
   ├─ Tkinter status window   → opened on demand from the tray
   └─ bsky-saves serve        → child subprocess, binds 127.0.0.1:47826
                                serves API + bundled GUI from the wheel
```

### Boundaries

- **Launcher** owns: the macOS app lifecycle, the tray icon and menu,
  the status window, the subprocess. Depends on `pystray`, `tkinter`
  (stdlib), and OS-delivered tray clicks.
- **Subprocess (`bsky-saves serve`)** owns: the HTTP API, the
  bundled GUI, token storage. The launcher does not reach into the
  helper's internals — it spawns it, captures its output, and
  terminates it.

### Interface between launcher and helper (v0.1)

1. The subprocess command line and environment.
2. The captured stdout/stderr stream.
3. The `127.0.0.1:47826` HTTP endpoint, hit with `GET /ping` for
   liveness — the same endpoint the GUI uses.
4. POSIX signals (`SIGTERM` on Quit).

The launcher does not reach into helper process memory or files. The
unit-isolation principle stands.

### Extension path (later versions)

When the launcher needs richer control over the helper (graceful
restart on port change, runtime allow-origin toggle, log-level
adjustment, "rotate token" button, etc.), the architecturally
correct shape is to **enrich the helper's HTTP API** with a
namespaced control surface (e.g. `/control/*` or `/admin/*`),
authenticated with the same bearer token the GUI already uses, owned
and versioned by the helper team. The launcher calls those
endpoints; it does not invent a side channel (named pipe, IPC
socket, direct file access).

The `protocol` and `features[]` fields on `/ping` are the natural
capability-negotiation channel — the launcher reads them to
discover which control endpoints exist in the bundled helper
version.

v0.1 ships no such control endpoints. Stating the path explicitly
keeps future patterns from eroding the boundary.

### Lifecycle

- **Launch:** launcher starts → spawns `bsky-saves serve` as
  child → polls `GET /ping` until 200 (with timeout) → tray icon
  enters "running" state. If the subprocess exits before `/ping`
  succeeds, surface captured stderr in an error dialog and quit.
- **Steady state:** launcher captures subprocess stdout/stderr into
  a bounded ring buffer (200 lines) for the future log-tail UI. The
  capture exists in v0.1 even though no widget renders it yet — so
  the follow-up spec adds a view, not a capture pipeline.
- **Quit:** launcher sends `SIGTERM` → waits up to 5 s → `SIGKILL`
  fallback → exits.
- **Helper crash mid-session:** launcher detects subprocess exit,
  switches tray icon to "stopped" state, surfaces captured stderr
  in the status window. **No auto-restart in v0.1.**

### Critical helper-side invariants the launcher must preserve

- Runs **as the user**, never as root. Briefcase `.app` bundles
  naturally run as the launching user; we add no privileged
  component, no post-install script, no escalation.
- The subprocess inherits the launcher's env unchanged. The
  launcher does not override `XDG_CONFIG_HOME`,
  `BSKY_SAVES_CONFIG_DIR`, or any path env. The token file lands at
  `~/Library/Application Support/bsky-saves/token` (the
  platform-conventional path the helper expects), with `0o600`
  perms managed by the helper itself.
- Port defaults to the helper's `47826`. **Port-collision recovery
  is out of scope for v0.1** — if a peer `bsky-saves` (e.g. from
  `pipx install`) is already bound, the helper fails to bind and
  the launcher surfaces the error. Documented as a known v0.1
  limitation.

## 3. Components

Five units, each with one purpose and a named interface.

### 3.1 `scripts/fetch_wheel.py` — wheel pinning & fetch

- **Purpose.** Deterministically obtain the `bsky-saves` wheel that
  will be frozen into the `.app`.
- **Inputs.** `wheel-version.txt` (string, the version to fetch)
  and `wheel.sha256` (hex digest, the expected SHA-256). Both
  committed to the repo root.
- **Behavior.** Download
  `bsky_saves-{WHEEL_VERSION}-py3-none-any.whl` from PyPI, verify
  SHA-256 against the pinned digest, place in a local `wheelhouse/`
  directory. Abort with non-zero exit on mismatch.
- **Dependencies.** `httpx` (or stdlib `urllib`); `hashlib`.
- **Consumer.** The Briefcase build step and `release.yml` call this
  before `briefcase build`.

### 3.2 `src/bsky_saves_launcher/supervisor.py` — subprocess supervisor

- **Purpose.** Own the `bsky-saves serve` child process across the
  launcher's lifetime.
- **In-process interface.** `start()`, `stop(timeout=5.0)`,
  `is_alive() -> bool`, `recent_logs() -> list[str]` (last N lines
  from the ring buffer), and an event callback for subprocess exit
  so the tray icon can react.
- **Behavior.** Spawn `bsky-saves serve` with inherited env and CWD.
  Attach two reader threads (stdout/stderr) feeding a thread-safe
  bounded ring buffer (200 lines). On `stop()`, send `SIGTERM`,
  wait, fall back to `SIGKILL` if needed. Liveness via `GET
  http://127.0.0.1:47826/ping` with a short timeout.
- **Dependencies.** stdlib `subprocess`, `threading`,
  `collections.deque`; `httpx` (already a wheel transitive dep).

### 3.3 `src/bsky_saves_launcher/tray.py` — menu-bar icon

- **Purpose.** Render the macOS menu-bar icon and dispatch its menu
  items.
- **In-process interface.** Constructor takes a supervisor handle
  and a callback to open the status window. `run()` blocks on the
  pystray event loop.
- **v0.1 menu items.** "Open GUI" → `webbrowser.open(
  "http://127.0.0.1:47826/")`. "Quit" → `supervisor.stop()` then
  exit the process. Left-click on the icon → invoke the
  open-status-window callback.
- **Icon states.** "running" (helper `/ping` succeeds), "starting"
  (subprocess up, `/ping` not yet 200), "stopped" (subprocess
  exited). Visual treatment of the three states is deferred to the
  status-window-contents follow-up spec.
- **Dependencies.** `pystray`, `Pillow` (pystray requirement),
  stdlib `webbrowser`.

### 3.4 `src/bsky_saves_launcher/status_window.py` — Tkinter status window

- **Purpose.** Show launcher/helper state on demand.
- **In-process interface.** `open(supervisor)` — creates the window
  if not already open, focuses it if it is. Reads from
  `supervisor.recent_logs()` and the helper's `/ping` response.
- **v0.1 contents.** Deferred. The module exists, the window
  renders with a placeholder, and the tray's "open status" gesture
  is wired up. Widget-level design lives in the follow-up spec; no
  non-trivial widget code lands in v0.1.
- **Dependencies.** `tkinter` (stdlib).

### 3.5 `src/bsky_saves_launcher/app.py` — entry point

- **Purpose.** Wire the other four units together.
- **Behavior.** Instantiate the supervisor → `start()` → instantiate
  the tray with supervisor + status-window opener → run tray event
  loop on the main thread (pystray on macOS requires the main
  thread). On tray exit, ensure supervisor is stopped.

### 3.6 What ships inside the `.app`

A single `.dmg` download is everything the user needs:

- **Python runtime** — bundled by Briefcase (its python.org-support
  builds). User does not need any system Python.
- **Launcher code** — the five units above.
- **Launcher Python deps** — `pystray`, `Pillow`, `httpx`, transitive.
- **`bsky-saves` wheel** — pinned + SHA-verified, with all runtime
  deps (`httpx`, `trafilatura`, lxml C extensions, etc.).
  Platform-correct wheels resolved at build time.
- **Bundled GUI** — automatically, because it is already vendored
  inside the `bsky-saves` wheel at `src/bsky_saves/_gui/`.
- **Tkinter** — Briefcase's macOS Python supports Tk.

Not in the bundle (user-side prerequisites): a web browser (every
macOS install has one) and macOS itself at whatever minimum
Briefcase's Python support targets (currently macOS 11+).

**Size budget.** GUI bootstrap §4.7 calls out ≤ 80 MB compressed
per OS. Target, not hard gate. Investigate if `.dmg` lands much
above ~120 MB.

### 3.7 Repo layout

```
bsky-saves-install/
├── pyproject.toml              Briefcase config + project deps
├── wheel-version.txt           pinned bsky-saves version
├── wheel.sha256                pinned wheel SHA-256
├── wheelhouse/                 gitignored; populated by build script
├── scripts/
│   └── fetch_wheel.py          unit 3.1
├── src/
│   └── bsky_saves_launcher/
│       ├── __init__.py
│       ├── app.py              unit 3.5 (Briefcase entry point)
│       ├── supervisor.py       unit 3.2
│       ├── tray.py             unit 3.3
│       └── status_window.py    unit 3.4
├── tests/                      pytest, mirrors src/
├── docs/
│   ├── bootstrap-from-gui.md
│   ├── bootstrap-from-core.md
│   └── superpowers/specs/      this file
├── .github/workflows/
│   ├── ci.yml
│   ├── release.yml
│   └── wheel-version-bump.yml
└── README.md
```

## 4. Cross-repo contract

### Inbound: wheel version bump from `bsky-saves`

The `bsky-saves` repo's `release.yml` fires `repository_dispatch`
events on every tag push. We add a third receiver: this repo gets a
dispatch after each wheel publishes to PyPI.

Event payload shape:

```json
{
  "event_type": "wheel-version-bump",
  "client_payload": {
    "version":   "0.7.0",
    "sha256":    "abc123...",
    "wheel_url": "https://files.pythonhosted.org/packages/.../bsky_saves-0.7.0-py3-none-any.whl",
    "ref_name":  "v0.7.0"
  }
}
```

`.github/workflows/wheel-version-bump.yml` listens, re-verifies the
payload's `wheel_url` returns a file whose SHA-256 matches
`client_payload.sha256` (defense in depth — the helper side has
already verified), updates `wheel-version.txt` and `wheel.sha256`
on a branch, opens a PR using a fine-grained PAT.

**Never auto-merge.** Bump PRs go through human review to catch
helper-behavior changes that need launcher-side updates.

### Outbound: GitHub Release artifacts (v0.1)

For the dogfood milestone, the v0.1 release attaches:

- `bsky-saves-install-X.Y.Z-macos.dmg` — unsigned `.app` in a `.dmg`.
- `SHA256SUMS` — SHA-256 of the `.dmg`.

Deferred to public-release:

- Universal vs arch-specific naming (`-macos-universal.dmg` vs
  `-macos-arm64.dmg` / `-macos-x86_64.dmg`) — pick at build time.
- `.msi` for Windows, `.AppImage` for Linux, single-binary fallbacks.
- `SBOM.cdx.json` (CycloneDX).
- sigstore signatures.

### Installer versioning

The installer has its own version axis, distinct from `bsky-saves`
and `bsky-saves-gui`.

- v0.1.0 = dogfood milestone, first release.
- Subsequent dogfood iterations: patch bumps (v0.1.1, v0.1.2).
- Crossing into public-release: minor bump (v0.2.0) or major
  (v1.0.0) — decided at that milestone.

### Branch / PR / release discipline

Inherited verbatim from helper repo conventions
(`docs/bootstrap-from-core.md` §4):

- Feature branches: `claude/<descriptive>-<suffix>` (Claude) or
  `<bare-descriptive>` (human).
- `main` is protected; PRs are user-initiated only; no auto-open
  without explicit say-so.
- Conventional commits.
- Spec → plan → subagent-driven implementation pipeline
  (`docs/superpowers/specs/` + `docs/superpowers/plans/`).
- Tag `vX.Y.Z` on `main` → release workflow fires → publishes
  artifacts to GH Releases.
- Force-push policy: fine on merged feature branches, never on `main`.

## 5. CI / build pipeline

Three workflows.

### 5.1 `.github/workflows/ci.yml` — PR + main verification

- **Triggers:** `pull_request` to any branch, `push` to `main`.
- **Runner:** `macos-latest`. Single OS for v0.1; public-release
  spec adds Windows + Linux jobs.
- **Jobs.**
  1. **lint** — `ruff check`.
  2. **type-check** — pick between `mypy` or `pyright` at
     scaffolding time. Lightweight typing in v0.1; add depth only
     where it earns its keep.
  3. **test** — `python -m pytest -q`. Unit tests cover the
     supervisor (mocked subprocess), `fetch_wheel.py` (mocked
     PyPI), and any pure logic. UI threads (pystray, Tkinter) are
     intentionally not unit-tested in v0.1 — they are exercised by
     the release-time smoke test.
- **Does not** build the `.app` on every PR. macOS runner minutes
  are the expensive resource; we save the build for `release.yml`.
  PRs touching packaging can opt in via a label-driven job, added
  later if it earns its keep.

### 5.2 `.github/workflows/release.yml` — tag-driven build

- **Trigger:** `push` of a `v*.*.*` tag on `main`.
- **Runner:** `macos-latest`.
- **Sequential jobs:**
  1. **fetch_wheel** — run `scripts/fetch_wheel.py`. Hard fail on
     SHA mismatch.
  2. **briefcase build** — `briefcase create macOS`, `briefcase
     build macOS`. Briefcase resolves project deps from
     `pyproject.toml`; the bundled wheel comes from `wheelhouse/`
     via a local-file dependency (exact syntax in `pyproject.toml`
     confirmed at scaffolding time).
  3. **briefcase package** — `briefcase package macOS --no-sign`.
     Produces an unsigned `.dmg`.
  4. **smoke** — boot the built `.app` headlessly, poll `GET
     http://127.0.0.1:47826/ping` until 200 (with timeout), verify
     the response `version` matches `WHEEL_VERSION` and that
     `gui_bundled: true`. Failing the smoke fails the release.
  5. **compute SHA + attach** — `shasum -a 256 *.dmg >
     SHA256SUMS`; attach `.dmg` + `SHA256SUMS` to the GH release.

### 5.3 `.github/workflows/wheel-version-bump.yml` — dispatch receiver

- **Trigger:** `repository_dispatch` with type `wheel-version-bump`.
- **Runner:** `ubuntu-latest` (no build; cheap runner).
- **Jobs.**
  1. Verify `client_payload.wheel_url` returns a file whose SHA-256
     matches `client_payload.sha256`.
  2. Update `wheel-version.txt` and `wheel.sha256` on a branch
     named `claude/wheel-bump-{version}`.
  3. Open a PR titled `build: bump bundled bsky-saves to vX.Y.Z`
     with a body referencing the upstream release notes.
- Uses `BSKY_SAVES_INSTALL_BUMP_PR_TOKEN` (this-repo secret) so the
  PR triggers `ci.yml`. `GITHUB_TOKEN`-authored PRs do not fire
  downstream workflows — same workaround the helper repo uses for
  `gui-version-bump.yml`.

### 5.4 Repo settings (configured after first PR merges)

- Branch protection on `main`: require PR, require CI passing, no
  force-push.
- Tag protection on `v*.*.*`.
- Two PAT secrets:
  - `BSKY_SAVES_INSTALL_DISPATCH_TOKEN` on `tenorune/bsky-saves`
    (fine-grained, scoped to this repo, `Contents:RW` + `Pull
    requests:RW`).
  - `BSKY_SAVES_INSTALL_BUMP_PR_TOKEN` on this repo (same scopes).
- Apple Developer signing cert in GH OIDC — added at public-release
  milestone.

## 6. Out of scope, follow-ups, and risks

### Explicit non-goals for v0.1

- Windows and Linux installers.
- Code signing and notarization.
- Autostart-on-login toggle.
- Update notification / "update available" badge.
- "Open hosted version" tray item.
- Status-window contents.
- Port-collision recovery.
- Auto-restart of the helper on mid-session crash.
- Helper control surface beyond `/ping` + signals.
- SBOM publication.
- External distribution channels (brew, winget, AUR, Flatpak, Snap,
  MAS).
- iOS / Android, Docker images, Pyodide-only mode.
- Telemetry. No outbound calls from the launcher in v0.1.

### Tracked human action items

1. **Apple Developer Program enrollment.** Begin as soon as this
   spec is approved; 1–4 week wall-clock lead. Owner: tenorune.
2. **PAT setup.** Create `BSKY_SAVES_INSTALL_DISPATCH_TOKEN`
   (fine-grained, scoped to this repo, `Contents:RW` + `Pull
   requests:RW`) on `tenorune/bsky-saves`. Create
   `BSKY_SAVES_INSTALL_BUMP_PR_TOKEN` (same scopes) on this repo.
3. **Helper-side dispatch wiring.** Coordinate with the helper team
   to add the `wheel-version-bump` dispatch to their `release.yml`,
   pointing at this repo. Payload shape in § 4.
4. **Repo settings.** Branch protection on `main`, tag protection
   on `v*.*.*`, configured after the first PR merges.

### Follow-up specs (future sessions)

- `docs/superpowers/specs/YYYY-MM-DD-status-window-contents.md` —
  widgets, log-tail rendering, icon-state visuals.
- `docs/superpowers/specs/YYYY-MM-DD-public-release-milestone.md` —
  Windows + Linux + signing + autostart + update notification +
  hosted-version tray item + external channels.
- `docs/superpowers/specs/YYYY-MM-DD-helper-control-endpoints.md` —
  coordination doc with the helper team for the `/control/*`
  surface.

### Risks

| ID | Risk | Mitigation in v0.1 |
|---|---|---|
| R1 | Signing-key compromise | N/A — v0.1 is unsigned. Risk applies to public-release milestone. |
| R2 | Bundled-wheel tampering | SHA-pin via `wheel.sha256`; fetch script aborts on mismatch; re-verification in `wheel-version-bump.yml`. |
| R3 | DNS rebinding against the launched helper | Wheel handles this (Host + Origin checks, pairing token). Installer must not relax those defenses; docs do not encourage `--allow-origin` use. |
| R4 | Silent auto-update channel | Out of scope. No update channel of any kind in v0.1. |
| R5 | Installer post-install scripts (escalation surface) | No post-install scripts in `.dmg` — drag-to-Applications only. No privileged components. |
| R6 | Briefcase template churn breaking builds | Pin Briefcase version in `pyproject.toml`; bump deliberately, not floating. |
| R7 | macOS Gatekeeper blocks dogfood `.app` | Documented bypass (right-click → Open) in repo README. Only user in v0.1 is tenorune. |
