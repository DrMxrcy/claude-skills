# agent — cost-tiered subagent orchestration

Turn the main Claude Code session into a **senior decision-maker** that keeps judgment
for itself and delegates labor to the cheapest model tier that can do the job well —
then verifies the result with fresh context before answering.

The expensive frontier model plans, decides, and reviews. Cheaper tiers do the
searching, editing, testing, and mechanical work. Verification is adversarial and runs
in clean context, so "done" means *checked*, not *claimed*.

## What gets installed

- **A fleet of project subagents** into `<agent-dir>/agents/`:

  | Agent | Model | Role |
  |---|---|---|
  | `executor` | opus | Implementation needing judgment |
  | `verifier` | opus | Fresh-context adversarial verification (never fixes) |
  | `security-executor` | opus | All security-sensitive work |
  | `mech-executor` | sonnet | Fully-specified mechanical work |
  | `scout` | haiku | Cheap read-only evidence |
  | `Explore` | haiku | Broad read-only exploration (overrides the built-in, expensive default) |

- **An orchestration policy** (`references/orchestration-policy.md`) merged into your
  `CLAUDE.md` / `AGENTS.md` as an idempotent marked block. It describes what the
  orchestrator keeps, how to write one-shot delegation specs, when to escalate, how to
  route high-risk work, and the final verification gate.

- **Optional model wiring** in `settings.json` — pins a capable main-session `model`
  with a `fallbackModel` chain, **only when you have not set a model yourself**.

## Install

```sh
./install.sh                 # this project: fleet → ./.claude/agents, policy → ./CLAUDE.md
./install.sh --global        # all projects: fleet → ~/.claude/agents
./install.sh --no-agent      # skip the fleet entirely
./install.sh --no-model      # don't touch settings.json model
./install.sh --no-claude-md  # don't merge the policy into CLAUDE.md
```

Run it once per project you want the fleet in. Everything is **additive and
idempotent**: the policy merge updates a marked block in place and never rewrites the
rest of your `CLAUDE.md`; re-running upgrades in place; removing the marker block
uninstalls the policy.

## Design principles

- **Role terms, never model names** in policy — survives model version changes.
- **No project coupling** — the agents carry zero stack-specific detail; project
  context (framework, contracts) lives in that project's own `CLAUDE.md`, which the
  agents already read.
- **Fresh-context verification** beats self-review — the `verifier` starts skeptical
  and tries to refute.
- **Spawn-cost awareness** — don't delegate a task that costs less than the handoff.

## Note: agents register only in new sessions

Newly installed or renamed subagents appear on the **next** session start. Until then,
dispatch `general-purpose` with the matching `model` override (`opus` / `sonnet` /
`haiku`) and the same brief.
