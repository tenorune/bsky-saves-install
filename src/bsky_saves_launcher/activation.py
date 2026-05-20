"""macOS NSApp activation policy control.

Two policies relevant for a menu-bar daemon launcher:

- NSApplicationActivationPolicyAccessory (=1): no Dock icon, no Cmd-Tab
  entry, menu-bar presence only. The "daemon" mode.
- NSApplicationActivationPolicyRegular   (=0): standard foreground app
  with Dock entry + Cmd-Tab.

Toggleable at runtime via NSApp.setActivationPolicy_. Going from Regular
to Accessory mid-session needs a `hide` first (and a brief `deactivate`)
to fully evict the app from the app switcher — without it, macOS lazily
keeps the app in Cmd-Tab even after the policy is supposedly Accessory.
The Dock's "recent applications" entry is a separate Dock-side cache
that we cannot suppress; the user clears it via right-click → Remove
from Dock or by toggling off System Settings → Desktop & Dock → Show
Recent Apps.
"""

from __future__ import annotations

ACTIVATION_POLICY_REGULAR = 0
ACTIVATION_POLICY_ACCESSORY = 1


def apply_activation_policy(*, show_in_dock: bool) -> None:
    """Apply the activation policy to the current NSApp.

    Args:
        show_in_dock: if True, app appears in Dock + Cmd-Tab. If False,
            app is menu-bar-only (Accessory).

    No-op on non-macOS platforms (lets the launcher import cleanly during
    development on Linux / in tests).
    """
    import sys

    if sys.platform != "darwin":
        return

    try:
        from AppKit import NSApplication  # type: ignore[import-not-found]
    except ImportError:
        return

    nsapp = NSApplication.sharedApplication()

    if show_in_dock:
        nsapp.setActivationPolicy_(ACTIVATION_POLICY_REGULAR)
        return

    # Regular → Accessory transition. Without hide_ + deactivate, macOS
    # often leaves the app in Cmd-Tab even though the policy is Accessory.
    # The order matters: hide and deactivate first, then change policy.
    try:
        nsapp.hide_(None)
    except Exception:
        pass
    try:
        nsapp.deactivate()
    except Exception:
        pass
    nsapp.setActivationPolicy_(ACTIVATION_POLICY_ACCESSORY)
