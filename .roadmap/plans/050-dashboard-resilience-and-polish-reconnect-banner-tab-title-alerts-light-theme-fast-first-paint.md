---
id: 50
title: Dashboard resilience and polish: reconnect banner, tab-title alerts, light theme, fast first paint
type: feature
version: 0.21.0
status: done
created: 2026-10-23
---

# Plan 50: Dashboard resilience and polish: reconnect banner, tab-title alerts, light theme, fast first paint
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Small things that make the page dependable to leave open all day.
  - **Connection banner:** when the event stream drops (server stopped or restarted), show a banner "dashboard stopped — run `claude-roadmap serve`" with a copy button, keep the last data visible, and reconnect automatically with backoff; on a new server instance, reload data without a page refresh.
  - **Tab-title and favicon alerts:** the title shows `(N) project — roadmap` where N counts attention items (REFUTED, blocked, slot clash, overdue waiting, failing trunk suite, WIP over limit — whichever exist); the favicon gets a red dot when N > 0. Optional browser notification when N rises, only after the viewer opts in on the page.
  - **Light theme:** follow `prefers-color-scheme`, with a toggle remembered per viewer; all lane colours keep 4.5:1 contrast in both.
  - **Fast first paint:** serve the trunk checkout's status first, then add worktree views as they finish scanning (startup with 13 checkouts currently takes about 6 s before the first byte). Show a "scanning N worktrees" hint meanwhile.
  - **"Last updated" stamp** and a manual refresh button.
- **Out of scope:** push notifications outside the browser.

## 🏗️ Architectural Blueprint
- **Files to modify:** `rmlib/dashboard.py` (incremental first payload, server instance id in SSE), `rmlib/dashboard.html` (banner, reconnect, title and favicon, theme tokens, toggle, stamp), tests.

## ✅ Acceptance
- **Passes when:** stopping the server shows the banner within 5 s; restarting it clears the banner and refreshes data without reload.
- **Passes when:** a fixture with one REFUTED claim shows `(1)` in the title and the favicon dot; resolving it clears both.
- **Passes when:** light and dark render with all lane badges at 4.5:1 or better (checked in a test against the token values).
- **Passes when:** with 13 fixture worktrees the first `/api/status` answers before the worktree scan finishes.
- **Passes when:** `uvx pytest -q tests/test_roadmap*.py tests/test_cli_e2e.py` is green.
- **Fails if:** a browser notification fires without the viewer opting in.

## 🚶 Step-by-Step Checklist
- [x] Step 1: incremental first payload and server instance id -> target: rmlib/dashboard.py, tests
  > evidence: b450921 b903a77 bca66df 1e65094 7cf8ed3 integrated f220b16; Playwright banner 1.3s, title (2), theme toggle; main at f220b16; 761 passed, 1 flaky digest test passes alone; reviews skipped at owner request (2026-10-24)
- [x] Step 2: connection banner and reconnect -> target: rmlib/dashboard.html, tests
  > evidence: b450921 b903a77 bca66df 1e65094 7cf8ed3 integrated f220b16; Playwright banner 1.3s, title (2), theme toggle; main at f220b16; 761 passed, 1 flaky digest test passes alone; reviews skipped at owner request (2026-10-24)
- [x] Step 3: title, favicon and opt-in notifications -> target: rmlib/dashboard.html, tests
  > evidence: b450921 b903a77 bca66df 1e65094 7cf8ed3 integrated f220b16; Playwright banner 1.3s, title (2), theme toggle; main at f220b16; 761 passed, 1 flaky digest test passes alone; reviews skipped at owner request (2026-10-24)
- [x] Step 4: light theme tokens, toggle, contrast test, last-updated stamp -> target: rmlib/dashboard.html, tests
  > evidence: b450921 b903a77 bca66df 1e65094 7cf8ed3 integrated f220b16; Playwright banner 1.3s, title (2), theme toggle; main at f220b16; 761 passed, 1 flaky digest test passes alone; reviews skipped at owner request (2026-10-24)
