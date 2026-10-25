---
id: 55
title: Dashboard: header too tall, panels not collapsible, trunk health shows every past run as a red chip
type: bug
version: 0.19.0
status: planned
created: 2026-10-25
foundIn: 38
---

# 🐛 Plan 55: Dashboard: header too tall, panels not collapsible, trunk health shows every past run as a red chip
> Type: bug · Target: v0.19.0

## 🔍 Symptom & Reproduction
- **Observed:** On statewide (430 items, ~40 suite runs) the header block takes a third of the screen before any item; the slot strip, trunk health tile, gate timeline and other panels cannot be collapsed; trunk health renders one chip per suite-run label (each run without --shards is its own shard), so superseded e2e/unit runs stay red forever and the failing-name list grows unbounded.
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
