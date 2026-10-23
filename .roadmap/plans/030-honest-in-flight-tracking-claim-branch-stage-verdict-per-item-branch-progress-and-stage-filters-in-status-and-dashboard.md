---
id: 30
title: Honest in-flight tracking: claim branch/stage/verdict per item, branch progress and stage filters in status and dashboard
type: feature
version: 0.19.0
status: planned
created: 2026-10-23
---

# Plan 30: Honest in-flight tracking: claim branch/stage/verdict per item, branch progress and stage filters in status and dashboard
> Type: feature · Target: v0.19.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Make `status` and the `serve` dashboard show all work done across branches, not just ticks on trunk. Evidence from a real consumer project (statewide-app, 2026-10-23): 30 unmerged `roadmap/<id>` branches, 27 worktrees, feature commits tagged `(plan NNN)` / `(bug NNN)`, and **branches never touch `.roadmap/` or ROADMAP.md**. Ticks and evidence lines are written on main only after the merge gate. So today's worktree merge view (which reads each checkout's plan checkboxes) shows 0% for every built branch. The fix reads git itself: discover each item's branch and tagged commits, derive an in-flight **lane** per item, and let the build loop record what git cannot know (stage, review verdict) with a trunk-committed `claim`.
- **Lanes (derived, display only):** `done` (all trunk steps ticked) · `gating` / `gate-ready` / `review` / `fixing` / `blocked` (from claim stage) · `building` (branch or tagged commits exist, no claim) · `stale` (branch with no commit in `staleDays`, default 7) · `planned`. Verdict enum: `CONFIRMED` · `PARTIAL` · `REFUTED`.
- **Out of scope:** changing how planned/active/done is derived (trunk checkboxes stay the only source of done); any write to a branch other than the current one; remote CI polling; ticking steps on branches; the parked incubator ideas.

## 🏗️ Architectural Blueprint
- **Files to create:** `skills/roadmap/scripts/rmlib/branches.py` (git discovery, cached by ref signature).
- **Files to modify:** `scripts/roadmap.py` (`claim` subparser; `status --open`, `--version`, `--in-flight`), `rmlib/sync.py` (status payload gains `branch`, `claim`, `lane`), `rmlib/ops.py` (claim write/clear, auto-clear on done), `rmlib/dashboard.py` + `dashboard.html` (default view = trunk plus branch overlay; the per-worktree dropdown stays as a secondary view), `references/state-model.md`, `references/quality-build.md`, `SKILL.md`, `tests/test_roadmap.py`, `tests/test_roadmap_serve.py`.
- **Discovery rules (branches.py):** a single `git for-each-ref refs/heads` call. A branch maps to item N when its name matches `settings.branchPattern` (default `roadmap/{id}` plus `roadmap/{id}-*`). Commits on any unmerged branch whose subject contains `(plan N)` or `(bug N)` also attach to N. Per branch: `ahead`/`behind` vs trunk, last commit sha/date/subject, merged flag, worktree path (from `git worktree list --porcelain`), and count of tagged commits. Non-item branches (e.g. `roadmap/v0.8.0`, `fix/*`) are listed under "other branches", not dropped. The result is cached on the for-each-ref output so the 1s dashboard tick stays cheap with 30+ branches.
- **Claim schema:** optional plan-frontmatter `claim:` block (`stage`, `verdict`, `note`, `branch` override, `updated`), written only by `roadmap.py claim <id> --stage X [--verdict V] [--note N] [--branch B]` and removed by `claim <id> --clear`. If `--branch` is omitted, the discovered branch is used.
- **Status JSON:** items gain `lane`, `claim` (object|null), `branch` ({name, ahead, behind, lastCommit, lastDate, worktree, taggedCommits, merged} | null). Old clients ignore the new keys. `/api/item` detail gains the branch's commit list (max 20).
- **Downstream impact:** works with or without worktrees and with no claims at all. Discovery alone turns "0% everywhere" into "building · roadmap/401 · 9 commits ahead". A missing or deleted branch gives `branch: null`, never an error.

## ✅ Acceptance
- **Passes when:** in a fixture repo with item 7 at 0/3 on trunk and branch `roadmap/7` 4 commits ahead, `status` shows item 7 as `building · roadmap/7 · +4` and `/api/status` returns `lane: "building"` plus branch data. A commit tagged `(plan 9)` on an unrelated branch attaches to item 9.
- **Passes when:** `claim 7 --stage gate-ready --verdict CONFIRMED` sets lane `gate-ready` and shows the verdict. `claim 7 --clear` reverts to the derived lane. Ticking the last trunk step clears the claim automatically.
- **Passes when:** the dashboard header shows done / in-flight / planned counts; each in-flight item shows a lane badge, verdict chip, branch name, commits-ahead and last-commit age; expanding an item lists its branch commits; "open only" and lane filters work.
- **Passes when:** `status --open` hides done items and shipped versions, `--version X` shows one version, and `--in-flight` shows only items with a branch or claim.
- **Passes when:** a branch with no commits in `staleDays` shows lane `stale`; invalid stage/verdict values are rejected with a clear error.
- **Passes when:** `python3 -m pytest tests/test_roadmap.py tests/test_roadmap_serve.py` is green, and a manual `serve` run against statewide-app (read-only) shows its built branches as in-flight instead of 0%.
- **Fails if:** done/active/planned derivation changes, any command writes outside the current checkout, ROADMAP.md is hand-edited, or the dashboard tick runs more than a few git calls per second when refs are unchanged.

## 🚶 Step-by-Step Checklist
- [ ] Step 1: `rmlib/branches.py` — ref discovery, branchPattern + `(plan N)`/`(bug N)` commit attribution, ahead/behind, worktree map, ref-signature cache, fixture-repo tests -> target: rmlib/branches.py, tests/test_roadmap.py
- [ ] Step 2: `claim` CLI — frontmatter write/clear, enum validation, auto-clear on done -> target: roadmap.py, rmlib/ops.py, tests/test_roadmap.py
- [ ] Step 3: lane derivation in the status payload and `status` text; `--open`, `--version`, `--in-flight` filters -> target: rmlib/sync.py, roadmap.py, tests/test_roadmap.py
- [ ] Step 4: dashboard — trunk plus branch overlay as the default view, lane badges, verdict chips, header counts, commit list on expand, open/lane filters, "other branches" panel -> target: rmlib/dashboard.py, rmlib/dashboard.html, tests/test_roadmap_serve.py
- [ ] Step 5: docs and build loop — claim at review/fixing/gate-ready/gating, branch naming `roadmap/<id>` and `(plan N)` commit tags as the convention -> target: references/state-model.md, references/quality-build.md, SKILL.md
- [ ] Step 6: read-only smoke run of `serve` and `status --in-flight` against statewide-app; record the before/after counts as evidence -> target: plan evidence
