# claude-skills

A collection of installable [Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
for AI-assisted coding — **Claude Code, Grok Build, OpenAI Codex, and compatible agents**. The flagship
**roadmap** skill keeps AI coders on-task with a versioned plan + quality-first multi-agent
build loop (implement → review → tests → check) so speed does not cost quality.

Each skill lives under `skills/<name>/` with its own detailed docs; new skills can be added
over time.

## Install

The installer works on **the directory you run it from** — `cd` into the project you want
to equip first, then run it. One command imports the skills, their `/`-commands, the
auto-sync hook, and project rules — no manual copying or settings edits, no clone required:

```bash
cd /path/to/your-project
curl -fsSL https://raw.githubusercontent.com/DrMxrcy/claude-skills/main/install.sh | bash
```

- **Global** (all projects, into `~/.claude`): append `| bash -s -- --global` — then you don't need per-project installs at all
- **From a clone into another project:** `cd /path/to/your-project && /path/to/claude-skills/install.sh`
- **Just one skill** (e.g. only the agent orchestration fleet): append `| bash -s -- --only=agent` (or `--only=roadmap`)
- **Flags:** `--global`, `--grok`, `--codex`, **`--both`** (Claude + Grok same version — best when switching coders), `--link`, `--only=<skill,...>`, `--no-hook`, `--no-orient`, `--no-commands`, `--no-claude-md`, `--no-agent`, `--gitignore`, `--init`

Then start a fresh Claude Code session **in that project** so the skills and commands load.
Replace `<owner>` / `DrMxrcy` with your fork's owner if you republish (or set
`SKILLS_REPO=owner/repo`).

What a project install writes:

```
your-project/
├── .claude/
│   ├── skills/roadmap/   # + skills/agent/ unless --no-agent / --only=roadmap
│   ├── agents/           # cost-tiered subagent fleet (executor, verifier, scout, …)
│   ├── commands/         # /roadmap:* and flat /roadmap-* aliases
│   └── settings.json     # Stop + SessionStart hooks merged in
├── CLAUDE.md             # roadmap rules block (idempotent, marked)
└── ROADMAP.md + .roadmap/  # only after `roadmap init` / --init
```

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

### OpenAI Codex

Install the roadmap skill and lifecycle hooks for Codex CLI with:

```bash
curl -fsSL https://raw.githubusercontent.com/DrMxrcy/claude-skills/main/install.sh | bash -s -- --codex
```

Codex has a fixed built-in slash-command menu, so installed skills do not add
`/roadmap-*` entries. Invoke the skill with `$roadmap` followed by the action instead:

```text
$roadmap status
$roadmap next
$roadmap build 1.0.0 --auto
```

Start a fresh Codex CLI session after installation. You can also select Roadmap from
Codex's skills UI. The plugin installation described in
[`codex-plugin/README.md`](codex-plugin/README.md) provides the same skill and hooks.
A bare `$roadmap` prints a compact action list; Codex does not provide nested skill-command
autocomplete.

## Updating

Re-run the install command — it's idempotent and is the update path (or `git pull && ./install.sh`
from a clone). It refreshes skills, commands, the hook, and the `CLAUDE.md` rules block in
place; your project's `ROADMAP.md` / `.roadmap/` data is never touched. Start a fresh session
afterward.

## Public repos: what to commit vs ignore

Roadmap data is designed to live **in git** — it's how multiple AI coders (Claude ↔ Grok ↔
Codex) stay in sync. But on a public repo you may not want your internal dev log or the
installed tooling published. The installer can write the recommended block for you
(idempotent — safe to re-run):

```bash
curl -fsSL https://raw.githubusercontent.com/DrMxrcy/claude-skills/main/install.sh | bash -s -- --gitignore
```

What it appends to `./.gitignore`:

```gitignore
# AI coding tooling — reinstallable via install.sh, no need to publish
.claude/
.grok/
.codex/
.agents/

# Full internal dev log (public notes stay in CHANGELOG.md)
CHANGELOG.internal.md
```

Keep **committed**: `ROADMAP.md`, `.roadmap/` (plans + config), `CHANGELOG.md`, and
`CLAUDE.md` / `AGENTS.md` — these are the shared brain across agents and sessions; ignoring
them breaks multi-coder sync and resume-after-crash.

If you don't even want the roadmap/plans public, also ignore:

```gitignore
# Only if plans must stay private — breaks cross-machine/multi-agent sync via git
ROADMAP.md
.roadmap/
```

Solo, single-machine use only — anyone cloning the repo (including your own cloud agents)
loses the plan state.

Alternative: install with `--global` so nothing lands in the project at all except
`ROADMAP.md` / `.roadmap/` / changelogs.

## Skills

| Skill | What it does | Docs |
|---|---|---|
| **roadmap** | On-task + high-quality AI coding harness: versioned plans, native agent invocation (`/roadmap:*`, `/roadmap-*`, or Codex `$roadmap`), quality-first multi-agent build (`--auto` still reviews), anti-drift CLI. | [skills/roadmap/README.md](skills/roadmap/README.md) |
| **agent** | Cost-tiered subagent orchestration: main session keeps judgment, delegates to the cheapest capable tier (executor/verifier on opus, mech-executor on sonnet, scout/Explore on haiku), adversarial fresh-context verification. | [skills/agent/README.md](skills/agent/README.md) |

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
