---
description: Build a roadmap plan item, a whole version/phase, or the current version
argument-hint: <plan id | version | empty> [--auto]
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

When the version's items are all done, run `status` and suggest
`/roadmap:release <next version>`.

The CLI lives at `.claude/skills/roadmap/scripts/roadmap.py` (project install) or
`~/.claude/skills/roadmap/scripts/roadmap.py` (global install).
