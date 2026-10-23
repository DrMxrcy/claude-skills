---
id: 27
title: Parallel-safe roadmap builds: per-item worktrees, fresh-session orchestration, pending-decision handoff and per-item token spend
type: feature
version: 0.20.0
status: active
created: 2026-10-23
---

# Plan 27: Parallel-safe roadmap builds: per-item worktrees, fresh-session orchestration, pending-decision handoff and per-item token spend
> Type: feature · Target: v0.20.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Let a user run several roadmap items in parallel without parallel writers colliding on the shared tree or on roadmap state, and without a long orchestrator context accumulating stale diffs. Each item runs in its own worktree and its own fresh session; roadmap state is written only at a single merge step.
- **Decisions:** No fixed concurrency cap; the driver runs as many unblocked items in parallel as the user starts. Per-item branches are cut from the version trunk `roadmap/v<version>`. Items merge into the trunk one at a time through a merge gate (lint, typecheck, unit, integration, build, schema checks) that runs on the trunk, not in the item branch. Builders run only targeted tests for code they touched; the full suite runs once per merged batch.
- **Out of scope:** Building the driver script itself (a follow-up item once the flags are verified against the installed Claude Code version). Changing the quality-review tiers. Auto-merging to main. Cross-provider orchestration.

## 🏗️ Architectural Blueprint
- **Files to create:** `.roadmap/notes/<id>-handoff.md` (written by `handoff`, not hand-authored).
- **Files to modify:**
  - `skills/roadmap/scripts/rmlib/report.py` — `orient` adds branch, dirty file list and last 5 commits; `handoff` accepts a pending-decision line and writes the brief to `.roadmap/notes/`.
  - `skills/roadmap/scripts/roadmap.py` — `handoff --pending "<text>"`; `check --tokens <n>` recorded next to the evidence line.
  - `skills/roadmap/scripts/rmlib/ops.py` — `check_step` stores the optional token count.
  - `commands/roadmap/build.md`, `commands/roadmap/handoff.md`, `commands/roadmap/next.md` — document one orchestrator per item, `--worktree` per item (`roadmap/<id>-<slug>`), and `--auto` as same-session multi-item.
  - `skills/roadmap/references/quality-build.md` — spawn budget per step, respawn-from-brief instead of resume, merge-only roadmap writes.
  - `skills/roadmap/SKILL.md` — routing and invocation table for the new options.
  - `tests/` — tests for orient output, handoff file creation, pending-decision enforcement and token recording.
- **Schema/interface changes:** `handoff` gains `--pending`; `check` gains `--tokens`. Both optional; existing invocations are unchanged.
- **Downstream impact:** Projects that installed the skill need `roadmap.py upgrade` for the new rules block. No change to `ROADMAP.md` layout or `config.json` keys.

## ✅ Acceptance
- **Passes when:** `orient` prints the current branch, a dirty-file list and the last 5 commits, and still prints the same output shape when the tree is clean.
- **Passes when:** `handoff --pending "<decision>"` writes `.roadmap/notes/<id>-handoff.md` containing the pending decision, and the plan file links to that note. `handoff` without `--pending` exits non-zero with a clear message when the active item has an open decision marker.
- **Passes when:** `check --plan <id> --step <n> --evidence "<cmd>: <result>" --tokens <n>` writes the token count on the evidence sub-line; omitting `--tokens` leaves the existing line format unchanged.
- **Passes when:** `build --worktree` on a single item creates `roadmap/<id>-<slug>`, not a version-wide branch.
- **Passes when:** the full pytest suite is green (`python3 -m pytest` from the repo root) and `python3 scripts/validate_skills.py` exits 0.
- **Fails if:** any roadmap state file (`ROADMAP.md`, `.roadmap/config.json`, changelogs) is written from a worktree other than the merge step, or the existing `check` and `status` output format changes for callers that pass no new flags.

## 🚶 Step-by-Step Checklist
- [x] Step 1: Extend `orient` with branch, dirty files and last 5 commits; cover clean and dirty trees in tests -> target: `skills/roadmap/scripts/rmlib/report.py`, `tests/`
  > evidence: python3 -m pytest -q: 334 passed; orient tests: 11 passed (branch, dirty files, last 5 commits, clean tree) (2026-10-23)
- [x] Step 2: Add `handoff --pending` that writes `.roadmap/notes/<id>-handoff.md` and links it from the plan; refuse when an open decision marker is unresolved -> target: `skills/roadmap/scripts/rmlib/report.py`, `skills/roadmap/scripts/roadmap.py`, `tests/`
  > evidence: python3 -m pytest -q: 337 passed; handoff tests: 5 passed (pending writes note, plain handoff refuses while OPEN, --resolve closes it, resolve without decision fails, pending requires --plan); validate_skills.py exit 0 (2026-10-23)
- [x] Step 3: Record optional `--tokens` on `check --evidence` beside the verifier ledger line -> target: `skills/roadmap/scripts/rmlib/ops.py`, `skills/roadmap/scripts/roadmap.py`, `tests/`
  > evidence: python3 -m pytest -q: 339 passed; check tokens tests: 11 passed (token recorded beside evidence, optional, negative refused); validate_skills.py exit 0 (2026-10-23) · tokens: 0
- [x] Step 4: Per-item worktree option for `build --worktree` (`roadmap/<id>-<slug>`) -> target: `commands/roadmap/build.md`, `skills/roadmap/references/quality-build.md`
  > evidence: python3 -m pytest -q: 340 passed; build_worktree doc test: 1 passed (single item -> roadmap/<id>-<slug>, version -> roadmap/v<version>); validate_skills.py exit 0; token spend not measured (2026-10-23)
- [ ] Step 5: Document one-orchestrator-per-item, spawn budget, respawn-from-brief and merge-only roadmap writes -> target: `skills/roadmap/references/quality-build.md`, `skills/agent/references/orchestration-policy.md`, `commands/roadmap/handoff.md`
- [ ] Step 6: Update the routing table and invocation notes in the skill and command docs -> target: `skills/roadmap/SKILL.md`, `commands/roadmap/next.md`
- [ ] Step 7: Merge gate for per-item branches into the version trunk: one item at a time, runs the gate on the trunk, reports conflicts without auto-resolving them, and removes the item worktree only after a green merge -> target: `skills/roadmap/scripts/roadmap.py`, `skills/roadmap/references/quality-build.md`
- [ ] Step 8: Shared builder brief read first by every spawned subagent, with stable content before task content so the prompt prefix caches; respawn from brief plus branch state, never resume -> target: `skills/roadmap/references/quality-build.md`, `skills/agent/references/brief-common.md`
