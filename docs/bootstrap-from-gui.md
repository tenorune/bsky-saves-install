# Bootstrap: `bsky-saves-installers` — Claude session kickoff

> **What this is.** Context for a fresh Claude session that will set up and
> work on a new `tenorune/bsky-saves-installers` repository — the third repo
> in the bsky-saves trio. This doc captures the state of the world from the
> GUI side as of GUI **v0.6.2** (released). The CLI team is providing a
> separate context dump from their side; both are inputs to the new session.

---

## 1. The trio in one paragraph

The bsky-saves project ships in three coordinated repos. **`bsky-saves-gui`**
(Svelte + Vite PWA) produces the browser-side experience — hosted at
`saves.lightseed.net` and bundled into the wheel as static files.
**`bsky-saves`** (Python daemon + wheel on PyPI) is the local-helper process
the GUI talks to over `http://localhost:47826` for image fetch, article
extraction, and thread hydration; the wheel includes the GUI bundle
(`bsky-saves serve --gui`) so a single `pipx install` gives the user a fully
local app. **`bsky-saves-installers`** — the repo this session is about —
freezes the wheel into single-file binaries and OS-native installers
(`.dmg` / `.msi` / `.AppImage`) so users who don't have Python (or don't
want a terminal) can still run the local helper.

## 2. State of the world (May 2026)

- **GUI:** **v0.6.2 released** (current); deployed at `saves.lightseed.net`
  and bundled into bsky-saves v0.6.4.
- **Wheel:** **bsky-saves v0.6.4** is on PyPI. First-run pairing-token
  print is live. Ships GUI v0.6.2 inside. `bsky-saves serve --gui` works;
  pairing UX between hosted-PWA and local helper is fully wired.
- **GUI ↔ wheel contract** is stable and battle-tested:
  - `MIN_HELPER_VERSION = '0.6.3'` in the GUI; `MAX_KNOWN_PROTOCOL = '2'`.
  - Helper exposes `GET /ping` returning
    `{name, version, protocol, gui_bundled, features[]}`.
  - Pairing token is a persistent secret at a platform-conventional path,
    `0600` perms, lazily generated on first `bsky-saves serve` or
    `bsky-saves token`. Substituted into the wheel-served `index.html` via
    sentinel replacement (`__BSKY_SAVES_TOKEN__`); the hosted PWA prompts
    the user to paste it.
- **CI / release model precedent** for cross-repo coordination is already
  proven on the GUI → wheel side:
  - Tag-driven artifact production (`release.yml`) gated separately from
    PR/main CI (`ci.yml`).
  - Release tarball `dist.tar.gz` + `.sha256` + `SBOM.cdx.json` attached to
    each GitHub release; downstream consumer pins by SHA, never by floating
    ref.
  - `repository_dispatch` from `bsky-saves-gui` into `tenorune/bsky-saves`
    fires a cross-repo bump PR (uses a fine-grained PAT scoped to that
    single repo, secret name `BSKY_SAVES_DISPATCH_TOKEN`). Never
    auto-merge; pin bumps go through human review.

The installers repo will inherit this pattern, sitting one hop further
downstream.

## 3. Fleet plan — where installers fit

```
┌─────────────────────────┐    ┌─────────────────────────┐    ┌─────────────────────────┐
│ bsky-saves-gui          │    │ bsky-saves              │    │ bsky-saves-installers   │
│ Svelte / Vite / PWA     │    │ Python daemon + wheel   │    │ Frozen binaries +       │
│                         │    │ ships GUI bundle inside │    │ OS-native installers    │
│ Cadence: hourly-daily   │    │ Cadence: weekly-monthly │    │ Cadence: monthly+       │
└───────────┬─────────────┘    └───────────┬─────────────┘    └───────────┬─────────────┘
            │ dist.tar.gz                  │ bsky-saves-X.Y.Z.whl         │ .dmg / .msi / .AppImage
            │ (per GUI tag)                │ (per wheel tag on PyPI)      │ (per installer tag)
            └───────► consumed by ────────►│                              │
                       wheel build         └───────► consumed by ────────►│
                                                       installer build    │
```

User segments served by each tier:

| Segment | Artifact | Refresh |
|---|---|---|
| Mobile / desktop visitor, no install | Hosted PWA at `saves.lightseed.net` | Per merge to `main` (GH Pages) |
| CLI user with Python | `pipx install bsky-saves` | Per wheel release (PyPI) |
| CLI user without Python | Standalone single binary | Per installer release (GH Releases) — **new repo's job** |
| Non-technical desktop user | OS-native installer + launcher | Per installer release — **new repo's job** |

