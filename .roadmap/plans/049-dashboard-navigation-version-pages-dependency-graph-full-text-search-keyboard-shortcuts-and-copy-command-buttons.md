---
id: 49
title: Dashboard navigation: version pages, dependency graph, full-text search, keyboard shortcuts and copy-command buttons
type: feature
version: 0.21.0
status: done
created: 2026-10-23
---

# Plan 49: Dashboard navigation: version pages, dependency graph, full-text search, keyboard shortcuts and copy-command buttons
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Make the dashboard the fastest way to find and act on work.
  - **Version pages** `#/version/<v>`: items grouped by lane, progress, forecast (when plan 44 exists), unreleased changelog preview (public and internal), and the release command to copy.
  - **Dependency graph** `#/graph`: inline SVG of `dependsOn` edges for the open versions, nodes coloured by lane, blocked chains highlighted, click a node to open its plan. Layered left-to-right layout computed in the page; no library.
  - **Full-text search**: `/api/search?q=` reusing the CLI `search` (titles, notes, plan bodies, incubator, notes files) with snippets; results page `#/search/<q>`.
  - **Keyboard**: `/` focus search, `g` then `l`/`i`/`c`/`g`/`v` go to list/ideas/changelog/graph/versions, `j`/`k` move through rows, `Enter` opens, `Esc` goes back, `?` shows the shortcut sheet. A command palette (`Ctrl/Cmd+K`) jumps to any plan, idea, version or page by fuzzy name.
  - **Copy-command buttons** on plan pages for the likely next CLI actions (`next`, `claim … --stage review`, `check --plan N --step K`, `slot`, `ruling`, `bug --found-in`), showing exactly what will be copied. The page itself stays read-only.
- **Out of scope:** write actions from the browser.

## 🏗️ Architectural Blueprint
- **Files to modify:** `rmlib/dashboard.py` (`/api/search`, `/api/version`), `rmlib/dashboard.html` (routes, graph SVG, keyboard layer, palette, copy buttons), tests.

## ✅ Acceptance
- **Passes when:** `#/version/0.21.0` lists items by lane with the changelog preview; `#/graph` renders nodes and edges matching `dependsOn`, and clicking a node opens its plan.
- **Passes when:** searching a word that appears only inside a plan body returns that plan with a snippet.
- **Passes when:** each documented shortcut works and the palette opens any plan by partial title; shortcuts do nothing while typing in an input.
- **Passes when:** copy buttons copy valid commands for the plan in view; no innerHTML; works at phone width.
- **Passes when:** `uvx pytest -q tests/test_roadmap*.py tests/test_cli_e2e.py` is green.
- **Fails if:** any endpoint writes.

## 🚶 Step-by-Step Checklist
- [x] Step 1: `/api/search` and search results page -> target: rmlib/dashboard.py, rmlib/dashboard.html, tests
  > evidence: b059501 6ebabab ef0d633 e840945 b3f3498 integrated da1e81e; merged a8eeb3b; 842 passed; Playwright single + serve --all 0 console errors; reviews skipped at owner request (2026-10-24)
- [x] Step 2: version pages with changelog preview -> target: rmlib/dashboard.py, rmlib/dashboard.html, tests
  > evidence: b059501 6ebabab ef0d633 e840945 b3f3498 integrated da1e81e; merged a8eeb3b; 842 passed; Playwright single + serve --all 0 console errors; reviews skipped at owner request (2026-10-24)
- [x] Step 3: dependency graph page -> target: rmlib/dashboard.html, tests
  > evidence: b059501 6ebabab ef0d633 e840945 b3f3498 integrated da1e81e; merged a8eeb3b; 842 passed; Playwright single + serve --all 0 console errors; reviews skipped at owner request (2026-10-24)
- [x] Step 4: keyboard shortcuts, palette, copy-command buttons -> target: rmlib/dashboard.html, tests
  > evidence: b059501 6ebabab ef0d633 e840945 b3f3498 integrated da1e81e; merged a8eeb3b; 842 passed; Playwright single + serve --all 0 console errors; reviews skipped at owner request (2026-10-24)
