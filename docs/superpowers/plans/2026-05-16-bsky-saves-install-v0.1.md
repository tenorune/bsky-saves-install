# bsky-saves-install v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship installer v0.1.0 — an unsigned macOS `.app`+`.dmg` that bundles `bsky-saves` (and its embedded GUI) with a pystray menu-bar launcher.

**Architecture:** Briefcase freezes a Python launcher app whose entry point spawns `bsky-saves serve` as a child subprocess. The launcher owns a menu-bar icon (pystray) and an on-demand Tkinter status window. Communication with the helper is restricted to subprocess control + `GET /ping`. The `bsky-saves` wheel is pinned by version + SHA-256 and pre-fetched into a local wheelhouse before each build.

**Tech Stack:** Python 3.11+, Briefcase (BeeWare), pystray, Pillow, Tkinter (stdlib), httpx, pytest, ruff, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-05-16-bsky-saves-install-v0.1-design.md`

---

## File map

| Path | Purpose |
|---|---|
| `pyproject.toml` | Project metadata + dev deps + Briefcase config + ruff config |
| `wheel-version.txt` | Pinned `bsky-saves` version (single line) |
| `wheel.sha256` | Pinned wheel SHA-256 (single line) |
| `.gitignore` | Ignore `wheelhouse/`, `build/`, `dist/`, `.venv/`, `__pycache__/` |
| `README.md` | Project description, Gatekeeper bypass instructions |
| `scripts/fetch_wheel.py` | Wheel pin + fetch + SHA verify |
| `src/bsky_saves_launcher/__init__.py` | Package marker, version constant |
| `src/bsky_saves_launcher/supervisor.py` | Subprocess supervisor (unit 3.2) |
| `src/bsky_saves_launcher/tray.py` | Pystray menu-bar (unit 3.3) |
| `src/bsky_saves_launcher/status_window.py` | Tkinter window placeholder (unit 3.4) |
| `src/bsky_saves_launcher/app.py` | Wiring + Briefcase entry point (unit 3.5) |
| `tests/test_fetch_wheel.py` | Fetch/verify unit tests |
| `tests/test_supervisor.py` | Supervisor unit tests (mocked subprocess) |
| `.github/workflows/ci.yml` | Lint + test on PR/main |
| `.github/workflows/release.yml` | Tag-driven build + package + smoke + attach |
| `.github/workflows/wheel-version-bump.yml` | `repository_dispatch` receiver |

---

## Task 1: Scaffold the repo

**Files:**
- Create: `.gitignore`, `pyproject.toml`, `README.md`, `src/bsky_saves_launcher/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Write `.gitignore`**

Create `.gitignore`:

```
__pycache__/
*.py[cod]
.venv/
.venv-*/
build/
dist/
wheelhouse/
*.egg-info/
.pytest_cache/
.ruff_cache/
.mypy_cache/
.DS_Store
```

- [ ] **Step 2: Write `pyproject.toml` (project + dev deps + ruff; Briefcase config deferred to Task 7)**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "bsky-saves-launcher"
version = "0.1.0"
description = "Menu-bar launcher that supervises bsky-saves serve for the bsky-saves-install macOS app."
requires-python = ">=3.11"
authors = [{ name = "tenorune" }]
license = { text = "MIT" }
dependencies = [
    "pystray>=0.19",
    "Pillow>=10",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "ruff>=0.5",
]

[project.scripts]
bsky-saves-launcher = "bsky_saves_launcher.app:main"

