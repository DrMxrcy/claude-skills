---
id: 37
title: Dashboard lane board: columns per lane with cards for branch, sha, verdict and last note, plus verdict and branch filter chips
type: feature
version: 0.21.0
status: done
created: 2026-10-23
---

# Plan 37: Dashboard lane board: columns per lane with cards for branch, sha, verdict and last note, plus verdict and branch filter chips
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** A board tab beside the list: columns planned, building, review, fixing, gate-ready, gating, landed, done (landed appears once that stage exists; blocked and stale render as flagged cards in their column or a side column).
  - Card: id, title, branch, short sha, verdict chip, last claim note, claim age, slot badge if reserved. Click opens the plan page.
  - Moving a card is **not** done by drag. The board stays read-only: each card has a "copy command" button that copies the matching `roadmap.py claim ...` line. Reason: a write endpoint on a local HTTP server is reachable from any web page the user visits, so writes stay in the CLI.
  - Filter chips shared by list and board: lane, verdict, branch, type, version; plus existing search.
  - Done column shows the last N (default 20) with "show all".
- **Out of scope:** write actions from the browser; drag and drop.

## 🏗️ Architectural Blueprint
- **Files to modify:** `rmlib/dashboard.html` (board tab, chips, copy buttons), `rmlib/dashboard.py` only if payload fields are missing, tests.

## ✅ Acceptance
- **Passes when:** the board shows each item in exactly one column matching its lane; card fields match `/api/status`.
- **Passes when:** chips filter list and board alike and persist per viewer; "copy command" yields a valid `claim` line.
- **Passes when:** the board updates live through the existing SSE refresh; works at phone width; no innerHTML; `uvx pytest -q tests/` green apart from known failures.
- **Fails if:** any HTTP endpoint accepts writes.

## 🚶 Step-by-Step Checklist
- [x] Step 1: board tab and columns from lanes -> target: rmlib/dashboard.html, tests
  > evidence: 5a3799a 0f170a5 3b3e42c c0ddb03; 14 board tests incl. node fake-DOM, copy commands drive real claims, no write endpoints; Playwright 1400px+390px; merged d584494; 682 passed in 253.13s (0:04:13); reviews skipped at owner request (2026-10-24)
- [x] Step 2: cards with branch, sha, verdict, note, age, copy command -> target: rmlib/dashboard.html, tests
  > evidence: 5a3799a 0f170a5 3b3e42c c0ddb03; 14 board tests incl. node fake-DOM, copy commands drive real claims, no write endpoints; Playwright 1400px+390px; merged d584494; 682 passed in 253.13s (0:04:13); reviews skipped at owner request (2026-10-24)
- [x] Step 3: shared filter chips -> target: rmlib/dashboard.html, tests
  > evidence: 5a3799a 0f170a5 3b3e42c c0ddb03; 14 board tests incl. node fake-DOM, copy commands drive real claims, no write endpoints; Playwright 1400px+390px; merged d584494; 682 passed in 253.13s (0:04:13); reviews skipped at owner request (2026-10-24)
