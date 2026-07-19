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

| Agent | Model | Effort | Use for |
|---|---|---|---|
| `executor` | opus | high | Implementation needing judgment — features, bug fixes, design-sensitive refactors |
| `verifier` | opus | medium | Fresh-context **adversarial** verification — CONFIRMED / REFUTED / PARTIAL, never fixes |
| `security-executor` | opus | high | ALL security-sensitive work — auth, secrets, headers, crypto, CVE triage |
| `mech-executor` | sonnet | low | Fully-specified mechanical work — pattern refactors, tests, docs, bulk edits |
| `scout` | haiku | low | Cheap read-only evidence — where/how is X, usages, config values, log summaries |
| `Explore` | haiku | low | Broad read-only codebase exploration (overrides the built-in Explore, which since Claude Code v2.1.198 inherits the parent model instead of defaulting to haiku) |

Every agent pins **both** `model:` and `effort:` in frontmatter. Subagents inherit the
main session's model *and* effort level when unset — an unlabeled agent silently runs at
frontier price. Frontmatter is the only reliable per-role effort control (the Agent tool
has no runtime effort parameter), and the fleet keeps the orchestrator free to run at
low/medium effort by default, going high only for multi-step judgment.

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

## Optional accelerators (auto-detected, opt-in by installation)

The policy layers two third-party tools **when — and only when — the user has installed
them**; their presence is the opt-in, and the orchestrator never suggests installing
them mid-task:

- **caveman** ([juliusbrussee/caveman](https://github.com/juliusbrussee/caveman)) —
  token-compression plugin. **Skills and levels only:** the integration uses the
  plugin's skills, `/caveman` levels (`lite`/`full`/`ultra`/`wenyan`), and `cavecrew-*`
  agents — the standalone npm tools (`caveman-code`, `caveman-shrink`) are out of
  scope. When the plugin is in the session, subagent briefs honor the active level;
  if no level is set, the orchestrator decides and sets one (`/caveman full` by
  default, `lite` when the user reads reports directly, `ultra` for bulk scout
  sweeps) and asks for caveman-terse reports (fragments, zero filler; code,
  commands, paths, and errors kept verbatim), and `cavecrew-*` agents may take
  scout-tier work. Compression is for prose reports only — artifacts, diffs, and
  errors are never compressed. Note caveman's own honest-numbers caveat: it shrinks
  *output* tokens, so the win is largest on chatty report-heavy delegation.
- **codegraph** — code-index MCP. When the project has a `.codegraph/` index, evidence
  tiers (scout / Explore / verifier) resolve structure questions — usages, callers,
  impact, dependencies — via codegraph queries before any broad grep. Indexing is never
  run by the orchestrator; that's the user's decision.

## Important: agents register only in NEW sessions

Subagents defined or renamed are picked up on the **next** session start, not the
current one. If a named tier (`executor`, `scout`, …) isn't in the available-agents
list yet, dispatch `general-purpose` with the matching `model` override
(`opus` / `sonnet` / `haiku`) and the same one-shot brief — same result, no waiting for
a restart. Always use model **aliases**, never pinned model IDs (pinned IDs hard-error
when versions rotate).
