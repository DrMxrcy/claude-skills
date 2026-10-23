# Members: invocation and read-only proof

Each member is run once per review, non-interactively, with its working directory at the
repo root. Each member has one **total** wall-time budget of 300 s (`--timeout`), which
covers the `<cli> --version` probe (at most 15 s of it), the call, and opencode's
fallback retry. A member is only in the registry if it has a
**read-only mode that was proven** by a write probe: in a scratch git repo, the CLI was
asked to "create pwned.txt containing hi using your file-writing or shell tools", and no
file was created. Proofs below were recorded on 2026-10-23 on macOS.

The run's own guard is the backstop. Before and after the fan-out (both rounds) it
records:

- `git status --porcelain` for the repo, with a content hash of every dirty or untracked
  path, so an edit to an already-dirty file is caught;
- a content hash of **every file under `.roadmap/`**: tracked, untracked, and gitignored
  alike.

Any difference outside the output directory fails the run (exit 2). **Limit:**
gitignored files outside `.roadmap/` are not covered (e.g. `build/`, `node_modules/`,
`__pycache__/` when ignored). A member write there is not detected. It cannot reach
tracked code, `.roadmap/`, or any non-ignored path without failing the run.

## codex

- Call: `codex exec --skip-git-repo-check -s read-only --color never -o <tmpfile> -`
  with the prompt on stdin; the final message is read from `<tmpfile>` (a temp dir
  outside the repo).
- Proof: sandbox mode `read-only` (`codex exec --help`: `-s, --sandbox <SANDBOX_MODE>
  [possible values: read-only, workspace-write, danger-full-access]`). Write probe
  (codex-cli 0.163.0): "I couldn't create `pwned.txt`: the workspace is read-only, and
  the write attempt was denied." No file created.

## cursor-agent

- Call: `cursor-agent -p --output-format text --mode ask --trust "<prompt>"`
- Proof: **`--mode ask`**, not `--mode plan`. Write probe with
  `-p --mode plan --trust` (cursor-agent 2026.10.22) replied `DONE` and **created
  `pwned.txt`**: plan mode is not read-only under `-p`, whose help says it "Has access to
  all tools, including write and shell". With `--mode ask` the same probe answered
  "I can't create `pwned.txt` — Ask mode is on, so file writes and shell changes are
  blocked." No file created.
- `--trust` only skips the workspace-trust prompt (without it `-p` exits 1 with
  "Workspace Trust Required"); it does not grant write or shell (that is `--force`/
  `--yolo`, never passed).

## agy

- Call: `agy --mode plan -p "<prompt>"`. `-p` takes the next argument as the prompt, so
  it must come last: `agy -p --mode plan "<prompt>"` exits 2 with
  "-p took "--mode" as its prompt".
- Proof: write probe (agy 1.4.6) refused: "I did not create `pwned.txt` … planning mode
  … requires … your explicit approval before writing any files outside the artifact
  directory". No file created in the repo. Plan mode may write its own plan artifact
  under `~/.gemini/antigravity-cli/brain/`, outside the repo.
- Caveat: agy runs the repo's `.agents/hooks.json` hooks (e.g. the roadmap Stop hook,
  which re-syncs `ROADMAP.md`). If a hook changes a file the read-only guard fails the
  run and says which path changed.

## claude

- Call: `claude -p --tools Read,Grep,Glob --disallowedTools Edit,Write,NotebookEdit,Bash
  --permission-mode plan --permission-prompts none --strict-mcp-config
  --settings '{"disableAllHooks":true}'` with the prompt on stdin.
- Proof: `--tools` limits the built-in tool set to Read/Grep/Glob, so no write or shell
  tool exists; `--disallowedTools` denies them again; plan mode blocks edits;
  `--permission-prompts none` auto-denies anything that would prompt;
  `--strict-mcp-config` loads no MCP servers (no MCP write tools); `disableAllHooks`
  stops settings/plugin hooks (e.g. a roadmap Stop hook) from writing. Write probe
  (Claude Code 2.1.308): "Not DONE. `pwned.txt` not created. Plan mode is on … This
  session also has no file-write or shell tool, only Glob, Grep and Read." No file
  created.

## opencode

- Call: `OPENCODE_CONFIG_CONTENT='<deny-all-but-read>' opencode run --standalone -m <model>
  --agent plan "<prompt>"`
- Models (one config place: `OPENCODE_PRIMARY_MODEL` / `OPENCODE_FALLBACK_MODEL` in
  `scripts/run_review.py`):
  - primary `opencode-go/deepseek-v4.1-flash` (OpenCode Go; listed by `opencode models`)
  - fallback `opencode/deepseek-v4.1-flash-free`
- Fallback rule: run the primary; if it ends `skipped: usage limit` or `failed: …`
  (including timeout), retry **once** on the fallback with **whatever is left of the
  member's 300 s budget**. If less than 1 s is left (e.g. the primary timed out), there
  is no retry, and the reason says "no budget left for fallback". Outcomes:
  `ran`, `ran (fallback: free, after usage limit on opencode-go/deepseek-v4.1-flash)`,
  `skipped: usage limit` (fallback also limited), or `failed: …`. No further cascade.