Each tier is a strict superset of the previous. No code forks — tier 2 is
the wheel frozen with PyInstaller/Briefcase/PyOxidizer; tier 3 is the
binary wrapped with a launcher (tray/menu-bar icon, autostart toggle,
"Open saves.lightseed.net" button).

## 4. MVP requirements (from `bsky-saves-serve-distribution-requirements.md`)

Verbatim shape of what the installers repo must produce:

1. **Cross-platform installers, no Python prerequisite.**
   - macOS: `.pkg` or `.dmg`. Universal binary (Apple Silicon + Intel).
   - Windows: `.exe` / `.msi`.
   - Linux: at minimum a static `.AppImage`. Optional `.deb` / `.rpm` /
     Flatpak / Snap.

   Bundle must include its own Python runtime (PyInstaller, Briefcase, or
   PyOxidizer). No separate Python install, no `pip`, no pipx.

   **Code signing + notarization: TBD.** Apple Developer ID + notarytool
   on macOS and Authenticode on Windows are the standard paths to avoid
   Gatekeeper / SmartScreen prompts, but procurement, cost, and signing
   infrastructure are decisions for the installers session to make. The
   workstream can ship unsigned for initial iteration (with documented
   user-side bypass steps) and add signing once the certs and CI key
   management are in place. See § 6 and § 12.

2. **GUI launcher.**
   When the user opens the installed app: a status window or
   tray/menu-bar icon shows current listening port (default `47826`),
   `bsky-saves` version, recent log tail, "Open saves.lightseed.net"
   button, "Quit" button. macOS menu bar, Windows system tray, Linux
   AppIndicator + window fallback. Launcher is a thin wrapper around
   `bsky-saves serve` — it spawns the daemon as a subprocess and
   surfaces UI. CLI `bsky-saves serve` keeps working for power users.

