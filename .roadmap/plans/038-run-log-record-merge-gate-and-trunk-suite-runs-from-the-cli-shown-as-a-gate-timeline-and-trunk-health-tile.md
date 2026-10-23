---
id: 38
title: Run log: record merge-gate and trunk suite runs from the CLI, shown as a gate timeline and trunk health tile
type: feature
version: 0.21.0
status: done
created: 2026-10-23
---

# Plan 38: Run log: record merge-gate and trunk suite runs from the CLI, shown as a gate timeline and trunk health tile
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Gate and suite runs happen in scratch folders nobody else can see. Record them as roadmap state.
  - `roadmap.py run --kind gate|suite --label L --result pass|fail [--items 388,393] [--branches a,b] [--duration 12m] [--log URL] [--failing "test names"] [--shards "unit=pass,e2e=fail"]` appends one JSON line to `.roadmap/runs.jsonl` (committed; append-only; trimmed to the last `settings.runsKeep`, default 200).
  - `status --runs` prints the last runs. Status payload gains `runs` (last 50) and `trunkHealth`: latest suite run per shard with failing names, plus commits trunk is ahead of the release branch (when `integrationBranch` / release branch differ).
  - Dashboard: gate timeline (label, items/branches, start, duration, result, log link) and a trunk health tile (per-shard green/red, failing names, ahead count).
- **Out of scope:** running gates or tests; polling CI providers (a later item can feed `run` from CI).

## 🏗️ Architectural Blueprint
- **Files to create:** `rmlib/runs.py`.
- **Files to modify:** `scripts/roadmap.py`, `rmlib/sync.py`, `rmlib/dashboard.*`, docs (merge gate step: record a run), tests.
- **Concurrency:** appends use an exclusive file lock; lines are self-contained JSON so concurrent sessions never corrupt the file; merge conflicts in runs.jsonl resolve by union (document a `merge=union` gitattribute line that `init`/`upgrade` add).

## ✅ Acceptance
- **Passes when:** two `run` calls append two parseable lines; `status --runs` shows them newest first; the trim keeps `runsKeep`.
- **Passes when:** the dashboard timeline lists gates with log links (http(s) only) and the health tile shows the latest suite shards with failing names.
- **Passes when:** `upgrade` adds the union-merge gitattribute; `uvx pytest -q tests/` green apart from known failures.
- **Fails if:** an unparseable line breaks status (skip it with a warning).

## 🚶 Step-by-Step Checklist
- [x] Step 1: runs.jsonl writer with lock, trim, and reader -> target: rmlib/runs.py, tests
  > evidence: 5ba3432 a05c050 abd61d1 8d2bcb1 2cf347c; 28 run-log tests incl. concurrent append and git union merge; merged aa5bbe6; 472 passed in 179.86s (0:02:59); reviews skipped at owner request (2026-10-23)
- [x] Step 2: `run` command and `status --runs`, payload `runs` + `trunkHealth` -> target: roadmap.py, rmlib/sync.py, tests
  > evidence: 5ba3432 a05c050 abd61d1 8d2bcb1 2cf347c; 28 run-log tests incl. concurrent append and git union merge; merged aa5bbe6; 472 passed in 179.86s (0:02:59); reviews skipped at owner request (2026-10-23)
- [x] Step 3: gitattributes union merge via init/upgrade -> target: rmlib/project.py, tests
  > evidence: 5ba3432 a05c050 abd61d1 8d2bcb1 2cf347c; 28 run-log tests incl. concurrent append and git union merge; merged aa5bbe6; 472 passed in 179.86s (0:02:59); reviews skipped at owner request (2026-10-23)
- [x] Step 4: dashboard gate timeline and trunk health tile -> target: rmlib/dashboard.html, tests
  > evidence: 5ba3432 a05c050 abd61d1 8d2bcb1 2cf347c; 28 run-log tests incl. concurrent append and git union merge; merged aa5bbe6; 472 passed in 179.86s (0:02:59); reviews skipped at owner request (2026-10-23)
- [x] Step 5: docs: merge gate records a run -> target: references/quality-build.md, SKILL.md
  > evidence: 5ba3432 a05c050 abd61d1 8d2bcb1 2cf347c; 28 run-log tests incl. concurrent append and git union merge; merged aa5bbe6; 472 passed in 179.86s (0:02:59); reviews skipped at owner request (2026-10-23)
