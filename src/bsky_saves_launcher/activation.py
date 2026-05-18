"""macOS NSApp activation policy control.

Two policies relevant for a menu-bar daemon launcher:

- NSApplicationActivationPolicyAccessory (=1): no Dock icon, no Cmd-Tab
  entry, menu-bar presence only. The "daemon" mode.
- NSApplicationActivationPolicyRegular   (=0): standard foreground app
  with Dock entry + Cmd-Tab.

Toggleable at runtime via NSApp.setActivationPolicy_. macOS has minor
visual quirks during the transition (Dock icon may flash briefly) but
the pattern is used by Bartender, Hammerspoon, AeroSpace, Rectangle,
and many others in production.
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

    policy = ACTIVATION_POLICY_REGULAR if show_in_dock else ACTIVATION_POLICY_ACCESSORY
    NSApplication.sharedApplication().setActivationPolicy_(policy)