3. **Auto-start on login (opt-in).**
   - macOS: LaunchAgent plist (`~/Library/LaunchAgents/…plist`).
   - Windows: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` or
     scheduled task.
   - Linux: `~/.config/autostart/bsky-saves.desktop`.
   Off by default; one-click on.

4. **Single-binary fallback** for power users / curl-pipe-bash / config
   management. Targets: `linux/amd64`, `linux/arm64`, `darwin/amd64`,
   `darwin/arm64`, `windows/amd64`.

5. **Capability probe**: already covered by the wheel's `/ping`
   endpoint — no installer-side work.

6. **Stable API contract**: the wheel already locks `/ping`,
   `/fetch-image`, `/extract-article`. The installer just runs the
   wheel; no API surface of its own.

7. **Versioning + upgrade signal.** The launcher should periodically check
   the `bsky-saves` releases feed and surface an "Update available" badge.
   Opt-out-able. Per-OS install size budget: ≤ 80 MB compressed (embedded
   Python + Trafilatura + httpx).

8. **Localhost-only by default**: wheel already enforces this; installer
   just propagates.

9. **Helpful error responses**: wheel-side; no installer work.

10. **No telemetry.** No outbound calls except the launcher's release-feed
    check (opt-out-able).

## 5. Acceptance criteria for the "serve-for-all" milestone

A non-technical user on macOS, Windows, and Linux can:

1. Visit a single landing page.
2. Download the right installer for their OS (auto-detected).
3. Run it (one double-click; no terminal).
4. Open the installed app and see a green "running" indicator within 60s.
5. Refresh `saves.lightseed.net` and see "the local helper (bsky-saves
   X.Y.Z)" detected in Settings → Backup.

Plus:
- Quit + restart with no re-setup.
- Patch upgrade by downloading a new installer; settings (port, autostart,
  allow-origins) survive.
- `/ping`, `/fetch-image`, `/extract-article` documented in an OpenAPI
  schema published alongside the release.
- `pipx install bsky-saves && bsky-saves serve` keeps working in parallel.

## 6. Recommended toolchain (starting point — confirm with CLI team)

- **Freeze tool**: **Briefcase** (BeeWare). Built for exactly this
  three-OS-installer use case, handles `.dmg` / `.msi` / `.AppImage`
  packaging and notarization plumbing in one tool. Falls back to
  **PyInstaller + per-OS tooling** (create-dmg + notarytool on macOS, WiX
  or Inno Setup on Windows, appimage-builder on Linux) if Briefcase
  proves too opinionated.
- **Launcher framework**: Briefcase + toga is the path of least
  resistance for tray/menu-bar + status window. Alternative:
  **pystray** (cross-OS tray) + a tiny Tkinter window — simpler if the
  team is unfamiliar with toga.
- **Subprocess management**: launcher spawns `bsky-saves serve` as a
  child process, captures stdout/stderr to an in-memory ring buffer for
  the log-tail UI, and tears it down on Quit. The subprocess must
  inherit the launcher's working directory and config-path env so the
  pairing token lands at the same on-disk location whether launched
  via CLI or via the app.
- **Signing + notarization (TBD — defer the call to the installers
  session).** The standard paths are:
  - macOS: Apple Developer ID (Application + Installer certs),
    notarization via `notarytool`. Avoids the "unidentified developer"
    Gatekeeper prompt. Cost: $99/yr Apple Developer + Apple's enrollment
    review time (typically 1–4 weeks for a new entity).
  - Windows: Authenticode cert (EV ideal for skipping SmartScreen on a
    new publisher; non-EV is cheaper but accrues SmartScreen
    reputation slowly). `signtool` in CI.
  - Linux: no OS-level signing requirement; consider GPG-signing the
    `.AppImage` for users who want to verify.

  The unsigned-MVP path is viable: ship installers with documented
  bypass instructions ("right-click → Open" on macOS, "More info → Run
  anyway" on Windows) and add signing later without breaking the
  cross-repo contract. The choice is primarily a cost/UX-polish trade-off,
  not a security one — runtime defenses (Host/Origin, pairing token) are
  in the wheel regardless.

## 7. Cross-repo contract (mirror of GUI → wheel pattern)

**Input pin.** Installer repo holds a `WHEEL_VERSION` (e.g. in
`pyproject.toml` or a sibling `wheel-version.txt`) and a committed
`wheel.sha256`. The build script:

1. Reads `WHEEL_VERSION` and the pinned SHA.
2. Downloads `bsky_saves-{WHEEL_VERSION}-*.whl` from PyPI (or from the
   wheel's GitHub release if PyPI is preferred not-of-record).
3. Verifies SHA. Aborts on mismatch.
4. Materializes a venv with the wheel + its runtime deps; freezes that
   into the platform binary.

**Cross-repo dispatch.** On every `vX.Y.Z` tag push, `bsky-saves`
`release.yml` fires a `repository_dispatch` into
`tenorune/bsky-saves-installers` after the wheel publishes. Receiving
workflow opens a bump PR. Suggested payload:

```json
{
  "event_type": "wheel-version-bump",
  "client_payload": {
    "version":    "0.6.4",
    "sha256":     "abc123…",
    "wheel_url":  "https://files.pythonhosted.org/packages/.../bsky_saves-0.6.4-py3-none-any.whl",
    "ref_name":   "v0.6.4"
  }
}
```

Requires a fine-grained PAT scoped to `tenorune/bsky-saves-installers`
with `Contents: read-and-write`, stored on the `bsky-saves` side as e.g.
`BSKY_SAVES_INSTALLERS_DISPATCH_TOKEN`. Never auto-merge.

**Output artifacts.** Per installer tag, attach to GH release:

- `bsky-saves-X.Y.Z-macos-universal.dmg` (notarized if signing is in scope)
- `bsky-saves-X.Y.Z-windows-x64.msi` (Authenticode-signed if signing is in scope)
- `bsky-saves-X.Y.Z-linux-x86_64.AppImage`
- `bsky-saves-X.Y.Z-linux-aarch64.AppImage`
- `bsky-saves-X.Y.Z-{darwin,linux,windows}-{amd64,arm64}` single binaries
- `SBOM.cdx.json`
- `SHA256SUMS`
- (Stretch) sigstore signatures.

## 8. Security risks (lifted from the GUI workstream doc, scoped to installers)

- **R1 (only if signing is in scope) — signing-key compromise.** If the
  installers repo eventually adds Apple Developer ID / Authenticode
  signing, those keys + the notarization tokens in CI become HVTs.
  Compromise = malicious installer signed with our identity.
  Mitigation: GH OIDC where possible, hardware-token-backed keys where
  not, strict access controls, rotate-on-leave. Until signing is in
  scope, this risk doesn't apply — but the user-visible Gatekeeper /
  SmartScreen warnings stand in for an integrity signal during that
  period.
- **R2 — bundled-wheel tampering.** Same risk as GUI → wheel:
  intermediate substitution. Mitigation: SHA-pin wheels by content, abort
  build on mismatch.
- **R3 — DNS rebinding against the launched helper.** The wheel handles
  this (Host + Origin checks, pairing token). Installer just hosts the
  daemon; no new attack surface, but installer docs should not encourage
  users to relax those defenses.
- **R4 — silent auto-update channel.** Explicitly **out of scope for
  MVP.** Launcher surfaces an "update available" badge; user clicks to
  download. Adding silent updates later requires code-signed update
  payloads + a kill-switch + a pinned channel URL.
- **R5 — installer post-install scripts.** macOS pkg post-install,
  Windows MSI custom actions — these run as the user (or as root, on
  macOS pkg). Keep them minimal. Auto-start setup should happen on first
  launch (user-initiated), not in the installer.

## 9. Non-goals (for MVP)

- iOS / Android native apps.
- Hosted SaaS version of `serve`.
- Bundling `serve` into the cf-worker.
- In-browser via Pyodide (can't bind a port).
- Silent auto-update.
- Anything that requires running the user's atproto session credentials
  in a context other than the local helper or the GUI itself.

## 10. Pointers — source-of-truth docs

In `tenorune/bsky-saves-gui`:

- `docs/bsky-saves-gui-dist-workstream.md` — full workstream doc:
  fleet plan, boundary artifacts, pin-bump flow, security risks
  (R1–R7), the 9 GUI-side smoke tests (S1–S9). The installers repo
  should mirror many of these gates with appropriate substitutions.
- `docs/bsky-saves-serve-distribution-requirements.md` — the
  "serve-for-all" spec; sections 1–10 are the contract.
- `docs/superpowers/specs/2026-05-01-bsky-saves-gui-design.md` —
  the overall design spec; the "Configuration / deploy-agnostic"
  section documents which env vars get baked at build time.
- `app/src/lib/min-helper-version.ts` — current `MIN_HELPER_VERSION`
  and `MAX_KNOWN_PROTOCOL`.
- `templates/cf-worker/README.md` — the worker proxy template the
  GUI also routes through; useful background for understanding the
  three-backend fallback model the helper sits at the top of.
- `.github/workflows/release.yml` — the tag-driven artifact pipeline
  the installer repo should mirror in shape.

In `tenorune/bsky-saves` (CLI team will detail):

- API spec for `/ping`, `/fetch-image`, `/extract-article`,
  `/auth/check`, the token-rotation surface.
- The `--gui` flag behavior and the `__BSKY_SAVES_TOKEN__` sentinel
  substitution.
- The platform-conventional config-path matrix.

## 11. First moves for the new session

A reasonable bootstrap order, in priority:

1. Create the `tenorune/bsky-saves-installers` repo with the same
   `claude/bsky-saves-installers-work-*` branching convention; wire
   GH Actions repo settings (tag protection, OIDC, repo variables).
2. Decide the freeze tool: **Briefcase** vs **PyInstaller + per-OS
   tooling**. Spike both for one OS (macOS DMG is the most demanding —
   it forces the notarization toolchain decision early).
3. Stand up the launcher skeleton: subprocess management, tray /
   menu-bar icon, status window, "Open saves.lightseed.net" button.
4. Wire the `WHEEL_VERSION` pin and the `repository_dispatch` listener
   from `bsky-saves`. Confirm a manual bump works end-to-end before
   automating.
5. Per-OS smoke tests: build installer, install on a clean runner,
   launch, hit `/ping`, verify response + version + autostart toggle.
6. Code-signing: see § 12 for the decision gate; if in scope, macOS
   first (longest lead time on Apple Developer enrollment), then
   Windows.
7. Cut a `v0.1.0` pre-release with all three platforms, internal-only.
   Iterate on the launcher UX before public release.

## 12. Open questions to flag to the user up front

- **Signing decision — first thing to settle.** Two paths:
  (a) Ship signed/notarized from v0.1 — requires Apple Developer
  enrollment (1–4 wks lead) + Authenticode cert procurement + CI key
  management. (b) Ship unsigned for initial iteration with documented
  bypass steps, add signing in a later minor release. Decide before
  cutting v0.1 because the answer drives the build-tool choice
  (Briefcase has stronger notarization plumbing than PyInstaller +
  separate tooling).
- **Linux package targets.** AppImage is required; are `.deb` / `.rpm`
  / Flatpak / Snap also in scope for v0.1, or follow-up?
- **Update notification cadence.** Daily? Weekly? On-launch? Whose
  endpoint serves the version feed (GH releases API directly, or a
  cached intermediate)?
- **Landing page.** Where does the "auto-detect your OS, here's your
  download" page live? `installers.lightseed.net`? A sub-route of
  `saves.lightseed.net`? Part of the `bsky-saves` repo's GH Pages?

---

**Session-start checklist.** Once you open the new session, read in
this order:
1. This document.
2. The CLI team's companion bootstrap.
3. `docs/bsky-saves-gui-dist-workstream.md` § 1–3, § 5.
4. `docs/bsky-saves-serve-distribution-requirements.md` in full.

Then start with item 1 of "First moves" (§ 11).
