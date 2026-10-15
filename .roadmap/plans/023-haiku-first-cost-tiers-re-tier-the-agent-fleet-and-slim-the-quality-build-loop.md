---
id: 23
title: Haiku-first cost tiers: re-tier the agent fleet and slim the quality build loop
type: chore
version: 0.18.0
status: active
created: 2026-10-15
---

# Plan 23: Haiku-first cost tiers: re-tier the agent fleet and slim the quality build loop
> Type: chore · Target: v0.18.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Cut subagent token spend without lowering code quality, now that Haiku 5.5 ($0.10/$0.50 per MTok, effort setting, 1M context) is Anthropic's recommended coding subagent. Re-tier the fleet (Sonnet implementer/verifier, Haiku mechanical + evidence, Opus reserved for security and explicit escalation), rewrite the orchestration policy around it, and slim the quality build loop from three subagents per step to two (one implementer, one combined spec+quality review) with a second review only on high-risk steps.
- **Out of scope:** renaming tiers (installed projects and CLAUDE.md blocks reference them by name); changing `buildRoles` schema or any `roadmap.py` behavior beyond the rules text; cutting v0.18.0.

## 🏗️ Architectural Blueprint
- **Files to create:** none
- **Files to modify:** `skills/agent/.claude/agents/{executor,verifier,mech-executor}.md` (frontmatter), `skills/agent/references/orchestration-policy.md`, `skills/agent/SKILL.md`, `skills/agent/README.md`, `skills/agent/VERSION`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `agy-plugin/plugins/agent/**` mirrors, `skills/roadmap/references/quality-build.md`, `skills/roadmap/SKILL.md`, `skills/roadmap/scripts/rmlib/core.py` (RULES_BLOCK build line), tests asserting the old wording.
- **Schema/interface changes:** none (agent names, `buildRoles` keys unchanged)
- **Downstream impact:** every project with the fleet installed must be re-installed (`install.sh` is idempotent) to pick up the new tiers; global `~/.claude/agents` symlinks update automatically.

## ✅ Acceptance
- **Passes when:** fleet frontmatter reads executor=sonnet/high, verifier=sonnet/medium, mech-executor=haiku/medium, scout/Explore=haiku/low, security-executor=opus/high, and every doc table agrees.
- **Passes when:** orchestration policy states the Opus-reserve rule, the Haiku 100K-token price cliff, and the two-agents-per-step build shape; `quality-build.md` and the RULES_BLOCK describe one implementer + one combined review, second review only for high-risk steps.
- **Passes when:** `python3 -m pytest tests -q` is green.
- **Fails if:** any tier is renamed, `roadmap.py` behavior changes, or an installed project still carries `model: opus` on `executor` after the re-install sweep.

## 🚶 Step-by-Step Checklist
- [x] Step 1: Re-tier fleet frontmatter + update every tier table (agent SKILL/README, root README) -> target: skills/agent, README.md
  > evidence: pytest tests -q: 332 passed (2026-10-15)
- [ ] Step 2: Rewrite orchestration policy (tiers, Opus-reserve, Haiku price cliff, token hygiene) and sync CLAUDE.md / AGENTS.md / agy-plugin mirrors -> target: skills/agent/references/orchestration-policy.md
- [ ] Step 3: Slim the quality build loop to implementer + one combined review; update quality-build.md, roadmap SKILL.md, RULES_BLOCK, and tests -> target: skills/roadmap
- [ ] Step 4: Bump agent VERSION to 0.5.0 and re-install the fleet into every existing project under ~/Desktop/Dev -> target: install.sh sweep
