---
id: 10
title: Typed human-readable ID prefixes (TSK-42, BUG-7) as display layer over int ids
type: feature
version: 0.16.0
status: active
created: 2026-08-20
---

# Plan 10: Typed human-readable ID prefixes (TSK-42, BUG-7) as display layer over int ids
> Type: feature · Target: v0.16.0
> Spec: [research note](../notes/2026-08-19-typed-human-readable-id-prefixes-tsk-42-bug-7-as-display-layer-over-int-ids.md)

## 🎯 Target Scope & Boundaries
- **Core objective:** Render type-prefixed display ids (FEAT-12, BUG-7, REF-3, CHORE-9) in CLI output (status, next, orient, handoff, dashboard) and accept them as input anywhere `--plan` takes an id. Int id in config stays the sole source of truth.
- **Out of scope:** No schema/config change; no change to plan filenames; no prefix customization setting.

## 🏗️ Architectural Blueprint
- **Files to create:** none
- **Files to modify:** skills/roadmap/scripts (core display helper + argparse id-resolver; status/next/orient/report; dashboard), tests
- **Schema/interface changes:** none — display + input parsing only
- **Downstream impact:** ROADMAP.md auto region and changelogs keep `#N` form (git-diff stability) unless trivially safe to switch

## 🚶 Step-by-Step Checklist
- [x] Step 1: display helper `display_id(item)` (FEAT/BUG/REF/CHORE + id) and use it in status, next, orient, handoff, serve output -> target: scripts + tests
- [ ] Step 2: input resolver — `--plan` accepts `7`, `#7`, or `BUG-7` (prefix must match item type; clear error otherwise) -> target: scripts + tests
