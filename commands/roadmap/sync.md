---
description: Recompute progress and re-render ROADMAP.md from the plan files
---

Run `python3 .claude/skills/roadmap/scripts/roadmap.py sync` (or the global path) to
recompute progress from the plan files and re-render the managed region of `ROADMAP.md`.

Use this if the dashboard looks stale or after editing plan files by hand. It only rewrites
the region between the `roadmap:auto` markers — the Idea Incubator and other free-form
content are left untouched.
