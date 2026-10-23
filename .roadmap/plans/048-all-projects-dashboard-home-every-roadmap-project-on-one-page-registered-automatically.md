---
id: 48
title: All-projects dashboard home: every roadmap project on one page, registered automatically
type: feature
version: 0.21.0
status: planned
created: 2026-10-23
---

# Plan 48: All-projects dashboard home: every roadmap project on one page, registered automatically
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** The roadmap lives in a dozen projects, each with its own dashboard on its own port. Give one home page for all of them with zero setup.
  - **Auto registry:** every `orient`, `status`, `serve` and `check` run records the project root, name and last-seen time in a per-user registry (`~/.roadmap/projects.json`, written atomically; failures are silent). No config.
  - `claude-roadmap serve --all` (also the default when `serve` runs outside any project) serves a home page `#/projects`: one card per registered project with name, current version and progress, in-flight / blocked / waiting counts, last activity, and alerts (REFUTED verdicts, slot clashes, WIP over limit, overdue waiting steps, failing trunk suite) where those features exist.
  - Clicking a card opens that project's normal dashboard pages under `#/p/<name>/...` in the same server, so one URL and one port cover everything. Per-project `serve` keeps working as now.
  - Projects whose path no longer exists are greyed and can be hidden (`roadmap.py projects --forget <name>`); `roadmap.py projects` lists the registry.
- **Out of scope:** remote machines; projects never opened with the CLI.

## 🏗️ Architectural Blueprint
- **Files to create:** `rmlib/registry.py`.
- **Files to modify:** `scripts/roadmap.py` (registry touch on the listed commands, `projects`, `serve --all`), `rmlib/dashboard.py` (multi-root server: per-project broadcasters started lazily when first viewed, home summary computed cheaply from `status()` only), `rmlib/dashboard.html` (home page and `#/p/<name>/` routing), the `claude-roadmap` shim (outside a project runs `serve --all`), docs, tests.
- **Cost:** the home page refreshes each project at most every 10 s; only the opened project gets the 1 s tick.

## ✅ Acceptance
- **Passes when:** after running `status` in two fixture projects, `serve --all` shows both cards with correct versions and counts.
- **Passes when:** opening a card shows that project's list and plan pages under `#/p/<name>/`; deep links work after reload.
- **Passes when:** a deleted project path shows greyed; `projects --forget` removes it; a broken registry file is ignored without errors.
- **Passes when:** `uvx pytest -q tests/test_roadmap*.py tests/test_cli_e2e.py` is green.
- **Fails if:** any command fails because the registry cannot be written.

## 🚶 Step-by-Step Checklist
- [ ] Step 1: registry module and touch from CLI commands, `projects` command -> target: rmlib/registry.py, roadmap.py, tests
- [ ] Step 2: multi-project server with lazy per-project broadcasters -> target: rmlib/dashboard.py, tests
- [ ] Step 3: home page and per-project routing -> target: rmlib/dashboard.html, tests
- [ ] Step 4: shim default and docs -> target: install.sh shim template, README, SKILL.md
