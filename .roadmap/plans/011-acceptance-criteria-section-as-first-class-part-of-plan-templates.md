---
id: 11
title: Acceptance criteria section as first-class part of plan templates
type: feature
version: 0.16.0
status: done
created: 2026-08-20
---

# Plan 11: Acceptance criteria section as first-class part of plan templates
> Type: feature · Target: v0.16.0
> Spec: [research note](../notes/2026-08-19-acceptance-criteria-section-as-first-class-part-of-plan-templates.md)

## 🎯 Target Scope & Boundaries
- **Core objective:** Add an "✅ Acceptance" section (explicit pass/fail criteria) to the three plan templates, and point the build-loop review prompts at it so spec/quality review subagents verify against it.
- **Out of scope:** No config/schema change; no CLI parsing of the section; existing plans untouched.

## 🏗️ Architectural Blueprint
- **Files to create:** none
- **Files to modify:** skills/roadmap/templates/feature-plan.md, bug-investigation.md, refactor-debt.md; SKILL.md + build command docs (review prompts reference Acceptance section when present)
- **Schema/interface changes:** none
- **Downstream impact:** import/promote-generated plans pick up new template automatically

## 🚶 Step-by-Step Checklist
- [x] Step 1: add Acceptance section to all three templates (2–3 example criteria lines each) -> target: templates
- [x] Step 2: reference the Acceptance section in SKILL.md build/review instructions; update docs/tests that assert template shape -> target: SKILL.md + tests
