---
id: 33
title: Numbered slot reservations: reserve the next migration (or any numbered sequence) per plan, with clash detection
type: feature
version: 0.21.0
status: done
created: 2026-10-23
---

# Plan 33: Numbered slot reservations: reserve the next migration (or any numbered sequence) per plan, with clash detection
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Projects with numbered sequences (DB migrations, ADR numbers, API versions, ports) double-book numbers when parallel branches each pick "the next one". Make reservations roadmap state.
  - Config `settings.slots`: named kinds, each with a `glob` + `pattern` (regex with one number group) used to find the highest number already on trunk, plus optional `width` for zero padding. Example kind `migration`: glob `packages/db/drizzle/*.sql`, pattern `^(\d{4})_`, width 4. No kinds configured = feature dormant.
  - `roadmap.py slot <id> --kind migration [--name domain_routing]` reserves max(trunk highest, highest reservation) + 1, records it on the plan (`slot_<kind>: 0269_domain_routing`), prints it. `slot <id> --kind K --release` frees it. Reservations live in plan frontmatter, so they travel with the trunk and are visible to every session.
  - `status --slots` lists per kind: trunk highest, then each reservation with plan id, lane, and match state.
  - **Clash detection:** a reservation is `ok` when the claimed/discovered branch contains a file matching the kind's glob with that number, `missing` when the branch has none yet, `clash` when two plans hold the same number or a branch adds a different number than reserved, `taken` when trunk already has the number from another plan. `deps-check`-style command `slot --check` exits non-zero on any clash, for use in merge gates.
- **Out of scope:** renaming files on branches; generating migration files.

## 🏗️ Architectural Blueprint
- **Files to create:** `rmlib/slots.py`.
- **Files to modify:** `scripts/roadmap.py`, `rmlib/parse.py` (slot_* keys), `rmlib/sync.py` (status payload `slots`), `rmlib/dashboard.*` (slot strip: trunk highest, reservations, clashes in red), docs, tests.
- **Git cost:** branch file lists come from one `git diff --name-only trunk...branch` per branch with a reservation, cached on the ref signature.

## ✅ Acceptance
- **Passes when:** with trunk at 0268, `slot 5 --kind migration --name x` reserves 0269 and `slot 6 --kind migration` reserves 0270.
- **Passes when:** a branch adding `0271_x.sql` for a plan that reserved 0269 shows `clash`, and `slot --check` exits 1.
- **Passes when:** a project with no `slots` config sees no change in status or dashboard output.
- **Passes when:** the dashboard shows the slot strip with clashes highlighted; `uvx pytest -q tests/` green apart from known failures.
- **Fails if:** two reservations can receive the same number.

## 🚶 Step-by-Step Checklist
- [x] Step 1: config schema, trunk-highest scan, `slot` reserve/release -> target: rmlib/slots.py, roadmap.py, tests
  > evidence: 22a389a 979930a cd8fe5e 8e2af65 dca63e1 ad6338e; merged 8b580f5; 446 passed incl. 40 slot tests; 6 concurrent reservations distinct; statewide read-only: trunk 0259, double-booked 0262/0263 at branch tips; reviews skipped at owner request (2026-10-23)
- [x] Step 2: branch match states and `slot --check` -> target: rmlib/slots.py, tests
  > evidence: 22a389a 979930a cd8fe5e 8e2af65 dca63e1 ad6338e; merged 8b580f5; 446 passed incl. 40 slot tests; 6 concurrent reservations distinct; statewide read-only: trunk 0259, double-booked 0262/0263 at branch tips; reviews skipped at owner request (2026-10-23)
- [x] Step 3: `status --slots` and status payload -> target: rmlib/sync.py, roadmap.py, tests
  > evidence: 22a389a 979930a cd8fe5e 8e2af65 dca63e1 ad6338e; merged 8b580f5; 446 passed incl. 40 slot tests; 6 concurrent reservations distinct; statewide read-only: trunk 0259, double-booked 0262/0263 at branch tips; reviews skipped at owner request (2026-10-23)
- [x] Step 4: dashboard slot strip -> target: rmlib/dashboard.html, rmlib/dashboard.py, tests
  > evidence: 22a389a 979930a cd8fe5e 8e2af65 dca63e1 ad6338e; merged 8b580f5; 446 passed incl. 40 slot tests; 6 concurrent reservations distinct; statewide read-only: trunk 0259, double-booked 0262/0263 at branch tips; reviews skipped at owner request (2026-10-23)
- [x] Step 5: docs and merge-gate guidance -> target: references/*.md, SKILL.md
  > evidence: 22a389a 979930a cd8fe5e 8e2af65 dca63e1 ad6338e; merged 8b580f5; 446 passed incl. 40 slot tests; 6 concurrent reservations distinct; statewide read-only: trunk 0259, double-booked 0262/0263 at branch tips; reviews skipped at owner request (2026-10-23)
