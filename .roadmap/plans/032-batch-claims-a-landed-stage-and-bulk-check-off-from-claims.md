---
id: 32
title: Batch claims, a landed stage, and bulk check-off from claims
type: feature
version: 0.21.0
status: planned
created: 2026-10-23
---

# Plan 32: Batch claims, a landed stage, and bulk check-off from claims
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Parallel builds move many items at once, and the parent re-derives by hand which branch held which steps. Make claims the record that drives transitions.
  - `claim 388 393 116 --stage gating` accepts several ids (same options for all; all-or-nothing validation).
  - New stage **`landed`**: merged into an integration branch (or trunk) but not yet on the release branch. Optional config `settings.integrationBranch` (default none = trunk). Lane derivation marks a branch `landed` automatically when its tip is contained in the integration branch but not in trunk, and records the landing sha.
  - `claim --landed <sha>` moves every claimed or discovered item whose branch tip is an ancestor of `<sha>` to `landed`, storing `claim_landed_sha`.
  - `check --landed [--evidence TEXT]` ticks every step of every item in `landed` whose landing sha is now contained in trunk, records the evidence (with the sha) under each step, and clears the claims. Dry-run by default listing what it would tick; `--yes` applies.
- **Out of scope:** pushing, merging, or running gates; changing done derivation (trunk checkboxes stay the source of done).

## 🏗️ Architectural Blueprint
- **Files to modify:** `scripts/roadmap.py`, `rmlib/ops.py` (multi-id claim, landed, bulk check), `rmlib/parse.py` (stage enum + `claim_landed_sha`), `rmlib/sync.py` (lane precedence: done > claim > landed-derived > stale/building), `rmlib/branches.py` (containment in integration branch, one batched call), docs, tests.
- **Schema:** `CLAIM_STAGES` gains `landed`; frontmatter key `claim_landed_sha`; config `integrationBranch`.

## ✅ Acceptance
- **Passes when:** `claim 1 2 3 --stage gating` updates all three; an invalid id among them changes none and exits non-zero.
- **Passes when:** in a fixture where roadmap/1 and roadmap/2 are merged into `integration` but not trunk, status shows both `landed` without a claim.
- **Passes when:** `claim --landed <sha>` moves exactly the items whose branch tips are ancestors of `<sha>`.
- **Passes when:** after the integration branch merges to trunk, `check --landed` lists the items, `check --landed --yes` ticks all their steps with evidence naming the sha, and clears their claims.
- **Passes when:** `uvx pytest -q tests/` is green apart from known failures.
- **Fails if:** an item is ticked whose work is not contained in trunk.

## 🚶 Step-by-Step Checklist
- [ ] Step 1: multi-id `claim` with all-or-nothing validation -> target: roadmap.py, rmlib/ops.py, tests
- [ ] Step 2: `landed` stage, integrationBranch containment in discovery, lane precedence -> target: rmlib/branches.py, rmlib/sync.py, rmlib/parse.py, tests
- [ ] Step 3: `claim --landed <sha>` -> target: roadmap.py, rmlib/ops.py, tests
- [ ] Step 4: `check --landed` dry-run and `--yes` -> target: roadmap.py, rmlib/ops.py, tests
- [ ] Step 5: docs (state-model, quality-build merge gate flow) -> target: references/*.md, SKILL.md
