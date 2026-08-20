---
id: {{ID}}
title: {{TITLE}}
type: {{TYPE}}
version: {{VERSION}}
status: planned
created: {{DATE}}
---

# ⚙️ Plan {{ID}}: {{TITLE}}
> Type: {{TYPE}} · Target: v{{VERSION}}

## 📉 Current Pain Points
-

## 📈 Target State
-

## 🛡️ Baseline Tests (must stay green)
-

## ✅ Acceptance
- **Passes when:** behavior is unchanged for callers — the baseline tests above stay green
- **Passes when:** <observable signal the debt is gone: dead path deleted, one implementation, no duplication>
- **Fails if:** public API, output shape, or performance regresses

## 📋 Checklist
- [ ] Step 1: Isolate current pathways
- [ ] Step 2: Scaffold new implementation
- [ ] Step 3: Run full regression
