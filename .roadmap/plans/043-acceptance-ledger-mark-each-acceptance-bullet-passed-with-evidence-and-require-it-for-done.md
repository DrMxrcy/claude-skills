---
id: 43
title: Acceptance ledger: mark each acceptance bullet passed with evidence, and require it for done
type: feature
version: 0.21.0
status: done
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
- [x] Step 1: acceptance parsing and `accept` command -> target: rmlib/parse.py, rmlib/ops.py, roadmap.py, tests
  > evidence: 250b375 5e3946c b091231 d3d069d + merges 51319cb e1e85c4; acceptance tests; merged ac3bbf9; 702 passed in 178.48s (0:02:58); reviews skipped at owner request (2026-10-24)
- [x] Step 2: completion gate behind `requireAcceptance`, `--force` -> target: rmlib/ops.py, rmlib/project.py, tests
  > evidence: 250b375 5e3946c b091231 d3d069d + merges 51319cb e1e85c4; acceptance tests; merged ac3bbf9; 702 passed in 178.48s (0:02:58); reviews skipped at owner request (2026-10-24)
- [x] Step 3: payload and dashboard display -> target: rmlib/sync.py, rmlib/dashboard.html, tests
  > evidence: 250b375 5e3946c b091231 d3d069d + merges 51319cb e1e85c4; acceptance tests; merged ac3bbf9; 702 passed in 178.48s (0:02:58); reviews skipped at owner request (2026-10-24)
- [x] Step 4: docs: spec review marks acceptance bullets -> target: references/quality-build.md, SKILL.md
  > evidence: 250b375 5e3946c b091231 d3d069d + merges 51319cb e1e85c4; acceptance tests; merged ac3bbf9; 702 passed in 178.48s (0:02:58); reviews skipped at owner request (2026-10-24)
