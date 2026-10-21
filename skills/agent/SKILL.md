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
| `verifier` | sonnet | high | Fresh-context **adversarial** verification — CONFIRMED / REFUTED / PARTIAL, never fixes |
| `security-executor` | opus | high | ALL security-sensitive work — auth, secrets, headers, crypto, CVE triage |
| `mech-executor` | haiku | medium | Fully-specified mechanical work — pattern refactors, tests, docs, bulk edits (escalate to `sonnet` override if it stalls) |
| `scout` | haiku | low | Cheap read-only evidence — where/how is X, usages, config values, log summaries, spec-conformance review, test runs |
| `Explore` | haiku | low | Broad read-only codebase exploration (overrides the built-in Explore, which since Claude Code v2.1.198 inherits the parent model instead of defaulting to haiku) |

**Why this split:** Opus writes code; a *different* model (Sonnet) reviews it so the review does not share the author's blind spots, with Opus (or a cross-provider reviewer where installed) as the second pass on high-risk steps. Review runs at **high** effort: for review work, effort
moves finding quality more than model choice does, so a cheaper model at high effort beats a
frontier model at medium. Haiku does everything whose output is a
fact (where is X, does the diff meet the acceptance list, did the tests pass, apply this
spec'd edit). Haiku 5.5 costs ~40x less than Opus 5.5 per token on prompts under 100K
tokens (5x more above that cliff — keep its briefs lean), so routing evidence and
mechanical work there is where the savings live; Sonnet is the escalation override
when a Haiku task stalls, not a default tier.

Every agent pins **both** `model:` and `effort:` in frontmatter. Subagents inherit the
main session's model *and* effort level when unset — an unlabeled agent silently runs at
frontier price. Frontmatter is the only reliable per-role effort control (the Agent tool
has no runtime effort parameter), and the fleet keeps the orchestrator free to run at
low/medium effort by default, going high only for multi-step judgment. Read-only roles
(`verifier`, `scout`, `Explore`) also pin `tools:` to Read/Grep/Glob/Bash — no Edit, Write,
or Agent — so a review cannot quietly turn into a fix or a sub-fleet.

The full orchestration policy — who keeps what, one-shot delegation specs, the
escalation rule, high-risk routing, and the final verification gate — is the CLAUDE.md
block in `references/orchestration-policy.md`. The installer merges that block into
your project (or global) CLAUDE.md and copies the fleet into `<agent-dir>/agents/`.

Spawn prompts are two parts for prompt caching: `references/brief-common.md` (byte-identical
across every project and task — reporting format, evidence rules, no-attribution commit
rule, stop-after-report rule) pasted first, then `references/brief-task.md` filled in
(repo, plan, step, inline plan body + acceptance lines, test commands, diff range).
Nothing variable appears before the end of the common part.

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
  scope. When the plugin is in the session, the orchestrator decides the level
  **during session orientation** — if the user hasn't set one explicitly, it chooses
  and sets one up front by session shape — `ultra` for orchestration-heavy sessions
  (multi-agent build chains, `--auto` runs, bulk sweeps), `full` for ordinary mixed
  work, `lite` when the user reads agent reports directly; the plugin's own session
  default doesn't count as decided and asks for caveman-terse reports (fragments, zero
  filler; code,
  commands, paths, and errors kept verbatim), and `cavecrew-*` agents may take
  scout-tier work. Compression is for prose reports only — artifacts, diffs, and
  errors are never compressed. Note caveman's own honest-numbers caveat: it shrinks
  *output* tokens, so the win is largest on chatty report-heavy delegation.
  The installer wires a **SessionStart hook** (`hooks/caveman-level.sh`). If the
  project pins a level in **`.claude/caveman-level`** (one word: `lite`/`full`/
  `ultra`/`wenyan`), the hook sets it outright at session start — writes the plugin's
  flag file and mode log, announces it as already active; nobody types anything.
  Without a preference file, it injects the decision prompt so the orchestrator
  chooses by session shape and persists the choice. Note the plugin's flag is
  global (`~/.claude/.caveman-active`), so the level follows whichever project
  started a session most recently. The hook no-ops when the plugin is absent; skip
  it with `--no-hook`.
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
