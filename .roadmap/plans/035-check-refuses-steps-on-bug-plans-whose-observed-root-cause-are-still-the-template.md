---
id: 35
title: check refuses steps on bug plans whose Observed/Root cause are still the template
type: feature
version: 0.21.0
status: planned
created: 2026-10-23
---

# Plan 35: check refuses steps on bug plans whose Observed/Root cause are still the template
> Type: feature · Target: v0.21.0

## 🎯 Target Scope & Boundaries
- **Core objective:** A bug plan shipped with Observed and Root cause blank. `check` refuses a step while the plan's required sections are still template text.
  - Required sections per type: bug = Observed, Root cause, Acceptance; feature/refactor/chore = Target Scope core objective, Acceptance. Configurable via `settings.requiredSections`.
  - "Still template" = section missing, empty, or containing the template's placeholder text (`<...>` placeholders, bare `**Core objective:**`).
  - Refusal names the empty sections and the file. `--force` overrides and records "forced past empty template" in the evidence line.
  - `tidy` also reports stub plans (report-only).
- **Out of scope:** judging the quality of filled sections.

## 🏗️ Architectural Blueprint
- **Files to modify:** `rmlib/ops.py` (check gate), `rmlib/parse.py` (section extraction + placeholder detection), `rmlib/incubator.py` or tidy module, `scripts/roadmap.py` (`--force`), docs, tests.

## ✅ Acceptance
- **Passes when:** `check --plan N --step 1` on a fresh bug plan fails naming Observed, Root cause, Acceptance; after filling them it succeeds.
- **Passes when:** `--force` succeeds and the evidence line records the override; `tidy` lists stub plans.
- **Passes when:** existing plans in this repo with filled sections are not refused; `uvx pytest -q tests/` green apart from known failures.
- **Fails if:** plans created before the template had these sections become uncheckable without `--force` (only refuse when the section heading exists and is empty, or the type requires it and the template defines it).

## 🚶 Step-by-Step Checklist
- [ ] Step 1: section extraction and placeholder detection -> target: rmlib/parse.py, tests
- [ ] Step 2: check gate, `--force`, evidence note -> target: rmlib/ops.py, roadmap.py, tests
- [ ] Step 3: tidy report and docs -> target: tidy module, references/state-model.md
