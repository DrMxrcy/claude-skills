---
id: 28
title: Council review: plan review and merge gate by multiple agent CLIs
type: feature
version: 0.19.0
status: planned
created: 2026-10-23
---

# Plan 28: Council review: plan review and merge gate by multiple agent CLIs
> Type: feature · Target: v0.19.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Before a plan is built, and before an item branch merges, every reachable agent CLI on the machine reviews the work read-only and returns one verdict. A rejection blocks the merge until it is resolved or the user overrides it.
- **Checkpoints:** (1) plan review, run after `/roadmap-plan` scaffolds a plan and before `/roadmap-build` writes code; (2) merge gate, run on the item diff against the plan's acceptance list before the branch merges into the trunk.
- **Members:** every installed CLI that is signed in and under its limit. Codex (GPT-6.1 Sol, read-only sandbox) and `agy` (Claude Opus 5.5 via `claude-opus-5-5-medium`, standing in for Gemini) are the first two. Cursor and OpenCode join only after their models are verified. A member that is missing, signed out, over its cap, or erroring is skipped and listed in the transcript. The Claude CLI joins when its weekly quota resets.
- **Limits:** per member, per review: 60,000 tokens and 5 minutes. A member that hits either cap is recorded as skipped, not retried.
- **Verdicts:** plan review returns SHIP IT, SHIP WITH CHANGES or RETHINK with the strongest objections. Merge gate returns APPROVE or REJECT with findings. Any REJECT or RETHINK blocks until resolved or overridden by the user.
- **Read-only:** members get the repo and the diff, never write tools. The parent keeps sole write and merge authority.
- **Out of scope:** automatic override, changing the quality-review tiers, auto-merging to main, cross-provider orchestration beyond the listed members, and installing or signing in any CLI.

## 🏗️ Architectural Blueprint
- **Files to create:** a council skill directory under `skills/council/` with `SKILL.md` and a small runner script that detects members, builds the prompt, runs each member with its cap, and writes one transcript per review to `.roadmap/notes/`.
- **Files to modify:**
  - `skills/roadmap/references/quality-build.md` — the plan-review and merge-gate checkpoints call the council.
  - `commands/roadmap/build.md` — the build refuses to start until the plan review has a verdict and no unresolved block.
  - `skills/roadmap/scripts/rmlib/ops.py` — records the council verdict and any override on the plan's evidence line.
  - `tests/` — coverage for member detection, caps, verdict parsing and the block rule.
- **Schema/interface changes:** an optional `council` block in `.roadmap/config.json` with per-member model, token cap and time cap. Absent config uses the defaults above.
- **Downstream impact:** projects that installed the skill need `roadmap.py upgrade` for the new rules block. Existing plans without a council verdict are not blocked retroactively.

## ✅ Acceptance
- **Passes when:** `/roadmap-plan` followed by the council plan review writes a transcript to `.roadmap/notes/` that lists each member as reviewed or skipped, with its verdict or its skip reason.
- **Passes when:** a member that is not installed, not signed in, or over its token or time cap is skipped, and the review still completes with the remaining members.
- **Passes when:** a REJECT from the merge gate blocks the merge, and the merge proceeds only after an explicit user override recorded on the plan.
- **Passes when:** the full test suite is green (`python3 -m pytest` from the repo root) and `python3 scripts/validate_skills.py` exits 0.
- **Fails if:** any council member can write to the repo, the merge proceeds on a REJECT without an override, a member's cap is exceeded without being stopped, or roadmap state is written by a council member instead of the parent.

## 🚶 Step-by-Step Checklist
- [ ] Step 1: Member detection and caps: find installed CLIs, check sign-in and quota, and enforce the per-member token and time caps -> target: `skills/council/`, `tests/`
- [ ] Step 2: Read-only review runner: send the plan or diff to each member, collect one verdict per member, and write the transcript -> target: `skills/council/`, `tests/`
- [ ] Step 3: Plan-review checkpoint wired into `/roadmap-plan` and `/roadmap-build` -> target: `commands/roadmap/build.md`, `skills/roadmap/references/quality-build.md`
- [ ] Step 4: Merge-gate checkpoint with the block-until-resolved-or-overridden rule and override recording -> target: `skills/roadmap/scripts/rmlib/ops.py`, `skills/roadmap/references/quality-build.md`, `tests/`
