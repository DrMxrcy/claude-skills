---
description: Build (implement) a roadmap plan item, checking off steps as tests pass
argument-hint: <plan id>
---

Implement a roadmap plan item end to end using the **roadmap** skill: $ARGUMENTS

1. Read the plan file at `.roadmap/plans/<id>-*.md` — its Target Scope, Architectural
   Blueprint, and Step-by-Step Checklist. If no id was given, run
   `python3 <roadmap.py> status` and ask which item to build.
2. Honor the guardrails: work this ONE item only, one checklist step at a time.
3. Execute the checklist:
   - If the superpowers `subagent-driven-development` skill is available, use it (fresh
     subagent per step + review). Otherwise use `executing-plans` (inline with
     checkpoints). If neither is installed, implement each step directly with TDD.
   - Before checking a step off, its build/tests MUST pass.
4. After each passing step:
   `python3 <roadmap.py> check --plan <id> --step <n>` (auto-syncs `ROADMAP.md`),
   then commit the code and the roadmap update together in one micro-commit.
5. When every step is done, run `python3 <roadmap.py> status`. If the current version's
   items are all complete, suggest `/roadmap:release <next version>`.

The CLI lives at `.claude/skills/roadmap/scripts/roadmap.py` (project install) or
`~/.claude/skills/roadmap/scripts/roadmap.py` (global install).
