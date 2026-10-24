---
id: 52
title: Leftovers: note error suggests a missing --audience flag; board copy commands lack the project under serve --all; board filters shared across projects
type: bug
version: 0.19.0
status: planned
created: 2026-10-24
foundIn: 48
---

# 🐛 Plan 52: Leftovers: note error suggests a missing --audience flag; board copy commands lack the project under serve --all; board filters shared across projects
> Type: bug · Target: v0.19.0

## 🔍 Symptom & Reproduction
- **Observed:** 1) roadmap.py note error text tells the user to pass --audience, but note has no such flag. 2) Under serve --all the board's copy-command buttons emit 'roadmap.py claim …' with no project path, so they only work when run inside that project. 3) Board choices (BOARD_PICK) and filter chips persist in one localStorage key for every project, so a filter set in one project applies to the next.
- **Expected:**
- **Repro steps:**

## 🩺 Root Cause
- **Culprit:**
- **Why:**

## ✅ Acceptance
- **Passes when:** the repro steps above no longer reproduce the symptom
- **Passes when:** the regression test fails on the old code and passes on the fix
- **Fails if:** <previously green test or adjacent behavior breaks>

## 🛠️ Checklist
- [ ] Step 1: Write a reproduction test
- [ ] Step 2: Apply the fix
- [ ] Step 3: Verify suite is green
