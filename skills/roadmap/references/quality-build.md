# Quality-first multi-agent build protocol

Default for `/roadmap-build` / `/roadmap-build` (including `--auto`) and
`/roadmap-next` / `/roadmap-next` on **Claude Code, Grok Build, and other agents**.

**Optimize for correctness and maintainability.** Speed comes from focused subagents and
small checklist steps — not from racing parallel writers or skipping review.

## Mission

Keep AI coders **on-task** (one plan item, real checklist, no dashboard thrash) while
**high-quality code** ships (implement → spec review → quality review → tests → check).

## Goals

1. High-quality code: tests green, matches plan/spec, reviewed before check-off.
2. Roadmap never drifts: only the **parent** session runs `roadmap.py`.
3. Use subagents for **fresh context + specialized roles**, not for racing two writers.
4. Same protocol on every agent — the Codex `$roadmap` form is the only surface difference.

## Hard rules

| Rule | Why |
|---|---|
| **One roadmap item at a time** | `dependsOn` / order; no multi-item parallel implementers by default |
| **Parent owns `roadmap.py`** | Children never `check` / `sync` / edit `ROADMAP.md` |
| **Tests before every `check`** | Parent runs the project test/build after implement + review |
| **No parallel writers on the same tree** | Quality > speed; conflicts hide bugs |
| **Subagent depth = 1** (Grok) | Only the parent spawns; children do not spawn kids |
| **Never skip review on `--auto`** | `--auto` only removes *user* checkpoints between items |

## Orchestration per item

- **One orchestrator per item.** One parent session owns one item from start to check-off. It is the only session that runs `roadmap.py`. A new item gets a new parent, not the old one with a longer context.
- **Respawn budget: four respawns per step** (five attempts in total). A respawn is a fresh subagent for the same step after a failure, a stall, or a BLOCKED report. Once the budget is spent, mark the step BLOCKED, record the reason in the handoff note (`handoff --plan <id> --pending "<decision>"`), and stop that item. Do not keep retrying.
- **Respawn, never resume.** A resumed subagent re-sends its whole transcript on every turn. A respawn starts clean from the shared brief (`brief-common.md`, then `brief-task.md`), the plan body, and the branch state on disk.
- **Merge-only roadmap writes.** Builders never edit `ROADMAP.md`, `.roadmap/`, or the changelogs. Roadmap state changes only in the parent's `check`, `claim`, and the single merge step for a per-item branch. This keeps parallel items from colliding on shared roadmap files.

The review-loop cap (two fix→review loops, above) is separate from the respawn budget: it limits how many times one step is re-reviewed, while the respawn budget limits how many times a stuck step gets a new subagent.

## In-flight claims (visibility while building)

Steps tick on trunk only after the merge gate, so a long review or gate would otherwise look idle. Name the item branch `roadmap/<id>` and tag each feature commit `(plan N)` or `(bug N)` so discovery attributes the work. The parent records the stage as the item moves:

| Moment | Command |
|---|---|
| Review starts | `python3 "$RM" claim <id> --stage review` |
| A fix round starts | `python3 "$RM" claim <id> --stage fixing` |
| Review passes | `python3 "$RM" claim <id> --stage gate-ready --verdict <CONFIRMED\|PARTIAL\|REFUTED>` |
| Merge gate runs | `python3 "$RM" claim <id> --stage gating` |
| Stuck (BLOCKED, budget spent, conflict) | `python3 "$RM" claim <id> --stage blocked --note "<reason>"` |
| Several items move together | `python3 "$RM" claim <id> <id> … --stage gating` (all-or-nothing) |
| Batch merged into the integration branch | `python3 "$RM" claim --landed <integration-branch>` |
| Integration branch merged into trunk | `python3 "$RM" check --landed` (review the list), then `check --landed --yes --evidence "<gate result>"` |

