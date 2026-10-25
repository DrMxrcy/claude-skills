---
id: 34
title: Rulings: record dated decisions on a plan from the CLI and show them on the dashboard
type: feature
version: 0.21.0
status: done
created: 2026-10-23
---

# Plan 34: Rulings: record dated decisions on a plan from the CLI and show them on the dashboard
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Plans collect decisions by convention (`- **Ruling (2026-10-22, owner):** ...`) appended by hand, because `note` is the changelog and rightly refuses them. Add a command and show the result.
  - `roadmap.py ruling <id> --text "..." [--by owner|<name>] [--approval]` appends a dated bullet under a `## ⚖️ Rulings` section (created if missing) in the plan body. `--approval` marks an owner sign-off.
  - Existing hand-written `**Ruling (date, who):**` bullets anywhere in the body are parsed too.
  - Status payload and `/api/item` include `rulings: [{date, by, text, approval}]`; the plan page and item card show them, with approvals flagged and a "needs approval" marker when the plan declares `approval: required` in frontmatter and none exists.
- **Out of scope:** editing or deleting rulings (append-only, edit the file by hand if wrong).

## 🏗️ Architectural Blueprint
- **Files to modify:** `scripts/roadmap.py`, `rmlib/ops.py`, `rmlib/parse.py` (ruling parser), `rmlib/sync.py`, `rmlib/dashboard.*`, docs, tests.

## ✅ Acceptance
- **Passes when:** `ruling 7 --text "Use tabs" --approval` adds a dated bullet under `## ⚖️ Rulings` and `/api/item?id=7` returns it with `approval: true`.
- **Passes when:** a pre-existing hand-written ruling bullet is parsed with its date and author.
- **Passes when:** the dashboard plan page lists rulings, approvals flagged; `uvx pytest -q tests/` green apart from known failures.
- **Fails if:** `ruling` writes to the changelog or to ROADMAP.md.

## 🚶 Step-by-Step Checklist
- [x] Step 1: `ruling` command and section writer -> target: roadmap.py, rmlib/ops.py, tests
  > evidence: 0cff1c3 40d9356 fc11562 08c9936; merged dcbd5c0; 444 passed; statewide read-only 65 rulings parsed from 46 plans; reviews skipped at owner request (2026-10-23)
- [x] Step 2: parser for command-written and hand-written rulings, payload fields -> target: rmlib/parse.py, rmlib/sync.py, tests
  > evidence: 0cff1c3 40d9356 fc11562 08c9936; merged dcbd5c0; 444 passed; statewide read-only 65 rulings parsed from 46 plans; reviews skipped at owner request (2026-10-23)
- [x] Step 3: dashboard display and approval markers -> target: rmlib/dashboard.html, tests
  > evidence: 0cff1c3 40d9356 fc11562 08c9936; merged dcbd5c0; 444 passed; statewide read-only 65 rulings parsed from 46 plans; reviews skipped at owner request (2026-10-23)
- [x] Step 4: docs -> target: references/state-model.md, SKILL.md
  > evidence: 0cff1c3 40d9356 fc11562 08c9936; merged dcbd5c0; 444 passed; statewide read-only 65 rulings parsed from 46 plans; reviews skipped at owner request (2026-10-23)
