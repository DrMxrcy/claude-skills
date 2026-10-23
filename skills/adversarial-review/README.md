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
    /adversarial-review diff --security         # every member on the security lens
    /adversarial-review diff --decided "sha1 for cache keys is intended"

Results go to `.roadmap/notes/review-<date>-<slug>/`: one `<member>.md` per member plus
`summary.md`, which holds the status table, the ranked findings, and the read-only
guard result.

## How it stays safe, and its limits

- **Read-only modes, each proven by a write probe** (details in `references/members.md`):
  - codex runs with `-s read-only`.
  - cursor-agent runs with `--mode ask`. `--mode plan` is not used because under `-p`
    it wrote a file.
  - agy runs with `--mode plan`.
  - claude gets only the Read, Grep and Glob tools, with hooks off.
  - opencode runs `--agent plan --standalone` with a config that denies everything but
    read, glob and grep, because its plan agent ran shell.
- **opencode models:** `opencode-go/deepseek-v4.1-flash` first. After a usage limit or
  failure it retries once on `opencode/deepseek-v4.1-flash-free`, using only what is
  left of opencode's budget.
- **Time:** each member has one total budget of 300 s. `--refute` adds a second round
  with its own 300 s budget. Worst case is about 300 s for a review, or 600 s with
  `--refute`.
- **Read-only guard:** `git status` plus content hashes of dirty or untracked paths, and
  of every file under `.roadmap/` (including gitignored ones). Any change fails the run
  with exit 2. Gitignored files outside `.roadmap/` are not covered.
- **Usage limits** are detected from specific phrases on any exit code and recorded as
  `skipped: usage limit`. They never stop the other members.
- **Evidence rule:** a finding needs an in-repo `path:line` whose line exists, evidence,
  and an impact path (at least 10 characters each). Anything else is dropped, not
  downgraded.
- **Review shape:**
  - Each member gets a lens (production breakage, security, or maintainability;
    `--security` gives everyone the security lens).
  - Findings carry a **Confirmed** or **Needs verification** label, and `summary.md`
    opens with a deterministic **BLOCK / CONCERNS / CLEAN** verdict.
  - An `injection-scan` pass reports repo text that tries to steer reviewers.
  - `RULES.md`, `DESIGN.md` and `ARCHITECTURE.md` are read by members, never pasted.

## Security checklists

The secaudit domain checklists are vendored under `references/security/`, with their MIT
license and an attribution file, so the review runs in any repo without the secaudit
plugin installed. To refresh them after a plugin update, run
`python3 skills/adversarial-review/scripts/sync-security-refs.py` (manual only). Its
`--check` flag exits 1 when they are behind, and `summary.md` shows a staleness line
when that happens.

## Files

| Path | What |
|---|---|
| `SKILL.md` | how Claude runs it and triages the result |
| `scripts/run_review.py` | detection, parallel fan-out, caps, usage-limit detection, read-only guard, triage |
| `prompts/adversarial.md` | the member prompt and the required `FINDING\|…` output format |
| `prompts/refute.md` | the `--refute` round prompt (`REFUTE\|…` / `UPHOLD\|…`) |
| `scripts/sync-security-refs.py` | manual sync of the secaudit checklists; `--check` reports staleness |
| `references/security/` | vendored secaudit checklists (`<domain>.md`), `LICENSE` (MIT), attribution `README.md`, `VERSION` |
| `references/members.md` | the call for each CLI, its write-probe proof, and why other CLIs are excluded |
