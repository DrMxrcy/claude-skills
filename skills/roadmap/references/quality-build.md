# Quality-first multi-agent build protocol

Default for `/roadmap-build` / `/roadmap:build` (including `--auto`) and
`/roadmap-next` / `/roadmap:next` on **Claude Code, Grok Build, and other agents**.

**Optimize for correctness and maintainability.** Speed comes from focused subagents and
small checklist steps — not from racing parallel writers or skipping review.

## Mission

Keep AI coders **on-task** (one plan item, real checklist, no dashboard thrash) while
**high-quality code** ships (implement → spec review → quality review → tests → check).

## Goals

1. High-quality code: tests green, matches plan/spec, reviewed before check-off.
2. Roadmap never drifts: only the **parent** session runs `roadmap.py`.
3. Use subagents for **fresh context + specialized roles**, not for racing two writers.
4. Same protocol on every agent — colon vs hyphen slash names are the only surface difference.

## Hard rules

| Rule | Why |
|---|---|
| **One roadmap item at a time** | `dependsOn` / order; no multi-item parallel implementers by default |
| **Parent owns `roadmap.py`** | Children never `check` / `sync` / edit `ROADMAP.md` |
| **Tests before every `check`** | Parent runs the project test/build after implement + review |
| **No parallel writers on the same tree** | Quality > speed; conflicts hide bugs |
| **Subagent depth = 1** (Grok) | Only the parent spawns; children do not spawn kids |
| **Never skip review on `--auto`** | `--auto` only removes *user* checkpoints between items |

## Item selection

1. `status` (or `next --json` for “whatever is next”).
2. `deps-check --plan <id>` — finish blockers first unless the user overrides.
3. Process items in `order` then id (or only the single id / `next` pick).
4. `--auto`: after an item hits 100%, continue to the next unblocked item without asking.

## Per-item loop (quality)

Parent reads the plan file + linked Spec / Detailed plan once, then for **each unfinished checklist step** (in order):

### A. Research (optional, parallel-safe)

- Spawn **`explore`** (read-only) with: step text, paths from the plan, and “return relevant files + constraints.”
- May run `background: true` while the parent prepares the implementer prompt.
- Do **not** let explore edit files.

### B. Implement (one writer)

- Prefer superpowers **`subagent-driven-development`** if installed (same shape as below).
- Else spawn **`general-purpose`** implementer with a **self-contained prompt**:
  - full step text + relevant plan/spec excerpts (do not make the child re-discover the whole plan)
  - files to touch, acceptance criteria, TDD expectation
  - “report DONE / DONE_WITH_CONCERNS / BLOCKED; do not run roadmap CLI”
- **One implementer at a time** for this item. Do not fan out multiple implementers unless steps are *proven* independent *and* use separate `isolation: worktree` worktrees with an explicit parent merge — default is **no**.

### C. Spec compliance review

- Spawn a **fresh** subagent (explore or general-purpose read-only / review-focused):
  - “Does the diff satisfy this step + linked spec? List gaps or extras. No drive-by refactors.”
- If gaps: re-dispatch implementer to fix; re-review until clean.

### D. Code quality review

- Spawn a **fresh** reviewer after spec is ✅:
  - correctness edge cases, naming, duplication, error handling, tests quality
- If issues: implementer fixes; re-review until approved.

### E. Parent verification + roadmap

Only the parent:

1. Run the project’s real build/tests for the change.
2. On green: `python3 "$RM" check --plan <id> --step <n>`
3. **Micro-commit code + roadmap immediately** (one commit per checked step).
   This is what makes rate-limits safe: the next agent only loses uncommitted
   in-flight work, never completed steps.
4. Proceed to the next step.

### F. Item complete

- Optional: one final item-level review subagent against the whole plan scope.
- If not `--auto`: pause and report to the user.
- If `--auto`: brief status line, then next unblocked item (`next` or remaining selection).

## Role mapping (Grok Build)

| Role | `subagent_type` | Notes |
|---|---|---|
| Research | `explore` | `capability_mode: read-only` if set; `background: true` OK |
| Implement | `general-purpose` | Full tools; shared tree by default |
| Spec / quality review | `explore` or `general-purpose` | Prefer read-only; no roadmap CLI |
| Orchestration | **parent only** | status, deps-check, check, commit, PR |

Grok: `spawn_subagent` from the parent; `get_command_or_subagent_output` for background explore. Watch children with Ctrl+B.

## Role mapping (Claude Code / Task tool)

Same roles via Task / subagent dispatch. Prefer superpowers SDD templates when present.

## What `--auto` changes

| | Default build | `--auto` |
|---|---|---|
| Between **steps** | Same quality gates | Same quality gates |
| Between **items** | Pause for user | Continue automatically |
| Reviews | Required | **Still required** |
| Tests before check | Required | Required |

## What `--worktree` / `--pr` change

- `--worktree`: do the whole selection inside `roadmap/v<version>` (or per-item branch) so main stays clean. Subagents inherit that cwd / work from parent’s tree.
- `--pr`: after selection is 100%, push + `gh pr create` — **never merge to main**.

## Anti-patterns (do not)

- Parallel implementers on the same files to “go faster”
- Child runs `roadmap.py check` or edits `ROADMAP.md`
- Checking off a step because “it looks done” without tests
- Skipping C/D reviews under `--auto`
- Spawning subagents from inside a subagent (Grok depth limit)
- Building multiple roadmap items at once without an explicit user request *and* clear file isolation

## Tiny steps (quality tip)

If a step is huge, split work *inside* the step with implement → review cycles, but only flip the checklist box when the **whole step** is done and tested. Prefer planning smaller steps at `/roadmap-plan` time.
