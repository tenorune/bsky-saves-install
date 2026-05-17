"""Entry point for `python -m bsky_saves_launcher` — used by Briefcase."""

import sys

from bsky_saves_launcher.app import main

if __name__ == "__main__":
    sys.exit(main())
