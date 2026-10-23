---
id: 40
title: Claim owners and a work-in-progress limit
type: feature
version: 0.21.0
status: planned
created: 2026-10-23
---

# Plan 40: Claim owners and a work-in-progress limit
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Parallel sessions can pick the same item, and nothing caps how much is open at once.
  - `claim <id> --owner <name>` (default: `$ROADMAP_OWNER`, else the git user name, else the agent name if known) stores `claim_owner`. A claim with an owner refreshed in the last `settings.claimTtlHours` (default 12) is **held**.
  - `claim` on an item held by another owner refuses unless `--take`; the refusal names the owner and claim age. `next` skips held items. `orient` lists the items this owner holds.
  - `settings.wipLimit` (default none). When in-flight items exceed it, `orient`, `next` and `status` print one warning line, and the dashboard header shows the count in red.
- **Out of scope:** locking files or branches; network identity.

## 🏗️ Architectural Blueprint
- **Files to modify:** `scripts/roadmap.py`, `rmlib/ops.py`, `rmlib/parse.py` (`claim_owner`), `rmlib/sync.py`, `rmlib/report.py` or wherever `orient`/`next` live, `rmlib/dashboard.html` (owner on cards and pages, WIP header), docs, tests.

## ✅ Acceptance
- **Passes when:** owner A claims item 5; owner B's `claim 5 --stage review` is refused naming A; with `--take` it succeeds; after the TTL it succeeds without `--take`.
- **Passes when:** `next` skips an item held by another owner; `orient` lists the current owner's held items.
- **Passes when:** with `wipLimit: 3` and 4 in-flight items, `status` prints the warning and the dashboard header flags it.
- **Passes when:** `uvx pytest -q tests/` is green apart from known failures.
- **Fails if:** an existing claim without an owner becomes unclaimable.

## 🚶 Step-by-Step Checklist
- [ ] Step 1: `claim_owner`, held check, `--take`, TTL -> target: rmlib/ops.py, rmlib/parse.py, roadmap.py, tests
- [ ] Step 2: `next` skips held items, `orient` lists own holds -> target: roadmap.py / report module, tests
- [ ] Step 3: `wipLimit` warning in CLI and dashboard -> target: rmlib/sync.py, rmlib/dashboard.html, tests
- [ ] Step 4: docs -> target: references/*.md, SKILL.md
