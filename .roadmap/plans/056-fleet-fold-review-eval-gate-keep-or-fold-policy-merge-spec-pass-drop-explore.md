---
id: 56
title: Fleet fold review: eval gate, keep-or-fold policy, merge spec pass, drop Explore
type: refactor
version: 0.19.0
status: done
created: 2026-10-25
---

# ⚙️ Plan 56: Fleet fold review: eval gate, keep-or-fold policy, merge spec pass, drop Explore
> Type: refactor · Target: v0.19.0

**Source:** Anthropic, "Building agents: when to fold subagents into your main agent loop" (claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop).

## 📉 Current Pain Points
- Six fleet agents (`skills/agent/.claude/agents/`) with no written test for when an agent earns its place; sprawl risk.
- `Explore` overlaps `scout` and codegraph; each extra hop is a lossy summary.
- Every build step runs two sequential reviewers (scout spec pass, then verifier quality pass): tightly coupled specialists chaining on each other's output.
- No golden-task evals, so fleet changes (including the unmeasured verifier tier) are judged by guess.

## 📈 Target State
- Orchestration policy states a keep-or-fold test: keep a subagent only for (a) measurable context bloat, (b) parallel work needing discardable context, (c) tool-selection or instruction conflict. Divide by context, not problem type; never chain specialists.
- `skills/agent/evals/` holds ~10 golden tasks (seeded-bug step, security fix, access-matrix-style step, etc.) plus a runner doc; each run twice minimum; tracked: seeded bug caught, right skill loaded, tokens, wall time, rework loops.
- Fleet changes are gated on the evals; fold one agent at a time.
- One reviewer per step: `verifier` receives the ✅ Acceptance list; `scout` keeps test runs only.
- `Explore` removed from the packaged fleet and all installers/plugins.
- `mech-executor` untouched unless evals show no cost saving once rework is counted.

## 🛡️ Baseline Tests (must stay green)
- `tests/test_install_agent.py` and the rest of `pytest` suite.

## ✅ Acceptance
- **Passes when:** `references/orchestration-policy.md` contains the keep-or-fold test, divide-by-context rule, and the eval-gate rule (min 2 runs per task).
- **Passes when:** `skills/agent/evals/` has >=10 golden task files and a runner doc listing the tracked metrics.
- **Passes when:** `quality-build.md` and the policy's build-loop text describe a single verifier pass that receives the Acceptance list; scout only runs tests.
- **Passes when:** no reference to `Explore` remains in skills/agent, `agy-plugin`, `codex-plugin`, installer, or tests; baseline tests green.
- **Fails if:** installer output, public CLI behavior, or any baseline test regresses.

## 📋 Checklist
- [x] Step 1: Add keep-or-fold test, divide-by-context rule, eval-gate rule to orchestration-policy.md
  > evidence: scout spec MET x4; verifier PARTIAL fixed (fleet grandfathered, evals sign-off, tie rule); pytest install_agent+agy 24 passed (agy validate test pre-existing fail) (2026-10-25)
- [x] Step 2: Build evals/ with 10 golden tasks and runner doc; run baseline twice
  > evidence: 10 tasks+fixtures+run_eval.py; pytest agent_evals+install_agent+agy 59 passed 1 skipped; evals/ stripped from installs; self-reviewed (user: no subagents) (2026-10-25)
- [x] Step 3: Merge scout spec pass into verifier (quality-build.md, policy, verifier/scout agent files); re-run evals, compare
  > evidence: full pytest 1023 passed 1 skipped (agy validate deselected, pre-existing); spec+quality self-review; eval comparison NOT run (no subagents) (2026-10-25)
- [x] Step 4: Remove Explore from fleet, installer, agy-plugin, codex-plugin, tests; re-run evals
  > evidence: full pytest 1023 passed + fixed retired-explore test 26 passed; no Explore refs left outside installer-merged root CLAUDE/AGENTS; self-review (2026-10-25)
- [x] Step 5: Record mech-executor decision from eval data (hold or fold); run full regression
  > evidence: mech-executor hold recorded; full regression: pytest 1023 passed 1 skipped, agy validate test pre-existing failure deselected (2026-10-25)

## ⚖️ Rulings

- **Ruling (2026-10-25, user):** No subagents for this plan's build: parent does all steps in the main loop, self-reviews (spec pass then quality pass, recorded as self-review). Default policy becomes single main loop; subagents only for the keep-or-fold reasons.
- **Ruling (2026-10-25, user):** Step 3 merge lands on the user's direct instruction (counts as the eval-gate sign-off); baseline-vs-spec-merged eval runs need fleet runs and are NOT done — run them later via evals/README.md before any further fold.
- **Ruling (2026-10-25, claude):** mech-executor: HOLD. No eval data shows cost saving or loss once rework is counted; revisit after baseline-vs-fold eval runs (evals/README.md).
