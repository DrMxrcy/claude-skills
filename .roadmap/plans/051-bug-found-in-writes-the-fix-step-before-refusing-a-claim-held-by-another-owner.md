---
id: 51
title: bug --found-in writes the Fix step before refusing a claim held by another owner
type: bug
version: 0.19.0
status: done
created: 2026-10-24
foundIn: 47
---

# 🐛 Plan 51: bug --found-in writes the Fix step before refusing a claim held by another owner
> Type: bug · Target: v0.19.0

## 🔍 Symptom & Reproduction
- **Observed:** With item N claimed by another owner, bug --found-in N appends the Fix step and found-during-build bullet, then set_claim refuses (held by ...); exit is non-zero but the plan file is already changed. file_bug in rmlib/ops.py calls atomic_write before set_claim.
- **Expected:** a claim held by another owner is detected before any file is written; the command exits non-zero with the hold message and the plan file is byte-for-byte unchanged (or with `--take`, both the step and the claim are written).
- **Repro steps:** `claim 5 --stage review --owner alice`; then as bob `bug "Menu clips" --found-in 5` → error "held by alice" but plan 5 now has the Fix step.

## 🩺 Root Cause
- **Culprit:** `file_bug` in `skills/roadmap/scripts/rmlib/ops.py`.
- **Why:** plans 40 (claim holds) and 47 (bug routing) were built in parallel; `file_bug` writes the plan with `atomic_write` and only then calls `set_claim`, which is where the hold check lives.

## ✅ Acceptance
- **Passes when:** the repro steps above no longer reproduce the symptom
- **Passes when:** the regression test fails on the old code and passes on the fix
- **Fails if:** a bug on an unheld in-flight item stops getting its Fix step and `fixing` claim, or `--take` stops overriding the hold.

## 🛠️ Checklist
- [x] Step 1: Write a reproduction test
  > evidence: b954627 regression test failed on old code; 7d5c3e0 fix; 87 bug+owner tests; merged 56ac747; 648 passed in 180.93s (0:03:00); reviews skipped at owner request (2026-10-24)
- [x] Step 2: Apply the fix
  > evidence: b954627 regression test failed on old code; 7d5c3e0 fix; 87 bug+owner tests; merged 56ac747; 648 passed in 180.93s (0:03:00); reviews skipped at owner request (2026-10-24)
- [x] Step 3: Verify suite is green
  > evidence: b954627 regression test failed on old code; 7d5c3e0 fix; 87 bug+owner tests; merged 56ac747; 648 passed in 180.93s (0:03:00); reviews skipped at owner request (2026-10-24)
