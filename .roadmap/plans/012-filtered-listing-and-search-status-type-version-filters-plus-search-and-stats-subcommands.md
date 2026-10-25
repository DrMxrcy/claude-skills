---
id: 12
title: "Filtered listing and search: status --type/--version filters, plus search and stats subcommands"
type: feature
version: 0.16.0
status: done
created: 2026-08-20
---

# Plan 12: Filtered listing and search: status --type/--version filters, plus search and stats subcommands
> Type: feature · Target: v0.16.0
> Spec: [research note](../notes/2026-08-19-filtered-listing-and-search-status-type-version-filters-plus-search-and-stats-subcommands.md)

## 🎯 Target Scope & Boundaries
- **Core objective:** `status --type T --version V --status S` filters; new `search <text>` (titles, notes, plan bodies, incubator bullets, case-insensitive) with `--json`; counts summary via `status --json` extension or tiny `stats` output.
- **Out of scope:** No fuzzy matching/ranking; no regex mode; no dashboard search UI.

## 🏗️ Architectural Blueprint
- **Files to create:** none (search fits existing command modules)
- **Files to modify:** roadmap.py argparse; status/report module; new search function reading config + plans + incubator; tests
- **Schema/interface changes:** none
- **Downstream impact:** `--json` output shapes stay backward compatible (filters only narrow the list)

## 🚶 Step-by-Step Checklist
- [x] Step 1: `status` filters (--type/--version/--status), text + JSON -> target: report + tests
- [x] Step 2: `search <text>` across titles/notes/plan bodies/incubator with file:line-ish refs, `--json` -> target: new search + tests
- [x] Step 3: counts by type/status/version (stats or status --json) + docs in SKILL.md command table -> target: report + SKILL.md + tests
