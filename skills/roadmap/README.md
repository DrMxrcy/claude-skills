# roadmap

A persistent tracking layer for AI-assisted development. You bring an idea or plan; the skill
breaks it into small, type-tagged, **versioned** units, links them into a living `ROADMAP.md`,
and keeps that dashboard in sync as code gets written — across many sessions.

It's a layer **on top of** your planning skills: it defers deep design to
`brainstorming`/`writing-plans`, uses `context7` and project MCPs for research, and a
deterministic Python CLI makes every mechanical edit so the dashboard never drifts.

> Install via the repo root [`install.sh`](../../README.md#install). After installing, start a
> fresh Claude Code session so the skill and `/roadmap:*` commands load.

## The loop

```
/roadmap:init                 # set up tracking (auto-adopts an existing repo)
/roadmap:plan <idea>          # brainstorm an idea into a tracked, versioned plan
/roadmap:build <id|version>   # implement an item or a whole phase, checking off as tests pass
/roadmap:review <version>     # verify a finished phase against its specs + code review
/roadmap:release <version>    # optional: pin a new version / git-tag (changelog is automatic)
```

`CHANGELOG.md` is rendered automatically on every sync — each item shows up once it hits
100%, grouped by its version. You don't need `/roadmap:release` to get a changelog.

`/roadmap:next` builds the next unfinished item in the current version. `/roadmap:status`
shows progress anytime; `/roadmap:sync` re-renders the dashboard.

For an **unattended phase build**, `/roadmap:build <version> --auto` runs items back-to-back
without checkpoints. If you have the [`ralph-loop`](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum)
plugin, you can drive it as a harness-enforced loop with a `--max-iterations` safety cap —
see the autonomous section in [`commands/roadmap/build.md`](../../commands/roadmap/build.md).

## Slash commands

| Command | Does |
|---|---|
| `/roadmap:init` | Initialize tracking (auto-detects adopt for existing repos) |
| `/roadmap:plan <idea>` | Brainstorm an idea into a tracked, versioned plan; links its spec/detailed plan |
| `/roadmap:build [id\|version] [--auto]` | Build one item, a whole version/phase, or the current version — step-by-step, tests before each check; `--auto` skips per-item checkpoints |
| `/roadmap:next` | Build the next unfinished item in the current version |
| `/roadmap:catchup [id]` | Reconcile the roadmap with work done outside the commands (checks off completed steps) |
| `/roadmap:status` | Show versions, items, types, and progress |
| `/roadmap:done <id> [step]` | Mark a step/item done and resync |
| `/roadmap:remove <id>` | Remove a tracked item — archive its plan, demote it to the Idea Incubator |
| `/roadmap:retarget --to V (--from VERS \| --plan IDS)` | Re-stamp items onto another version (e.g. consolidate shipped work into one release on a branch) |
| `/roadmap:review [version]` | Verify a finished phase against its specs + code review before release |
| `/roadmap:release <version>` | Optional: pin a new current version / `git tag` (changelog is automatic) |
| `/roadmap:changelog [version]` | Print the live changelog; backfill past versions' dates from git tags / notes from history |
| `/roadmap:reevaluate [version]` | Audit the codebase against the roadmap — surface missed/duplicate/stale work and resequence |
| `/roadmap:sync` | Recompute progress and re-render `ROADMAP.md` |

The CLI also has `version` (prints the installed skill version, e.g. to confirm an update applied).

## Command reference (in depth)

The three reconcilers are easy to confuse, so here is the precise division of labour:
**`sync`** only re-renders from existing checkboxes (never reads your code). **`catchup`**
reads your code to check off steps of items that *already exist*. **`reevaluate`** audits
the whole roadmap against the codebase and *reorganizes* it (adds missed items, merges
dupes, flags stale work, resequences). Use the one that matches the drift you have.

### Setup & planning

- **`/roadmap:init`** — Sets up tracking in the current project: creates `.roadmap/`
  (`config.json` + `plans/`), a `ROADMAP.md` with managed markers, and adds the rules
  block to `CLAUDE.md`. On an existing repo it auto-adopts (detects the current version
  from `package.json`/`pyproject.toml`/git tags). Idempotent — safe to re-run; existing
  items and version are preserved.
- **`/roadmap:plan <idea>`** — Turns a raw idea into a tracked, versioned item. Brainstorms
  scope, classifies the **type** (`feature`/`bug`/`refactor`/`chore`) and **version** (the
  semver bump), researches as needed, then runs `new` to create the plan file with a
  step-by-step checklist. If it produces a spec or detailed plan, those are saved under
  `docs/` and linked at the top of the plan so `build` can follow them.

### Building

- **`/roadmap:build [id|version] [--auto]`** — The workhorse. A bare **id** builds that one
  item; a **version** (e.g. `1.0.0`) builds every incomplete item in that phase; **empty**
  builds the current version. Works one checklist step at a time, requires build/tests to
  pass before checking a step off, and commits code + roadmap together. Without `--auto`
  it pauses for a checkpoint after each item; `--auto` runs the whole selection back-to-back.
- **`/roadmap:next`** — Builds just the next unfinished item in the current version (the
  lowest-id item that isn't 100%). Equivalent to one item of a `build` run.
- **`/roadmap:done <id> [step]`** — Manually mark a step (or a whole item, if no step given)
  complete and resync. The quick path when you finished something by hand and just need the
  dashboard to reflect it.

### Reconciling drift

- **`/roadmap:sync`** — Recomputes progress from the plan checkboxes and re-renders the
  managed region of `ROADMAP.md`. Pure view refresh; never inspects source code. Runs
  automatically after every mutation and via the optional Stop hook.
- **`/roadmap:catchup [id]`** — For work done *outside* the commands: reads the code and git
  history for the targeted (or current-version) items and checks off the steps that are
  genuinely implemented. Reconciles **progress** of items that already exist.
- **`/roadmap:reevaluate [version]`** — The structural audit. Scans the codebase + git
  history and produces an **advisory** report of: missed/untracked work, done-but-untracked
  features, **duplicates/overlap**, stale/obsolete items, gaps, and sequencing problems.
  After you approve, it applies changes via the CLI only — `new`, `check`, `depends`,
  `reorder`, and `merge` — and never auto-deletes a plan. Run it periodically as the backlog
  grows.

### Status, shipping & sharing

- **`/roadmap:status`** — Prints the project, current version, and every item with its type
  and progress. The fast orientation command at the start of a session.
- **`/roadmap:review [version]`** — Before releasing, verifies a finished phase against its
  linked specs and does a code review, so you cut a version only when the work truly matches
  the plan.
- **`/roadmap:remove <id>`** — Removes a tracked item the clean way: archives its plan to
  `.roadmap/archive/`, drops it from the registry, clears any dependency on it, and leaves a
  `- (was #id) title` breadcrumb under the Idea Incubator. The recoverable alternative to
  hand-editing `config.json`. (To consolidate two items instead of dropping one, use `merge`.)
- **`/roadmap:release <version>`** — **Optional.** Pins a new current version and can `git tag`
  it. **Guarded**: refuses if the current version still has incomplete items (`--force` to
  override). It no longer writes the changelog — that's automatic (see below).
- **`/roadmap:changelog [version]`** — Prints the live `CHANGELOG.md`. `--backfill` dates past
  versions from their `git tag v<ver>`; you can also reconstruct missing notes from git history.

## CLI

The commands drive a deterministic CLI you can also run directly:

```bash
roadmap=.claude/skills/roadmap/scripts/roadmap.py   # or ~/.claude/skills/roadmap/scripts/roadmap.py
python3 $roadmap init [--name N] [--adopt] [--no-claude-md]
python3 $roadmap new --type feature|bug|refactor|chore --title "..." [--version V] [--note "..."]
python3 $roadmap note --plan ID --text "user-facing summary"
python3 $roadmap check --plan ID --step N [--undo] [--all-done]
python3 $roadmap status [--json]
python3 $roadmap sync
python3 $roadmap changelog [--backfill]                     # print the live changelog; --backfill dates past versions from git tags
python3 $roadmap remove --plan ID                           # archive + drop an item, demote to Incubator
python3 $roadmap depends --plan ID --on 2,5 [--clear]       # advisory dependency ordering
python3 $roadmap release --version V [--tag] [--force]      # optional version pin / git tag
python3 $roadmap reorder --version V --order 3,1,2          # explicit item order within a version
python3 $roadmap merge --into KEEP_ID --from 2,5            # combine duplicate items into one
python3 $roadmap retarget --to 1.0.0 --from 1.3.0,1.6.0    # re-stamp items onto another version
python3 $roadmap import PATH
python3 $roadmap version
```

`reorder`, `merge`, and `depends` are the verbs `/roadmap:reevaluate` uses to resequence and
dedupe: `reorder` sets an explicit order for items in a version (the dashboard renders by that
order, falling back to id order); `merge` folds the source items' checklist steps into the
keeper, deletes the source plans, and retargets any dependencies onto the keeper; `depends`
records advisory ordering (`dependsOn`) that merge/remove keep consistent. `remove` archives a
single item and demotes it to the Idea Incubator. `retarget` changes the *version* of existing
items — select by `--from <versions>` or `--plan <ids>` — to consolidate shipped work into one
release (do it on a branch; the CLI edits roadmap state, not git).

## Versioning & changelog (user-facing)

- **Semver picks the version**: bug fix → patch (`x.y.Z`), backward-compatible feature →
  minor (`x.Y.0`), breaking change or a whole new phase → major (`X.0.0`). A *phase* is just
  a version; type (`bug`/`feature`/…) is set per item. `/roadmap:plan` classifies both.
- Each item carries a plain-language **`note`** (set at `new --note` or later via `note`).
- `CHANGELOG.md` is **rendered automatically on every `sync`** from the item registry, grouped
  into **✨ New / 🐛 Fixed / ⚡ Improved** using each item's note (falling back to its title). An
  item appears once it hits 100%; its version's heading is dated once *all* the version's items
  are complete (the date is persisted so re-renders are stable). In-progress versions show
  `(in progress)` with `(pending)` lines. The latest section is ready to paste into the
  **App Store "What's New"** or a website changelog — no `release` step required.
- `release` is **optional and guarded** — it only pins a new current version / `git tag` and
  refuses an incomplete version (`--force` to override). It does not write the changelog.

## How it works (anti-drift)

State lives in the target project:

```
ROADMAP.md          # human-readable dashboard (rendered view)
.roadmap/
├── config.json     # project, current version, next id, item registry
└── plans/NNN-*.md  # one plan per item: frontmatter + checklist of tiny steps
CHANGELOG.md        # rendered on every sync from the item registry (per version)
```

- **Plan files** are the source of truth for progress (the checklist).
- **`config.json`** is the source of truth for ids, current version, and the item registry.
- **`ROADMAP.md`** is regenerated by `sync` between the `<!-- roadmap:auto:start -->` /
  `<!-- roadmap:auto:end -->` markers. Everything outside (your **Idea Incubator** / backlog)
  is free-form and never touched. The model never hand-maintains the dashboard, so it can't
  drift. Full schema: [`references/state-model.md`](references/state-model.md).

**Tags** = the `type` field (feature/bug/refactor/chore). **Milestones** = `version`; a
phase is just a version (`v1.0.0`), so `/roadmap:build 1.0.0` builds the whole phase.

## Project rules (CLAUDE.md)

`init` and the installer add a small, idempotent rules block to your project's `CLAUDE.md`
(creating it if absent) so the discipline applies in every session — see
[`example/CLAUDE.md`](example/CLAUDE.md). It tells Claude to check status at session start,
work one item at a time, keep an active plan, and update only through the CLI. Opt out with
`--no-claude-md`.

## Auto-sync hook

The installer wires an opt-in Stop hook (`hooks/roadmap-sync.sh`) into `settings.json` that
runs `sync` each session as a safety net. The CLI already syncs after every mutation, so the
hook is belt-and-suspenders. Skip it with `--no-hook`.

## Plans link their detail

When `plan` produces a spec or detailed plan (via `writing-plans`), it saves them under
`docs/` and links them at the top of the plan file. `build`, `next`, and the skill's execute
phase follow those links as the authoritative how-to — the checklist stays the tracking unit.
