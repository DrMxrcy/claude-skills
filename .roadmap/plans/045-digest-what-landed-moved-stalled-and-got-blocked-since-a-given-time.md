---
id: 45
title: Digest: what landed, moved, stalled and got blocked since a given time
type: feature
version: 0.21.0
status: planned
created: 2026-10-23
---

# Plan 45: Digest: what landed, moved, stalled and got blocked since a given time
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Catch up after a break without reading every plan.
  - `roadmap.py digest [--since 1d|3h|<date>|last]` reports, for the window: items completed; steps ticked (by item); claims that changed stage or verdict; items that became stale or blocked; new branches and new plans; gate and suite runs (when the run log exists); ideas added; and a "needs attention" list (REFUTED verdicts, blocked claims, conflicts, off-plan files, WIP over limit — whichever features exist).
  - `--since last` uses a per-user gitignored stamp written each time digest runs.
  - `--format md` for pasting into chat; `--json` for tools. `orient` prints a 3-line digest since the last session.
  - Dashboard: a "since" selector on a digest page (`#/digest`).
- **Out of scope:** sending the digest anywhere (email, Slack).

## 🏗️ Architectural Blueprint
- **Files to create:** `rmlib/digest.py`.
- **Data:** git log of `.roadmap/` and ROADMAP.md over the window (claim and tick changes are frontmatter/checkbox diffs), evidence dates, branch discovery, run log.
- **Files to modify:** `scripts/roadmap.py`, orient code, `rmlib/dashboard.*`, docs, tests.

## ✅ Acceptance
- **Passes when:** in a fixture where item 2 completed, item 3 moved review→gate-ready, and item 4 went stale within the window, `digest --since 1d` lists exactly those under the right headings.
- **Passes when:** `--since last` covers only changes after the previous run; `--format md` and `--json` produce valid output.
- **Passes when:** `orient` shows a short digest; the dashboard digest page renders.
- **Passes when:** `uvx pytest -q tests/` is green apart from known failures.
- **Fails if:** digest writes anything tracked by git.

## 🚶 Step-by-Step Checklist
- [ ] Step 1: window parsing and change collection from git history -> target: rmlib/digest.py, tests
- [ ] Step 2: `digest` command with md/json output and `--since last` stamp -> target: roadmap.py, tests
- [ ] Step 3: orient summary -> target: orient code, tests
- [ ] Step 4: dashboard digest page -> target: rmlib/dashboard.html, rmlib/dashboard.py, tests
