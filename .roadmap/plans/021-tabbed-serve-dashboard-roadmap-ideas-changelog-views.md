---
id: 21
title: "Tabbed serve dashboard: Roadmap, Ideas, Changelog views"
type: feature
version: 0.18.0
status: done
created: 2026-08-28
---

# Plan 21: Tabbed serve dashboard: Roadmap, Ideas, Changelog views
> Type: feature · Target: v0.18.0

## 🎯 Target Scope & Boundaries
- **Core objective:** `roadmap serve` gets a tab bar in the header — **Roadmap** (today's view, unchanged), **Ideas** (the Idea Incubator bullets), **Changelog** (versions + notes from the existing `/api/changelog`). Tab choice persists in localStorage; the SSE live stream keeps driving the Roadmap tab.
- **Out of scope:** Any write path (the dashboard stays read-only — no editing ideas or checking steps from the browser). No new dependencies; still a single static `dashboard.html` + stdlib HTTP server. No auth/remote binding change (127.0.0.1 only).

## 🏗️ Architectural Blueprint
- **Files to create:** none.
- **Files to modify:**
  - `skills/roadmap/scripts/roadmap.py` — add `list_incubator_bullets` and `incubator_file` to the `rm` SimpleNamespace handed to the dashboard.
  - `skills/roadmap/scripts/rmlib/dashboard.py` — new `/api/ideas` GET endpoint (root-aware, same `?root=` convention as `/api/item`), returning `{"file": ..., "bullets": [...]}`; errors returned as `{"error": ...}` like the other endpoints.
  - `skills/roadmap/scripts/rmlib/dashboard.html` — tab bar, three panes, per-tab render functions, lazy fetch on first activation + refetch when the SSE payload changes, tab persistence.
- **Schema/interface changes:** `rm` interface grows two callables; one new read-only JSON endpoint.
- **Downstream impact:** none outside serve; CLI commands untouched.

## ✅ Acceptance
- **Passes when:** `roadmap serve` shows a Roadmap/Ideas/Changelog tab bar; clicking Ideas lists the incubator bullets (from `ROADMAP.md` or `settings.incubatorFile`), and Changelog lists versions newest-first with notes/sections; reloading the page returns to the last tab.
- **Passes when:** `GET /api/ideas` returns bullets JSON, `GET /api/ideas?root=N` reads worktree N, and an absent incubator yields an empty list, not a 500.
- **Passes when:** the existing test suite is green (`python3 -m pytest` in the repo).
- **Fails if:** any browser-side write path is added, innerHTML is used for server data, the SSE Roadmap view regresses, or the dashboard gains a runtime dependency.

## 🚶 Step-by-Step Checklist
- [x] Step 1: Expose incubator readers on the `rm` interface and add the `/api/ideas` endpoint -> target: roadmap.py, rmlib/dashboard.py
  > evidence: pytest: 324 passed; live serve on :4799 returned /api/ideas + /api/changelog JSON and the tab bar in / (2026-08-28)
- [x] Step 2: Tab bar + Ideas pane in the dashboard UI (lazy load, persisted tab) -> target: rmlib/dashboard.html
  > evidence: pytest: 324 passed; live serve on :4799 returned /api/ideas + /api/changelog JSON and the tab bar in / (2026-08-28)
- [x] Step 3: Changelog pane rendering the existing /api/changelog payload -> target: rmlib/dashboard.html
  > evidence: pytest: 324 passed; live serve on :4799 returned /api/ideas + /api/changelog JSON and the tab bar in / (2026-08-28)
- [x] Step 4: Tests for /api/ideas (present, empty, root-scoped) + full suite green -> target: tests/
  > evidence: pytest: 324 passed; live serve on :4799 returned /api/ideas + /api/changelog JSON and the tab bar in / (2026-08-28)
