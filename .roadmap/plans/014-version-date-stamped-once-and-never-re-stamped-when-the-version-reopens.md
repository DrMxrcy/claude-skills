---
id: 14
title: Version date stamped once and never re-stamped when the version reopens
type: bug
version: 0.17.0
status: planned
created: 2026-08-20
---

# 🐛 Plan 14: Version date stamped once and never re-stamped when the version reopens
> Type: bug · Target: v0.17.0

## 🔍 Symptom & Reproduction
- **Observed:** v0.16.0 shipped with changelog date 2026-08-13: the version was momentarily 100% on that date (only FEAT-8 in it), sync stamped `versionDates["0.16.0"]`, and when items 10–13 were later added and finished on 2026-08-20 the stale date survived into both changelogs. Caught by the v0.16.0 release review; hand-fixed in config for that cut.
- **Expected:** a version's date reflects when it actually reached 100% most recently — adding incomplete items to an already-stamped version clears (or re-stamps) its date.
- **Repro steps:** init scratch repo → one item in vX, check all steps (sync stamps date) → add second incomplete item to vX → complete it later → date still shows first stamp.

## 🩺 Root Cause
- **Culprit:** `rmlib/sync.py` (~lines 128–138) — `if version in version_dates: continue` skips stamped versions forever; `release()` in ops.py never re-stamps either.
- **Why:** stamping logic assumes versions only ever go from incomplete to complete once.

## ✅ Acceptance
- **Passes when:** the repro above yields the later completion date in config and both changelogs
- **Passes when:** regression test fails on old code, passes on fix; already-released (cut) versions keep their historical dates
- **Fails if:** dates of fully shipped versions below currentVersion change on sync

## 🛠️ Checklist
- [ ] Step 1: Write a reproduction test
- [ ] Step 2: Apply the fix (clear/re-stamp date when a stamped, uncut version regains incomplete items)
- [ ] Step 3: Verify suite is green
