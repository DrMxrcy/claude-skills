---
id: 57
title: Dashboard simplification: one home per fact, answer-first pages, monochrome, no badge clutter (Vercel design principles)
type: refactor
version: 0.21.0
status: planned
created: 2026-10-25
---

# ⚙️ Plan 57: Dashboard simplification: one home per fact, answer-first pages, monochrome, no badge clutter (Vercel design principles)
> Type: refactor · Target: v0.21.0

## 📉 Current Pain Points
-

## 📈 Target State
-

## 🛡️ Baseline Tests (must stay green)
-

## ✅ Acceptance
- **Passes when:** behavior is unchanged for callers — the baseline tests above stay green
- **Passes when:** <observable signal the debt is gone: dead path deleted, one implementation, no duplication>
- **Fails if:** public API, output shape, or performance regresses

## 📋 Checklist
- [ ] Step 1: Isolate current pathways
- [ ] Step 2: Scaffold new implementation
- [ ] Step 3: Run full regression
## 🎯 Target Scope & Boundaries
- **Core objective:** The dashboard grew one plan at a time (30-55) and now repeats the same facts in several places with a badge for everything. The owner cannot tell what is going on. Redesign the information architecture and visual system using the principles in https://vercel.com/design.md (reference copy of the rules: see Notes below). Same data, same routes, same read-only server; fewer, clearer surfaces.
- **Rules to apply (from the Vercel design rules):**
  - Give each fact one home; combine duplicate sections; each section answers a new question.
  - First viewport presents the answer (what needs attention, what is moving), not setup.
  - Design in monochrome; color only for meaningful state, always paired with a text cue. Do not color ordinary progress green.
  - No pills or badges for ordinary metadata; no nested cards; no borders to repair hierarchy; spacing separates regions.
  - Exhaustive ledgers (run history, worktrees, conflicts, other branches, commits) go after the decision path or behind disclosure, showing current and total counts.
  - Sentence-case headings that state the question; no all-caps labels, no em dashes in UI copy; equal peers get identical type roles; tabular numerals for aligned numbers.
  - No visible theme switcher (follow the system setting); no pulsing or decorative motion.
  - Geist Sans for UI and Geist Mono only for ids, commands, paths, shas (load from Google Fonts with a system-font fallback so the offline dashboard still works).
- **Information architecture (target):**
  - Roadmap list: one row per item = id, title, state word (only when not planned/done), progress fraction. At most ONE attention marker per row (blocked, refuted, clash, off-plan, overdue/awaiting, template text) with the reason in text. Drop per-row type badges (the id prefix already says FEAT/BUG), "0/N accepted" when nothing is accepted yet, ruling counts, owner, sha; those live on the plan page.
  - Header: project, version, overall progress, one sentence of state (e.g. "9 in flight, 8 blocked, 3 need attention"). Counts appear here only, not again in version headers or panels.
  - A single "Health" tab (route #/health) becomes the one home for trunk health, merge gates, slots, conflicts, worktrees, other branches and scope drift. The list page keeps at most a one-line link to it when something is red. Remove those panels from the list page.
  - "Needs attention" has one home: the top of the Roadmap page (the same list the digest and the tab title use). The digest page keeps its time-window story and links to it rather than repeating it.
  - Plan page, answer first: title, state sentence, the next action (one copy command), then the checklist with evidence, then acceptance, rulings, waits; branch, commits, overlaps and files go in a "Details" disclosure at the end. No duplicated facts block.
  - Board: cards show id, title, and the one attention reason; everything else on the plan page.
  - Versions, graph, search, ideas, changelog: apply the same type, spacing and color rules; remove duplicated counts.
- **Out of scope:** new data, new endpoints beyond moving panels to #/health, changes to CLI output, write actions.

## 🏗️ Architectural Blueprint
- **Files to modify:** `skills/roadmap/scripts/rmlib/dashboard.html` (layout, tokens, page renderers), `skills/roadmap/scripts/rmlib/dashboard.py` only if the health route needs a payload already computed elsewhere, tests under `tests/test_roadmap_*.py` that pin removed markup (update them to the new structure, keep their intent: escaping, no innerHTML, routing, copy commands valid).
- **Approach:** first an audit pass: screenshot every page (list, board, plan, idea, notes, digest, versions, version, graph, search, health, all-projects home) on statewide at 1400x900 and 390x844 in both themes, and list every duplicated fact and every badge with where it appears. Then implement against that list. Before/after screenshots kept in the run's scratch folder.

## ✅ Acceptance
- **Passes when:** an audit table (fact, current homes, new single home) is recorded in this plan's evidence, and every duplicated fact in it has exactly one home after the change.
- **Passes when:** on statewide at 1400x900, the Roadmap page's first viewport shows the state sentence, the needs-attention list and the first item rows, with no panels above them.
- **Passes when:** a list row shows at most one colored marker, and every colored element on any page carries a text cue (checked by a test over the rendered fixture DOM).
- **Passes when:** #/health shows trunk health, merge gates, slots, conflicts, worktrees, other branches and scope drift, each collapsible with a one-line summary, and none of them render on the Roadmap page.
- **Passes when:** no visible theme switcher; no em dashes or all-caps labels in UI strings; text still goes in via textContent only.
- **Passes when:** `uvx pytest -q tests/test_roadmap*.py tests/test_cli_e2e.py` is green and serve --all routing, board, plan pages and copy commands still work (Playwright pass with zero console errors).
- **Fails if:** any data the dashboard showed before becomes unreachable (it may move, not vanish), or the page breaks offline.

## 🚶 Step-by-Step Checklist
- [ ] Step 1: audit: screenshots of every page, duplicated-fact table, badge inventory -> target: plan evidence, scratch screenshots
- [ ] Step 2: type, color and spacing tokens (Geist, monochrome, state colors with text cues), remove theme switcher -> target: rmlib/dashboard.html, tests
- [ ] Step 3: header state sentence and the Roadmap page: single needs-attention block, simplified rows, panels removed -> target: rmlib/dashboard.html, tests
- [ ] Step 4: #/health page as the one home for health, gates, slots, conflicts, worktrees, branches, drift -> target: rmlib/dashboard.html, rmlib/dashboard.py, tests
- [ ] Step 5: plan page answer-first with Details disclosure; board cards simplified -> target: rmlib/dashboard.html, tests
- [ ] Step 6: versions, graph, search, ideas, changelog, digest, all-projects home pass; before/after screenshots and Playwright run -> target: rmlib/dashboard.html, tests

## Notes
- Source: https://vercel.com/design.md (Vercel report-website design rules). Key rule groups used: one evidence home per claim, first viewport presents the argument, monochrome with state color plus text cue, no badge/pill metadata, no nested cards, ledgers behind disclosure, sentence-case headings, Geist Sans/Mono split, no visible theme controls, default to stillness.
