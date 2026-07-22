<!-- roadmap:rules:start -->
## Roadmap tracking
This project uses the **roadmap** skill so AI coders (Claude Code, Grok Build, and others) stay **on-task** and ship **high-quality** code — not ad-hoc thrash. Living truth is **git**: `ROADMAP.md` + `.roadmap/` (plans, config) + `CHANGELOG*.md` via the deterministic CLI only.

### Surfaces (every agent)
- **Use the host agent's native invocation:**
  - Claude Code discovers **colon**: `/roadmap:status`, `/roadmap:build`, `/roadmap:next`
  - Grok Build discovers **hyphen only**: `/roadmap-status`, `/roadmap-build`, `/roadmap-next`
  - OpenAI Codex invokes the skill: `$roadmap status`, `$roadmap build 3`, `$roadmap next` (Codex's slash-command list is fixed; installed skills do not add `/roadmap-*` commands)
  - Bare space form works on Claude/Grok: `/roadmap status`, `/roadmap build 3`, `/roadmap next`
  - **Never tell a Grok user only `/roadmap:…`** — those do not appear in Grok's slash menu. Prefer writing `/roadmap:build` **·** `/roadmap-build` (or the bare form).
- **`--auto` is only for build** (item/version/empty selection), e.g. `/roadmap-build 1.2.0 --auto`, `/roadmap build 80 --auto`, or `$roadmap build 80 --auto`. **`next` has no `--auto`** — it always does exactly one item then stops. To chain items use `build` with `--auto`, not `next --auto`.
- **CLI resolve once:** probe `.claude|.grok|.agents` skills paths (project then `$HOME`); never hand-edit `ROADMAP.md`.

### Always on-task
- **Orient first:** at session start run `roadmap.py orient` (or the host's roadmap status invocation, or read `ROADMAP.md`) before writing code. SessionStart orient may inject this automatically.
- **Nothing off-roadmap:** features/bugs → `/roadmap:plan` / `/roadmap-plan` before coding; park ideas with `/roadmap:idea` / `/roadmap-idea` (one bullet; long write-ups → linked `.roadmap/notes/`). Promote with `/roadmap:promote` / `/roadmap-promote`.
- **Incubator hygiene:** the Idea Incubator may live in `ROADMAP.md` or an external file (`settings.incubatorFile`, usually `.roadmap/IDEAS.md`) — the CLI resolves it; never hardcode the location. When it gets messy, groom with `/roadmap:tidy` / `/roadmap-tidy` (prose → notes files, curate ideas vs the roadmap; `tidy --externalize` moves it out of `ROADMAP.md`).
- **One item at a time.** Active plan in `.roadmap/plans/` required for functional code. No multitasking across features/bugs. Respect `dependsOn` (`roadmap.py next` skips blocked items).
- **Specs are law:** follow each plan's linked Spec / Detailed plan; the checklist is the tracker, not the design.

### Quality-first build (default for `/roadmap:build` / `/roadmap-build`, including `--auto`)
- Per checklist step: optional **explore** research → **one** implementer subagent → **spec review** subagent → **quality review** subagent → parent runs real build/tests → only then `roadmap.py check` → **micro-commit code+roadmap immediately** (one commit per checked step).
- **Parent owns all `roadmap.py` calls**; children never edit `ROADMAP.md` or run `check`.
- **No parallel implementers** on the same working tree by default (conflicts hide bugs).
- **`--auto`** skips *user* pauses between items only — **never** skip reviews or tests.
- Prefer superpowers `subagent-driven-development` when available; else native subagents (Grok `spawn_subagent`, Claude Task).

### Multi-coder sync & rate limits
- **Git is the shared brain** across Claude ↔ Grok ↔ any agent. Chat memory is not a plan.
- **Formal `handoff` is optional.** Rate limits, crashes, and killed sessions are normal.
- **Micro-commit after every successful `check`** so a rate-limit loses at most the in-flight step, never a whole item.
- **Abrupt switch / resume (no prior handoff):** open the other agent in the same repo → `git status` (commit any left code+roadmap) → `roadmap.py orient` or `handoff` (SessionStart orient counts) → if drift, `/roadmap:catchup` / `/roadmap-catchup` after tests → continue from the **next unchecked plan step** via `/roadmap:next` / `/roadmap-next` or build. Do **not** re-derive the plan from the dead chat.
- **Ideal leave (when you can):** after a checked step commit is already done; optional `roadmap.py handoff` + `git push`.
- **Never** maintain a private parallel plan outside `.roadmap/`.

### Integrity
- **Never hand-edit `ROADMAP.md`.** Use CLI / `/roadmap:done` / `/roadmap-done`.
- **Catchup** only after verifying tests for steps done outside the loop.
- **Ship clean:** before release, `/roadmap:review` / `/roadmap-review` (spec + code review); curate public notes via changelog/audience.
<!-- roadmap:rules:end -->
