---
id: 36
title: Worktree map: status --worktrees and a dashboard worktree panel with safe-to-remove marks
type: feature
version: 0.21.0
status: planned
created: 2026-10-23
---

# Plan 36: Worktree map: status --worktrees and a dashboard worktree panel with safe-to-remove marks
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Parallel builds leave dozens of worktrees. Show them in one table instead of a hand-run survey.
  - `status --worktrees` lists each linked worktree: path, branch, item id and lane (via discovery), dirty file count, unmerged commits vs trunk, claim stage, last commit age, and a **safe to remove** mark (clean, and branch fully merged into trunk or deleted).
  - Dashboard worktree panel with the same columns; panel header turns red when the count exceeds `settings.worktreeWarn` (default 20).
  - The removal command for safe worktrees is printed (`git worktree remove <path>`), never run.
- **Out of scope:** removing worktrees or branches automatically.

## 🏗️ Architectural Blueprint
- **Files to modify:** `rmlib/branches.py` (worktree enumeration incl. dirty counts, batched and cached; dirty counts refreshed at most every 10 s), `rmlib/sync.py` (payload `worktrees`), `scripts/roadmap.py`, `rmlib/dashboard.*`, docs, tests.
- **Cost:** dirty count needs one `git status --porcelain` per worktree; cache with a time budget so the 1 s dashboard tick does not run them every second.

## ✅ Acceptance
- **Passes when:** in a fixture with three worktrees (dirty, merged-clean, unmerged-clean) `status --worktrees` shows correct dirty counts, unmerged counts, and marks only the merged-clean one safe.
- **Passes when:** the dashboard panel shows the same rows and the red header past the threshold.
- **Passes when:** the dashboard tick with 30 worktrees and unchanged refs runs no per-worktree git calls more often than every 10 s; `uvx pytest -q tests/` green apart from known failures.
- **Fails if:** any command deletes a worktree or branch.

## 🚶 Step-by-Step Checklist
- [ ] Step 1: worktree enumeration with dirty counts and time-budgeted cache -> target: rmlib/branches.py, tests
- [ ] Step 2: `status --worktrees` and payload -> target: roadmap.py, rmlib/sync.py, tests
- [ ] Step 3: dashboard panel -> target: rmlib/dashboard.html, tests
- [ ] Step 4: docs -> target: references/*.md
