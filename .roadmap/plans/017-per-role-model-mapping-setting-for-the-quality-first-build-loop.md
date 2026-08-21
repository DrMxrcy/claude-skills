---
id: 17
title: Per-role model mapping setting for the quality-first build loop
type: feature
version: 0.17.0
status: planned
created: 2026-08-21
---

# Plan 17: Per-role model mapping setting for the quality-first build loop
> Type: feature · Target: v0.17.0
> Spec: [notes](../notes/2026-08-20-per-role-model-mapping-setting-for-the-quality-first-build-loop.md)

## 🎯 Target Scope & Boundaries
- **Core objective:** `settings.buildRoles` — optional map {"implementer": "...", "specReviewer": "...", "qualityReviewer": "...", "explorer": "..."} naming the model/agent tier per build-loop role. CLI: `orient`/`handoff` surface it when set; build docs (SKILL.md, quality-build.md, commands/roadmap/build.md) instruct the parent to apply the mapping when spawning subagents. Values are free-form strings (host-agnostic — Claude model names, Grok agents, whatever the host understands).
- **Out of scope:** no validation of model names; no per-item overrides; CLI does not spawn agents itself.

## 🏗️ Architectural Blueprint
- **Files to create:** none
- **Files to modify:** rmlib/report.py (orient payload + human line when buildRoles set), SKILL.md settings table + build docs, references/quality-build.md, commands/roadmap/build.md, tests
- **Schema/interface changes:** `settings.buildRoles` (object, optional) — additive
- **Downstream impact:** none when unset (default)

## ✅ Acceptance
- **Passes when:** with buildRoles set, `orient` (human + --json) shows the mapping; unset → output identical to today
- **Passes when:** build docs tell the parent to honor the mapping per role
- **Fails if:** any behavior change when the setting is absent

## 🚶 Step-by-Step Checklist
- [ ] Step 1: orient/handoff surfacing + tests -> target: report.py + tests
- [ ] Step 2: docs wiring (settings table, build loop, quality-build) -> target: docs
