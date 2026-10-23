---
id: 34
title: Rulings: record dated decisions on a plan from the CLI and show them on the dashboard
type: feature
version: 0.21.0
status: planned
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
- [ ] Step 1: `ruling` command and section writer -> target: roadmap.py, rmlib/ops.py, tests
- [ ] Step 2: parser for command-written and hand-written rulings, payload fields -> target: rmlib/parse.py, rmlib/sync.py, tests
- [ ] Step 3: dashboard display and approval markers -> target: rmlib/dashboard.html, tests
- [ ] Step 4: docs -> target: references/state-model.md, SKILL.md
