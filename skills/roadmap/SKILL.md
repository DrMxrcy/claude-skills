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
   - `roadmap.py new --type <T> --title "<title>" [--version <V>] --note "<user-facing one-liner>"`
     scaffolds the plan file; then fill in scope/blueprint/checklist (tiny testable steps).
     The `--note` is plain-language, benefit-focused — it becomes the user-facing CHANGELOG /
     App Store "What's New" line. The CLI auto-runs `sync`.

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
   - Ensure every completed item has a clear user-facing `note` (set/fix with
     `roadmap.py note --plan <id> --text "<plain-language summary>"`) so the generated
     `CHANGELOG.md` reads for end users, not developers.
   - The user-facing `CHANGELOG.md` is rendered automatically on every `sync` (each item
     appears once it hits 100%, grouped by its version). `release` is **optional** — use it
     only to pin a new current version or create a `git tag` (`--tag`); it no longer owns the
     changelog. Run `roadmap.py changelog` anytime to print the latest.

## Command reference
- `init [--name N] [--adopt]` — scaffold (adopt = existing repo, non-destructive)
- `new --type T --title "..." [--version V] [--note "..."]` — scaffold + register a plan
- `note --plan ID --text "..."` — set an item's user-facing changelog line
- `check --plan ID --step N [--undo] [--all-done]` — flip checkboxes
- `remove --plan ID` — archive a plan, drop it, demote it to the Idea Incubator
- `depends --plan ID --on IDS [--clear]` — set advisory dependency ordering
- `reorder --version V --order IDS` — set display/build order within a version
- `merge --into KEEP --from IDS` — fold duplicate items into one keeper
- `retarget --to V (--from VERS | --plan IDS)` — re-stamp items onto another version
- `sync` — recompute progress + re-render ROADMAP.md **and CHANGELOG.md** (safe anytime)
- `upgrade` — refresh this project's CLAUDE.md rules to the installed skill version
- `changelog [--backfill]` — print the live changelog; `--backfill` dates past versions from git tags
- `release --version V [--tag] [--force]` — bump version (optional; changelog is automatic)
- `status [--json]` — print current state
- `import PATH` — extract checklist lines from a file into a plan

## Optional automation
A Stop hook (`hooks/roadmap-sync.sh`) can run `sync` automatically each session. It is
opt-in — see README. The CLI commands already `sync` after every mutation, so the hook is
only a safety net.
