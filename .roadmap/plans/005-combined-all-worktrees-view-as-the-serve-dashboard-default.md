---
id: 5
title: Combined all-worktrees view as the serve dashboard default
type: feature
version: 0.15.0
status: done
created: 2026-07-26
---

# Plan 5: Combined all-worktrees view as the serve dashboard default
> Type: feature · Target: v0.15.0

## 🎯 Target Scope & Boundaries
- **Core objective:** With multiple worktrees, the dashboard defaults to a merged
  "all worktrees" view: items merged by id across checkouts, most-progressed copy
  wins, tagged with the branch it lives on; per-branch views stay in the dropdown.
- **Out of scope:** cross-branch diffing/conflict UI; combining across different
  projects.

## 🏗️ Architectural Blueprint
- **Files to create:** none
- **Files to modify:** `rmlib/dashboard.py` (merge + combined broadcaster,
  `root=all` default), `rmlib/dashboard.html` (all-option, branch badge),
  `tests/test_roadmap.py`
- **Schema/interface changes:** combined payload items gain `branch` + `_root`;
  `root` query accepts `all` (default when >1 checkout).
- **Downstream impact:** none for single-checkout projects.

## 🚶 Step-by-Step Checklist
- [x] Step 1: `_merge_status()` — merge item lists by id (most steps done wins, branch tag), highest currentVersion; unit tests -> target: rmlib/dashboard.py, tests/test_roadmap.py
- [x] Step 2: combined broadcaster + `root=all` default on endpoints; dashboard "all worktrees" option, branch badge, per-item root for step fetches -> target: rmlib/dashboard.py, rmlib/dashboard.html
