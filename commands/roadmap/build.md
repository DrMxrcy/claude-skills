---
description: Build a roadmap plan item, a whole version/phase, or the current version
argument-hint: <plan id | version | empty> [--auto] [--worktree] [--pr]
---

Implement roadmap work using the **roadmap** skill. Target: $ARGUMENTS

First run `python3 <roadmap.py> status` to see items, their versions, and progress, then
interpret the argument:
- A bare number (e.g. `3`) → that single plan item.
- A version (contains dots, e.g. `1.0.0`) → every incomplete item in that version (a whole phase).
- Empty → every incomplete item in the CURRENT version.
- `--auto` anywhere in the argument → build all selected items end-to-end **without** pausing
  for a checkpoint between items (still one item at a time, still tests-before-check). Without
  `--auto`, pause after each item (the default).
- `--worktree` → isolate the work in a git worktree before building (see below). Without it,
  build on the current branch (the default).
- `--pr` → when the selection reaches 100%, push and open a PR instead of stopping locally;
  **never merge to main** (see below).

These flags compose. `--auto --worktree --pr` on a version is the fully hands-off phase build:
isolate → loop the whole version → open a PR for review. They are agent-interpreted directives
(parsed from the argument here), not flags on the CLI.

Build the selected item(s) **one item at a time, in ascending id order**. For each item:
1. Read its plan file `.roadmap/plans/<id>-*.md` (Target Scope, Architectural Blueprint,
   Step-by-Step Checklist). If the plan links a **Spec** or **Detailed plan** (e.g. paths
   under `docs/superpowers/`), open and follow those as the authoritative implementation
   guide — the checklist is the tracking unit; the detailed plan has the how.
2. Execute its checklist step-by-step — prefer the superpowers `subagent-driven-development`
   skill (fresh subagent per step + review), else `executing-plans` (inline checkpoints),
   else implement directly with TDD. Build/tests MUST pass before a step is checked off.
3. After each passing step: `python3 <roadmap.py> check --plan <id> --step <n>`
   (auto-syncs `ROADMAP.md`), then commit code + roadmap together in one micro-commit.
4. When the item is complete: if `--auto` was given, report briefly and continue to the next
   item; otherwise **pause for a checkpoint** — report what shipped and let the user confirm
   before starting the next item.

When the version's items are all done: if `--pr` was given, follow the PR gate below;
otherwise run `status` and suggest `/roadmap:review` then `/roadmap:release <next version>`.

## `--worktree` — isolate the build

When `--worktree` is present, before building anything derive `<project>` (the project name
from `python3 <roadmap.py> status`) and `<version>` (the target version), then:

```
git worktree add ../<project>-v<version> -b roadmap/v<version>
```

and run the whole build **inside that worktree** so `main` is never touched. (For a single-item
build, name the branch after the item, e.g. `roadmap/<id>-<slug>`.)

## `--pr` — open a PR, never merge

When `--pr` is present, after the selection hits 100% and `status` confirms it: push the
branch and open a PR — but **DO NOT MERGE TO MAIN**. Wait for code review and automated tests.

```
git push -u origin roadmap/v<version>
gh pr create --fill   # then report the PR URL; do not merge
```

## Fully hands-off (optional — only if the `ralph-loop` plugin is installed)

`--auto --worktree --pr` already gives a hands-off phase build inline. **Only if** the
`ralph-loop` plugin is installed and you want a harness-enforced loop with a hard iteration
cap, drive the same flow with it instead. If it isn't installed, ignore this section.

First read `python3 <roadmap.py> status` for `<VERSION>` (target version), `<PROJECT>` (project
name → worktree path `../<PROJECT>-v<VERSION>`), and the **count of unfinished items in that
version** (→ `--max-iterations` = that count + a small buffer). Then emit (filling `<…>`; the
command may be invoked as `/ralph-loop` or, namespaced, `/ralph-loop:ralph-loop`):

```
/ralph-loop:ralph-loop --completion-promise 'v<VERSION> DONE' --max-iterations <UNFINISHED+buffer> "First: git worktree add ../<PROJECT>-v<VERSION> -b roadmap/v<VERSION> and work inside it. Loop until roadmap v<VERSION> is 100%: run /roadmap:status, build the next unfinished v<VERSION> item (one step, or fan out subagents), tests MUST pass, mark done via the roadmap CLI, commit code+roadmap together. Never hand-edit ROADMAP.md. When all v<VERSION> items hit 100%, push and gh pr create but DO NOT MERGE TO MAIN — wait for code review and automated tests — then output <promise>v<VERSION> DONE</promise>."
```

Each iteration advances the version; the loop stops when it hits 100% (you output the promise)
or `--max-iterations` is reached. The work lands on a `roadmap/v<version>` branch as a PR,
never direct to main.

The CLI lives at `.claude/skills/roadmap/scripts/roadmap.py` (project install) or
`~/.claude/skills/roadmap/scripts/roadmap.py` (global install).
