---
id: 47
title: Bug routing: a bug command that fixes in-flight plans in place or files a linked bug item, and an incubator that refuses bugs
type: feature
version: 0.21.0
status: done
created: 2026-10-23
bugsFound: 51
---

# Plan 47: Bug routing: a bug command that fixes in-flight plans in place or files a linked bug item, and an incubator that refuses bugs
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Bugs sometimes get parked in the Idea Incubator, where nothing tracks them. Route every bug by where it lives.
  - `roadmap.py bug "<title>" [--found-in <id>] [--observed TEXT] [--version X]`:
    - **In-flight origin** (`--found-in` names an item that is not done and has a branch or claim): append a step `- [ ] Step N: Fix: <title>` to that plan, add the observation under a `## 🐞 Found during build` section, set its claim stage to `fixing` (keeping verdict), and print what changed. No new item.
    - **Shipped origin** (origin done, or no `--found-in`): create a `bug` item in the current version (or `--version`), with Observed pre-filled from `--observed`, `foundIn: <id>` recorded on both plans (two-way link), and print the new plan path.
  - `idea` refuses text that reads like a bug report (heuristics: broken, crash, error, fails, regression, doesn't/does not work, wrong, missing, clips, exception, 500) and suggests the `bug` command; `--force` keeps it as an idea.
  - `tidy` reports existing bug-like incubator bullets; `promote` defaults `--type bug` for them.
  - The project rules block (CLAUDE.md / AGENTS.md, via `upgrade`) gains one line: bugs go through `roadmap.py bug`, never the incubator.
  - Dashboard: plan page shows "Found during build" fixes and `foundIn` links; bug items show their origin.
- **Out of scope:** auto-detecting bugs from test output; triage by severity (a later item).

## 🏗️ Architectural Blueprint
- **Files to modify:** `scripts/roadmap.py`, `rmlib/ops.py` (bug routing, append step), `rmlib/incubator.py` (idea refusal, tidy, promote default), `rmlib/core.py` (rules block line), `rmlib/sync.py` (`foundIn` in payload), `rmlib/dashboard.html`, docs, tests.

## ✅ Acceptance
- **Passes when:** with item 5 in flight, `bug "Menu clips" --found-in 5` appends a Fix step to plan 5, sets claim stage `fixing`, and creates no new item.
- **Passes when:** with item 6 done, `bug "Export empty" --found-in 6 --observed "CSV has headers only"` creates a bug item with Observed filled and `foundIn` links both ways.
- **Passes when:** `idea --title "Login page crashes on submit"` is refused with the `bug` suggestion; `--force` stores it; `tidy` lists it.
- **Passes when:** `upgrade` writes the new rules line; the dashboard shows found-during-build fixes and origin links.
- **Passes when:** `uvx pytest -q tests/` is green apart from known failures.
- **Fails if:** a bug for an in-flight item creates a separate item, or ordinary feature ideas are refused (test a set of 20 real incubator bullets from this repo and statewide-app: zero false refusals for non-bugs).

## 🚶 Step-by-Step Checklist
- [x] Step 1: `bug` command with in-flight vs shipped routing, step append, foundIn links -> target: roadmap.py, rmlib/ops.py, tests
  > evidence: 0ca9170 f8afcc2 b571684; 0 false refusals on 372 non-bug titles + 44 statewide ideas; merged 3ae1a72; 574 passed in 165.88s (0:02:45); reviews skipped at owner request (2026-10-24)
- [x] Step 2: idea refusal heuristics with `--force`, tidy report, promote default -> target: rmlib/incubator.py, tests
  > evidence: 0ca9170 f8afcc2 b571684; 0 false refusals on 372 non-bug titles + 44 statewide ideas; merged 3ae1a72; 574 passed in 165.88s (0:02:45); reviews skipped at owner request (2026-10-24)
- [x] Step 3: rules block line and docs -> target: rmlib/core.py, references/state-model.md, SKILL.md
  > evidence: 0ca9170 f8afcc2 b571684; 0 false refusals on 372 non-bug titles + 44 statewide ideas; merged 3ae1a72; 574 passed in 165.88s (0:02:45); reviews skipped at owner request (2026-10-24)
- [x] Step 4: payload and dashboard display -> target: rmlib/sync.py, rmlib/dashboard.html, tests
  > evidence: 0ca9170 f8afcc2 b571684; 0 false refusals on 372 non-bug titles + 44 statewide ideas; merged 3ae1a72; 574 passed in 165.88s (0:02:45); reviews skipped at owner request (2026-10-24)
