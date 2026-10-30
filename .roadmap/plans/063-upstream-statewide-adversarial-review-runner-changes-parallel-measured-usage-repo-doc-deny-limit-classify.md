---
id: 63
title: Upstream statewide adversarial-review runner changes: --parallel, measured usage, repo doc deny, limit classify
type: feature
version: 0.19.0
status: planned
created: 2026-10-30
---

# Plan 63: Upstream statewide adversarial-review runner changes: --parallel, measured usage, repo doc deny, limit classify
> Type: feature · Target: v0.19.0

## 🎯 Target Scope & Boundaries
- **Core objective:** port the statewide-only changes in statewide-app's `.agents/skills/adversarial-review/scripts/run_review.py` (as of statewide commit `16cb582ac~1`; it forked from claude-skills `b1b38ef`) into `skills/adversarial-review/scripts/run_review.py`, on top of plans 59/60 (prompt-only, redact-before-cap). The changes: `--parallel N` (threaded per-member chunk calls; usage floor counts in-flight calls), `MEASURED_CALLS` (measured usage replaces --chunk-cost after 5 calls), `REPO_DENY` + `--include-docs` (repo and --resume runs skip planning records and agent tooling by default), extra usage-limit phrases (`quota reached`, `resource_exhausted`), `classify(..., reply=)` (a reply with FINDING/REFUTE/UPHOLD/NOT_CHECKED lines counts as ran; only error lines among the last STDERR_TAIL_LINES of stderr are checked), sha1 → sha256 digests in the live guard.
- **Out of scope:** changing plan 59/60 behaviour; statewide's own repo paths.

## 🏗️ Architectural Blueprint
- **Files to modify:** skills/adversarial-review/scripts/run_review.py, skills/adversarial-review/SKILL.md (document --parallel, --include-docs, the default repo deny), tests/test_adversarial_review*.py.
- **Schema/interface changes:** new flags `--parallel N` (default 1) and `--include-docs`. `REPO_DENY` must be generic: drop the statewide-only entry `statewide-docs`; keep `.roadmap`, `ROADMAP.md`, `CHANGELOG*.md`, `docs/*`, `.security-audit`, agent dirs, `.codegraph`.
- **Downstream impact:** do a three-way merge (base = `git show b1b38ef:skills/adversarial-review/scripts/run_review.py`, statewide = `git -C /Users/jp/Desktop/Dev/statewide/statewide-app show 16cb582ac~1:.agents/skills/adversarial-review/scripts/run_review.py`, ours = HEAD). Decide whether `--prompt-only repo` also applies REPO_DENY unless --include-docs (it should, for parity).

## ✅ Acceptance
- **Passes when:** every statewide hunk listed above is present in the repo file, and plan 59/60 tests still pass.
- **Passes when:** new tests cover `--parallel 2` (chunks spread across workers, floor stops with in-flight calls counted, no chunk run twice), MEASURED_CALLS switching to measured cost, REPO_DENY applied for repo and absent with --include-docs, classify treating a reply with FINDING lines as ran despite "rate limit" in stderr, and the new limit phrases.
- **Passes when:** `python3.11 -m pytest -q tests/test_adversarial_review.py tests/test_adversarial_review_chunks.py` is green.
- **Fails if:** `statewide-docs` or any other statewide-only path ships in the generic file, or the default (`--parallel 1`) chunk loop changes order or stop behaviour.

## 🚶 Step-by-Step Checklist
- [ ] Step 1: Three-way merge the statewide runner changes with tests -> target: skills/adversarial-review/scripts/run_review.py, tests/
- [ ] Step 2: Document --parallel, --include-docs and the default repo deny in SKILL.md and the command files -> target: skills/adversarial-review/SKILL.md, commands/
