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

## Per-item loop (quality, cost-tiered)

Parent reads the plan file + linked Spec / Detailed plan once, then for **each unfinished checklist step** (in order). **Two to three subagents per step, never an unlabeled one** — a `general-purpose` child with no model inherits the parent's frontier model and effort, which is where build loops burn tokens. Default role → tier (the `agent` skill's fleet; use the matching `model` override on `general-purpose` when a tier isn't installed):

| Role | Tier | Model | When |
|---|---|---|---|
| Research | `scout` / `Explore` | haiku | **Only** when the plan doesn't already name the files |
| Implement | `executor` | opus | Every step |
| Spec review | `scout` | haiku | Every step — acceptance list → MET / NOT MET / UNVERIFIED |
| Quality review | `verifier` | opus | Every step — one adversarial pass |
| Second quality pass | `verifier` (fresh) | opus | **High-risk steps only** (auth, billing, migrations, shared state, public contracts) |
| Test run for evidence | `scout` | haiku | When the parent wants the result line without the log in its context |

### A. Research (skip by default)

- Skip when the plan's Blueprint already lists the files to touch — the implementer reads them itself.
- Otherwise spawn **`scout`** (read-only, haiku) with: step text + "return the relevant files, call sites, and constraints as `path:line`." May run `background: true` while the parent prepares the implementer prompt. Never lets it edit.

### B. Implement (one writer, `executor`)

- Prefer superpowers **`subagent-driven-development`** if installed (same shape as below).
- Else spawn **`executor`** with a **self-contained, one-shot prompt**:
  - full step text + the ✅ Acceptance lines + only the plan/spec excerpts the step needs (paths, not pasted files)
  - files to touch, TDD expectation, "run the project tests before reporting"
  - "report DONE / DONE_WITH_CONCERNS / BLOCKED with the test command + result line; do not run roadmap CLI"
- **One implementer at a time** for this item. Do not fan out multiple implementers unless steps are *proven* independent *and* use separate `isolation: worktree` worktrees with an explicit parent merge — default is **no**.

### C. Spec review (`scout`, haiku)

- Fresh **`scout`** gets the step text + ✅ Acceptance list and runs `git diff` itself (don't paste the diff — it is cheaper for haiku to read it than for the parent to relay it):
  - "For each criterion: MET / NOT MET / UNVERIFIED with `path:line`. List extras outside the step. No quality opinions."
- Any NOT MET → re-dispatch `executor` with the gap list; re-run the scout pass. **Cap at two fix→review loops**, then the parent reads the gap itself.

### D. Quality review (`verifier`, opus)

- After spec is clean, one fresh **`verifier`** pass: correctness edge cases, error handling, contract drift, test quality; any "Fails if" line in ✅ Acceptance is a hard blocker. Returns CONFIRMED / REFUTED / PARTIAL with evidence.
- REFUTED/PARTIAL → `executor` fixes → **re-run only the verifier** (spec already passed). Same two-loop cap.
- **High-risk steps** (touching auth, billing, permissions, migrations, shared state, concurrency, public API contracts) get a **second, independent verifier** with a different framing; otherwise one pass is the default.

### E. Parent verification + roadmap

Only the parent:

1. Run the project's real build/tests for the change — directly, or via **`scout`** returning the decisive result line verbatim when the log would bloat the parent's context.
2. On green: `python3 "$RM" check --plan <id> --step <n> --evidence "<command>: <real result>"`
   — paste the actual test output line you (or the scout) saw (e.g. `pytest -q: 312 passed`), never a guess.
3. **Micro-commit code + roadmap immediately** (one commit per checked step).
   This is what makes rate-limits safe: the next agent only loses uncommitted
   in-flight work, never completed steps.
4. Proceed to the next step.

### F. Item complete

- Item-level review: **only** for items with three or more steps or any high-risk step — one `verifier` pass against the whole plan scope. Small items are covered by their per-step reviews.
- If not `--auto`: pause and report to the user.
- If `--auto`: brief status line, then next unblocked item (`next` or remaining selection).

## Worker availability and review fallback (Codex, Gemini CLI, Kimi, Copilot, restricted sessions)

The tier table above is the **default when native workers are available and permitted**. Repository or session restrictions take precedence over delegation and model-routing instructions anywhere in this skill. Stay in the host's native tooling: in Codex use Codex collaboration tools; never invoke the Claude CLI, load `.claude/agents/` definitions, or use Claude model aliases from another coder. Shared tooling living under `.claude/skills/` stays usable — its location does not authorize switching coders.

If implementation or review workers are unavailable or prohibited, the parent **continues the authorized work**:

1. Implement as the **sole writer**.
2. Run a **separate spec-compliance pass** — fresh read of `git diff` against the step text and ✅ Acceptance list; fix findings and repeat until clean.
3. Run a **separate code-quality pass** — adversarial correctness, edge cases, error handling, contract drift, test quality; fix findings and repeat until clean.
4. Use capable **permitted read-only reviewers** for whichever passes the host offers.
5. In the `check --evidence` text, **record which passes were independent and which were parent self-reviews**, with findings and evidence. Never claim a worker review happened when it did not.

Worker unavailability alone is never a blocker and never justifies refusing or abandoning the task. The fallback keeps the same plan scope, acceptance criteria, real build/test gates before every `check`, and code-plus-roadmap micro-commits; `--auto` still skips user pauses only, never review passes or tests. Preserve any worker's in-flight work and report the independence limit in the step summary.

## Role mapping (Grok Build)

| Role | `subagent_type` | Notes |
|---|---|---|
| Research | `explore` | `capability_mode: read-only` if set; `background: true` OK |
| Implement | `general-purpose` | Full tools; shared tree by default |
| Spec / quality review | `explore` or `general-purpose` | Prefer read-only; no roadmap CLI |
| Orchestration | **parent only** | status, deps-check, check, commit, PR |

Grok: `spawn_subagent` from the parent; `get_command_or_subagent_output` for background explore. Watch children with Ctrl+B.

When `settings.buildRoles` is set in `.roadmap/config.json` (`explorer` / `implementer` / `specReviewer` / `qualityReviewer` → model or agent names, shown on the `Roles:` line of `orient`/`handoff`), the parent applies that mapping when spawning each subagent — values are host-specific and honored best-effort. Absent, the default mapping is the tier table above: `explorer=scout`, `implementer=executor`, `specReviewer=scout`, `qualityReviewer=verifier`.

## Role mapping (Claude Code / Task tool)

Same roles via Task / subagent dispatch using the fleet tiers above. Prefer superpowers SDD templates when present.

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
- Spawning an unlabeled `general-purpose` reviewer or implementer (inherits the parent's frontier model + effort)
- Pasting whole files or diffs into a haiku brief instead of letting it read them (and pushing it past the 100K-token price cliff)
- Spawning subagents from inside a subagent (Grok depth limit)
- Building multiple roadmap items at once without an explicit user request *and* clear file isolation

## Tiny steps (quality tip)

If a step is huge, split work *inside* the step with implement → review cycles, but only flip the checklist box when the **whole step** is done and tested. Prefer planning smaller steps at `/roadmap-plan` time.