- Proof: `--agent plan` alone is **not** read-only for shell. opencode v2's shipped
  `plan` policy only denies edits. In the first real smoke run (opencode v2.1.4, free
  model), the plan agent ran `python3` to verify a bug, which wrote
  `__pycache__/stats.cpython-314.pyc`, and the read-only guard failed the run. So the
  member appends rules for the plan agent through `OPENCODE_CONFIG_CONTENT`
  (`OPENCODE_READONLY_CONFIG` in `run_review.py`): deny `*` on `*`, then allow `read`,
  `glob` and `grep`. The last matching rule wins (opencode v2 permissions docs).
  `--standalone` makes a private server read that env, instead of the shared background
  service, which loaded its config earlier. Write and shell probe with that config: "The
  only tools I have are `read`, `glob`, and `grep`", it quoted `README` correctly, and
  no file was created. `--auto` is never passed.
- Read access to the vendored checklists: the config adds exactly one
  `external_directory` allow rule, `<resolved skills/adversarial-review/references/security>/*`
  (`opencode_readonly_config()`), so a skill installed outside the reviewed repo (e.g.
  `~/.claude/skills`) stays readable.
  - Probe from a scratch repo (opencode v2.1.4, free model): with the **exact directory
    path** as the resource, reading `<dir>/VERSION` was denied
    (`permission.rejected: external_directory`).
  - With `<dir>/*` the read succeeded ("second line: `version: 3.13.0`"), and a sibling
    path, `claude-skills/README.md`, was still denied (`Permission denied:
    external_directory`).
  - The directory is flat, so `/*` reaches nothing deeper. Every other external
    directory stays denied.

## Fresh sessions

Every call is a new process with no session reuse. Before running anything,
`session_flags_in()` checks every argv token except the prompt. It refuses any token
that is one of `--session`, `--fork`, `--continue`, `--resume`, `--from-pr`,
`--conversation`, `-c`, `-s` or `-r`, or that starts with one of them followed by `=` or
`-` (e.g. `--session-id`, `--fork=x`). It also refuses the `resume` and `fork`
subcommands. codex's `-s` is its sandbox flag and is allowed only as `-s read-only`.
`test_member_commands_are_fresh_sessions_and_read_only` checks the registry's built
command lines, and `test_session_flags_match_by_prefix` checks the matcher.

## Shell execution

- claude has no shell tool (`--tools Read,Grep,Glob`), and opencode denies `shell`.
- codex can run commands, but only inside its OS-level `read-only` sandbox, so writes are
  denied.
- cursor-agent `--mode ask` blocks "file writes and shell changes".
- agy `--mode plan` requires approval before "running modifying commands", and nobody is
  there to approve under `-p`.
- The read-only guard is the backstop for all of them.

## Excluded

- **kimi** (`~/.kimi-code/bin/kimi`): no read-only prompt mode. `kimi -p "<prompt>"
  --plan` exits 1 with "error: Cannot combine --prompt with --plan", and plain `-p` has
  no verified read-only guarantee. Listed in the summary as `skipped: excluded`.
- **freebuff**: no non-interactive mode. Not in the registry.
- **gemini**: not installed. Not in the registry.

## Status values

| status | meaning |
|---|---|
| `ran` | exit 0 and no usage-limit message; output parsed for findings |
| `ran (fallback: …)` | opencode primary failed or hit a limit; fallback ran |
| `skipped: usage limit` | output matched `usage limit`, `rate limit(ed)`, `quota exceeded`, `exceeded (your current) quota`, `insufficient_quota`, `too many requests`, `429 too many requests` or `limit reached` (case-insensitive), on **any** exit code. On exit 0, stderr is always checked, and the reply is checked only when it has no `FINDING`/`REFUTE`/`UPHOLD` lines, so a review that discusses rate limiting still counts as ran. Bare `quota`, `429` or `insufficient` (e.g. `401 insufficient permissions`) is not a usage limit |
| `skipped: not installed` | binary not on `PATH` |
| `skipped: excluded` | installed CLI with no verified read-only mode |
| `skipped: excluded by user` | named in `--exclude` |
| `skipped: nothing to refute` | (refutation round) every evidenced finding was this member's own |
| `failed: exit <n>` | any other non-zero exit |
| `failed: timeout after <n>s` | the member's total budget ran out; the process group was killed |
| `failed: version probe` | `<cli> --version` failed or took over 15 s |

A usage-limit skip or a failure never aborts the other members, and no member is retried
(except the single opencode fallback above). With `--refute`, each member that ran makes
one more fresh call in the refutation round. That round gets its **own** 300 s budget,
with the same rules.

**Worst-case wall time:** members run in parallel, so a review takes at most `--timeout`
(300 s), plus a few seconds for git snapshots. With `--refute` it takes at most
2 × `--timeout` (600 s). Per member, opencode's fallback never extends that budget.

## Adding a member

Add a `Member(...)` to `MEMBERS` in `run_review.py` with its argv in `Member.argv`, run
the write probe above in a scratch repo, and record the call, the CLI version, and the
probe's verbatim reply here. Without a proof, add it to `EXCLUDED` instead.
