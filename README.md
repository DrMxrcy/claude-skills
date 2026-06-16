# claude-skills

Local skills for AI-assisted coding, installable with the skills CLI. The first skill is **roadmap**.

## Install

One command imports the skill(s) and wires the auto-sync hook for you — no manual
copying, no editing `settings.json`, no cloning required.

**Straight from GitHub (no clone):**
```bash
# into the current project's .claude/skills + Stop hook
curl -fsSL https://raw.githubusercontent.com/<owner>/claude-skills/main/install.sh | bash

# into ~/.claude/skills (available in every project)
curl -fsSL https://raw.githubusercontent.com/<owner>/claude-skills/main/install.sh | bash -s -- --global
```

**From a clone:**
```bash
./install.sh            # this project's .claude/skills + Stop hook
./install.sh --global   # ~/.claude/skills (all projects)
```

Options: `--global` (user-level), `--link` (symlink for development), `--no-hook`
(skip the Stop hook), `--init` (also run `roadmap init` now). Env overrides:
`SKILLS_REPO` / `SKILLS_REF` (which repo/branch to fetch in remote mode).

> Replace `<owner>` with your GitHub owner/org. The default for remote mode is
> `DrMxrcy/claude-skills`; override with `SKILLS_REPO=owner/repo`.

Alternatively: `npx skills add <owner>/claude-skills`, or copy `skills/roadmap/`
into `.claude/skills/` by hand.

## Skills
- **roadmap** — versioned, type-tagged roadmap as a persistent tracking layer. Maintains `ROADMAP.md` + `.roadmap/` via a deterministic Python CLI (one trackable item at a time, no drift).

## CLI (used by the skill; you can also run it directly)
```bash
python3 skills/roadmap/scripts/roadmap.py init --name "My Project"
python3 skills/roadmap/scripts/roadmap.py init --adopt --name "Existing Project"
python3 skills/roadmap/scripts/roadmap.py new --type feature --title "Auth setup"
python3 skills/roadmap/scripts/roadmap.py check --plan 1 --step 1
python3 skills/roadmap/scripts/roadmap.py status
python3 skills/roadmap/scripts/roadmap.py release --version 0.0.2
```

## Optional: auto-sync Stop hook
Add to `.claude/settings.json` to keep `ROADMAP.md` synced automatically:
```json
{ "hooks": { "Stop": [ { "hooks": [
  { "type": "command", "command": "bash skills/roadmap/hooks/roadmap-sync.sh" }
] } ] } }
```

## Requirements
Python 3 (stdlib only; `pyproject.toml` version detection uses `tomllib`, Python 3.11+). No third-party dependencies.
