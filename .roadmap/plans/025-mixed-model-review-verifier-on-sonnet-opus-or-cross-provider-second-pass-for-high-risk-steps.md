---
id: 25
title: Mixed-model review: verifier on sonnet, opus or cross-provider second pass for high-risk steps
type: chore
version: 0.18.0
status: done
created: 2026-10-15
---

# Plan 25: Mixed-model review: verifier on sonnet, opus or cross-provider second pass for high-risk steps
> Type: chore · Target: v0.18.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Same-model review shares blind spots. Move `verifier` to sonnet/medium so Opus-written code is reviewed by a different model at half the input cost; high-risk steps get a second pass from Opus (model override) or a cross-provider reviewer (Codex/Gemini) where installed.
- **Out of scope:** renaming tiers; changing executor.

## 🏗️ Architectural Blueprint
- **Files to modify:** verifier frontmatter, agent SKILL/README tables, root README, orchestration policy + synced blocks, quality-build.md tier table, roadmap SKILL.md, RULES_BLOCK + example, agent VERSION.

## ✅ Acceptance
- **Passes when:** `verifier.md` reads model sonnet / effort medium and every table and rules line agrees; high-risk second pass names opus override or cross-provider reviewer.
- **Passes when:** `pytest tests -q` green.
- **Fails if:** executor leaves opus or any tier is renamed.

## 🚶 Step-by-Step Checklist
- [x] Step 1: Flip verifier to sonnet/medium, update docs/policy/rules, bump agent VERSION 0.5.1, re-sweep projects -> target: skills/agent, skills/roadmap
  > evidence: pytest tests -q: 332 passed; verifier.md model: sonnet (2026-10-15)
