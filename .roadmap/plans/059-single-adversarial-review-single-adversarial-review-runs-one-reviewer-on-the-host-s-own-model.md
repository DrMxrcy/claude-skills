---
id: 59
title: Single adversarial review: /single-adversarial-review runs one reviewer on the host's own model
type: feature
version: 0.19.0
status: done
created: 2026-10-29
---

# Plan 59: Single adversarial review: /single-adversarial-review runs one reviewer on the host's own model
> Type: feature · Target: v0.19.0

## 🎯 Target Scope & Boundaries
- **Core objective:** a second command, `/single-adversarial-review`, that reviews the same targets as `/adversarial-review` (diff, branch:, version:, plan:, repo) with exactly one reviewer: the agent session the command runs in. No member CLI is spawned, so the review uses whatever model the host is on (OpenCode's current model inside OpenCode, Claude's inside Claude Code, and so on). It reuses the council's prompt, target context, lens, `--decided` list, deny list and secret redaction, so both commands judge by the same rules.
- **Out of scope:** changing `/adversarial-review` council behaviour or its members; model pinning for the single review (the host's model is the point); a snapshot sandbox for the host session; Codex command files (Codex invokes skills as `$adversarial-review`).

## 🏗️ Architectural Blueprint
- **Files to create:** `commands/single-adversarial-review.md`.
- **Files to modify:** `skills/adversarial-review/scripts/run_review.py` (new `--prompt-only` mode), `skills/adversarial-review/SKILL.md` (a "Single review" section), `install.sh` (install the new command beside `/adversarial-review`, same agents, same `--link` handling), `tests/test_adversarial_review.py`, `tests/test_install.py` or `tests/test_install_agent.py`.
- **Schema/interface changes:** `run_review.py TARGET --prompt-only [--security] [--decided ...] [--deny ...] [--base REF]` builds the exact prompt a council member would get (single-lens: production breakage unless `--security`), writes it to `<run-dir>/prompt.md`, prints that path, and exits 0 without running any member, preflight, model.md check or snapshot copy. Same exit 1 cases as today (bad target, clean tree, not a git repo). `repo` with `--prompt-only` writes one `prompt-<chunk-id>.md` per chunk in risk order.
- **Downstream impact:** the command file tells the host agent to run `--prompt-only`, read the prompt, review the live repo read-only following it, apply the skill's evidence rule to its own findings (open each `path:line`, quote within 3 lines, impact path), and report verdict (BLOCK / CONCERNS / CLEAN) and the findings table. It writes nothing outside the run dir and fixes nothing unless asked.

## ✅ Acceptance
- **Passes when:** `python3 skills/adversarial-review/scripts/run_review.py diff --prompt-only` on a dirty tree writes `.roadmap/notes/review-<date>-<slug>/prompt.md`, prints its path, starts no member process (verified by a test that fails if `subprocess` member launch is reached), and the prompt contains the redacted diff, the lens and any `--decided` item.
- **Passes when:** `--prompt-only` on a clean tree with target `diff` exits 1 with the same message as the council run.
- **Passes when:** `./install.sh --opencode` (and the Claude default) installs `commands/single-adversarial-review.md` next to `adversarial-review.md`; `--codex` installs neither; `--no-commands` installs neither.
- **Passes when:** `python3.11 -m pytest -q tests/test_adversarial_review.py tests/test_adversarial_review_chunks.py tests/test_install.py tests/test_install_agent.py` is green.
- **Fails if:** any existing council behaviour, output file, exit code or test changes; or the single command spawns any model CLI.

## 🚶 Step-by-Step Checklist
- [x] Step 1: `--prompt-only` mode in run_review.py with tests -> target: skills/adversarial-review/scripts/run_review.py, tests/test_adversarial_review.py
  > evidence: pytest 4 files: 164 passed; spec review (scout haiku) all acceptance MET; quality review (verifier sonnet) PARTIAL, 4 findings fixed (cap-boundary redaction, deny block in prompt, arg quoting, chunk scope text), re-tested by parent (2026-10-29)
- [x] Step 2: `/single-adversarial-review` command, SKILL.md section, install.sh wiring with install tests -> target: commands/single-adversarial-review.md, skills/adversarial-review/SKILL.md, install.sh, tests/test_install*.py
  > evidence: pytest 4 files: 164 passed; spec review (scout haiku) all acceptance MET; quality review (verifier sonnet) PARTIAL, 4 findings fixed (cap-boundary redaction, deny block in prompt, arg quoting, chunk scope text), re-tested by parent (2026-10-29)
