---
name: adversarial-review
description: >
  Read-only adversarial review of a diff, branch, roadmap version, single plan, or the
  whole repo (including roadmap state and versions) by several model CLIs at once —
  codex, claude, agy, cursor-agent, opencode — then Claude triages the ranked findings.
  Members that hit a usage limit, are missing, or fail are recorded and skipped, never
  retried. Triggers on "adversarial review", "multi-model review", "have the other CLIs
  review this", "council review of the diff", "/adversarial-review".
argument-hint: "[diff | branch:<base> | version:<v> | plan:<id> | repo]"
---

# Adversarial review

One adversarial prompt goes to every installed member CLI in parallel, each in a
**proven read-only mode**. Each member runs once, with a 300 s cap. The script writes
one file per member plus a ranked `summary.md`. **You (Claude) do the final judgement.**
Nothing is fixed automatically.

## Run it

Resolve the script once. Check `.claude|.grok|.agents/skills/adversarial-review/scripts/run_review.py`
in the project first, then under `$HOME`. In this source repo it is
`skills/adversarial-review/scripts/run_review.py`.

    python3 <run_review.py> [TARGET] [--base REF] [--members a,b] [--exclude a,b]
                            [--refute] [--timeout 300]
    python3 <run_review.py> --list          # installed / excluded members + proofs

- `--exclude <member>` leaves a member out and records it as
  `skipped: excluded by user`. For a diff Claude wrote, `--exclude claude` gives a
  cross-vendor review.
- `--refute` (off by default, one extra call per member) adds a second round. Each
  member that ran gets, in a fresh process, the evidenced findings it did not report
  itself (`prompts/refute.md`), and must disprove them with
  `REFUTE|<id>|<path:line>|<evidence>`. A refutation counts only with a real
  `path:line` and evidence. Refuted findings leave the ranked list and appear under
  **Refuted**, with both sides' evidence. Survivors stay ranked.
- Every call is a fresh session. No `--continue`, `-c`, `--session`, `--resume`, or
  `--fork` flag is ever passed, and the script checks each built command line.

| TARGET | Context given to members |
|---|---|
| `diff` (default) | `git diff HEAD` plus untracked files. With `--base REF`: `git diff REF...HEAD` |
| `branch:<base>` | `git log <base>..HEAD` and `git diff <base>...HEAD` |
| `version:<v>` | every `.roadmap/plans/*.md` whose frontmatter `version:` is `<v>`; members check each step and ✅ Acceptance line against the code |
| `plan:<id>` | that one plan file, checked the same way |
| `repo` | tracked file list, `ROADMAP.md`, VERSION files, and the plan list; members read whatever they need |

Context over 90 KB is truncated with a note telling members to read the files directly.
The prompt is `prompts/adversarial.md`, with `{{TARGET}}` and `{{CONTEXT}}` filled in.

Output: `.roadmap/notes/review-<YYYY-MM-DD>-<target-slug>/`, holding one `<member>.md`
per member (status, command with the prompt redacted, exit code, time, raw reply) and
`summary.md`. Exit codes: `0` written; `1` bad target, clean tree, or not a git repo;
`2` the **read-only guard failed**.

## Members and safety

Members, their exact calls, and the write-probe proof for each are in
`references/members.md`. Summary:

- **Included:** codex (`-s read-only`), cursor-agent (`--mode ask`, because `--mode plan`
  wrote a file under `-p`), agy (`--mode plan`), claude (`--tools Read,Grep,Glob`, plan
  mode, hooks off), and opencode (`--agent plan --standalone`, plus a config that denies
  everything but read/glob/grep, because its plan agent ran shell). opencode uses
  `opencode-go/deepseek-v4.1-flash` first and retries once on
  `opencode/deepseek-v4.1-flash-free` after a usage limit or failure.
- **Excluded:** kimi (`-p` cannot be combined with `--plan`), freebuff (no
  non-interactive mode), and gemini (not installed).
- **Usage limit:** a non-zero exit whose output matches usage limit, rate limit, quota,
  too many requests, 429, limit reached, or insufficient is recorded as
  `skipped: usage limit`. The other members still finish.
- **Read-only guard:** `git status` plus a content hash of every dirty or untracked path
  is taken for the repo and for `.roadmap/` before and after the run. Any change outside
  the output directory marks the run **FAILED** in `summary.md`, lists the changed paths,
  and exits 2. When that happens, tell the user which paths changed. Do not trust the
  findings, and do not revert their files for them.

## Triage (your part)

`summary.md` already ranks findings deterministically:

1. Each member ends its reply with
   `FINDING|<critical|high|medium|low>|<path:line or NONE>|<title>|<evidence>` lines.
2. Findings are deduped by (`path:line`, normalized title). The highest severity
   reported wins, and **agree** counts the distinct members.
3. A finding is **evidenced** only when it has a real `path:line` (the file must exist in
   the repo) **and** evidence text. Evidenced findings are ranked by severity, then
   agreement. Everything else is listed under **Unconfirmed** and is never ranked as
   confirmed.
4. With `--refute`, evidenced findings get ids (`F1`…). Any finding refuted with a
   cited `path:line` and evidence moves to **Refuted**.

Then do the judgement:

- For each **Refuted** entry, read both the claim and the refutation at their cited
  lines, and decide which one is right. A member's refutation is evidence, not a verdict.
- Open every evidenced `path:line` and mark it **confirmed**, **refuted** (say why), or
  **needs-info**. Agreement between members is a signal, not proof. Refute findings
  whose evidence does not match the file.
- Check unconfirmed findings only when they are critical or high. Promote one only after
  you find the location yourself.
- Report a short table to the user: verdict · severity · `path:line` · one-line reason.
  Then add the member status line, including any `skipped: usage limit`, so they know
  which models actually reviewed.
- Do not fix anything unless the user asks. On a roadmap project, real bugs become plan
  items (`/roadmap-plan`) or parked ideas (`/roadmap-idea`), not drive-by edits.