- Claims live in plan frontmatter (`claim_*` keys, see `state-model.md`). `claim <id> --clear` drops one.
- Ticking the final step on trunk (step 5 below) removes the claim automatically.
- `status --in-flight` lists claimed or branch-backed items. The dashboard shows each lane, branch, and commit count.
- **Integration branch** (`settings.integrationBranch`): when item branches merge into an integration branch before trunk, a branch it contains reads `landed` with no claim. That derived lane vanishes once trunk contains the branch, so run `claim --landed <integration-branch>` right after each merge into integration; it records the landing sha that `check --landed` later proves is in trunk. `check --landed` never ticks an item whose landing sha or current branch tip trunk lacks.

## Merge gate (per-item branches)

When an item was built in its own worktree (`roadmap/<id>`, see `build.md`), its branch lands in the version trunk `roadmap/v<version>` through one gate. Only the parent runs this, one item at a time.

1. **Clean trunk first.** `git -C <trunk-worktree> status` must be clean. A dirty trunk stops the merge; report it, do not stash.
2. **Merge the item branch into the trunk** with `--no-ff`. Do not rebase the item branch and do not force-push.
3. **Conflicts stop the gate.** If the merge conflicts, abort it (`git merge --abort`), list the conflicting paths, and report them as BLOCKED with a `handoff --pending` note. Never auto-resolve a conflict.
4. **Run the full gate on the trunk**, not in the item branch: the project's lint, typecheck, unit tests, integration tests, and build. Builders ran only targeted tests, so the full suite runs here once per merged batch.
5. **Green:** record the result with `check --evidence` against the item's last step, then remove the item worktree (`git worktree remove <path>`) and delete the branch. Removal happens only after a green gate.
6. **Red:** reset the trunk to its pre-merge commit (`git -C <trunk-worktree> reset --hard <pre-merge-sha>`, a commit this gate created, never a commit someone else made), keep the item worktree, and report the failing command. The item is not checked off.

Roadmap state is written only at step 5, from the parent, never from the item worktree.

**With an integration branch** (`settings.integrationBranch`), steps 1–4 merge into the integration branch instead, and step 5 becomes `claim --landed <integration-branch>` for the batch (no ticks yet). When the integration branch itself passes the gate into trunk, `check --landed` lists what trunk now contains and `check --landed --yes --evidence "<gate result>"` ticks those items in one step.

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
| Quality review | `verifier` | sonnet, high effort | Every step — one adversarial pass by a different model than the author |
| Second quality pass | `verifier` + `opus` override, or cross-provider reviewer (Codex/Gemini) where installed | opus / other family | **High-risk steps only** (auth, billing, migrations, shared state, public contracts) |
| Test run for evidence | `scout` | haiku | When the parent wants the result line without the log in its context |

### A. Research (skip by default)

- Skip when the plan's Blueprint already lists the files to touch — the implementer reads them itself.
- Otherwise spawn **`scout`** (read-only, haiku) with: step text + "return the relevant files, call sites, and constraints as `path:line`." May run `background: true` while the parent prepares the implementer prompt. Never lets it edit.

### B. Implement (one writer, `executor`)

- Prefer superpowers **`subagent-driven-development`** if installed (same shape as below).
- Else spawn **`executor`** with a **self-contained, one-shot prompt**, stable content first, task content last (see *Spawn prompt shape* below):
  - the plan body (Scope, Blueprint, Spec/Detailed-plan excerpts the step needs) and the ✅ Acceptance lines **pasted inline** — not as a file path to read. Keep "read the file" only for files over ~300 lines; a builder that has the plan in its prompt starts writing instead of re-deriving it.
  - full step text, files to touch, TDD expectation, "run the project tests before reporting"
  - "report DONE / DONE_WITH_CONCERNS / BLOCKED with the test command + result line; do not run roadmap CLI"
- **One implementer at a time** for this item. Do not fan out multiple implementers unless steps are *proven* independent *and* use separate `isolation: worktree` worktrees with an explicit parent merge — default is **no**.

