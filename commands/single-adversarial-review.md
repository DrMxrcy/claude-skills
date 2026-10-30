---
description: Read-only adversarial review by this session's own model, one reviewer, no member CLIs
argument-hint: "[diff | branch:<base> | version:<v> | plan:<id> | repo] [--base REF] [--security] [--decided TEXT] [--deny GLOB] [--chunk-budget N] [--include-docs]"
---

Run a read-only adversarial review with **one reviewer: you**, on the model this session
already uses. It uses the **adversarial-review** skill's prompt and rules, but no member
CLI is started. Target: $ARGUMENTS (default: `diff`, the working tree vs HEAD).

1. Resolve `run_review.py`: check `.claude|.grok|.agents/skills/adversarial-review/scripts/run_review.py`
   in the project first, then under `$HOME`. In the source repo it is
   `skills/adversarial-review/scripts/run_review.py`.
2. Run `python3 <run_review.py> <arguments> --prompt-only` from the repo root, where
   `<arguments>` are the user's arguments passed through unchanged. Keep quoted values
   intact as one argument each, for example `--decided "text with spaces"`. It runs no
   model. It writes the prompt one council member would get (production-breakage lens,
   or security with `--security`) and prints `prompt: <path>`. For `repo` it prints one
   `prompt-<chunk-id>.md` per chunk, in risk order. If it exits **1**, report the error
   (for example a clean tree: suggest `branch:<base>`, `plan:<id>` or `repo`).
3. Read the prompt and follow it as the reviewer. Review the live repo **read-only**:
   read, search and run read-only git commands only. Do not edit, create or delete files,
   and do not start another model CLI or subagent to review for you. Do not open files
   listed in the prompt's **Do not read these paths** block (the default deny list plus
   any `--deny` glob; for `repo`, also planning records and agent tooling unless
   `--include-docs`). For `repo`, review the chunk prompts in the order printed.
4. Apply the skill's **evidence rule** to your own findings before you report them. For
   each one, open its `path:line`, check that a quote of at least 10 characters appears
   within 3 lines of that line, and state its impact path. Drop any finding that fails;
   do not downgrade it.
5. Pick the verdict by the skill's **Triage** rules: **BLOCK** for a critical finding,
   or a high one that is Confirmed; **CONCERNS** for any other finding; **CLEAN** when
   nothing survives.
6. Report the verdict, a findings table (severity · label · `path:line` · title ·
   impact), your not-checked line, and the prompt path. Write nothing outside the run
   directory. Do not fix anything unless asked. Real bugs become `/roadmap-plan` items.
