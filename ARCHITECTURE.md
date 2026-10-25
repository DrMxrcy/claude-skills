# Architecture

## What this repo is
`claude-skills` is a collection of installable [Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview). It is not a web app or a service. The product is the files under `skills/`, `commands/` and `agy-plugin/` / `codex-plugin/`, delivered by `install.sh` into a target project or global agent directory.

## Stack
- **Language:** Python 3, standard library only. No third-party dependencies.
- **Shell:** `install.sh` (bash, `set -euo pipefail`) and hook scripts (`*.sh`).
- **Tests:** pytest, one `tests/test_<name>.py` per skill or installer concern, shared fixtures in `tests/conftest.py`.
- **Dashboard:** a single self-contained `dashboard.html` (vanilla JS, no build step), served by `rmlib/dashboard.py`.

## Folders
```
skills/<name>/          SKILL.md (agent-loaded), README.md, VERSION, scripts/, templates/, references/, hooks/
skills/roadmap/scripts/roadmap.py     CLI entry point (all state mutations)
skills/roadmap/scripts/rmlib/         internals: core, parse, ops, sync, changelog, incubator, report, dashboard, project, handoff_note
skills/agent/.claude/agents/          subagent fleet templates (copied into the target's agents/ dir)
commands/<skill>/                     slash commands (roadmap-*.md), installed as flat /roadmap-* files
schemas/skill.schema.json             install-layout contract (documentation)
scripts/validate_skills.py            enforcer for the layout contract
scripts/build-*-plugin.sh             assemble Codex and Antigravity plugin bundles
install.sh                            one-command installer, local or curl | bash
tests/                                pytest suite
docs/superpowers/                     historical specs and plans (reference only)
```

## Roadmap state and data flow
The roadmap skill is the main piece. Its state lives in git, not in a database:

1. **Plan files** `.roadmap/plans/NNN-slug.md` hold the checklist and frontmatter. Status is derived from checkboxes.
2. **`.roadmap/config.json`** holds the project name, current version, the item registry and settings.
3. **`ROADMAP.md`** is a rendered view. Only the region between the `roadmap:auto` markers is regenerated, by `sync`.
4. **`CHANGELOG.md`** (public) and **`CHANGELOG.internal.md`** (full log) are written by the release flow.

Flow: `roadmap.py` commands read and write these files atomically. A Stop hook runs sync and a drift check. A SessionStart/PreInvocation hook runs `orient` to inject the current version and next item. The dashboard reads the same files and pushes updates over Server-Sent Events on `/events`.

## Installation flow
`install.sh` resolves a `skills/` source (local clone, `SKILLS_SRC`, or a GitHub tarball), copies each skill into the target agent directory (`.claude`, `.grok`, `.codex`, or `.agents`), wires hooks into that agent's settings format, writes flat slash commands, and merges marker-delimited rule blocks into `CLAUDE.md` / `AGENTS.md`. Every step is idempotent. Re-running it is the update path.

Agent targets have different hook and command formats. Keep those differences inside `install.sh` and the per-agent plugin builders, not in the skill scripts.

## Boundaries
- Scripts never call the network and never need credentials.
- Skill guidance (methodology) lives in `SKILL.md` and `references/`. Deterministic file edits live in scripts.
- `ROADMAP.md` and `.roadmap/` are written only by `roadmap.py`.
- Installed files in target projects are generated. Edit the source under `skills/` and `commands/`, then reinstall.
