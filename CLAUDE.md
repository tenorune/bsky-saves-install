# CLAUDE.md

Notes for future Claude sessions working in this repo.

## Read `docs/lessons.md` before debugging UI / layout issues

`docs/lessons.md` is the standing record of hard-won debugging facts about this codebase — especially the macOS PyObjC / AppKit interactions (NSPopover, NSStackView, NSVisualEffectView) that are easy to get wrong and time-consuming to rediscover. Consult it any time you're touching popover layout, panel rendering, or any AppKit code that's behaving unexpectedly. When you finish a debugging session that produced a non-trivial finding, append it to that file.
