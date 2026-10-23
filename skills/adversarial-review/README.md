# adversarial-review: multi-CLI read-only review with Claude triage

Sends one adversarial prompt to every installed agent CLI (codex, claude, agy,
cursor-agent, opencode) in parallel. Each runs in a mode that was proven read-only. The
script then ranks their findings so Claude can make the final call. A model that is over
its usage limit, not installed, or failing is recorded and skipped. The rest of the
review still runs.

## Install

From a clone of this repo, into the project you want reviewed:

    ./install.sh --only=adversarial-review            # skill + /adversarial-review command
    ./install.sh --global --only=adversarial-review   # all projects (~/.claude)

A plain `./install.sh` installs it together with the other skills. The skill is
self-contained under `skills/adversarial-review/` and uses only the Python standard
library.

## Use

    /adversarial-review                 # working-tree diff vs HEAD
    /adversarial-review branch:main     # this branch vs main
    /adversarial-review version:0.19.0  # every plan in a roadmap version
    /adversarial-review plan:29         # one plan item
    /adversarial-review repo            # whole repo incl. roadmap state
    /adversarial-review diff --exclude claude   # cross-vendor review of a Claude diff
    /adversarial-review diff --refute           # + round 2: members try to disprove each other

Results go to `.roadmap/notes/review-<date>-<slug>/`: one `<member>.md` per member plus
`summary.md`, which holds the status table, the ranked findings, and the read-only
guard result.

## Files

| Path | What |
|---|---|
| `SKILL.md` | how Claude runs it and triages the result |
| `scripts/run_review.py` | detection, parallel fan-out, caps, usage-limit detection, read-only guard, triage |
| `prompts/adversarial.md` | the member prompt and the required `FINDING\|…` output format |
| `prompts/refute.md` | the `--refute` round prompt (`REFUTE\|…` / `UPHOLD\|…`) |
| `references/members.md` | the call for each CLI, its write-probe proof, and why other CLIs are excluded |
