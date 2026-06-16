---
description: Initialize roadmap tracking in this project (auto-detects existing repo for adopt mode)
---

Set up roadmap tracking in this project using the **roadmap** skill.

If the project already has code (a `package.json`/`pyproject.toml`, source files, or git
history), use **adopt** mode so the starting version is seeded from the project and any
existing `TODO.md`/`README` roadmap is ingested non-destructively. Otherwise initialize
greenfield.

The CLI lives at `.claude/skills/roadmap/scripts/roadmap.py` (project install) or
`~/.claude/skills/roadmap/scripts/roadmap.py` (global install):

- Greenfield: `python3 <path> init --name "<project name>"`
- Existing repo: `python3 <path> init --adopt --name "<project name>"`

Then confirm `ROADMAP.md` and `.roadmap/` were created and show the result.
