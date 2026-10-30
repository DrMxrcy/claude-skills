# adversarial-review: multi-CLI read-only review with Claude triage

Sends one adversarial prompt to every installed agent CLI (codex, claude, agy,
cursor-agent, opencode) in parallel. Each runs in a read-only mode, inside a sanitized
snapshot of the target, and the script ranks their findings so Claude can make the final
call. A model that is over its usage limit, not installed, or failing is recorded and
skipped. The rest of the review still runs.

## Install

From a clone of this repo, into the project you want reviewed:

    ./install.sh --only=adversarial-review            # skill + /adversarial-review command
    ./install.sh --global --only=adversarial-review   # all projects (~/.claude)

A plain `./install.sh` installs it together with the other skills. The skill is
self-contained (Python standard library only).

## Use

    /adversarial-review                 # working-tree diff vs HEAD
    /adversarial-review branch:main     # this branch vs main
    /adversarial-review version:0.19.0  # every plan in a roadmap version
    /adversarial-review plan:29         # one plan item
    /adversarial-review repo            # whole repo, one module chunk per call
    /adversarial-review repo --parallel 2       # two chunk calls per member at once
    /adversarial-review repo --include-docs     # also plans, changelogs, docs/, agent dirs
    /adversarial-review --resume <run-dir>      # continue a chunked repo run
    /adversarial-review diff --exclude claude   # cross-vendor review of a Claude diff
    /adversarial-review diff --refute           # + round 2: members try to disprove each other
    /adversarial-review diff --security         # every member on the security lens

Results go to `.roadmap/notes/review-<date>-<slug>/`: one `<member>.md` per member plus
`summary.md`. The summary holds the verdict, the status table, the ranked findings, the
snapshot and guard results, and the not-checked lines.

A `repo` run is chunked by module under `--chunk-budget`, with risky chunks first. It
reviews code: `.roadmap`, `ROADMAP.md`, `CHANGELOG*.md`, `docs/` and agent tooling
directories are left out unless `--include-docs`. It
writes `model.md` (each member's probed model and effort flags), `coverage.json` and one
result per chunk as each finishes, so `--resume` continues after a usage limit. With
`openusage` installed, each member's chunk calls are planned from its remaining window,
and it stops at `--usage-floor`. If the repo has a `.codegraph/` index, chunks get
`codegraph explore` context. The runner never indexes.

## Safety in short

- Members run in a temporary snapshot. `.env*`, keys, `.npmrc`, `.netrc`, `.git/`,
  `node_modules/`, gitignored files, and anything matched by `--deny` are left out.
- Each member gets an environment allowlist: basic variables plus its own CLI's auth
  variables only.
- A live-tree `git status` and `.roadmap/` guard fails the run if anything changes.
- If `openusage` is installed, a member whose usage window is already at 0 is skipped
  before it is called. Only provider ids, percents and reset times are recorded.
- Secrets (AWS keys, GitHub tokens, private keys, random-looking `KEY=value` values) are
  redacted from every prompt and snapshot. `summary.md` lists the files sent.
- A finding counts only if its quote really appears near its `path:line`. Removing a
  finding by refutation needs two members with verified quotes.

`SKILL.md` has the details: each member's command and read-only mode, the opencode
fallback, the excluded CLIs, and the residual risks.

## Files

| Path | What |
|---|---|
| `SKILL.md` | how Claude runs it, the members, safety, and triage |
| `scripts/run_review.py` | snapshot, fan-out, caps, usage limits, guard, redaction, evidence checks, triage |
| `scripts/chunk_plan.py` | repo chunks under a token budget, risk order, `coverage.json`, CodeGraph context |
| `scripts/probe_models.py` | writes `model.md` from each CLI's `--help` (never calls a model) |
| `prompts/adversarial.md` | the member prompt, including the security lens and the output format |
| `prompts/refute.md` | the `--refute` round prompt |
