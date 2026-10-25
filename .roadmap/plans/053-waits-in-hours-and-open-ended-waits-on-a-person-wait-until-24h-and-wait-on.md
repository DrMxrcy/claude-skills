---
id: 53
title: Waits in hours and open-ended waits on a person: wait --until 24h and wait --on
type: feature
version: 0.21.0
status: done
created: 2026-10-24
---

# Plan 53: Waits in hours and open-ended waits on a person: wait --until 24h and wait --on
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Plan 46 waits take days, weeks or a date. Real steps also wait hours (a 24h or 72h soak) or wait on people with no fixed end (user testing). Support both without changing how waiting steps count.
  - `wait <id> --step N --until 24h|72h` accepts hours (`h`) alongside `d`/`w`/dates. Due time is stored with time of day (UTC) when hours are used; countdowns show hours when under 2 days ("5h left", "3h overdue").
  - `wait <id> --step N --on "<person or team>" [--reason TEXT] [--until ...]` marks the step waiting on someone. With no `--until` it has no due date: never "overdue", but `orient`, the digest and the dashboard list it every day as "awaiting <who> (since <date>, N days)". With `--until` it behaves as today plus the person text.
  - The marker stays `[~]` (not done everywhere). The stored text gains `on: <who>` and `since: <date>`; old markers parse unchanged.
  - `release --with-waiting` and `retarget --split` carry `--on` waits into follow-ups unchanged.
  - Dashboard: waiting badge shows "awaiting dispatch team · 3d" for open-ended waits; board waiting column and digest attention list include them (open-ended waits older than `settings.waitNudgeDays`, default 7, count as attention).
- **Out of scope:** notifying the person; scheduling tests.

## 🏗️ Architectural Blueprint
- **Files to modify:** `rmlib/parse.py` (wait marker fields), `rmlib/ops.py` (hours, `--on`), `scripts/roadmap.py` (`--on`), `rmlib/sync.py` (waitingSteps fields, due logic), `rmlib/report.py` and `rmlib/digest.py` (reminder lines, attention), `rmlib/dashboard.html` (badge text), docs, tests.

## ✅ Acceptance
- **Passes when:** `wait 7 --step 2 --until 24h` sets a due time 24 hours ahead and the countdown shows hours.
- **Passes when:** `wait 7 --step 3 --on "dispatch team" --reason "user testing"` with no date shows as awaiting in orient, digest and dashboard every day, never overdue, and becomes an attention item after waitNudgeDays.
- **Passes when:** `check --plan 7 --step 3` ends the wait; `release --with-waiting` moves an `--on` wait into the follow-up with its person and since-date.
- **Passes when:** plans with old-style wait markers parse and count exactly as before.
- **Passes when:** `uvx pytest -q tests/test_roadmap*.py tests/test_cli_e2e.py` is green.
- **Fails if:** a waiting step counts as done anywhere, or existing `--until 7d` behaviour changes.

## 🚶 Step-by-Step Checklist
- [x] Step 1: hours in `--until`, time-of-day due, hour countdowns -> target: rmlib/ops.py, rmlib/parse.py, rmlib/sync.py, tests
  > evidence: 45f7941 8334669 9156a2a; 20 wait-on tests incl. old-style markers unchanged; 839 passed in worktree; merged 5c84d10; 839 passed in 245.64s (0:04:05); reviews skipped at owner request (2026-10-24)
- [x] Step 2: `--on` open-ended waits, marker fields, reminders in orient and digest, attention after waitNudgeDays -> target: roadmap.py, rmlib/ops.py, rmlib/report.py, rmlib/digest.py, tests
  > evidence: 45f7941 8334669 9156a2a; 20 wait-on tests incl. old-style markers unchanged; 839 passed in worktree; merged 5c84d10; 839 passed in 245.64s (0:04:05); reviews skipped at owner request (2026-10-24)
- [x] Step 3: follow-ups carry `--on`, dashboard badge and board column text, docs -> target: rmlib/ops.py, rmlib/dashboard.html, references/state-model.md, SKILL.md, tests
  > evidence: 45f7941 8334669 9156a2a; 20 wait-on tests incl. old-style markers unchanged; 839 passed in worktree; merged 5c84d10; 839 passed in 245.64s (0:04:05); reviews skipped at owner request (2026-10-24)
