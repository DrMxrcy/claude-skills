---
id: 8
title: Auto-release nudge: when current version hits 100%, prompt or auto-run roadmap release before starting next version
type: feature
version: 0.16.0
status: planned
created: 2026-08-13
---

# Plan 8: Auto-release nudge: when current version hits 100%, prompt or auto-run roadmap release before starting next version
> Type: feature · Target: v0.16.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Make releasing part of the roadmap flow itself. When every item in the current version is 100%, the CLI detects "version complete — uncut" and, per `settings.autoRelease` (`off` | `nudge` (default) | `auto`), either prints a release nudge or runs `release` directly before new work proceeds. Prevents finished versions piling up as "(in progress)" (the Parkboxd failure mode).
- **Out of scope:** Git tagging changes, changelog rendering changes, any dashboard/serve UI for this (nudge text in SSE payload is fine if free), version-number auto-bump heuristics.

## 🏗️ Architectural Blueprint
- **Files to create:** none
- **Files to modify:**
  - `skills/roadmap/scripts/rmlib/sync.py` — helper `uncut_complete_version(root) -> str | None` reusing `_version_complete` + progress map; surface in `status`/`orient` output.
  - `skills/roadmap/scripts/rmlib/ops.py` — gate in `check_step` (after final step of final item completes → nudge/auto-release), and in `new_item` / `promote_idea` / `next_item` path when targeting a later version while current is complete.
  - `skills/roadmap/scripts/rmlib/core.py` — read `settings.autoRelease` from config (default `nudge`).
  - `skills/roadmap/SKILL.md` + build/next command docs — document the gate and config knob.
- **Schema/interface changes:** new optional `settings.autoRelease` key in `.roadmap/config.json`; no plan-file schema change.
- **Downstream impact:** `--auto` build chains hit the same gate between versions; `auto` mode must be non-interactive-safe (no prompt, just release + print). `off` preserves today's behavior exactly.

## 🚶 Step-by-Step Checklist
- [ ] Step 1: Detection helper `uncut_complete_version` + surface "version complete — uncut" in status/orient -> target: rmlib/sync.py
- [ ] Step 2: `settings.autoRelease` config read (off|nudge|auto, default nudge) -> target: rmlib/core.py
- [ ] Step 3: Wire gate into check_step / new_item / promote_idea / next_item (nudge prints command; auto calls release()) -> target: rmlib/ops.py
- [ ] Step 4: Tests for all three modes + docs (SKILL.md, build/next command md) -> target: tests, skills/roadmap/SKILL.md
