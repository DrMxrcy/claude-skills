---
id: 46
title: Waiting steps and split retarget: time-gated checks no longer hold up a release or drag the whole feature to the next version
type: feature
version: 0.21.0
status: planned
created: 2026-10-23
---

# Plan 46: Waiting steps and split retarget: time-gated checks no longer hold up a release or drag the whole feature to the next version
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Some steps can only be verified after time passes (a 7-day soak in production, a certificate or DNS propagation window, a retention or billing cycle, a store review). Today such a step keeps the item below 100%, blocks the version cut, and `retarget` moves the entire feature, including all the shipped work, to the next version. Separate "built" from "verified after a wait".
  - **Waiting steps:** `roadmap.py wait <id> --step N --until <date|7d> [--reason TEXT]` marks a step as waiting (`- [~] Step N: ... (waiting until 2026-10-30: soak)`). A waiting step counts as not done, but the item gets lane `waiting` once all its other steps are ticked. `wait --clear` reverts it.
  - **Due reminders:** `orient`, `next`, `status` and the digest list waiting steps that are due today or overdue, first in the list. `check` on a waiting step works as normal and removes the wait marker.
  - **Release with waiting steps:** `release` of a version whose only unfinished steps are waiting steps is allowed with `--with-waiting`. Those items ship in the changelog as released, and each waiting step moves into an automatic **follow-up item** in the next version (`Follow-up: <title> — verify after soak`, linked both ways, carrying the wait date and reason). Without the flag, `release` names the waiting steps and suggests the flag.
  - **Split retarget:** `retarget <id> --version X --split` keeps the ticked steps in the current version (the original item completes there) and moves only the unticked steps into a new linked follow-up item in version X. Plain `retarget` stays as is.
  - **Dashboard:** `waiting` lane badge with a countdown ("4d left", "due", "2d overdue"); waiting steps highlighted on the plan page; follow-up links both ways; the board (#37) gets a waiting column.
- **Out of scope:** scheduling or running the verification itself; notifications outside the CLI and dashboard.

## 🏗️ Architectural Blueprint
- **Files to modify:** `rmlib/parse.py` (`[~]` step state with until/reason), `rmlib/ops.py` (wait, check on waiting step, follow-up creation, split retarget), `rmlib/changelog.py` / release code (`--with-waiting`), `rmlib/sync.py` (lane `waiting`, progress counts waiting separately: `done`, `waiting`, `total`), `scripts/roadmap.py`, orient/next code, `rmlib/dashboard.html`, docs, tests.
- **Compatibility:** older skill versions read `[~]` as unticked (correct: not done). ROADMAP.md progress shows `5/7 (+1 waiting)`.

## ✅ Acceptance
- **Passes when:** `wait 7 --step 3 --until 7d --reason soak` marks the step; with all other steps ticked, item 7 shows lane `waiting` and the countdown in status and dashboard.
- **Passes when:** on the due date, `orient` and `next` list the step first; `check --plan 7 --step 3` ticks it and the item becomes done.
- **Passes when:** `release 0.21.0` with item 7 waiting refuses naming the step; `release 0.21.0 --with-waiting` ships it and creates a linked follow-up item in the next version holding the waiting step with its date.
- **Passes when:** `retarget 9 --version 0.22.0 --split` on an item with 4 of 6 steps ticked leaves item 9 done in its version with 4 steps and creates a follow-up in 0.22.0 with the 2 open steps.
- **Passes when:** `uvx pytest -q tests/` is green apart from known failures.
- **Fails if:** a waiting step ever counts as done, or plain `retarget` changes behaviour.

## 🚶 Step-by-Step Checklist
- [ ] Step 1: `[~]` waiting step format, `wait` and `wait --clear`, check on a waiting step -> target: rmlib/parse.py, rmlib/ops.py, roadmap.py, tests
- [ ] Step 2: `waiting` lane, progress counts, due reminders in orient, next and status -> target: rmlib/sync.py, orient code, tests
- [ ] Step 3: follow-up item creation with two-way links -> target: rmlib/ops.py, tests
- [ ] Step 4: `release --with-waiting` and `retarget --split` -> target: release code, roadmap.py, tests
- [ ] Step 5: dashboard countdown, plan-page highlight, follow-up links -> target: rmlib/dashboard.html, tests
- [ ] Step 6: docs -> target: references/state-model.md, SKILL.md
