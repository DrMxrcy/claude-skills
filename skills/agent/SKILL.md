---
name: agent
description: >
  Cost-tiered subagent orchestration for Claude Code (and other agents that load
  skills). Use when you want the main session to act as a senior decision-maker that
  delegates labor to the cheapest capable model tier — implementation (executor),
  adversarial verification (verifier), security work (security-executor), mechanical
  edits (mech-executor), and read-only evidence (scout / Explore). Installs a fleet of
  project subagents plus an orchestration policy that merges into CLAUDE.md. Triggers
  on "orchestrate", "delegate to subagents", "spin up the agent fleet", "who should do
  this work", "keep the main model on judgment".
argument-hint: "(guidance skill — no slash commands)"
---

# Agent — cost-tiered orchestration

**Mission:** keep the expensive frontier model doing judgment, not labor. The main
session (the orchestrator) decides WHAT and delegates any evidence-checkable work to
the cheapest tier that can do it well, then verifies with fresh context before it
answers. Policy is written in **role terms, never model names**, so it survives model
version changes.

## The fleet (project subagents)

| Agent | Model | Use for |
|---|---|---|
| `executor` | opus | Implementation needing judgment — features, bug fixes, design-sensitive refactors |
| `verifier` | opus | Fresh-context **adversarial** verification — CONFIRMED / REFUTED / PARTIAL, never fixes |
| `security-executor` | opus | ALL security-sensitive work — auth, secrets, headers, crypto, CVE triage |
| `mech-executor` | sonnet | Fully-specified mechanical work — pattern refactors, tests, docs, bulk edits |
| `scout` | haiku | Cheap read-only evidence — where/how is X, usages, config values, log summaries |
| `Explore` | haiku | Broad read-only codebase exploration (overrides the built-in Explore so it stops inheriting the expensive main model) |

The full orchestration policy — who keeps what, one-shot delegation specs, the
escalation rule, high-risk routing, and the final verification gate — is the CLAUDE.md
block in `references/orchestration-policy.md`. The installer merges that block into
your project (or global) CLAUDE.md and copies the fleet into `<agent-dir>/agents/`.

## Install

From the repo root (or piped from GitHub with `curl … | bash`):

    ./install.sh                 # this project: fleet → ./.claude/agents, policy → ./CLAUDE.md
    ./install.sh --global        # all projects: fleet → ~/.claude/agents
    ./install.sh --no-agent      # skip the fleet entirely
    ./install.sh --no-model      # don't touch settings.json model
    ./install.sh --no-claude-md  # don't merge the policy into CLAUDE.md

The policy merge is **idempotent and additive** — it updates a marked block
(`<!-- agent:orchestration:start -->` … `<!-- agent:orchestration:end -->`) in place
and never rewrites the rest of your CLAUDE.md. Re-running upgrades the block in place;
deleting the two markers (and the text between them) removes it. Run the installer
once per project you want the fleet in.

The model wiring is non-destructive: it sets `model` / `fallbackModel` in
settings.json **only when you have no `model` set**, so an explicit model choice is
never overridden.

## Important: agents register only in NEW sessions

Subagents defined or renamed are picked up on the **next** session start, not the
current one. If a named tier (`executor`, `scout`, …) isn't in the available-agents
list yet, dispatch `general-purpose` with the matching `model` override
(`opus` / `sonnet` / `haiku`) and the same one-shot brief — same result, no waiting for
a restart. Always use model **aliases**, never pinned model IDs (pinned IDs hard-error
when versions rotate).
