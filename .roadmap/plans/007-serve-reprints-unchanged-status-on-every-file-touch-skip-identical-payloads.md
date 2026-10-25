---
id: 7
title: Serve reprints unchanged status on every file touch — skip identical payloads
type: bug
version: 0.15.0
status: done
created: 2026-07-26
---

# 🐛 Plan 7: Serve reprints unchanged status on every file touch — skip identical payloads
> Type: bug · Target: v0.15.0

## 🔍 Symptom & Reproduction
- **Observed:** with an agent working in the repo, serve's terminal reprints the
  same `↻ current …` line many times (mtime signature flaps on every file touch
  even when the rendered status is identical) and pushes redundant SSE frames.
- **Expected:** only print / push when the status payload actually changed.
- **Repro steps:**

## 🩺 Root Cause
- **Culprit:**
- **Why:**

## 🛠️ Checklist
- [x] Step 1: Write a reproduction test
- [x] Step 2: Apply the fix
- [x] Step 3: Verify suite is green
