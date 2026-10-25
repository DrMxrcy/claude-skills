---
id: 24
title: Sole-writer fallback for AI coders without native subagents
type: chore
version: 0.18.0
status: done
created: 2026-10-15
---

# Plan 24: Sole-writer fallback for AI coders without native subagents
> Type: chore · Target: v0.18.0

## 🎯 Target Scope & Boundaries
- **Core objective:** The build loop must stay runnable on coders with no native subagents (Codex, Gemini CLI, Kimi, Copilot, restricted sessions): the parent implements as sole writer, runs separate spec and quality review passes itself (or via permitted read-only reviewers), records who actually reviewed and the independence limits, and keeps every test gate + micro-commit. Never fabricate independent review; never switch coders mid-task.
- **Out of scope:** new CLI behavior.

## 🏗️ Architectural Blueprint
- **Files to modify:** `skills/roadmap/references/quality-build.md`, `skills/roadmap/SKILL.md`, `skills/roadmap/scripts/rmlib/core.py` (RULES_BLOCK), `skills/roadmap/example/CLAUDE.md`, `skills/agent/references/orchestration-policy.md` + synced blocks, agy mirror.

## ✅ Acceptance
- **Passes when:** rules block, quality-build.md, and orchestration policy each state the sole-writer fallback and the "record real reviewers, never fabricate independence" rule.
- **Passes when:** `pytest tests -q` green.
- **Fails if:** fallback weakens test-before-check or micro-commit gates.

## 🚶 Step-by-Step Checklist
- [x] Step 1: Add sole-writer fallback wording to build docs, rules block, policy; sync + upgrade -> target: skills/roadmap, skills/agent
  > evidence: pytest tests -q: 332 passed; 'sole writer' present in rules block, policy, quality-build.md (2026-10-15)
