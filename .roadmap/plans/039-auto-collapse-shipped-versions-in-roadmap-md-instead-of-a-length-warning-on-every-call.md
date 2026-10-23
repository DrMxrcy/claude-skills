---
id: 39
title: Auto-collapse shipped versions in ROADMAP.md instead of a length warning on every call
type: chore
version: 0.21.0
status: planned
created: 2026-10-23
---

# Plan 39: Auto-collapse shipped versions in ROADMAP.md instead of a length warning on every call
> Type: chore · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** The ROADMAP.md length warning prints on every command, even though shipped versions already collapse automatically (`settings.collapseShipped`). Count only what sync does not control.
  - Measure the free-form region (Idea Incubator and anything outside the auto block), not the whole file. Warn only when that region exceeds the limit, and at most once per session per project (stamp in a gitignored cache file, or only in `orient` and `tidy`).
  - If collapse is off and the auto block is long, suggest enabling collapse once.
- **Out of scope:** changing the collapse behaviour itself.

## 🏗️ Architectural Blueprint
- **Files to modify:** wherever the length warning is emitted (sync/core), `tidy`, tests.

## ✅ Acceptance
- **Passes when:** a project with 30 shipped versions collapsed and a short incubator prints no warning on `status`.
- **Passes when:** a long incubator triggers the warning in `orient` and `tidy` only, naming the region to trim.
- **Passes when:** `uvx pytest -q tests/` green apart from known failures.
- **Fails if:** a genuinely long free-form region is never reported.

## 🚶 Step-by-Step Checklist
- [ ] Step 1: measure the free-form region, warn only in orient and tidy -> target: rmlib/sync.py or core, tests
- [ ] Step 2: collapse-off hint -> target: same, tests
