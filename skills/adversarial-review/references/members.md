# Members: invocation and read-only proof

Each member is run once per review, non-interactively, with its working directory at the
repo root, under a 300 s wall-time cap (`--timeout`). `run_review.py` probes
`<cli> --version` first (15 s cap). A member is only in the registry if it has a
**read-only mode that was proven** by a write probe: in a scratch git repo, the CLI was
asked to "create pwned.txt containing hi using your file-writing or shell tools", and no
file was created. Proofs below were recorded on 2026-10-23 on macOS.

The run's own guard is the backstop: `git status --porcelain` (plus a content hash of
every dirty or untracked path) is recorded for the repo and for `.roadmap/` before and
after the fan-out. Any difference outside the output directory fails the run.

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
  (including timeout), retry **once** on the fallback with its own 300 s cap. Outcomes:
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

## Fresh sessions

Every call is a new process with no session reuse. No member is ever passed
`--continue`, `-c`, `--session`, `--resume`, `--fork`, or `resume` (and no `-s`, except
codex, where `-s` is `--sandbox`). `run_review.py` checks each built argv with
`session_flags_in()` before it runs anything, and
`test_member_commands_are_fresh_sessions_and_read_only` checks the registry.

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
| `ran` | exit 0; output parsed for findings |
| `ran (fallback: …)` | opencode primary failed or hit a limit; fallback ran |
| `skipped: usage limit` | non-zero exit and output matched `usage limit\|rate limit\|quota\|too many requests\|429\|limit reached\|insufficient` (case-insensitive) |
| `skipped: not installed` | binary not on `PATH` |
| `skipped: excluded` | installed CLI with no verified read-only mode |
| `skipped: excluded by user` | named in `--exclude` |
| `skipped: nothing to refute` | (refutation round) every evidenced finding was this member's own |
| `failed: exit <n>` | any other non-zero exit |
| `failed: timeout after <n>s` | wall-time cap hit; the process group was killed |
| `failed: version probe` | `<cli> --version` failed or took over 15 s |

A usage-limit skip or a failure never aborts the other members, and no member is retried
(except the single opencode fallback above). With `--refute`, each member that ran makes
one more fresh call in the refutation round, under the same cap and the same rules.

## Adding a member

Add a `Member(...)` to `MEMBERS` in `run_review.py` with its argv in `Member.argv`, run
the write probe above in a scratch repo, and record the call, the CLI version, and the
probe's verbatim reply here. Without a proof, add it to `EXCLUDED` instead.
