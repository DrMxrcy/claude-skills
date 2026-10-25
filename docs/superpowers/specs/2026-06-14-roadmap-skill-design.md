# Roadmap Skill — Design Spec

**Date:** 2026-06-14
**Status:** Approved design → ready for implementation plan
**Repo:** `claude-skills` (multi-skill repo; `roadmap` is skill #1)

## 1. Purpose

A persistent, local **roadmap tracking + planning** skill for AI-assisted coding. The
developer arrives with an idea or rough plan; the skill researches it, breaks it into
small trackable units, tags them by type, links them into a versioned roadmap, and keeps
that roadmap in sync as code gets written — across many sessions ("chats").

It is a **persistent tracking layer on top of** existing planning skills. It does NOT
re-implement deep design. It defers the thinking to superpowers `brainstorming` /
`writing-plans`, uses `context7` for library docs and project MCPs (e.g. codegraph) for
impact analysis, then captures the result into durable, versioned roadmap artifacts.

### Why the previous bash script failed
The original approach wrote a root `CLAUDE.md` with passive instructions ("update the
checkbox", "micro-commit") and relied on the model **remembering** to follow them every
turn. That always drifts. This design fixes it two ways:
1. **Deterministic scripts** do the mechanical edits (flip checkbox, recompute %, bump
   version) instead of the model hand-editing markdown.
2. **The dashboard is a rendered view**, regenerated from source-of-truth files — the
   model never hand-maintains it, so it cannot drift.

## 2. Scope

**In scope (this spec):**
- The `roadmap` skill: `SKILL.md` + `roadmap.py` CLI + templates + optional Stop hook.
- Greenfield `init` AND **adopt mode** for importing into existing repos.
- Multi-skill-ready repo structure installable via `npx skills add DrMxrcy/claude-skills`.

**Out of scope (YAGNI for now):**
- Other skills in the repo (structure supports them; none built yet).
- A separate status-label taxonomy beyond `type` + derived progress status.
- Remote/issue-tracker sync (GitHub issues, Jira). May reuse `gh` opportunistically but
  not a requirement.

## 3. Repo structure (the skill source)

```
claude-skills/
├── README.md
├── .claude-plugin/plugin.json        # marketplace compatibility (optional)
└── skills/
    └── roadmap/
        ├── SKILL.md                  # routes phases; embeds working guardrails
        ├── scripts/
        │   └── roadmap.py            # single CLI, subcommands (Python 3 stdlib only)
        ├── templates/
        │   ├── ROADMAP.md
        │   ├── feature-plan.md
        │   ├── bug-investigation.md
        │   └── refactor-debt.md
        ├── hooks/
        │   └── roadmap-sync.sh        # optional Stop hook (opt-in, documented)
        └── references/
            └── state-model.md         # full schema + file formats (progressive disclosure)
```

- **Discovery:** the skills CLI walks `skills/<name>/SKILL.md`. Future skills add siblings.
- **Language:** scripts are **Python 3, stdlib only** (no pip). Pre-installed on macOS;
  reliable for markdown/JSON editing and progress math.

## 4. State the skill maintains in a TARGET project

```
ROADMAP.md            # human-readable dashboard, at repo root
.roadmap/
├── config.json       # project name, current version, next id, item registry, settings
└── plans/
    ├── 001-auth-setup.md
    └── 002-fix-login-bug.md
```

### Source-of-truth model (anti-drift)
- **Plan files** = source of truth for per-item **progress** (the checklist).
- **`config.json`** = source of truth for **ids, current version, item registry**.
- **`ROADMAP.md`** = a **rendered view**. The machine-managed region lives between
  `<!-- roadmap:auto:start -->` and `<!-- roadmap:auto:end -->` and is **regenerated** by
  `roadmap.py sync`. Content **above** the markers (e.g. "Idea Incubator" / backlog) is
  free-form and never touched by scripts.

### Plan file format
```markdown
---
id: 003
title: Auth setup
type: feature           # feature | bug | refactor | chore
version: 0.1.0          # target version (milestone)
status: active          # DERIVED from checkboxes: backlog|planned|active|done
created: 2026-06-14
---

# Plan 003: Auth setup
> Type: feature · Target: v0.1.0

## Target Scope & Boundaries
- Core objective: ...
- Out of scope: ...

## Architectural Blueprint
- Files to create / modify / schema / downstream impact

## Step-by-Step Checklist
- [ ] Step 1: ... -> target: path
- [ ] Step 2: ... -> target: path
```

- `status` is **derived** by `sync`: no steps checked → `planned` (or `backlog` if not yet
  assigned a version); some checked → `active`; all checked → `done`. It is written back
  into frontmatter for human readability but always recomputed from checkboxes.
- **Tagging** = the `type` field (feature/bug/refactor/chore). Milestone = `version`.
  No separate manual status taxonomy (honors decision: type-based tagging + versioning).

### config.json shape
```json
{
  "project": "My Project",
  "currentVersion": "0.1.0",
  "nextId": 4,
  "items": [
    { "id": 1, "slug": "auth-setup", "title": "Auth setup",
      "type": "feature", "version": "0.1.0", "file": "plans/001-auth-setup.md" }
  ],
  "settings": { "autoCommit": true, "gitTagOnRelease": false }
}
```

## 5. `roadmap.py` subcommands (deterministic core)

All commands are idempotent where possible and print machine-readable + human-readable
output. They operate on `.roadmap/` relative to the current repo root (located by walking
up to the nearest `.roadmap/` or git root).

| Command | Behavior |
|---|---|
| `init [--name NAME] [--adopt]` | Scaffold `ROADMAP.md` + `.roadmap/`. Greenfield seeds `v0.0.1`. `--adopt` seeds version from `package.json`/`pyproject.toml`/latest git tag and leaves room for imported items. |
| `new --type T --title "..." [--version V]` | Allocate `nextId`, scaffold plan file from the matching template, register in `config.json`. Prints new file path. Does NOT fill in plan content (the skill/model does that). |
| `check --plan ID --step N [--undo]` | Flip exactly one checkbox in a plan file. `--all-done` marks every step. |
| `sync` | Recompute each item's % from checkboxes, recompute per-version rollup %, recompute derived `status`, regenerate the `ROADMAP.md` managed region. Idempotent. |
| `release --version V [--tag]` | Mark `currentVersion` complete in the rollup, set `currentVersion = V`, optional `git tag`. |
| `status [--json]` | Print versions, items, %s, grouped by type. `--json` for machine use. |
| `import` | Helper for adopt mode: parse an existing planning file (path arg) or stdin into one-or-more plan files (see §6). |

**Failure behavior:** commands validate inputs (e.g. unknown `--plan` id) and exit non-zero
with a clear message; they never partially corrupt files (write to temp, then atomic
rename). `sync` is safe to run anytime.

## 6. Adopt / import mode (existing repos)

`init --adopt` is the entry point when the repo already has code.

1. **Detect & seed version:** read `package.json` `version`, `pyproject.toml`, or latest
   `git tag`; use it as `currentVersion` (fallback `v0.0.1`).
2. **Survey the codebase:** the SKILL.md instructs the model to understand existing
   structure — using project MCPs (codegraph) or Glob/Grep — before proposing items. The
   script does not analyze code; it only scaffolds.
3. **Ingest existing planning artifacts (optional):** if the user has a plan file, or the
   repo has `TODO.md` / a roadmap section in `README.md` / an existing `ROADMAP.md`, the
   model parses it and calls `roadmap.py new ...` per discovered unit, then fills each plan
   file. `roadmap.py import <path>` assists by extracting checklist-shaped lines.
4. **Non-destructive:** if a `ROADMAP.md` already exists, adopt **preserves** it above the
   managed markers (moves existing content into the free-form region) rather than
   overwriting. Never clobbers existing files without surfacing it first.

## 7. SKILL.md behavior (phase routing + integration)

On invocation the skill detects state and routes:

- **No `.roadmap/`** → run `init` (ask greenfield vs `--adopt` if the repo has code).
- **User brings an idea/plan** → classify `type` → **research** (context7 for libs;
  project MCPs for impact) → **defer deep design to `brainstorming`/`writing-plans` if
  installed** → `new` to scaffold the plan file → fill it → `sync`.
- **Working an item** → lean on `executing-plans`; after each step: `check` → `sync` →
  micro-commit (if `autoCommit`).
- **A version's items all `done`** → propose `release` and bump to next version.

**Graceful degradation:** every integration (superpowers skills, context7, MCPs, `gh`) is
optional. If absent, the skill does the equivalent inline and continues.

**Working guardrails (embedded in SKILL.md, not a passive CLAUDE.md):** one trackable item
at a time; no functional code without an active plan file; run tests for a step before
`check`-ing it; commit code + roadmap updates together.

## 8. Optional Stop hook

`hooks/roadmap-sync.sh` runs `roadmap.py sync` on session Stop so the dashboard never drifts
even if the model forgets a `sync`. **Opt-in**: README documents adding it to
`settings.json`; not auto-installed. It is a safety net, not the primary mechanism.

## 9. Testing strategy

- **`roadmap.py`** — unit tests (TDD) on a temp dir fixture: init (greenfield + adopt),
  new (id allocation, template selection), check (flip/undo, idempotency), sync (progress
  math, managed-region regeneration, preserves free-form region), release (version bump),
  import (extracts checklist lines), atomic writes / error on bad input.
- **Skill** — verify end-to-end against a scratch repo: a greenfield walkthrough and an
  adopt walkthrough, asserting the rendered `ROADMAP.md` matches expectations.

## 10. Deliverables

1. Repo plumbing: `README.md`, `.claude-plugin/plugin.json`.
2. `skills/roadmap/SKILL.md` (phase routing + guardrails + integration).
3. `skills/roadmap/scripts/roadmap.py` (+ tests).
4. Templates: `ROADMAP.md`, `feature-plan.md`, `bug-investigation.md`, `refactor-debt.md`.
5. `hooks/roadmap-sync.sh` + opt-in docs.
6. `references/state-model.md` (full schema).
```
