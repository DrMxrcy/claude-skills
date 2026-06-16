# claude-skills

Local skills for AI-assisted coding, installable with the skills CLI. The first skill is **roadmap**.

## Install
```bash
npx skills add <owner>/claude-skills
```
Or copy `skills/roadmap/` into `.claude/skills/` in your project.

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
