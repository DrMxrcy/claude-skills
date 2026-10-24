---
id: 52
title: Leftovers: note error suggests a missing --audience flag; board copy commands lack the project under serve --all; board filters shared across projects
type: bug
version: 0.19.0
status: done
created: 2026-10-24
foundIn: 48
---

# 🐛 Plan 52: Leftovers: note error suggests a missing --audience flag; board copy commands lack the project under serve --all; board filters shared across projects
> Type: bug · Target: v0.19.0

## 🔍 Symptom & Reproduction
- **Observed:** 1) roadmap.py note error text tells the user to pass --audience, but note has no such flag. 2) Under serve --all the board's copy-command buttons emit 'roadmap.py claim …' with no project path, so they only work when run inside that project. 3) Board choices (BOARD_PICK) and filter chips persist in one localStorage key for every project, so a filter set in one project applies to the next.
- **Expected:** 1) the note refusal names only real commands (`roadmap audience --plan N --to public|internal`). 2) under serve --all, copied commands start with `cd '<project root>' &&` so they run from anywhere; single-project output unchanged. 3) filter chips and the board's show-all-done toggle are stored per project under serve --all; single-project keys unchanged.
- **Repro steps:** 1) refuse a status-dump note on a public item and read the message. 2) serve --all, copy a board command, run it from $HOME. 3) set a lane chip in project A, open project B.

## 🩺 Root Cause
- **Culprit:** note refusal text in `rmlib/ops.py`; board copy commands and storage keys in `rmlib/dashboard.html`; `/api/status` lacked the project root (`rmlib/dashboard.py`).
- **Why:** plans 37 and 48 were built in parallel, so the board never learned the all-projects mode; the note message predates the `audience` command.

## ✅ Acceptance
- **Passes when:** the three repro steps no longer reproduce (tests in tests/test_roadmap_board.py and tests/test_roadmap_serve_all.py)
- **Passes when:** a copied all-mode command run via `sh -c` from another folder lands in the project, including a root with a space and a quote
- **Fails if:** single-project copy commands or storage keys change, or note stops refusing status dumps.

## 🛠️ Checklist
- [x] Step 1: Write a reproduction test
  > evidence: 04812c9 merged 5e7d6dc; 819 passed (roadmap+e2e), 847 incl. install in worktree; 6 new tests; reviews skipped at owner request (2026-10-24)
- [x] Step 2: Apply the fix
  > evidence: 04812c9 merged 5e7d6dc; 819 passed (roadmap+e2e), 847 incl. install in worktree; 6 new tests; reviews skipped at owner request (2026-10-24)
- [x] Step 3: Verify suite is green
  > evidence: 04812c9 merged 5e7d6dc; 819 passed (roadmap+e2e), 847 incl. install in worktree; 6 new tests; reviews skipped at owner request (2026-10-24)