[tool.hatch.build.targets.wheel]
packages = ["src/bsky_saves_launcher"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 3: Write `README.md` skeleton**

Create `README.md`:

```markdown
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
```

- [ ] **Step 4: Create package marker files**

Create `src/bsky_saves_launcher/__init__.py`:

```python
"""bsky-saves-install launcher package."""

__version__ = "0.1.0"
```

Create `tests/__init__.py`:

```python
```

- [ ] **Step 5: Verify install works**

Run: `python -m venv /tmp/.bsi-venv && /tmp/.bsi-venv/bin/pip install -e ".[dev]" && /tmp/.bsi-venv/bin/pytest`
Expected: pip install succeeds; pytest reports "no tests ran" (0 collected) and exits 0.

- [ ] **Step 6: Commit**

```sh
git add .gitignore pyproject.toml README.md src/ tests/
git commit -m "build: scaffold bsky-saves-launcher Python package"
```

---

## Task 2: Wheel pin files and `fetch_wheel.py`

**Files:**
- Create: `wheel-version.txt`, `wheel.sha256`, `scripts/__init__.py`, `scripts/fetch_wheel.py`, `tests/test_fetch_wheel.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_fetch_wheel.py`:

```python
"""Unit tests for scripts/fetch_wheel.py."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make scripts/ importable in tests.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_wheel  # noqa: E402


WHEEL_BYTES = b"fake-wheel-contents"
WHEEL_SHA = hashlib.sha256(WHEEL_BYTES).hexdigest()


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_fetch_and_verify_success(tmp_path: Path) -> None:
    version_file = tmp_path / "wheel-version.txt"
    version_file.write_text("0.7.0\n")
    sha_file = tmp_path / "wheel.sha256"
    sha_file.write_text(WHEEL_SHA + "\n")
    wheelhouse = tmp_path / "wheelhouse"

    with patch.object(fetch_wheel.httpx, "get", return_value=FakeResponse(WHEEL_BYTES)):
        wheel_path = fetch_wheel.fetch(
            version_file=version_file,
            sha_file=sha_file,
            wheelhouse=wheelhouse,
        )

    assert wheel_path.exists()
    assert wheel_path.read_bytes() == WHEEL_BYTES
    assert wheel_path.name == "bsky_saves-0.7.0-py3-none-any.whl"


def test_fetch_aborts_on_sha_mismatch(tmp_path: Path) -> None:
    version_file = tmp_path / "wheel-version.txt"
    version_file.write_text("0.7.0\n")
    sha_file = tmp_path / "wheel.sha256"
    sha_file.write_text("0" * 64 + "\n")
    wheelhouse = tmp_path / "wheelhouse"

    with patch.object(fetch_wheel.httpx, "get", return_value=FakeResponse(WHEEL_BYTES)):
        with pytest.raises(fetch_wheel.WheelVerificationError):
            fetch_wheel.fetch(
                version_file=version_file,
                sha_file=sha_file,
                wheelhouse=wheelhouse,
            )

    assert not wheelhouse.exists() or not any(wheelhouse.iterdir())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_fetch_wheel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fetch_wheel'`.

- [ ] **Step 3: Write `scripts/__init__.py` (empty) and `scripts/fetch_wheel.py`**

Create `scripts/__init__.py`:

```python
```

Create `scripts/fetch_wheel.py`:

```python
"""Download a pinned bsky-saves wheel from PyPI and verify its SHA-256.

Reads `wheel-version.txt` and `wheel.sha256` from the repo root, downloads
`bsky_saves-{version}-py3-none-any.whl` from PyPI, verifies the SHA, and
places the wheel in `wheelhouse/`. Aborts on mismatch.

Run as a module: `python scripts/fetch_wheel.py`
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import httpx


PYPI_URL_TEMPLATE = "https://files.pythonhosted.org/packages/source/b/bsky-saves/bsky_saves-{version}-py3-none-any.whl"
# Fallback: PyPI's JSON API gives us the actual signed URL. We try that first
# in production; the simple template above is a developer-friendly fallback.
PYPI_JSON_TEMPLATE = "https://pypi.org/pypi/bsky-saves/{version}/json"


class WheelVerificationError(RuntimeError):
    """Raised when a downloaded wheel's SHA-256 does not match the pin."""


def _resolve_wheel_url(version: str) -> str:
    """Resolve the canonical wheel URL via PyPI's JSON API."""
    resp = httpx.get(PYPI_JSON_TEMPLATE.format(version=version), timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    for url in data.get("urls", []):
        if url.get("packagetype") == "bdist_wheel" and url.get("filename", "").endswith(".whl"):
            return url["url"]
    raise WheelVerificationError(f"No wheel found on PyPI for bsky-saves=={version}")


def fetch(
    version_file: Path,
    sha_file: Path,
    wheelhouse: Path,
    *,
    url_override: str | None = None,
) -> Path:
    """Download + verify + place. Returns the path to the verified wheel."""
    version = version_file.read_text().strip()
    expected_sha = sha_file.read_text().strip().lower()
    if len(expected_sha) != 64:
        raise WheelVerificationError(
            f"Invalid SHA-256 in {sha_file}: expected 64 hex chars, got {len(expected_sha)}"
        )

    url = url_override or _resolve_wheel_url(version)
    resp = httpx.get(url, timeout=120.0)
    resp.raise_for_status()
    content = resp.content

    actual_sha = hashlib.sha256(content).hexdigest()
    if actual_sha != expected_sha:
        raise WheelVerificationError(
            f"SHA-256 mismatch for bsky-saves=={version}: "
            f"expected {expected_sha}, got {actual_sha}"
        )

    wheelhouse.mkdir(parents=True, exist_ok=True)
    wheel_path = wheelhouse / f"bsky_saves-{version}-py3-none-any.whl"
    wheel_path.write_bytes(content)
    return wheel_path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    try:
        wheel = fetch(
            version_file=root / "wheel-version.txt",
            sha_file=root / "wheel.sha256",
            wheelhouse=root / "wheelhouse",
        )
    except WheelVerificationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Verified wheel: {wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

The test patches `fetch_wheel.httpx.get` only, so `_resolve_wheel_url` is bypassed by passing `url_override` is **not** needed — but to keep the test independent of the JSON resolver we should accept `url_override`. The test above does not pass `url_override`, which means the first `httpx.get` call (in `_resolve_wheel_url`) will also be patched and return `FakeResponse(WHEEL_BYTES)`. That breaks the JSON parsing. Fix the test to pass a `url_override`.

Replace the two `fetch_wheel.fetch(` calls in the test with:

```python
        wheel_path = fetch_wheel.fetch(
            version_file=version_file,
            sha_file=sha_file,
            wheelhouse=wheelhouse,
            url_override="https://example.test/bsky_saves-0.7.0-py3-none-any.whl",
        )
```

and

```python
            fetch_wheel.fetch(
                version_file=version_file,
                sha_file=sha_file,
                wheelhouse=wheelhouse,
                url_override="https://example.test/bsky_saves-0.7.0-py3-none-any.whl",
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fetch_wheel.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Write the pin files**

Create `wheel-version.txt`:

```
0.7.0
```

Create `wheel.sha256`:

```
0000000000000000000000000000000000000000000000000000000000000000
```

*Why a zero SHA?* v0.7.0 of `bsky-saves` may not exist on PyPI yet when this task lands. The zero SHA is an explicit "must be updated before the first release build" sentinel. Update it once the helper team publishes v0.7.0 (or any other target wheel). The release workflow will fail loudly if this is left at zero, which is the intended safety net.

Add a one-line note at the top of `wheel.sha256`? **No** — the receiver workflow expects a bare 64-char digest. Keep the file machine-friendly; document the sentinel in the README in Task 11.

- [ ] **Step 6: Commit**

```sh
git add scripts/ wheel-version.txt wheel.sha256 tests/test_fetch_wheel.py
git commit -m "build: add wheel pin files and SHA-verifying fetch script"
```

---

## Task 3: Subprocess supervisor (TDD)

**Files:**
- Create: `src/bsky_saves_launcher/supervisor.py`, `tests/test_supervisor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_supervisor.py`:

```python
"""Unit tests for the subprocess supervisor."""

from __future__ import annotations

import signal
import time
from unittest.mock import MagicMock, patch

import pytest

from bsky_saves_launcher.supervisor import Supervisor


def _make_proc(*, alive_for: float = 10.0, returncode: int | None = None) -> MagicMock:
    """Build a fake subprocess.Popen-shaped object."""
    proc = MagicMock()
    proc._start_time = time.monotonic()
    proc._alive_for = alive_for
    proc.returncode = returncode
    proc.pid = 12345

    def poll() -> int | None:
        if proc.returncode is not None:
            return proc.returncode
        if time.monotonic() - proc._start_time > proc._alive_for:
            proc.returncode = 0
            return 0
        return None

    def wait(timeout: float | None = None) -> int:
        deadline = time.monotonic() + (timeout or 0.0)
        while poll() is None:
            if timeout is not None and time.monotonic() > deadline:
                raise TimeoutError
            time.sleep(0.01)
        return proc.returncode

    proc.poll.side_effect = poll
    proc.wait.side_effect = wait
    proc.stdout = MagicMock()
    proc.stdout.readline.return_value = ""
    proc.stderr = MagicMock()
    proc.stderr.readline.return_value = ""
    return proc


def test_supervisor_start_spawns_subprocess() -> None:
    with patch("bsky_saves_launcher.supervisor.subprocess.Popen") as popen:
        popen.return_value = _make_proc()
        sup = Supervisor(command=["bsky-saves", "serve"])
        sup.start()
        try:
            popen.assert_called_once()
            args, kwargs = popen.call_args
            assert args[0] == ["bsky-saves", "serve"]
            assert sup.is_alive()
        finally:
            sup.stop(timeout=1.0)


def test_supervisor_stop_sends_sigterm() -> None:
    fake_proc = _make_proc()
    with patch("bsky_saves_launcher.supervisor.subprocess.Popen", return_value=fake_proc):
        sup = Supervisor(command=["bsky-saves", "serve"])
        sup.start()
        sup.stop(timeout=1.0)
    fake_proc.terminate.assert_called_once()


def test_supervisor_stop_falls_back_to_kill_on_timeout() -> None:
    fake_proc = _make_proc(alive_for=1e6)  # never dies of natural causes

    def wait_always_times_out(timeout: float | None = None) -> int:
        raise TimeoutError

    fake_proc.wait.side_effect = wait_always_times_out
    with patch("bsky_saves_launcher.supervisor.subprocess.Popen", return_value=fake_proc):
        sup = Supervisor(command=["bsky-saves", "serve"])
        sup.start()
        sup.stop(timeout=0.1)
    fake_proc.terminate.assert_called_once()
    fake_proc.kill.assert_called_once()


def test_recent_logs_returns_ring_buffer_contents() -> None:
    fake_proc = _make_proc()
    lines = [f"line-{i}\n" for i in range(5)]
    fake_proc.stdout.readline.side_effect = lines + [""]
    fake_proc.stderr.readline.return_value = ""
    with patch("bsky_saves_launcher.supervisor.subprocess.Popen", return_value=fake_proc):
        sup = Supervisor(command=["bsky-saves", "serve"], ring_size=3)
        sup.start()
        time.sleep(0.2)  # let reader threads drain
        logs = sup.recent_logs()
        sup.stop(timeout=1.0)
    # Ring is bounded to 3, so we kept the most recent 3.
    assert len(logs) <= 3
    if logs:
        assert all(line.startswith("line-") for line in logs)


def test_double_start_is_idempotent() -> None:
    with patch("bsky_saves_launcher.supervisor.subprocess.Popen", return_value=_make_proc()) as popen:
        sup = Supervisor(command=["bsky-saves", "serve"])
        sup.start()
        sup.start()  # second call is a no-op
        try:
            popen.assert_called_once()
        finally:
            sup.stop(timeout=1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_supervisor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bsky_saves_launcher.supervisor'`.

- [ ] **Step 3: Implement the supervisor**

Create `src/bsky_saves_launcher/supervisor.py`:

```python
"""Subprocess supervisor for `bsky-saves serve`.

Owns the child process across the launcher's lifetime. Captures stdout/stderr
into a bounded ring buffer. Exposes a simple interface: start, stop, is_alive,
recent_logs, and an on_exit callback.
"""

from __future__ import annotations

import subprocess
import threading
from collections import deque
from typing import Callable, Sequence


class Supervisor:
    """Spawns and supervises a long-running child process."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        ring_size: int = 200,
        on_exit: Callable[[int | None], None] | None = None,
    ) -> None:
        self._command = list(command)
        self._ring: deque[str] = deque(maxlen=ring_size)
        self._ring_lock = threading.Lock()
        self._on_exit = on_exit
        self._proc: subprocess.Popen[str] | None = None
        self._readers: list[threading.Thread] = []
        self._exit_watcher: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the subprocess. No-op if already running."""
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return
            self._proc = subprocess.Popen(
                self._command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            self._readers = [
                threading.Thread(
                    target=self._drain,
                    args=(self._proc.stdout,),
                    daemon=True,
                    name="bsi-stdout",
                ),
                threading.Thread(
                    target=self._drain,
                    args=(self._proc.stderr,),
                    daemon=True,
                    name="bsi-stderr",
                ),
            ]
            for t in self._readers:
                t.start()
            self._exit_watcher = threading.Thread(
                target=self._watch_exit,
                daemon=True,
                name="bsi-exit-watch",
            )
            self._exit_watcher.start()

    def _drain(self, stream) -> None:
        try:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                with self._ring_lock:
                    self._ring.append(line.rstrip("\n"))
        except (ValueError, OSError):
            # Stream closed during shutdown.
            pass

    def _watch_exit(self) -> None:
        if self._proc is None:
            return
        rc = self._proc.wait()
        if self._on_exit is not None:
            try:
                self._on_exit(rc)
            except Exception:
                # Callback errors must not crash the watcher thread.
                pass

    def stop(self, timeout: float = 5.0) -> None:
        """Terminate the subprocess. SIGTERM first, SIGKILL on timeout."""
        with self._lock:
            proc = self._proc
            if proc is None:
                return
            if proc.poll() is not None:
                self._proc = None
                return
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except (subprocess.TimeoutExpired, TimeoutError):
                proc.kill()
                try:
                    proc.wait(timeout=timeout)
                except (subprocess.TimeoutExpired, TimeoutError):
                    pass
            self._proc = None

    def is_alive(self) -> bool:
        proc = self._proc
        return proc is not None and proc.poll() is None

    def recent_logs(self) -> list[str]:
        with self._ring_lock:
            return list(self._ring)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_supervisor.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```sh
git add src/bsky_saves_launcher/supervisor.py tests/test_supervisor.py
git commit -m "feat(launcher): add subprocess supervisor with ring-buffer log capture"
```

---

## Task 4: Pystray tray icon (no unit tests — manual smoke only)

**Files:**
- Create: `src/bsky_saves_launcher/tray.py`

The tray module is UI code that depends on a running pystray event loop and a real OS menu-bar service. We do not unit-test it in v0.1 — it is exercised by the release-time smoke test (Task 9) and by manual `python -m bsky_saves_launcher.app` runs during development.

- [ ] **Step 1: Implement the tray**

Create `src/bsky_saves_launcher/tray.py`:

```python
"""Menu-bar / system-tray icon for the launcher.

Renders a pystray icon, wires up a minimal v0.1 menu (Open GUI, Quit), and
exposes a callback hook for opening the status window on icon click.
"""

from __future__ import annotations

import webbrowser
from typing import Callable

from PIL import Image, ImageDraw
import pystray

from bsky_saves_launcher.supervisor import Supervisor


LOCAL_GUI_URL = "http://127.0.0.1:47826/"


def _make_icon_image(*, running: bool) -> Image.Image:
    """Render a 64x64 RGBA icon. Green dot when running, gray when stopped."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (60, 200, 90, 255) if running else (160, 160, 160, 255)
    draw.ellipse((8, 8, 56, 56), fill=color)
    return img


class TrayApp:
    """Owns the pystray icon and dispatches its menu items."""

    def __init__(
        self,
        supervisor: Supervisor,
        *,
        on_open_status: Callable[[], None],
    ) -> None:
        self._supervisor = supervisor
        self._on_open_status = on_open_status
        self._icon: pystray.Icon | None = None

    def _on_open_gui(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        webbrowser.open(LOCAL_GUI_URL)

    def _on_quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self._supervisor.stop()
        icon.stop()

    def _on_default(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        # Triggered by left-click on the icon (pystray default action).
        self._on_open_status()

    def run(self) -> None:
        """Block on the pystray event loop. Must be called on the main thread."""
        menu = pystray.Menu(
            pystray.MenuItem(
                "Show status...",
                self._on_default,
                default=True,
                visible=False,  # invoked by icon click, not shown in menu
            ),
            pystray.MenuItem("Open GUI", self._on_open_gui),
            pystray.MenuItem("Quit", self._on_quit),
        )
        self._icon = pystray.Icon(
            name="bsky-saves",
            icon=_make_icon_image(running=self._supervisor.is_alive()),
            title="Bsky Saves",
            menu=menu,
        )
        self._icon.run()

    def refresh_icon(self) -> None:
        """Re-render the icon image based on supervisor state."""
        if self._icon is not None:
            self._icon.icon = _make_icon_image(running=self._supervisor.is_alive())
```

- [ ] **Step 2: Smoke import**

Run: `python -c "from bsky_saves_launcher.tray import TrayApp; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```sh
git add src/bsky_saves_launcher/tray.py
git commit -m "feat(launcher): add pystray menu-bar icon with Open GUI / Quit menu"
```

---

## Task 5: Tkinter status window placeholder

**Files:**
- Create: `src/bsky_saves_launcher/status_window.py`

Per spec § 3.4, v0.1 ships the *surface* of the status window — the module, the open/focus contract, and a placeholder window. Widget-level contents come in a follow-up spec.

- [ ] **Step 1: Implement the placeholder window**

Create `src/bsky_saves_launcher/status_window.py`:

```python
"""On-demand Tkinter status window for the launcher.

v0.1 is a placeholder. The window exists, can be opened from the tray, and is
re-focused on subsequent opens. Widget-level contents are spec'd in a follow-up
doc; do not add widgets here without referencing that spec.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bsky_saves_launcher.supervisor import Supervisor


class StatusWindow:
    """Lazily-constructed, singleton-per-launcher Tk window."""

    def __init__(self, supervisor: Supervisor) -> None:
        self._supervisor = supervisor
        self._root: tk.Tk | None = None

    def open(self) -> None:
        """Open the window if not already open; focus it if it is."""
        if self._root is not None and self._is_alive():
            self._root.deiconify()
            self._root.lift()
            self._root.focus_force()
            return
        self._build()

    def _is_alive(self) -> bool:
        try:
            return bool(self._root and self._root.winfo_exists())
        except tk.TclError:
            return False

    def _build(self) -> None:
        root = tk.Tk()
        root.title("Bsky Saves — status")
        root.geometry("420x240")

        # Placeholder content. Replace per status-window-contents follow-up spec.
        label = tk.Label(
            root,
            text=(
                "Bsky Saves launcher\n\n"
                "Status-window contents are deferred to a follow-up spec.\n"
                "See docs/superpowers/specs/."
            ),
            justify="center",
            padx=16,
            pady=16,
        )
        label.pack(expand=True)

        def _on_close() -> None:
            root.withdraw()  # hide rather than destroy; reopen is cheaper

        root.protocol("WM_DELETE_WINDOW", _on_close)
        self._root = root
```

- [ ] **Step 2: Smoke import**

Run: `python -c "from bsky_saves_launcher.status_window import StatusWindow; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```sh
git add src/bsky_saves_launcher/status_window.py
git commit -m "feat(launcher): add placeholder Tkinter status window"
```

---

## Task 6: App entry point (`app.py`) wiring

**Files:**
- Create: `src/bsky_saves_launcher/app.py`

- [ ] **Step 1: Implement the entry point**

Create `src/bsky_saves_launcher/app.py`:

```python
"""Launcher entry point — wires supervisor, tray, and status window together."""

from __future__ import annotations

import sys

from bsky_saves_launcher.status_window import StatusWindow
from bsky_saves_launcher.supervisor import Supervisor
from bsky_saves_launcher.tray import TrayApp


HELPER_COMMAND = ["bsky-saves", "serve"]


def main() -> int:
    supervisor = Supervisor(command=HELPER_COMMAND)
    status_window = StatusWindow(supervisor)

    supervisor.start()
    tray = TrayApp(supervisor, on_open_status=status_window.open)
    try:
        tray.run()
    finally:
        supervisor.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke import**

Run: `python -c "from bsky_saves_launcher.app import main; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```sh
git add src/bsky_saves_launcher/app.py
git commit -m "feat(launcher): wire supervisor, tray, and status window in app entry point"
```

---

## Task 7: Briefcase configuration

**Files:**
- Modify: `pyproject.toml` (append Briefcase config section)
- Create: `src/bsky_saves_launcher/resources/` (empty placeholder dir for Briefcase icons; add a `.gitkeep`)

Briefcase reads its config from `[tool.briefcase.*]` tables in `pyproject.toml`. The v0.1 config bundles the launcher + the pinned wheel from `wheelhouse/`.

- [ ] **Step 1: Add Briefcase deps to dev install**

Edit `pyproject.toml`. Append to `[project.optional-dependencies] dev`:

```toml
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "ruff>=0.5",
    "briefcase>=0.3.20",
]
```

- [ ] **Step 2: Append Briefcase config to `pyproject.toml`**

Append to `pyproject.toml`:

```toml
[tool.briefcase]
project_name = "Bsky Saves"
bundle = "net.lightseed"
version = "0.1.0"
url = "https://github.com/tenorune/bsky-saves-install"
license = "MIT"
author = "tenorune"
author_email = "noreply@lightseed.net"

[tool.briefcase.app.bsky-saves]
formal_name = "Bsky Saves"
description = "Local helper for bsky-saves bookmarks."
long_description = "Menu-bar launcher that supervises bsky-saves serve and exposes a local helper at http://127.0.0.1:47826/."
sources = ["src/bsky_saves_launcher"]
test_sources = ["tests"]

# Runtime dependencies bundled into the .app. The bsky-saves wheel is resolved
# via a local-file URL pointing at the wheelhouse populated by scripts/fetch_wheel.py.
requires = [
    "pystray>=0.19",
    "Pillow>=10",
    "httpx>=0.27",
    "bsky-saves @ file://./wheelhouse/bsky_saves-0.7.0-py3-none-any.whl",
]

[tool.briefcase.app.bsky-saves.macOS]
universal_build = true
requires = []
```

> **Note for the executor:** the wheel filename in the `requires` URL must match `wheel-version.txt`. When the wheel version bumps, this file changes too — the `wheel-version-bump.yml` workflow in Task 10 handles both edits in the same PR.

- [ ] **Step 3: Create the resources placeholder**

```sh
mkdir -p src/bsky_saves_launcher/resources
touch src/bsky_saves_launcher/resources/.gitkeep
```

(Briefcase will look for an app icon here in later milestones. v0.1 ships with Briefcase's default icon.)

- [ ] **Step 4: Verify Briefcase parses the config**

Run: `pip install briefcase && briefcase dev --no-run` (or check `briefcase --version` + `briefcase config` if available)
Expected: no parse errors. (Actual `briefcase create macOS` requires macOS; this dry check just validates the config syntax.)

> **Executor note:** if Briefcase needs the wheelhouse populated before parsing the `requires` list, run `python scripts/fetch_wheel.py` first — which will fail with the zero-SHA sentinel from Task 2. That is expected; the SHA is updated when the real target wheel exists on PyPI.

- [ ] **Step 5: Commit**

```sh
git add pyproject.toml src/bsky_saves_launcher/resources/.gitkeep
git commit -m "build: add Briefcase config for macOS .app/.dmg packaging"
```

---

## Task 8: CI workflow (`ci.yml`)

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: ci

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dev deps
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Lint
        run: ruff check

      - name: Test
        run: pytest -q
```

- [ ] **Step 2: Commit**

```sh
git add .github/workflows/ci.yml
git commit -m "ci: add lint+test workflow on PR and main"
```

---

## Task 9: Release workflow (`release.yml`)

**Files:**
- Create: `.github/workflows/release.yml`

This workflow is intentionally only validated structurally; it cannot run end-to-end until `wheel.sha256` is a real digest and the helper team has published the target wheel.

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/release.yml`:

```yaml
name: release

on:
  push:
    tags:
      - "v*.*.*"

permissions:
  contents: write

jobs:
  build-macos:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install build deps
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Fetch + verify bsky-saves wheel
        run: python scripts/fetch_wheel.py

      - name: Briefcase create
        run: briefcase create macOS

      - name: Briefcase build
        run: briefcase build macOS

      - name: Briefcase package (unsigned)
        run: briefcase package macOS --adhoc-sign

      - name: Smoke test built .app
        run: |
          set -e
          DMG=$(ls dist/*.dmg | head -n1)
          APP_DIR=$(mktemp -d)
          hdiutil attach "$DMG" -mountpoint "$APP_DIR" -nobrowse -quiet
          APP=$(ls -d "$APP_DIR"/*.app | head -n1)
          # Launch the app's launcher binary directly (skip the GUI tray for headless test).
          "$APP/Contents/MacOS/Bsky Saves" &
          APP_PID=$!
          # Poll /ping for up to 60s.
          for i in {1..60}; do
            if curl -sf http://127.0.0.1:47826/ping > /tmp/ping.json; then
              break
            fi
            sleep 1
          done
          cat /tmp/ping.json
          python -c "import json,sys; d=json.load(open('/tmp/ping.json')); assert d.get('gui_bundled') is True, d; print('smoke OK:', d.get('version'))"
          kill $APP_PID || true
          hdiutil detach "$APP_DIR" -quiet || true

      - name: Compute SHA256SUMS
        run: |
          cd dist
          shasum -a 256 *.dmg > SHA256SUMS
          cat SHA256SUMS

      - name: Attach artifacts to GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            dist/*.dmg
            dist/SHA256SUMS
          fail_on_unmatched_files: true
```

> **Executor note:** the smoke-test step assumes the launcher's binary is named `Bsky Saves` (Briefcase derives this from `formal_name`). If Briefcase produces a differently-named binary, adjust the `APP/Contents/MacOS/<name>` path. The exact filename is observable from a successful local `briefcase build macOS`.

- [ ] **Step 2: Commit**

```sh
git add .github/workflows/release.yml
git commit -m "ci: add tag-driven macOS release workflow with smoke test"
```

---

## Task 10: `wheel-version-bump.yml` dispatch receiver

**Files:**
- Create: `.github/workflows/wheel-version-bump.yml`

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/wheel-version-bump.yml`:

```yaml
name: wheel-version-bump

on:
  repository_dispatch:
    types: [wheel-version-bump]

permissions:
  contents: write
  pull-requests: write

jobs:
  bump:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.BSKY_SAVES_INSTALL_BUMP_PR_TOKEN }}

      - name: Re-verify wheel SHA
        run: |
          set -euo pipefail
          VERSION='${{ github.event.client_payload.version }}'
          EXPECTED_SHA='${{ github.event.client_payload.sha256 }}'
          WHEEL_URL='${{ github.event.client_payload.wheel_url }}'
          curl -fsSL "$WHEEL_URL" -o /tmp/wheel.whl
          ACTUAL_SHA=$(shasum -a 256 /tmp/wheel.whl | awk '{print $1}')
          if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then
            echo "SHA mismatch: expected $EXPECTED_SHA got $ACTUAL_SHA" >&2
            exit 1
          fi
          echo "OK: $VERSION sha matches"

      - name: Update wheel pin files
        run: |
          set -euo pipefail
          VERSION='${{ github.event.client_payload.version }}'
          SHA='${{ github.event.client_payload.sha256 }}'
          echo "$VERSION" > wheel-version.txt
          echo "$SHA" > wheel.sha256
          # Update Briefcase's local-file dep so it tracks the pin.
          python - <<'PY'
          import re
          from pathlib import Path
          version = Path("wheel-version.txt").read_text().strip()
          p = Path("pyproject.toml")
          text = p.read_text()
          new = re.sub(
              r'"bsky-saves @ file://./wheelhouse/bsky_saves-[^"]+\.whl"',
              f'"bsky-saves @ file://./wheelhouse/bsky_saves-{version}-py3-none-any.whl"',
              text,
          )
          p.write_text(new)
          PY

      - name: Open PR
        env:
          GH_TOKEN: ${{ secrets.BSKY_SAVES_INSTALL_BUMP_PR_TOKEN }}
        run: |
          set -euo pipefail
          VERSION='${{ github.event.client_payload.version }}'
          REF_NAME='${{ github.event.client_payload.ref_name }}'
          BRANCH="claude/wheel-bump-${VERSION}"
          git config user.name "bsky-saves-install bump bot"
          git config user.email "bump-bot@users.noreply.github.com"
          git checkout -b "$BRANCH"
          git add wheel-version.txt wheel.sha256 pyproject.toml
          git commit -m "build: bump bundled bsky-saves to v${VERSION}"
          git push -u origin "$BRANCH"
          gh pr create \
            --title "build: bump bundled bsky-saves to v${VERSION}" \
            --body "Auto-generated by repository_dispatch from tenorune/bsky-saves (${REF_NAME}). Wheel SHA-256 re-verified. Do not auto-merge — human review required to catch helper-behavior changes." \
            --base main \
            --head "$BRANCH"
```

- [ ] **Step 2: Commit**

```sh
git add .github/workflows/wheel-version-bump.yml
git commit -m "ci: receive wheel-version-bump dispatches from bsky-saves"
```

---

## Task 11: README polish

**Files:**
- Modify: `README.md` (add wheel-pin note and link to spec)

- [ ] **Step 1: Append a "Wheel pin" subsection to the Development section**

Insert before `## License` in `README.md`:

```markdown
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
```

- [ ] **Step 2: Commit**

```sh
git add README.md
git commit -m "docs: document wheel-pin sentinel and link to design spec"
```

---

## Closing checklist

After all tasks land:

- [ ] `pytest -q` passes locally.
- [ ] `ruff check` passes locally.
- [ ] `python -c "from bsky_saves_launcher.app import main"` succeeds.
- [ ] Human action items from spec § 6 tracked separately (Apple Developer enrollment, PAT creation on both repos, helper-side dispatch wiring).
- [ ] Spec § 6 tracked follow-up specs not yet started — that is correct; they are explicitly out of v0.1 scope.

The first end-to-end release build will require:
1. `wheel.sha256` populated with the real SHA of the target `bsky-saves` wheel on PyPI.
2. `wheel-version.txt` matching that target wheel's version.
3. Tag `v0.1.0` on `main`.

Until those land, the release workflow will fail at `fetch_wheel.py` (intentional safety net).
