---
id: 26
title: Review-effort and cache-stable briefs: verifier sonnet/high, read-only tool scopes, inline plan bodies, diff-scoped re-verification
type: chore
version: 0.18.0
status: active
created: 2026-10-21
---

# Plan 26: Review-effort and cache-stable briefs: verifier sonnet/high, read-only tool scopes, inline plan bodies, diff-scoped re-verification
> Type: chore · Target: v0.18.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Review effort matters more than review model, and same-model review shares the author's blind spots. Move `verifier` to sonnet/high, scope read-only roles to read-only tools (Bash kept for tests), split the subagent brief into a cache-stable common part and a task part, send builders the plan body inline, and re-verify only the diff since the last verdict.
- **Out of scope:** renaming tiers, changing `executor`/`security-executor` models, measuring sent-back findings per run (follow-up after one batch).

## 🏗️ Architectural Blueprint
- **Files to create:** `skills/agent/references/brief-common.md`, `skills/agent/references/brief-task.md`
- **Files to modify:** `skills/agent/.claude/agents/{verifier,scout,Explore}.md` (tools, verifier model/effort, dedupe codegraph line), `skills/agent/SKILL.md` + `README.md` tables, `skills/agent/references/orchestration-policy.md` (+ synced CLAUDE.md/AGENTS.md blocks), `skills/roadmap/references/quality-build.md` (sections B, C, D, tier table), `skills/agent/VERSION`, agy/codex plugin mirrors via build scripts.
- **Schema/interface changes:** none.
- **Downstream impact:** installed projects pick up new frontmatter on re-install.

## ✅ Acceptance
- **Passes when:** `verifier.md` reads model sonnet / effort high, has no Edit/Write/NotebookEdit/Agent in `tools:`, and states it reviews a different model's work; `scout.md` and `Explore.md` tools are read-only plus Bash; no model IDs anywhere in fleet frontmatter.
- **Passes when:** `brief-common.md` contains no dates, branch names, paths, or placeholders and ends with the "report is your final action" rule; `brief-task.md` holds every variable as a placeholder.
- **Passes when:** quality-build.md says builders get plan body + acceptance inline (file path only for >300 lines), re-verification receives a diff range, verifier and builder are different models by default with the blind-spot reason, and spawn prompts put stable content first.
- **Passes when:** `pytest tests -q` green and plugin mirrors rebuilt.
- **Fails if:** any writer tier loses tools, or a verifier is left on opus/medium.

## 🚶 Step-by-Step Checklist
- [x] Step 1: Fleet frontmatter — verifier sonnet/high + different-model line, read-only tool scopes, dedupe codegraph sentence; sync tables/policy; bump agent VERSION -> target: skills/agent
  > evidence: pytest tests -q: 332 passed; verifier.md model sonnet/effort high/tools Read,Grep,Glob,Bash; codegraph line kept per user (2026-10-21)
- [x] Step 2: Cache-stable brief — brief-common.md + brief-task.md, referenced from SKILL.md -> target: skills/agent/references
  > evidence: pytest tests/test_install_agent.py tests/test_validate_skills.py tests/test_agy_plugin.py -q: 39 passed; brief-common.md has no paths/dates, ends with stop rule (2026-10-21)
- [ ] Step 3: Quality-build protocol — inline plan body, diff-scoped re-verification, mixed-model rationale, stable-first spawn order; rebuild plugin mirrors -> target: skills/roadmap/references/quality-build.md
