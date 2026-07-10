# Example Project

Your own project notes and conventions live here (build/test commands, code style,
architecture pointers, etc.). The roadmap skill never touches this area.

The block below is what the roadmap skill adds — via `install.sh` or the first
`roadmap init` / `/roadmap:init` / `/roadmap-init`. It is inserted idempotently between the
`roadmap:rules` markers, so your content above and below is always preserved. The same
block is also written to `AGENTS.md` for agent-neutral readers (Grok, Codex, Cursor, …).

<!-- roadmap:rules:start -->
## Roadmap tracking
This project tracks work in `ROADMAP.md` via the **roadmap** skill.
- **Slash names:** Claude Code → `/roadmap:<cmd>` (e.g. `/roadmap:status`); Grok Build and other flat-command agents → `/roadmap-<cmd>` (e.g. `/roadmap-status`). Bare `/roadmap <cmd>` also works on either.
- At the start of a work session, run `roadmap.py orient` or `/roadmap:status` / `/roadmap-status` (or read `ROADMAP.md`) before continuing.
- New features or found bugs become roadmap items via `/roadmap:plan` / `/roadmap-plan` before coding; park stray ideas in the Idea Incubator via `/roadmap:idea` / `/roadmap-idea` (one bullet each — long write-ups become linked `.roadmap/notes/` files, never inline prose) — nothing is built off-roadmap. Promote parked ideas with `/roadmap:promote` / `/roadmap-promote`.
- No functional code without an active plan in `.roadmap/plans/`. Work one checklist item at a time; do not multitask across features/bugs. Respect `dependsOn` — build dependencies first (`roadmap.py next` skips blocked items).
- When building an item, follow its linked Spec / Detailed plan as the authoritative how-to (the checklist is just the tracker).
- Mark a step done only after its build/tests pass, and commit the code + roadmap update together; if work was done outside the commands, run `/roadmap:catchup` / `/roadmap-catchup` to reconcile.
- Update status only through the roadmap CLI / `/roadmap:done` / `/roadmap-done`; never hand-edit `ROADMAP.md`.
<!-- roadmap:rules:end -->
