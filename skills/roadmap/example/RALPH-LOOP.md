# Example: autonomous phase build via ralph-loop

This is what `/roadmap:build <version> --auto --worktree --pr` produces for the
[`ralph-loop`](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum)
plugin — a harness-enforced loop that builds a whole version in an isolated worktree and
opens a PR (never merging to main). The roadmap skill fills the `<…>` from
`roadmap.py status`: `<VERSION>` (target version), `<PROJECT>` (worktree path
`../<PROJECT>-v<VERSION>`), and `<N>` = the version's unfinished-item count + a small buffer.

```
/ralph-loop:ralph-loop --completion-promise 'v<VERSION> DONE' --max-iterations <N> "First: git worktree add ../<PROJECT>-v<VERSION> -b roadmap/v<VERSION> and work inside it. Loop until roadmap v<VERSION> is 100%: run /roadmap:status, build the next unfinished v<VERSION> item (one step, or fan out subagents), tests MUST pass, mark done via the roadmap CLI, commit code+roadmap together. Never hand-edit ROADMAP.md. When all v<VERSION> items hit 100%, push and gh pr create but DO NOT MERGE TO MAIN — wait for code review and automated tests — then output <promise>v<VERSION> DONE</promise>."
```

Concrete: for project `acme` at version `1.4.0` with 12 unfinished items, `<PROJECT>`=`acme`,
`<VERSION>`=`1.4.0`, `<N>`≈`15`. The loop stops when the version hits 100% (it outputs the
promise) or `--max-iterations` is reached; the work lands on `roadmap/v1.4.0` as a PR.

See the "Fully hands-off" section of [`commands/roadmap/build.md`](../../../commands/roadmap/build.md).
