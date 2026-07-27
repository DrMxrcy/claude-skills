---
id: 6
title: Live worktree re-discovery in serve — added/deleted checkouts update the dashboard
type: feature
version: 0.15.0
status: done
created: 2026-07-26
---

# Plan 6: Live worktree re-discovery in serve — added/deleted checkouts update the dashboard
> Type: feature · Target: v0.15.0

## 🎯 Target Scope & Boundaries
- **Core objective:** serve re-discovers worktrees every few seconds: deleted
  checkouts drop out of the dashboard (no ghost "v? 0/0" rows), new ones appear,
  all without restarting. Simplify to ONE SSE stream carrying every root's status
  plus the merged view; the dropdown switches views client-side.
- **Out of scope:** watching for the origin checkout itself being deleted while
  serve runs from inside it.

## 🏗️ Architectural Blueprint
- **Files to create:** none
- **Files to modify:** `rmlib/dashboard.py` (single fleet broadcaster with
  periodic re-discovery; delete `_CombinedBroadcaster` + per-root broadcasters),
  `rmlib/dashboard.html` (client-side view switch, no SSE reconnect),
  `tests/test_roadmap.py`
- **Schema/interface changes:** SSE/status payload becomes
  `{_roots, statuses[], merged}`; `root=N` only remains on `/api/item`.
- **Downstream impact:** none — dashboard is the only consumer.

## 🚶 Step-by-Step Checklist
- [x] Step 1: fleet broadcaster — one watcher scans all roots' signatures each second and re-runs `_discover_roots` every 5th tick; payload `{_roots, statuses, merged}`; drop `_CombinedBroadcaster`/per-root fleet; unit test payload shape -> target: rmlib/dashboard.py, tests/test_roadmap.py
- [x] Step 2: client-side view switch — dropdown re-renders from the last payload (no reconnect), out-of-range/removed selection falls back to "all" -> target: rmlib/dashboard.html
