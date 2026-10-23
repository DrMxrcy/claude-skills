---
id: 44
title: Version forecast: estimate each open version's finish date from recent pace
type: feature
version: 0.21.0
status: planned
created: 2026-10-23
---

# Plan 44: Version forecast: estimate each open version's finish date from recent pace
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Show whether a version is on track.
  - Pace = steps ticked per day over the last `settings.forecastDays` (default 14), from the dated evidence lines `check` already writes (fall back to git log of plan files when evidence dates are missing).
  - Per open version: remaining steps, pace, forecast date, and a range (pace ±1 standard deviation of daily ticks). Not shown with fewer than 5 ticks in the window ("not enough history").
  - Optional `settings.versionTargets: {"0.21.0": "2026-11-15"}`; when set, the forecast shows on track / at risk / late against it.
  - `status` prints the forecast on each open version header; payload `forecast` per version; dashboard version headers show it, with a small burn-down sparkline on the version page.
- **Out of scope:** per-person velocity; story points.

## 🏗️ Architectural Blueprint
- **Files to create:** `rmlib/forecast.py`.
- **Files to modify:** `rmlib/sync.py`, `scripts/roadmap.py`, `rmlib/dashboard.html`, docs, tests.

## ✅ Acceptance
- **Passes when:** a fixture with 20 ticks over 10 days and 30 remaining steps forecasts about 15 days out, with a range.
- **Passes when:** fewer than 5 ticks shows "not enough history"; a target date yields on track / at risk / late correctly.
- **Passes when:** the dashboard version header shows the forecast.
- **Passes when:** `uvx pytest -q tests/` is green apart from known failures.
- **Fails if:** a version with zero remaining steps shows a forecast instead of done.

## 🚶 Step-by-Step Checklist
- [ ] Step 1: pace from evidence dates with git fallback, forecast and range -> target: rmlib/forecast.py, tests
- [ ] Step 2: targets, status output and payload -> target: rmlib/sync.py, roadmap.py, tests
- [ ] Step 3: dashboard header and burn-down sparkline -> target: rmlib/dashboard.html, tests
