# claude-skills

A collection of installable [Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
for AI-assisted coding (Claude Code and compatible agents). Each skill lives under
`skills/<name>/` with its own detailed docs; new skills can be added over time.

## Install

One command imports the skills, their `/`-commands, the auto-sync hook, and project rules —
no manual copying or settings edits, no clone required:

```bash
curl -fsSL https://raw.githubusercontent.com/DrMxrcy/claude-skills/main/install.sh | bash
```

- **Global** (all projects): append `| bash -s -- --global`
- **From a clone:** `./install.sh`
- **Flags:** `--global`, `--link` (dev symlink), `--no-hook`, `--no-commands`, `--no-claude-md`, `--init`

Then start a fresh Claude Code session so the skills and commands load. Replace `<owner>` /
`DrMxrcy` with your fork's owner if you republish (or set `SKILLS_REPO=owner/repo`).

## Updating

Re-run the install command — it's idempotent and is the update path (or `git pull && ./install.sh`
from a clone). It refreshes skills, commands, the hook, and the `CLAUDE.md` rules block in
place; your project's `ROADMAP.md` / `.roadmap/` data is never touched. Start a fresh session
afterward.

## Skills

| Skill | What it does | Docs |
|---|---|---|
| **roadmap** | A persistent, versioned, type-tagged roadmap that breaks ideas into trackable plans and keeps `ROADMAP.md` in sync — with `/roadmap:*` commands. | [skills/roadmap/README.md](skills/roadmap/README.md) |

## Repository layout

```
skills/<name>/          # each skill: SKILL.md + scripts/templates/refs + README.md
commands/<skill>/       # slash commands for that skill (installed to .claude/commands)
install.sh              # one-command installer (local or curl | bash)
.claude-plugin/         # plugin manifest (marketplace compatibility)
tests/                  # pytest suite
```

To add a skill: drop it in `skills/<name>/` (with a `SKILL.md` and a `README.md`), add any
`commands/<name>/` files, and list it in the table above. The installer picks up every skill
under `skills/` automatically.

## Requirements

Python 3, standard library only (no third-party deps). `pyproject.toml` version detection
uses `tomllib` (Python 3.11+); everything else works on older Python 3.
