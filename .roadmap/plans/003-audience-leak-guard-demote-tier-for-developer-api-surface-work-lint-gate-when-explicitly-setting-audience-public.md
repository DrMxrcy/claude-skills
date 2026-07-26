---
id: 3
title: Audience leak guard: DEMOTE tier for developer/API-surface work + lint gate when explicitly setting audience public
type: feature
version: 0.15.0
status: done
created: 2026-07-23
---

# Plan 3: Audience leak guard: DEMOTE tier for developer/API-surface work + lint gate when explicitly setting audience public
> Type: feature · Target: v0.15.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Stop developer/API-surface items from landing in the public changelog. Real-world leak (Parkboxd v1.6.1): items 335 "API key manager" and 336 "Posting API editor parity" shipped `audience: public` and rendered into CHANGELOG.md; item 334 (admin FeedHealthStrip work) is the same class. Two gaps: (1) no DEMOTE tier for developer-surface work — "api key" is WARN only; (2) an explicit `audience: public` (set at `new --audience` or `audience --to public`) bypasses `demote_tells` entirely with zero feedback.
- **Out of scope:** Changing WARN-tier behavior; retroactive rewriting of consumer projects' changelogs; any LLM-based classification.

## 🏗️ Architectural Blueprint
- **Files to create:** none
- **Files to modify:**
  - `skills/roadmap/scripts/rmlib/changelog.py` — add `DEMOTE_DEVSURFACE` list to `DEMOTE_TELLS` (terms like: "api key", "api keys", "posting api", "public api", "rest api", "api consumer", "developer portal", "developer tools", "sdk", "rate limit", "data-feed coverage", "feed health"). Bare "api" stays WARN (too many false positives — e.g. genuinely public "share link" features).
  - `skills/roadmap/scripts/rmlib/ops.py` (or wherever `set_audience` / `new` live) — when audience is explicitly set to `public`, run `demote_tells(title + note)`; on hits, refuse with the tell list unless `--force` (mirror the existing status-tell hard-block in `note`/`new --note`).
  - `skills/roadmap/scripts/roadmap.py` — `--force` plumbed through `audience` subcommand.
  - Mirror all changes into `codex-plugin/plugins/roadmap/skills/roadmap/scripts/` copy.
  - `tests/test_roadmap.py` — cases: dev-surface tell demotes unclassified item; explicit `audience --to public` refused on tell without `--force`; `--force` overrides; bare "api" does not demote.
  - `SKILL.md` / `README.md` — document the gate.
- **Schema/interface changes:** `audience` subcommand gains `--force`. No data format changes.
- **Downstream impact:** Agents setting `--audience public` on dev-surface items now get a hard stop instead of silence; existing explicit-public items untouched (gate applies at set time only).

## 🚶 Step-by-Step Checklist
- [x] Step 1: Add DEMOTE_DEVSURFACE tier + tests -> target: rmlib/changelog.py, tests/test_roadmap.py
- [x] Step 2: Lint gate on explicit public (new --audience / audience --to public) with --force override + tests -> target: rmlib/ops.py, roadmap.py, tests
- [x] Step 3: Mirror to codex-plugin copy, update SKILL.md/README, full test run -> target: codex-plugin/, docs
