---
id: 31
title: Dashboard: trunk plus branches always the default view, URL in every refresh log line, and full pages for each plan and idea
type: feature
version: 0.19.0
status: done
created: 2026-10-23
---

# Plan 31: Dashboard: trunk plus branches always the default view, URL in every refresh log line, and full pages for each plan and idea
> Type: feature · Target: v0.19.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Three fixes to the `serve` dashboard, reported against statewide-app on 2026-10-23.
  1. **Default view:** "trunk + branches" is always the view on page load, the one that shows everything. A view picked earlier (stored in localStorage, or chosen in the dropdown) must not stick across reloads, and opening the page from any worktree must not land on that worktree's view.
  2. **Findable URL:** the terminal prints the URL once, at startup. If that line scrolls away there is no way to find the page again. Every refresh log line carries the URL. The per-checkout log lines collapse into one summary line (trunk view, plus the number of checkouts), with per-checkout detail only under `--verbose`. Running `serve` again while a dashboard is up prints the running URL and exits 0 (check that `_running_dashboard` already does this and make it loud).
  3. **Pages, not dropdowns:** every plan and every idea gets its own page, using hash routing so it works without a server change: `#/plan/<id>`, `#/idea/<n>`, `#/notes/<file>`. The list rows link to these pages; inline expand dropdowns go away.
     - The plan page shows: title, type, version, lane badge, claim (stage, verdict, note), branch facts and commit list, the full plan markdown rendered (checklist with ticked state, evidence lines, acceptance), linked files (notes the plan references, the plan file path), and dependsOn / blockedBy links to other plan pages.
     - The idea page shows the bullet and its linked `.roadmap/notes/` file rendered in full, plus a "promote" hint showing the CLI command (the page itself stays read-only).
     - Back navigation and deep links work: a copied URL opens the same page.
- **Out of scope:** any write action from the browser (the dashboard stays read-only); editing plans; changing lane logic; authentication.

## 🏗️ Architectural Blueprint
- **Files to modify:** `skills/roadmap/scripts/rmlib/dashboard.py` (log line format, `--verbose`, `/api/item` returns the raw plan body plus linked note paths, new `/api/note?path=` restricted to `.roadmap/notes/*.md` and `.roadmap/plans/*.md` inside the project root), `rmlib/dashboard.html` (router, plan / idea / note pages, small safe markdown renderer that builds DOM nodes, no innerHTML), `scripts/roadmap.py` (`serve --verbose`), `tests/test_roadmap_serve.py`.
- **Security:** `/api/note` must reject path traversal, absolute paths and symlinks escaping the root, and anything that is not `.md` under the two allowed dirs. All rendered text goes in through `textContent`; link hrefs are only allowed for http(s) and in-app `#/` routes.
- **Downstream impact:** old `?view=` or localStorage view keys are ignored on load. The SSE refresh re-renders the current page in place without losing scroll position or the route.

## ✅ Acceptance
- **Passes when:** opening the dashboard from main or from any worktree, after picking another view and reloading, shows "trunk + branches".
- **Passes when:** every refresh log line contains `http://127.0.0.1:<port>`; with 20+ worktrees, a refresh prints one line unless `--verbose` is passed; a second `serve` prints the running URL.
- **Passes when:** clicking a plan opens `#/plan/<id>` with the rendered plan body, checklist state, evidence, claim, branch commits and dependency links; reloading that URL shows the same page; Back returns to the list with its filters kept.
- **Passes when:** clicking an idea with a notes file opens `#/idea/<n>` showing the note rendered; ideas without notes show the bullet alone.
- **Passes when:** `/api/note` returns 400/404 for `../`, absolute paths, non-md files and paths outside the allowed dirs (tests).
- **Passes when:** `uvx pytest -q tests/` is green apart from the known `test_agy_cli_plugin_validate` failure, and a manual `serve` against statewide-app shows the pages.
- **Fails if:** any browser action writes to the repo, raw markdown or commit text is injected as HTML, or the trunk view loses branch or lane data.

## 🚶 Step-by-Step Checklist
- [x] Step 1: serve logging — URL on every refresh line, collapsed per-checkout lines, `--verbose`, loud already-running message -> target: rmlib/dashboard.py, roadmap.py, tests/test_roadmap_serve.py
  > evidence: 33acf1b; merged ce672e5; roadmap+serve tests 352 passed; Playwright fixture check 0 console errors; reviews skipped at owner request (2026-10-23)
- [x] Step 2: default view always trunk + branches on load, ignore stored view -> target: rmlib/dashboard.html, tests/test_roadmap_serve.py
  > evidence: e40d604; merged ce672e5; roadmap+serve tests 352 passed; Playwright fixture check 0 console errors; reviews skipped at owner request (2026-10-23)
- [x] Step 3: `/api/item` plan body + linked notes, `/api/note` with path restrictions -> target: rmlib/dashboard.py, tests/test_roadmap_serve.py
  > evidence: f86579e /api/note path rejections tested; merged ce672e5; roadmap+serve tests 352 passed; Playwright fixture check 0 console errors; reviews skipped at owner request (2026-10-23)
- [x] Step 4: hash router plus plan, idea and note pages with a safe markdown renderer; list rows link to them -> target: rmlib/dashboard.html, tests/test_roadmap_serve.py
  > evidence: 4515287; merged ce672e5; roadmap+serve tests 352 passed; Playwright fixture check 0 console errors; reviews skipped at owner request (2026-10-23)
- [x] Step 5: smoke run against statewide-app, then sync the updated skill into the project copies -> target: plan evidence
  > evidence: statewide-app serve: URL on every line, 1 summary line for 13 checkouts, /api/item?id=401 body+20 commits, /api/note traversal 400; skill synced to 12 projects + ~/.agents (uncommitted there); found 401 misattributed to roadmap/133, routed to plan 32 (2026-10-23)
