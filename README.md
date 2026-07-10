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
- **Flags:** `--global`, `--grok` (target Grok Build), `--link` (dev symlink), `--no-hook`, `--no-commands`, `--no-claude-md`, `--init`

Then start a fresh Claude Code session so the skills and commands load. Replace `<owner>` /
`DrMxrcy` with your fork's owner if you republish (or set `SKILLS_REPO=owner/repo`).

### Grok Build

Grok Build reads Claude Code's `.claude/` directory (skills, hooks, `CLAUDE.md`) out of the
box, so a normal project install already works there. For a native install that doesn't
depend on the Claude-compat shim, add `--grok`:

```bash
curl -fsSL https://raw.githubusercontent.com/DrMxrcy/claude-skills/main/install.sh | bash -s -- --grok
```

This targets `./.grok/` (or `~/.grok/` with `--global`), wires the auto-sync Stop hook as
native `.grok/hooks/roadmap-sync.json`, still writes the `CLAUDE.md` rules block (Grok reads
it natively), and installs **flat** slash commands Grok can actually discover:

| Claude Code | Grok Build |
|---|---|
| `/roadmap:next` | `/roadmap-next` |
| `/roadmap:build` | `/roadmap-build` |
| `/roadmap:status` | `/roadmap-status` |
| `/roadmap:<cmd>` | `/roadmap-<cmd>` |

Grok only loads flat `commands/*.md` (nested `commands/roadmap/*.md` never show up in the
slash menu). A default Claude install also drops the flat aliases into `.claude/commands/`
so Grok's Claude-compat path gets `/roadmap-next` too. Bare `/roadmap` still works with
subcommand args (`/roadmap next`). Verify with `grok inspect`.

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
