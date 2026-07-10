# Contributing

## Adding a new skill

This is a multi-skill repo. To add one:

1. **Create the skill** under `skills/<name>/`:
   - `SKILL.md` with YAML frontmatter (`name`, `description`) — this is what agents load.
   - `README.md` — detailed docs for the skill.
   - Any `scripts/`, `templates/`, `references/`, `hooks/` it needs.
2. **Add slash commands** (optional) under `commands/<name>/*.md`. Claude Code loads nested
   files as `/<name>:<file>`. Grok Build only discovers **flat** `commands/*.md`, so the
   installer also ships each file as `<name>-<file>.md` → `/<name>-<file>` (e.g.
   `/roadmap-next`). On pure `--grok` installs, only the flat form is written.
3. **List it** in the Skills table in the root `README.md`, linking to `skills/<name>/README.md`.
4. **Tests:** add `tests/test_<name>.py` (pytest, stdlib-only fixtures in `tests/conftest.py`).

The installer (`install.sh`) auto-discovers every skill under `skills/` (any dir with a
`SKILL.md`) and every command dir under `commands/` — no installer edits required.

## Running tests

```bash
python3 -m pytest -q          # use python3.11 if your python3 lacks a working stdlib
bash -n install.sh            # shell syntax check
```

## Conventions

- Scripts: **Python 3, standard library only** (no third-party deps).
- Keep deterministic file edits in scripts; keep guidance/methodology in `SKILL.md`.
- Commit code and any tracking/doc updates together.
