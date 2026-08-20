---
id: {{ID}}
title: {{TITLE}}
type: {{TYPE}}
version: {{VERSION}}
status: planned
created: {{DATE}}
---

# 🐛 Plan {{ID}}: {{TITLE}}
> Type: {{TYPE}} · Target: v{{VERSION}}

## 🔍 Symptom & Reproduction
- **Observed:**
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
