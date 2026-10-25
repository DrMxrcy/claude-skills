---
description: Read-only adversarial review by every installed model CLI, then triage the findings
argument-hint: "[diff | branch:<base> | version:<v> | plan:<id> | repo] [--base REF] [--exclude a,b] [--refute] [--security] [--decided TEXT] [--deny GLOB] [--no-preflight] [--chunk-budget N] [--resume RUN_DIR]"
---

Run a read-only adversarial review using the **adversarial-review** skill. Target: $ARGUMENTS
(default: `diff`, the working tree vs HEAD).

1. Resolve `run_review.py`: check `.claude|.grok|.agents/skills/adversarial-review/scripts/run_review.py`
   in the project first, then under `$HOME`. In the source repo it is
   `skills/adversarial-review/scripts/run_review.py`.
2. Run `python3 <run_review.py> $ARGUMENTS` from the repo root. Members take up to 300 s
   each and run in parallel, so start it in the background if your host allows that. Do
   not retry members that are skipped or failed. Add `--exclude claude` when Claude wrote
   the diff, so the review is cross-vendor. Add `--refute` only when the user asks for a
   refutation round, because it costs one more call per member.
3. If it exits **2**, the read-only guard failed. Tell the user which paths changed (they
   are listed in `summary.md`), treat every finding as untrusted, and stop. Do not
   revert their files for them. If it exits **1**, report the error (for example a clean
   tree: suggest `branch:<base>`, `plan:<id>` or `repo`).
4. Read `summary.md` in the printed output directory. Triage as the skill's
   **Triage** section says. Open each evidenced `path:line` and mark it confirmed,
   refuted, or needs-info. Treat member agreement as a signal, not proof.
5. Start from the summary's **Verdict** (BLOCK / CONCERNS / CLEAN) and the per-finding
   labels (Confirmed / Needs verification). Pass known, intended choices with
   `--decided`, so members do not re-flag them.
6. Report a short verdict table (verdict · severity · `path:line` · reason), the member
   status line (which models ran, which were skipped for a usage limit or not
   installed), and the output directory. Do not fix anything unless asked. Real bugs
   become `/roadmap-plan` items.
