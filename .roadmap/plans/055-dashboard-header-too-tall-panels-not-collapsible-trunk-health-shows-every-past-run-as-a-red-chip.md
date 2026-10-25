---
id: 55
title: Dashboard: header too tall, panels not collapsible, trunk health shows every past run as a red chip
type: bug
version: 0.19.0
status: done
created: 2026-10-25
foundIn: 38
---

# 🐛 Plan 55: Dashboard: header too tall, panels not collapsible, trunk health shows every past run as a red chip
> Type: bug · Target: v0.19.0

## 🔍 Symptom & Reproduction
- **Observed:** On statewide (430 items, ~40 suite runs) the header block takes a third of the screen before any item; the slot strip, trunk health tile, gate timeline and other panels cannot be collapsed; trunk health renders one chip per suite-run label (each run without --shards is its own shard), so superseded e2e/unit runs stay red forever and the failing-name list grows unbounded.
- **Expected:** (1) compact header: title, version, view select, progress and counts on at most two short rows; attention/refresh/alerts/theme as small controls on the same row; tabs + filter controls on one row; header no taller than ~140px at 1400px wide. (2) every panel (slots, trunk health, gate timeline, worktrees, conflicts, other branches) is a collapsible section with a one-line summary in its header (e.g. `trunk health · 2 failing (e2e, unit) · last suite 3h ago`), collapsed by default unless red, state remembered per project; expand-all/collapse-all covers panels too. (3) trunk health shows the latest result per suite kind: runs grouped by a normalised shard key (explicit `--shards` names, else the label with commit shas, spec counts and parenthetical notes stripped, e.g. `e2e`, `unit`), only the newest run per key shown, superseded runs in a collapsed history; failing names capped at 5 with `+N more`.
- **Repro steps:** `claude-roadmap serve` in statewide-app (40+ suite runs in .roadmap/runs.jsonl) at 1400x900.

## 🩺 Root Cause
- **Culprit:** `rmlib/dashboard.html` header layout and panel renderers (slotStrip, runPanel/healthTile, gates, worktreePanel, conflicts, otherSection); `rmlib/runs.py` trunk_health shard keying.
- **Why:** each panel was added by a separate plan (33, 36, 38, 41, 50) as an always-open block; trunk health keyed shards by raw label, which only works when runs pass `--shards`.

## ✅ Acceptance
- **Passes when:** at 1400x900 on statewide (read-only serve) the first item row is visible without scrolling, and every panel collapses and remembers its state across reloads (Playwright check, screenshot recorded)
- **Passes when:** a runs fixture with five `e2e ... on <sha>` suite runs (older fail, newest pass) shows one `e2e` chip, green, with older runs only in history; failing names over 5 show `+N more`
- **Fails if:** status JSON `trunkHealth` drops fields existing consumers use, board/plan pages or serve --all routing regress, or text goes in via innerHTML.

## 🛠️ Checklist
- [x] Step 1: Write a reproduction test
  > evidence: ad6adf6 repro tests failed before fix; a487569; header 242px -> 89px at 1400x900 on statewide, first item visible without scroll, panels collapse and persist; merged 5acfe6b; 848 passed in 446.26s (0:07:26); reviews skipped at owner request (2026-10-25)
- [x] Step 2: Apply the fix
  > evidence: ad6adf6 repro tests failed before fix; a487569; header 242px -> 89px at 1400x900 on statewide, first item visible without scroll, panels collapse and persist; merged 5acfe6b; 848 passed in 446.26s (0:07:26); reviews skipped at owner request (2026-10-25)
- [x] Step 3: Verify suite is green
  > evidence: ad6adf6 repro tests failed before fix; a487569; header 242px -> 89px at 1400x900 on statewide, first item visible without scroll, panels collapse and persist; merged 5acfe6b; 848 passed in 446.26s (0:07:26); reviews skipped at owner request (2026-10-25)
