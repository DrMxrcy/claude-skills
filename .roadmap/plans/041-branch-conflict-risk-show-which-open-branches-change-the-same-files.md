---
id: 41
title: Branch conflict risk: show which open branches change the same files
type: feature
version: 0.21.0
status: done
created: 2026-10-23
---

# Plan 41: Branch conflict risk: show which open branches change the same files
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** With many open branches, merge conflicts surface only at the merge gate. Predict them.
  - For each unmerged item branch, collect changed files vs trunk (`git diff --name-only trunk...branch`, cached per branch tip).
  - Pairs of branches sharing changed files form an overlap list: the two items, the shared files (max 10 shown), and a risk level (high when a shared file is changed by both in overlapping line ranges, using `git merge-tree --write-tree` where git >= 2.38 for an exact conflict check; otherwise file overlap only).
  - `status --conflicts` prints the overlap list sorted by risk. Payload gains `conflicts`. Dashboard: a conflicts panel, and on each plan page the items it overlaps with.
  - Suggest a merge order: items with no overlaps first, then by fewest overlaps.
- **Out of scope:** resolving conflicts; rebasing branches.

## 🏗️ Architectural Blueprint
- **Files to create:** `rmlib/conflicts.py`.
- **Files to modify:** `rmlib/sync.py`, `scripts/roadmap.py`, `rmlib/dashboard.*`, docs, tests.
- **Cost:** per-branch file lists and pairwise merge-tree results cached on branch tips; recomputed only for branches whose tip moved.

## ✅ Acceptance
- **Passes when:** fixture branches A and B both edit `x.py` on the same lines: `status --conflicts` shows A–B high risk with `x.py`; branch C editing `y.py` alone shows no overlap and comes first in the suggested order.
- **Passes when:** without merge-tree support, file overlap is still reported as medium risk.
- **Passes when:** the dashboard panel and plan page list overlaps; an unchanged refs tick runs no extra git calls.
- **Passes when:** `uvx pytest -q tests/` is green apart from known failures.
- **Fails if:** any command modifies a branch or the index.

## 🚶 Step-by-Step Checklist
- [x] Step 1: per-branch changed files and pairwise overlap with merge-tree check, cached -> target: rmlib/conflicts.py, tests
  > evidence: 9093403 3f79d12 + dashboard step; 20 conflict tests; statewide read-only 36 overlapping pairs, 9 high, 1.1s; merged ce62386; 615 passed in 210.00s (0:03:30); reviews skipped at owner request (2026-10-24)
- [x] Step 2: `status --conflicts`, payload, merge-order suggestion -> target: roadmap.py, rmlib/sync.py, tests
  > evidence: 9093403 3f79d12 + dashboard step; 20 conflict tests; statewide read-only 36 overlapping pairs, 9 high, 1.1s; merged ce62386; 615 passed in 210.00s (0:03:30); reviews skipped at owner request (2026-10-24)
- [x] Step 3: dashboard panel and plan-page overlaps -> target: rmlib/dashboard.html, tests
  > evidence: 9093403 3f79d12 + dashboard step; 20 conflict tests; statewide read-only 36 overlapping pairs, 9 high, 1.1s; merged ce62386; 615 passed in 210.00s (0:03:30); reviews skipped at owner request (2026-10-24)
