---
id: 43
title: Acceptance ledger: mark each acceptance bullet passed with evidence, and require it for done
type: feature
version: 0.21.0
status: planned
created: 2026-10-23
---

# Plan 43: Acceptance ledger: mark each acceptance bullet passed with evidence, and require it for done
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** The ✅ Acceptance list is the definition of done, but only checklist steps get ticked, so a plan can reach 100% with acceptance bullets never verified.
  - `roadmap.py accept <id> --line N --evidence "cmd + result"` marks acceptance bullet N as met (records `> accepted: <date> <evidence>` under it). `--fail` records a failure. `accept <id>` with no flags lists the bullets with their state.
  - `Fails if:` bullets are guards, not marked.
  - Setting `settings.requireAcceptance` (default off for existing projects, on for new `init`): the final `check` that would complete an item is refused while any `Passes when:` bullet is unmarked; the refusal lists them. `--force` overrides and records it.
  - Status payload: `acceptance: {met, failed, total}`; dashboard plan page shows each bullet with its state and evidence; cards show `3/5 accepted`.
- **Out of scope:** running the evidence commands automatically.

## 🏗️ Architectural Blueprint
- **Files to modify:** `rmlib/parse.py` (acceptance bullet parsing + markers), `rmlib/ops.py` (accept, completion gate), `scripts/roadmap.py`, `rmlib/sync.py`, `rmlib/project.py` (`init` default), `rmlib/dashboard.html`, docs (build loop: spec review marks acceptance), tests.

## ✅ Acceptance
- **Passes when:** `accept 7 --line 2 --evidence "pytest green"` writes the marker under bullet 2 and `accept 7` lists it as met.
- **Passes when:** with `requireAcceptance` on, ticking the final step of a plan with an unmarked bullet is refused naming it; `--force` succeeds and records the override.
- **Passes when:** with the setting off, behaviour is unchanged; the dashboard shows per-bullet state.
- **Passes when:** `uvx pytest -q tests/` is green apart from known failures.
- **Fails if:** existing projects get the gate without opting in.

## 🚶 Step-by-Step Checklist
- [ ] Step 1: acceptance parsing and `accept` command -> target: rmlib/parse.py, rmlib/ops.py, roadmap.py, tests
- [ ] Step 2: completion gate behind `requireAcceptance`, `--force` -> target: rmlib/ops.py, rmlib/project.py, tests
- [ ] Step 3: payload and dashboard display -> target: rmlib/sync.py, rmlib/dashboard.html, tests
- [ ] Step 4: docs: spec review marks acceptance bullets -> target: references/quality-build.md, SKILL.md
