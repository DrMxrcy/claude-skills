# Rules

Roadmap workflow rules (plans first, one item at a time, micro-commits, CLI-only state) are in [AGENTS.md](AGENTS.md) and [CLAUDE.md](CLAUDE.md). This file covers code style and what AI coders must never do in this repo.

## Code style
- **Python 3 stdlib only.** Do not add a third-party import, dependency or `requirements.txt`. Check that the module is already used in the repo before reaching for it.
- **Deterministic edits in scripts, guidance in Markdown.** Anything that changes files belongs in a script or CLI command. Methodology belongs in `SKILL.md` or `references/`.
- **Atomic writes.** Write state files through the existing helpers in `rmlib` so a partial failure cannot corrupt a plan or config.
- **Idempotent installers.** Any change to `install.sh` must be safe to run twice and must update marker-delimited blocks in place rather than appending duplicates.
- **Shell:** keep `set -euo pipefail`. Check with `bash -n install.sh`.
- **Names:** skill directories and frontmatter `name` are lowercase kebab-case and must match. Commands are the hyphen form (`/roadmap-build`). Never use the colon form in new text.
- **Keep it small.** Make the fewest changes that address the request. No unrequested features, flags or abstractions.

## Tests and checks
Run these before a step is checked off:
```bash
python3 -m pytest -q                  # full suite (or -n auto with pytest-xdist)
bash -n install.sh                    # shell syntax
python3 scripts/validate_skills.py    # skills/ layout vs schemas/skill.schema.json
```
- Add or update `tests/test_<name>.py` for any behavior change. Tests use `tmp_path`, never the real repo.
- Do not skip, weaken or delete a test to make it pass. Fix the cause.

## Versioning
- Each skill's `VERSION` file is semver with no leading `v`. Bump it when a skill's behavior changes.
- Do not hand-edit `ROADMAP.md`, `.roadmap/config.json` or `CHANGELOG*.md` to record a release. Use the `roadmap.py` release flow.

## Never
- Never write secrets, tokens or API keys into the repo, skill files, templates or tests.
- Never write a global `CLAUDE.md`. Roadmap rules are project-specific. The installer's `--global` path must skip them, and Codex and Antigravity global installs write only `AGENTS.md` in their own directory.
- Never make the installer overwrite a user's existing instruction file content outside the managed markers.
- Never commit `CHANGELOG.internal.md`, `.claude/`, `.grok/`, `.codex/` or `.agents/` into a public repo's tracked files. These are covered by the `--gitignore` block.
- Never run a destructive git operation (reset, force push, clean) without the user asking.
- Never bypass `roadmap.py` by editing its managed state directly.
- Never claim a check passed that did not run. Report failing or skipped checks as limitations.
