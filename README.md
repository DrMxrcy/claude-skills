# claude-skills

Local skills for AI-assisted coding, installable with the skills CLI. The first skill is **roadmap**.

## Install

One command sets up everything — no manual copying, no editing `settings.json`, no
cloning. For a project install it imports the skill, installs the `/roadmap:*` slash
commands, wires the auto-sync Stop hook, and adds roadmap rules to `CLAUDE.md`
(creating it if absent).

**Straight from GitHub (no clone):**
```bash
# this project's .claude (skills + /roadmap:* commands + hook + CLAUDE.md rules)
curl -fsSL https://raw.githubusercontent.com/DrMxrcy/claude-skills/main/install.sh | bash

# into ~/.claude (available in every project; skips CLAUDE.md)
curl -fsSL https://raw.githubusercontent.com/DrMxrcy/claude-skills/main/install.sh | bash -s -- --global
```

**From a clone:**
```bash
./install.sh            # this project's .claude/* + CLAUDE.md rules
./install.sh --global   # ~/.claude (all projects)
```

Options: `--global` (user-level), `--link` (symlink for development), `--no-hook`
(skip the Stop hook), `--no-commands` (skip the slash commands), `--no-claude-md`
(don't touch `CLAUDE.md`), `--init` (also run `roadmap init` now). Env overrides:
`SKILLS_REPO` / `SKILLS_REF` (which repo/branch to fetch in remote mode).

> Replace `DrMxrcy` with your GitHub owner/org. The default for remote mode is
> `DrMxrcy/claude-skills`; override with `SKILLS_REPO=owner/repo`.

Alternatively: `npx skills add DrMxrcy/claude-skills`, or copy `skills/roadmap/`
into `.claude/skills/` by hand.

## Skills
- **roadmap** — versioned, type-tagged roadmap as a persistent tracking layer. Maintains `ROADMAP.md` + `.roadmap/` via a deterministic Python CLI (one trackable item at a time, no drift).

## Slash commands
The installer adds these to `.claude/commands/roadmap/`:

| Command | Does |
|---|---|
| `/roadmap:init` | Initialize roadmap tracking (auto-detects adopt for existing repos) |
| `/roadmap:plan <idea>` | Brainstorm an idea into a tracked, versioned plan |
| `/roadmap:build <id>` | Implement a plan item step-by-step, checking off as tests pass |
| `/roadmap:status` | Show versions, items, and progress |
| `/roadmap:done <id> [step]` | Mark a step/item done and resync |
| `/roadmap:release <version>` | Cut a new version |
| `/roadmap:sync` | Recompute progress and re-render `ROADMAP.md` |

## CLI (used by the skill; you can also run it directly)
```bash
python3 skills/roadmap/scripts/roadmap.py init --name "My Project"
python3 skills/roadmap/scripts/roadmap.py init --adopt --name "Existing Project"
python3 skills/roadmap/scripts/roadmap.py new --type feature --title "Auth setup"
python3 skills/roadmap/scripts/roadmap.py check --plan 1 --step 1
python3 skills/roadmap/scripts/roadmap.py status
python3 skills/roadmap/scripts/roadmap.py release --version 0.0.2
```

## Auto-sync Stop hook
The installer wires this into `settings.json` automatically (use `--no-hook` to skip). It
keeps `ROADMAP.md` synced even if a `sync` is missed. To add it by hand instead:
```json
{ "hooks": { "Stop": [ { "hooks": [
  { "type": "command", "command": "bash .claude/skills/roadmap/hooks/roadmap-sync.sh" }
] } ] } }
```

## Requirements
Python 3 (stdlib only; `pyproject.toml` version detection uses `tomllib`, Python 3.11+). No third-party dependencies.
