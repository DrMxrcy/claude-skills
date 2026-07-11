---
name: roadmap
description: >
  Keep AI coders (Claude Code, Grok Build, others) on-task while shipping high-quality code.
  Use when planning features/bugs/refactors, tracking a project roadmap, breaking work into
  trackable units, building with quality-first multi-agent review, marking done, or cutting a
  version. Maintains versioned ROADMAP.md + .roadmap/ via a deterministic CLI. Triggers on
  "roadmap", "plan this feature", "track this", "build the next item", "mark done", "cut a
  version", /roadmap, /roadmap-next, /roadmap-build, /roadmap-status.
argument-hint: "[status|next|build|plan|idea|init|done|review|release|sync|…] [args]"
---

# Roadmap

**Mission:** keep AI coders on-task and ship high-quality code — on Claude Code, Grok Build,
or any agent that loads this skill. Plans and checklists are the rails; subagent implement +
dual review is the default build quality bar; the CLI is the only way the dashboard moves.

A persistent tracking layer on top of your planning skills. You decide WHAT; the
`roadmap.py` CLI makes every mechanical edit so the dashboard never drifts.

**Always mutate state through the CLI — never hand-edit ROADMAP.md.** The `roadmap.py` CLI
ships with the skill under the host agent's skills dir (`.claude`, `.grok`, or `.agents` —
project-level or home) — **do not search or glob for it**; probe those fixed candidates.
Resolve it once and reuse `$RM` (run from the project root):

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
python3 "$RM" <command>
```

## Slash commands (agent-specific names)

| Action | Claude Code | Grok Build | Either |
|---|---|---|---|
| Init | `/roadmap:init` | `/roadmap-init` | `/roadmap init` |
| Plan | `/roadmap:plan …` | `/roadmap-plan …` | `/roadmap plan …` |
| Next item | `/roadmap:next` | `/roadmap-next` | `/roadmap next` |
| Build | `/roadmap:build …` | `/roadmap-build …` | `/roadmap build …` |
| Status | `/roadmap:status` | `/roadmap-status` | `/roadmap status` |
| (rest) | `/roadmap:<cmd>` | `/roadmap-<cmd>` | `/roadmap <cmd>` |

**When recommending a command to the user, always list hyphen (Grok) and/or bare form —
never colon-only.** Grok only discovers flat `commands/roadmap-*.md`; nested
`commands/roadmap/next.md` → `/roadmap:next` does **not** show in Grok's menu.
`--auto` only on **build** (not next).

**Also works:** invoke this skill with a subcommand as the argument — `/roadmap next`,
`/roadmap build 1.0.0`, `/roadmap status` — and route exactly like the dedicated command.

## Subcommand routing (when invoked as `/roadmap` with args)

If the user message / `$ARGUMENTS` starts with one of these verbs, run that flow and stop
(do not fall through to generic phase detection):

| First token | Do this |
|---|---|
| `status` | `roadmap.py status` (+ summarize) |
| `sync` | `roadmap.py sync` |
| `next` | Build the lowest-id unfinished item in the **current** version (same as `/roadmap-next`) |
| `handoff` | Multi-coder switch brief (sync state when leaving Claude for Grok or vice versa) |
| `build` | Build the rest of the args (id / version / empty / flags) — same as `/roadmap-build` |
| `plan` | Brainstorm remaining args into a tracked plan |
| `idea` | Park remaining args in the Idea Incubator |
| `init` | Initialize / adopt |
| `done` | Mark step/item done |
| `remove` / `retarget` / `review` / `release` / `changelog` / `catchup` / `reevaluate` / `tidy` / `upgrade` | Follow that command's flow |

If there are no args (bare `/roadmap`), use **Phase routing** below.

## Working guardrails (apply whenever this skill is active)
- At the start of a session, run `roadmap.py orient` / `handoff` (or status) before writing code.
- New features or found bugs become roadmap items (`/roadmap:plan`) before coding; park stray ideas in the Idea Incubator — nothing is built off-roadmap.
- **Incubator hygiene — ROADMAP.md stays skimmable.** One bullet per parked idea, added via
  `roadmap.py idea --title "..."`. Long-form content — brainstorm output, deferred review
  findings, phase sketches, option analyses — goes to a linked `.roadmap/notes/` file
  (`idea --body/--body-file`) or a spec under `docs/`, and gets ONE linked bullet; never
  paste prose walls into ROADMAP.md. `status` warns when the file outgrows these bounds;
  groom it back with `/roadmap:tidy` · `/roadmap-tidy` (`roadmap.py tidy` prints the
  report — the only sanctioned direct edit of the free-form region, never the auto region).
  The incubator itself may live in an external file (`settings.incubatorFile`, usually
  `.roadmap/IDEAS.md` via `tidy --externalize`) — the CLI resolves the location; groom
  and read ideas wherever it points.
- One trackable item at a time. No multitasking across features/bugs.
- No functional code without an active plan file in `.roadmap/plans/`.
- Run the build/tests for a step BEFORE you `check` it.
- Commit code + roadmap updates together in one micro-commit.

## Switching between AI coders (Claude ↔ Grok ↔ …)

The **git repo** is the shared brain — not chat history. **`handoff` is optional** (a
nicer brief). Rate limits, crashes, and hard kills usually mean you never ran it — that
is fine if you micro-committed along the way.

| Shared in git | Owner |
|---|---|
| `ROADMAP.md`, `.roadmap/`, `CHANGELOG*.md` | CLI only |
| Plan checklists / progress | CLI `check` |
| `CLAUDE.md` + `AGENTS.md` rules block | `init` / `upgrade` |

**Ideal leave (when you can):** micro-commit after each checked step; optional
`python3 "$RM" handoff` + push.

**Abrupt leave (rate limit / kill — no handoff):**

1. Open the other agent in the **same repo**.
2. `git status` — commit anything the previous agent left (code + roadmap if present).
3. `python3 "$RM" orient` or `handoff` (SessionStart orient often already ran).
4. Drift warning → `/roadmap-catchup` after tests for steps done but not checked.
5. Read the active plan’s **next unchecked step** — continue quality-first build.
   Do **not** re-derive the plan from the dead chat.

**Why this works:** every `check` + micro-commit moves truth into git. The dead session’s
context is disposable; unfinished work is either committed or still in the working tree.

Install both agents at the same skill version: `./install.sh --global --both`.

## Phase routing
On invocation, detect state and pick a phase:

1. **No `.roadmap/` directory?** → Initialize.
   - If the repo already has code: `roadmap.py init --adopt --name "<name>"`, then survey
     existing structure (use codegraph/MCP if present, else Glob/Grep) and ingest any
     `TODO.md` / README roadmap / existing `ROADMAP.md` via `roadmap.py import <path>`.
   - Greenfield: `roadmap.py init --name "<name>"`.

2. **User brings an idea/plan** → Break it down.
   - Not ready to build yet? Park it instead: `roadmap.py idea --title "<one-liner>"
     [--body-file <write-up>]` — one incubator bullet, long content in a linked notes file.
   - Classify **type**: feature | bug | refactor | chore (this picks the template).
   - Choose the **target version** by semver — type drives the bump:
     bug fix → **patch** (x.y.**Z**); backward-compatible feature → **minor** (x.**Y**.0);
     breaking change or a whole new phase → **major** (**X**.0.0). Assign with `--version`
     (omit to use the current version).
   - Research: use **context7** for library/API docs; use project **MCPs** (e.g. codegraph)
     for impact analysis. Degrade gracefully if unavailable.
   - Defer the deep design to **superpowers `brainstorming`/`writing-plans` if installed**;
     otherwise design inline.
   - `roadmap.py new --type <T> --title "<title>" [--version <V>] --note "<user-facing one-liner>" [--audience public|internal]`
     scaffolds the plan file; then fill in scope/blueprint/checklist (tiny testable steps).
     The `--note` is plain-language, benefit-focused (no vendor/tool names, file paths, or
     issue refs) — it becomes the **public** CHANGELOG / App Store "What's New" line.
     `--audience` routes the item: `public` → curated `CHANGELOG.md`, `internal` →
     `CHANGELOG.internal.md`. Omit it to take the type default (`feature`/`bug` → public,
     `refactor`/`chore` → internal) and override when judgment differs. The CLI auto-runs
     `sync` and warns if a public note reads internal.

3. **Working an item** → Execute (**quality-first multi-agent**).
   - Read the plan file. If it links a **Spec** or **Detailed plan** (e.g. paths under
     `docs/`), open and follow those as the authoritative implementation guide — the
     checklist is the tracking unit; the detailed plan has the how.
   - **Default protocol** (also used by `/roadmap-build … --auto`): one item at a time;
     per checklist step → optional `explore` research → **one** implementer subagent →
     **spec review** subagent → **quality review** subagent → parent runs real tests →
     only then `roadmap.py check` + commit. Parent owns all roadmap CLI; children never
     edit `ROADMAP.md`. Do **not** parallelize implementers on the same tree; `--auto`
     skips user pauses between items, **not** reviews. Full write-up:
     [`references/quality-build.md`](references/quality-build.md).
   - Prefer superpowers **`subagent-driven-development`** when installed; else native
     subagents (Grok `spawn_subagent`, Claude Task). Fallback: `executing-plans` or
     direct TDD with the same gates.
   - After each step passes its test: `roadmap.py check --plan <id> --step <n>`, then
     commit code + roadmap together.

4. **A version's items are all done** → Review, then release.
   - Verify the phase against its specs + code-review the work (`/roadmap:review`) before
     shipping — confirm every item is genuinely implemented and matches its spec.
   - Confirm each completed item's **audience** (`roadmap.py audience --plan <id> --to
     public|internal`) and give every *public* item a clear user-facing `note`
     (`roadmap.py note --plan <id> --text "<plain-language summary>"`). Items with a
     high-confidence internal tell (admin/operator, compliance, security-disclosure, SEO
     plumbing) **auto-route to the internal changelog** unless you explicitly set them public;
     softer wording tells only warn. `/roadmap:changelog` audits the version and reports
     auto-routings, public items missing a note, and notes worded internally.
   - Two changelogs render automatically on every `sync`: **`CHANGELOG.md`** (public — only
     `audience: public` items, from their `note` only, never the raw title; versions with
     internal-only work get one "behind-the-scenes" roll-up line) and
     **`CHANGELOG.internal.md`** (every item, title fallback — the full dev log). Items appear
     once they hit 100%, grouped by version. `release` is **optional** — use it to pin a new
     current version or `git tag` (`--tag`); it no longer owns the changelog. Run
     `roadmap.py changelog [--internal]` anytime to print the latest.
   - After `release` pins a newer current version, shipped versions **collapse to one
     summary line** on the dashboard (count + ship date + changelog pointer) — full detail
     stays in `CHANGELOG.internal.md` and `.roadmap/plans/`. Opt out with
     `settings.collapseShipped: false` in `.roadmap/config.json`.

## Command reference
- `init [--name N] [--adopt]` — scaffold (adopt = existing repo, non-destructive)
- `new --type T --title "..." [--version V] [--note "..."] [--audience public|internal]` — scaffold + register a plan
- `idea --title "..." [--body "..." | --body-file PATH]` — park an idea: one incubator bullet; a body becomes a linked `.roadmap/notes/` file
- `promote [--match T | --index N] [--type T] …` — lift an incubator bullet into a tracked plan
- `note --plan ID --text "..."` — set an item's user-facing changelog line (lints public notes)
- `audience --plan ID --to public|internal` — route an item to the public or internal changelog
- `check --plan ID --step N [--undo] [--all-done]` — flip checkboxes (+ records `last_seen_sha`)
- `next [--version V] [--force] [--json]` — next unfinished item (skips incomplete `dependsOn`)
- `deps-check --plan ID [--force]` — warn if dependencies are incomplete
- `remove --plan ID` — archive a plan, drop it, demote it to the Idea Incubator
- `depends --plan ID --on IDS [--clear]` — set dependency ordering (`next`/`build` honor it)
- `reorder --version V --order IDS` — set display/build order within a version
- `merge --into KEEP --from IDS` — fold duplicate items into one keeper
- `retarget --to V (--from VERS | --plan IDS)` — re-stamp items onto another version
- `orient [--json] [--hook]` — session orientation (project, progress, next item, drift)
- `handoff [--json]` — multi-coder switch brief (orient + git dirty + checklist)
- `drift-check` — nudge if commits landed without a check-off
- `tidy [--json] [--externalize [PATH]]` — report-only free-form/incubator hygiene analysis (long bullets, nested blocks, dupes vs tracked items, stray prose); `--externalize` moves the incubator into a linked external file (default `.roadmap/IDEAS.md`; `idea`/`promote`/`remove` follow via `settings.incubatorFile`); `/roadmap:tidy` applies the grooming + idea curation
- `sync` — recompute progress + re-render ROADMAP.md **and both changelogs** (safe anytime)
- `upgrade` — refresh this project's `CLAUDE.md` + `AGENTS.md` rules to the installed skill version
- `changelog [--internal] [--backfill]` — print the public (or `--internal`) changelog + audit warnings; `--backfill` dates past versions from git tags
- `release --version V [--tag] [--force]` — bump version (optional; changelog is automatic)
- `status [--json]` — print current state (shows `blocked by […]` when deps incomplete)
- `import PATH` — extract checklist lines from a file into a plan

## Optional automation
- **Stop** (`hooks/roadmap-sync.sh`): `sync` + `drift-check` each turn — safety net + catchup nudge.
- **SessionStart** (`hooks/roadmap-orient.sh`): injects current version + next item into context.
Both are opt-in via the installer (`--no-hook` / `--no-orient`). CLI mutations already `sync`.
