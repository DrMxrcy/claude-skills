---
name: roadmap
description: Use when planning features/bugs/refactors, tracking a project roadmap, breaking an idea or plan into trackable units, marking work done, or cutting a version. Maintains a versioned ROADMAP.md + .roadmap/ plan files via a deterministic CLI. Triggers on "roadmap", "plan this feature", "track this", "break this down", "mark done", "cut a version", "import into roadmap".
---

# Roadmap

A persistent tracking layer on top of your planning skills. You decide WHAT; the
`roadmap.py` CLI makes every mechanical edit so the dashboard never drifts.

**Always mutate state through the CLI — never hand-edit ROADMAP.md.** Run the CLI as
`python3 <path-to-this-skill>/scripts/roadmap.py <command>` from the target project root.

## Working guardrails (apply whenever this skill is active)
- At the start of a session, run `roadmap.py status` to orient on current progress before continuing.
- New features or found bugs become roadmap items (`/roadmap:plan`) before coding; park stray ideas in the Idea Incubator — nothing is built off-roadmap.
- One trackable item at a time. No multitasking across features/bugs.
- No functional code without an active plan file in `.roadmap/plans/`.
- Run the build/tests for a step BEFORE you `check` it.
- Commit code + roadmap updates together in one micro-commit.

## Phase routing
On invocation, detect state and pick a phase:

1. **No `.roadmap/` directory?** → Initialize.
   - If the repo already has code: `roadmap.py init --adopt --name "<name>"`, then survey
     existing structure (use codegraph/MCP if present, else Glob/Grep) and ingest any
     `TODO.md` / README roadmap / existing `ROADMAP.md` via `roadmap.py import <path>`.
   - Greenfield: `roadmap.py init --name "<name>"`.

2. **User brings an idea/plan** → Break it down.
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

3. **Working an item** → Execute.
   - Read the plan file. If it links a **Spec** or **Detailed plan** (e.g. paths under
     `docs/`), open and follow those as the authoritative implementation guide — the
     checklist is the tracking unit; the detailed plan has the how.
   - Lean on **superpowers `executing-plans`**.
   - After each step passes its test: `roadmap.py check --plan <id> --step <n>`, then
     commit code + roadmap together.

4. **A version's items are all done** → Review, then release.
   - Verify the phase against its specs + code-review the work (`/roadmap:review`) before
     shipping — confirm every item is genuinely implemented and matches its spec.
   - Confirm each completed item's **audience** (`roadmap.py audience --plan <id> --to
     public|internal`) and give every *public* item a clear user-facing `note`
     (`roadmap.py note --plan <id> --text "<plain-language summary>"`). `/roadmap:changelog`
     audits the version and warns about public items missing a note or worded internally.
   - Two changelogs render automatically on every `sync`: **`CHANGELOG.md`** (public — only
     `audience: public` items, from their `note` only, never the raw title; versions with
     internal-only work get one "behind-the-scenes" roll-up line) and
     **`CHANGELOG.internal.md`** (every item, title fallback — the full dev log). Items appear
     once they hit 100%, grouped by version. `release` is **optional** — use it to pin a new
     current version or `git tag` (`--tag`); it no longer owns the changelog. Run
     `roadmap.py changelog [--internal]` anytime to print the latest.

## Command reference
- `init [--name N] [--adopt]` — scaffold (adopt = existing repo, non-destructive)
- `new --type T --title "..." [--version V] [--note "..."] [--audience public|internal]` — scaffold + register a plan
- `note --plan ID --text "..."` — set an item's user-facing changelog line (lints public notes)
- `audience --plan ID --to public|internal` — route an item to the public or internal changelog
- `check --plan ID --step N [--undo] [--all-done]` — flip checkboxes
- `remove --plan ID` — archive a plan, drop it, demote it to the Idea Incubator
- `depends --plan ID --on IDS [--clear]` — set advisory dependency ordering
- `reorder --version V --order IDS` — set display/build order within a version
- `merge --into KEEP --from IDS` — fold duplicate items into one keeper
- `retarget --to V (--from VERS | --plan IDS)` — re-stamp items onto another version
- `sync` — recompute progress + re-render ROADMAP.md **and both changelogs** (safe anytime)
- `upgrade` — refresh this project's CLAUDE.md rules to the installed skill version
- `changelog [--internal] [--backfill]` — print the public (or `--internal`) changelog + audit warnings; `--backfill` dates past versions from git tags
- `release --version V [--tag] [--force]` — bump version (optional; changelog is automatic)
- `status [--json]` — print current state
- `import PATH` — extract checklist lines from a file into a plan

## Optional automation
A Stop hook (`hooks/roadmap-sync.sh`) can run `sync` automatically each session. It is
opt-in — see README. The CLI commands already `sync` after every mutation, so the hook is
only a safety net.
