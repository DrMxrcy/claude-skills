---
description: Build a roadmap plan item, a whole version/phase, or the current version (quality-first multi-agent)
argument-hint: <plan id | version | empty> [--auto] [--worktree] [--pr]
---

Implement roadmap work using the **roadmap** skill. Target: $ARGUMENTS

**Default mode is high quality, not maximum parallelism.** Use the quality-first multi-agent
protocol below (and the full write-up in the skill’s
`references/quality-build.md` when installed). Especially for
`/roadmap-build <version> --auto` / `/roadmap-build 1.2.0 --auto`.

## Resolve selection

First run `python3 <roadmap.py> status`, then interpret the argument:

- A bare number (e.g. `3`) → that single plan item.
- A version (contains dots, e.g. `1.2.0`) → every incomplete item in that version (a whole phase).
- Empty → every incomplete item in the CURRENT version.
- `--auto` → build all selected items end-to-end **without user pauses between items**.
  **Still one item at a time. Still tests + reviews before every check.** Does **not** skip quality gates.
- `--worktree` → isolate the whole build in a git worktree (see below).
- `--pr` → when the selection reaches 100%, push and open a PR; **never merge to main**.

Flags compose: `--auto --worktree --pr` on a version = hands-off phase build with full quality gates.

**Agent slash names (always cite both — Grok does not load colon forms):**
- Claude Code: `/roadmap:build 80` · `/roadmap:build 1.2.0 --auto`
- Grok Build: **`/roadmap-build 80`** · **`/roadmap-build 1.2.0 --auto`**
- Either: `/roadmap build 80` · `/roadmap build 1.2.0 --auto`
- **Not valid:** `next --auto` (use `build … --auto` to chain items; `next` is one item only)

## Build order

1. Prefer `python3 <roadmap.py> next` logic for “whatever is next” (skips incomplete `dependsOn`).
2. Otherwise process selected items in ascending `order` / id, **one item fully complete before the next**.
3. Per item: `python3 <roadmap.py> deps-check --plan <id>` — finish blockers first unless the user overrides.

## Quality-first multi-agent protocol (default)

**Parent session = orchestrator only for roadmap state.** Children never run `roadmap.py` or edit `ROADMAP.md`.

For each unfinished checklist step of the current item:

| Phase | Who | What |
|---|---|---|
| **0. Context** | Parent | Read plan + linked Spec / Detailed plan. Extract the step + acceptance criteria. |
| **1. Research** | `explore` subagent (optional, may be background) | Map files/APIs; return paths + constraints. Read-only. |
| **2. Implement** | **One** `general-purpose` subagent | TDD for this step only. Self-review. Report DONE / DONE_WITH_CONCERNS / BLOCKED. |
| **3. Spec review** | Fresh subagent | Diff vs step + spec. Gaps → implementer fixes → re-review until ✅. |
| **4. Quality review** | Fresh subagent | Correctness, tests, maintainability. Issues → fix → re-review until ✅. |
| **5. Verify + check** | **Parent only** | Run real project build/tests. On green: `python3 <roadmap.py> check --plan <id> --step <n>`, then commit code + roadmap together. |

Prefer superpowers **`subagent-driven-development`** when installed — it is the same shape
(implement → spec review → quality review per task). Else use native subagents
(Grok: `spawn_subagent`; Claude: Task / subagents).

### Parallelism policy (quality over speed)

- **Do** parallelize: background `explore` while preparing the implementer prompt.
- **Do not** by default: multiple implementers on the same working tree.
- **Do not**: build multiple roadmap items in parallel (breaks depends / review narrative).
- **Do not**: skip steps 3–5 under `--auto`.
- Grok: only the parent spawns subagents (nesting depth 1). Watch kids with Ctrl+B.

If steps are *proven* file-disjoint and the user asked for speed, you may use
`isolation: worktree` implementers — but merge carefully and still run full reviews + tests
before each `check`. Default for `/roadmap-build … --auto` remains **serial implement + dual review**.

### When the item is done

- Optional: one item-level review against full plan scope.
- Without `--auto`: pause and report; wait for user before the next item.
- With `--auto`: one-line status, then the next unblocked selected item.

When the whole selection is 100%: if `--pr`, follow the PR gate; else suggest
`/roadmap:review` / `/roadmap-review` then `/roadmap:release` / `/roadmap-release`.

## `--worktree` — isolate the build

When `--worktree` is present, before building:

```
git worktree add ../<project>-v<version> -b roadmap/v<version>
```

(`<project>` and `<version>` from `status`). Run the **entire** selection inside that worktree.
Single-item builds may use `roadmap/<id>-<slug>` instead.

## `--pr` — open a PR, never merge

After selection hits 100%:

```
git push -u origin roadmap/v<version>
gh pr create --fill   # report URL; do not merge
```

## Fully hands-off harness (optional — only if `ralph-loop` is installed)

`--auto --worktree --pr` already loops inline with quality gates. **Only if** ralph-loop is
installed and you want a hard iteration cap, drive the same flow with it. If missing, ignore.

```
/ralph-loop:ralph-loop --completion-promise 'v<VERSION> DONE' --max-iterations <UNFINISHED+buffer> "Work inside git worktree ../<PROJECT>-v<VERSION> on branch roadmap/v<VERSION>. Loop until roadmap v<VERSION> is 100%: status, build next unblocked item with quality-first multi-agent protocol (implement + spec review + quality review per step; parent-only roadmap CLI; tests before check), commit code+roadmap. Never hand-edit ROADMAP.md. At 100%: push + gh pr create, DO NOT MERGE, then <promise>v<VERSION> DONE</promise>."
```

**Finding the CLI (`<roadmap.py>`) — do not search for it.**

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