### C. Spec review (`scout`, haiku)

- Fresh **`scout`** gets the step text + ✅ Acceptance list and runs `git diff` itself (don't paste the diff — it is cheaper for haiku to read it than for the parent to relay it):
  - "For each criterion: MET / NOT MET / UNVERIFIED with `path:line`. List extras outside the step. No quality opinions."
- Any NOT MET → re-dispatch `executor` with the gap list; re-run the scout pass. **Cap at two fix→review loops**, then the parent reads the gap itself.

### D. Quality review (`verifier`, sonnet at high effort — a different model than the author)

- **Why a different model:** builder and verifier tiers are different models by default because a model reviewing its own output shares its blind spots — it rationalizes the same assumptions it wrote. Independent blind spots are the point; the cheaper model is a side benefit. **Why high effort:** for review work, effort moves finding quality more than model choice does, so the verifier runs high while the orchestrator stays low/medium.
- After spec is clean, one fresh **`verifier`** pass: correctness edge cases, error handling, contract drift, test quality; any "Fails if" line in ✅ Acceptance is a hard blocker. Returns CONFIRMED / REFUTED / PARTIAL with evidence.
- REFUTED/PARTIAL → before dispatching the fix, the parent snapshots the tree: `git add -N .` (intent-to-add, so new files appear in diffs) then `git stash create` — prints a commit SHA without touching the working tree; empty when the tree is clean, then use `HEAD`. Copy the literal SHA into the verifier prompt (shell variables do not survive between tool calls). `executor` fixes → `git add -N .` again for files the fix created → **re-run only the verifier, scoped to the fix**: its prompt receives the diff range `git diff <baseline-sha>` plus the specific findings sent back, and it verifies only that diff and those findings — not the whole step again (spec already passed; the unchanged code already has a verdict). Same two-loop cap.
- **High-risk steps** (touching auth, billing, permissions, migrations, shared state, concurrency, public API contracts) get a **second, independent pass** — `verifier` with an `opus` model override, or a cross-provider reviewer (Codex/Gemini CLI) where installed, for maximum blind-spot diversity; otherwise one pass is the default.

### E. Parent verification + roadmap

Only the parent:

1. Run the project's real build/tests for the change — directly, or via **`scout`** returning the decisive result line verbatim when the log would bloat the parent's context.
2. On green: `python3 "$RM" check --plan <id> --step <n> --evidence "<command>: <real result>"`
   — paste the actual test output line you (or the scout) saw (e.g. `pytest -q: 312 passed`), never a guess.
   Append the review ledger in a fixed shape so it can be counted later: `verifier: <CONFIRMED|REFUTED|PARTIAL>, <n> findings, <m> acted on`. Measurement: `grep -ho 'verifier: [A-Z]*, [0-9]* findings, [0-9]* acted on' .roadmap/plans/*.md` tallies review quality per batch — the number that decides whether the review tier and effort stay as configured.
3. **Micro-commit code + roadmap immediately** (one commit per checked step).
   This is what makes rate-limits safe: the next agent only loses uncommitted
   in-flight work, never completed steps.
4. Proceed to the next step.

### F. Item complete

- Item-level review: **only** for items with three or more steps or any high-risk step — one `verifier` pass against the whole plan scope. Small items are covered by their per-step reviews.
- If not `--auto`: pause and report to the user.
- If `--auto`: brief status line, then next unblocked item (`next` or remaining selection).

## Spawn prompt shape (prompt caching)

Every subagent prompt is two parts, in this order: the `agent` skill's `references/brief-common.md` pasted verbatim first (reporting format, evidence rules, commit rule, stop-after-report — identical across every project and task), then `references/brief-task.md` filled in (repo, plan, step, inline plan body + acceptance, test commands, diff range). Nothing variable appears before the end of the common part, so the cached prefix stays byte-identical from one spawn to the next.

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
