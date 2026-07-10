# Example Project

Your own project notes and conventions live here (build/test commands, code style,
architecture pointers, etc.). The roadmap skill never touches this area.

The block below is what the roadmap skill adds — via `install.sh` or the first
`roadmap init` / `/roadmap:init` / `/roadmap-init`. It is inserted idempotently between the
`roadmap:rules` markers, so your content above and below is always preserved. The same
block is also written to `AGENTS.md` for agent-neutral readers (Grok, Codex, Cursor, …).

<!-- roadmap:rules:start -->
## Roadmap tracking
This project uses the **roadmap** skill so AI coders (Claude Code, Grok Build, and others) stay **on-task** and ship **high-quality** code — not ad-hoc thrash. The living source of truth is `ROADMAP.md` + `.roadmap/plans/` via the deterministic CLI.
- **Slash names:** Claude Code → `/roadmap:<cmd>` (e.g. `/roadmap:status`); Grok Build → `/roadmap-<cmd>` (e.g. `/roadmap-status`). Bare `/roadmap <cmd>` works on either.
- **Orient first:** at session start run `roadmap.py orient` or `/roadmap:status` / `/roadmap-status` (or read `ROADMAP.md`) before writing code.
- **Nothing off-roadmap:** new features/bugs become items via `/roadmap:plan` / `/roadmap-plan` before coding; park ideas with `/roadmap:idea` / `/roadmap-idea` (one bullet; long write-ups → linked `.roadmap/notes/`). Promote with `/roadmap:promote` / `/roadmap-promote`.
- **One item at a time.** Active plan in `.roadmap/plans/` required for functional code. No multitasking across features/bugs. Respect `dependsOn` (`roadmap.py next` skips blocked items).
- **Quality-first build (default for `/roadmap:build` / `/roadmap-build`, including `--auto`):** for each checklist step — optional explore research → one implementer subagent → **spec review** subagent → **quality review** subagent → parent runs real build/tests → only then `check` + **micro-commit code+roadmap immediately**. Parent owns all `roadmap.py` calls; children never edit `ROADMAP.md`. `--auto` skips user pauses between items, **not** reviews or tests. Prefer superpowers `subagent-driven-development` when available.
- **Specs are law:** follow each plan's linked Spec / Detailed plan; the checklist is the tracker, not the design.
- **Never hand-edit `ROADMAP.md`.** Use the CLI / `/roadmap:done` / `/roadmap-done`. If work happened outside the loop, `/roadmap:catchup` / `/roadmap-catchup` after verifying tests.
- **Multi-coder sync / rate limits:** the **git repo** is the shared brain — formal `handoff` is optional. Micro-commit after every checked step so a rate-limit mid-session loses at most one unfinished step. On any new agent (or after rate-limit): `git pull` if needed → `roadmap.py orient` or `handoff` (SessionStart orient also runs) → if dirty, commit or inspect → if drift, catchup after tests → continue `next`/`build` from the plan checklist. Never keep a private parallel plan in chat.
- **Ship clean:** before release, `/roadmap:review` / `/roadmap-review` the version (spec + code review).
<!-- roadmap:rules:end -->
