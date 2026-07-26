---
id: 4
title: Worktree-aware serve/orient: detect git worktrees, warn when dashboard serves a stale branch's roadmap vs main checkout
type: feature
version: 0.15.0
status: active
created: 2026-07-26
---

# Plan 4: Worktree-aware serve/orient: detect git worktrees, warn when dashboard serves a stale branch's roadmap vs main checkout
> Type: feature · Target: v0.15.0

## 🎯 Target Scope & Boundaries
- **Core objective:** One `roadmap serve` run from any checkout (main or linked git
  worktree) serves ALL checkouts that have a `.roadmap/`: the dashboard grows a
  worktree switcher, and starting serve from a second checkout finds the running
  instance instead of starting a duplicate.
- **Out of scope:** orient-side stale-branch warnings (separate follow-up), live
  re-discovery of worktrees added after startup (restart serve to pick them up).

## 🏗️ Architectural Blueprint
- **Files to create:** none
- **Files to modify:** `rmlib/dashboard.py` (root discovery, per-root broadcasters,
  `?root=N` on the JSON/SSE endpoints), `rmlib/dashboard.html` (switcher UI),
  `tests/test_roadmap.py`
- **Schema/interface changes:** status payload gains `_root` (index) and `_roots`
  (list of `{path, branch, name}`); all API endpoints accept optional `root=N`.
- **Downstream impact:** none — single-checkout behavior is byte-identical
  (`_roots` has one entry, switcher hidden).

## 🚶 Step-by-Step Checklist
- [x] Step 1: `_discover_roots()` — enumerate `git worktree list --porcelain`, keep checkouts with `.roadmap/`, capture branch; graceful fallback to `[root]` outside git; unit tests -> target: rmlib/dashboard.py, tests/test_roadmap.py
- [x] Step 2: multi-root serve — per-root `_Broadcaster`s, `root=N` query on `/events`, `/api/status`, `/api/item`, `/api/changelog`; port + already-running dedupe keyed on primary (main-checkout) root -> target: rmlib/dashboard.py
- [ ] Step 3: dashboard switcher — worktree/branch selector in header when >1 root, SSE reconnect + step fetches scoped to selected root -> target: rmlib/dashboard.html
