---
description: Mark a roadmap step or item as done and resync the dashboard
argument-hint: <plan id> [step number]
---

Mark progress on a roadmap item: $ARGUMENTS

Before marking a step done, make sure its tests/build pass. Then flip the checkbox via the
roadmap CLI (it auto-syncs the dashboard):

- One step: `python3 <roadmap.py> check --plan <id> --step <n>`
- Whole item: `python3 <roadmap.py> check --plan <id> --all-done`
- Undo: add `--undo`

After updating, commit the code and the roadmap changes together in one micro-commit.
