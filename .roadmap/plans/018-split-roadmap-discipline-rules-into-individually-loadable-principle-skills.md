---
id: 18
title: Split roadmap discipline rules into individually loadable principle skills
type: refactor
version: 0.17.0
status: done
created: 2026-08-21
---

# Plan 18: Split roadmap discipline rules into individually loadable principle skills
> Type: refactor · Target: v0.17.0
> Spec: [notes](../notes/2026-08-20-split-roadmap-discipline-rules-into-individually-loadable-principle-skills.md)

## 🎯 Target Scope & Boundaries
- **Core objective:** cut per-session context cost of the CLAUDE.md/AGENTS.md rules block. Move the long-form norms (multi-coder sync narrative, quality-build protocol detail, incubator hygiene detail) into skill reference files loaded on demand (references/ already exists — extend it), and shrink the injected rules block that `init`/`upgrade` writes to a compact core (orient-first, nothing off-roadmap, one item at a time, micro-commit, never hand-edit) plus pointers to the references.
- **Out of scope:** no new standalone skills/ directories per principle (pstack-style 23-skill split is overkill here); no behavior change to CLI; existing installed projects only change on `upgrade`.

## 🏗️ Architectural Blueprint
- **Files to create:** possibly 1–2 new references/*.md (e.g. multi-coder-sync.md) — reuse existing quality-build.md where it fits
- **Files to modify:** rmlib/project.py (RULES block template), SKILL.md pointers, tests asserting rules-block content
- **Schema/interface changes:** none; rules-block version marker bumps so `upgrade` refreshes it
- **Downstream impact:** projects get the smaller block on next `roadmap.py upgrade`

## ✅ Acceptance
- **Passes when:** injected rules block shrinks meaningfully (target ≥40% fewer lines) while every dropped norm lives in a referenced file the block names
- **Passes when:** `upgrade` swaps old block for new in an existing project (test)
- **Fails if:** any core guardrail (CLI-only edits, one-item-at-a-time, micro-commit, orient-first) disappears from the injected block

## 🚶 Step-by-Step Checklist
- [x] Step 1: draft compact rules block + move long-form to references, update project.py + tests -> target: project.py, references/
  > evidence: block 41 to 22 lines (46%); reviewer traced every dropped norm to SKILL.md/references; mutations killed (2026-08-21)
- [x] Step 2: verify upgrade path swaps blocks in an existing repo; sync SKILL.md pointers -> target: tests + docs
  > evidence: live upgrade swap verified idempotent in scratch repo; fresh init gets compact block (2026-08-21)
