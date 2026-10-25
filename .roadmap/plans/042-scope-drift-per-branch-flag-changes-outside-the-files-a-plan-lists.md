---
id: 42
title: Scope drift per branch: flag changes outside the files a plan lists
type: feature
version: 0.21.0
status: done
created: 2026-10-23
---

# Plan 42: Scope drift per branch: flag changes outside the files a plan lists
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Keep each branch inside its plan. Plans already list "Files to create" / "Files to modify" and step targets.
  - Parse the plan's declared paths (blueprint bullets and `-> target:` parts; directories and simple globs allowed; backticked paths preferred).
  - Compare the branch's changed files vs trunk. Files outside the declared set are **off-plan**. Always-allowed paths (tests, lockfiles, `.roadmap/`, changelogs) are configurable via `settings.scopeAllow`.
  - `status --drift` lists items with off-plan files. Payload `offPlan: [paths]` per item. Dashboard: off-plan count chip on cards and a list on the plan page.
  - A plan with no declared paths reports "no declared scope" instead of flagging everything.
- **Out of scope:** blocking commits; judging whether the extra change is justified (that is the reviewer's call).

## 🏗️ Architectural Blueprint
- **Files to modify:** `rmlib/parse.py` (declared path extraction), `rmlib/conflicts.py` or `branches.py` (reuse the cached changed-file lists from the conflict item), `rmlib/sync.py`, `scripts/roadmap.py`, `rmlib/dashboard.html`, docs, tests.

## ✅ Acceptance
- **Passes when:** a plan declaring `src/a.py` with a branch changing `src/a.py`, `tests/test_a.py` and `src/b.py` reports only `src/b.py` as off-plan.
- **Passes when:** directory and glob declarations match; a plan with no declared paths shows "no declared scope".
- **Passes when:** running against this repo's merged plans 30 and 31 reports any off-plan files truthfully (record the result as evidence).
- **Passes when:** `uvx pytest -q tests/` is green apart from known failures.
- **Fails if:** tests, lockfiles or `.roadmap/` files are flagged by default.

## 🚶 Step-by-Step Checklist
- [x] Step 1: declared-path extraction from plan bodies -> target: rmlib/parse.py, tests
  > evidence: f23aacb ad69ee0 integrated 72ec453; plan 30 merge 1 off-plan, plan 31 merge 1 off-plan; statewide 10 branches 5 off-plan 5 no scope; main at f220b16; 761 passed, 1 flaky digest test passes alone; reviews skipped at owner request (2026-10-24)
- [x] Step 2: off-plan computation with allow list, `status --drift`, payload -> target: rmlib/sync.py, roadmap.py, tests
  > evidence: f23aacb ad69ee0 integrated 72ec453; plan 30 merge 1 off-plan, plan 31 merge 1 off-plan; statewide 10 branches 5 off-plan 5 no scope; main at f220b16; 761 passed, 1 flaky digest test passes alone; reviews skipped at owner request (2026-10-24)
- [x] Step 3: dashboard chip and plan-page list -> target: rmlib/dashboard.html, tests
  > evidence: f23aacb ad69ee0 integrated 72ec453; plan 30 merge 1 off-plan, plan 31 merge 1 off-plan; statewide 10 branches 5 off-plan 5 no scope; main at f220b16; 761 passed, 1 flaky digest test passes alone; reviews skipped at owner request (2026-10-24)
