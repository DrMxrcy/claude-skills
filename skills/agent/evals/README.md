# Golden-task evals for the agent fleet

Ten small, fixed tasks that measure what the fleet actually does. Run them before any fleet change
(folding an agent, merging review passes, a permanent tier change). This is the eval gate from
`references/orchestration-policy.md`: fold one agent at a time, fold only if the folded
configuration scores equal or better, and grade the **final result**, not the subtask.

Dev-only: `install.sh` and the agy plugin build strip `evals/` from installed copies.

## Layout

```
evals/
  run_eval.py            stdlib helper: list / materialize / grade / record / report
  tasks/NN-slug.md       one golden task each (prompt, seeded defect, agents, rubric)
  fixtures/NN-slug/      tiny self-contained repo the task runs against
    _step/               optional: committed on top as HEAD (the "step under review")
    _oracle/             hidden oracle tests, run only by `grade`
    _solution/           hidden reference fix, used only by the self-tests
  results/ledger.jsonl   your runs (gitignored)
```

| # | Task | Category | Tests |
|---|---|---|---|
| 01 | lookup-direct | lookup | no delegation for a trivial lookup |
| 02 | where-is-x | exploration | finding every usage without `Explore` |
| 03 | review-off-by-one | seeded bug | reviewer catches a floor-vs-ceiling page count |
| 04 | review-missing-auth | seeded bug, high risk | reviewer catches a missing admin check; fix goes to `security-executor` |
| 05 | security-path-traversal | security fix | routing to `security-executor`; complete containment fix |
| 06 | review-hollow-test | seeded bug | reviewer catches a test that asserts nothing (and the bug it hides) |
| 07 | spec-unmet-acceptance | spec conformance | one Acceptance bullet silently unmet (does the spec pass survive a merge into `verifier`?) |
| 08 | mech-bulk-rename | mechanical | cheap tier finishes a 5-file rename without rework |
| 09 | clean-pass-control | control | reviewer must **not** invent a defect |
| 10 | multi-file-feature | feature | full implement → review → test loop across 3 files |

## Configurations

A configuration is one fleet + policy state. Name it after the change under test:

| Config | Fleet state |
|---|---|
| `baseline` | current fleet: scout spec pass + verifier quality pass, `Explore` present |
| `spec-merged` | one `verifier` pass that receives the ✅ Acceptance list; scout runs tests only |
| `no-explore` | `spec-merged` plus `Explore` removed |
| `mech-folded` | candidate: `mech-executor` work routed to another tier |

Each config is a git ref of this repo (a branch or worktree) that you install from.

## Running one task

Run **every task at least twice per configuration.** A failure can show up in only one of two runs.

```sh
E=skills/agent/evals
dir=$(python3 $E/run_eval.py materialize 03 /tmp/eval-03-baseline-r1)   # fresh git repo
(cd "$dir" && bash /path/to/<config-ref>/install.sh --project --only=agent)
# Start a NEW Claude Code session in $dir (agents register only at session start),
# paste the task's ## Prompt block verbatim, and let it run to completion.
python3 $E/run_eval.py grade 03 "$dir"      # PASS / FAIL / NO-ORACLE
```

Don't steer mid-run. If the orchestrator asks a question, answer only from the task file, and count the question as a rework loop.

## Metrics (one ledger row per run)

| Field | How to measure |
|---|---|
| `caught_bug` | `y` if a reviewer report (before any fix) names the task's **must report** defect at the right place; `n` otherwise; `na` for tasks with no seeded defect (01, 02, 05, 08, 09, 10) |
| `skills_ok` | `y` if the agents and skills in the transcript match the task's *Expected agents and skills* for this config, and no forbidden tier was used |
| `tokens` | total tokens for the session, main loop plus subagents (`/cost`, or the session usage log) |
| `wall_s` | seconds from submitting the prompt to the final answer |
| `rework` | count of fix → re-review loops, plus any clarifying question the run needed |
| `rubric_pass` | `y` only if **every** PASS bullet holds and no FAIL bullet triggers (includes `grade`) |

```sh
python3 $E/run_eval.py record --task 03 --config baseline \
  --caught-bug y --skills-ok y --tokens 48210 --wall-s 312 --rework 1 --rubric-pass y \
  --notes "verifier cited pager.py:8"
# --run is optional (auto-numbers per task+config); --ledger PATH overrides the default
```

## Ledger format

`results/ledger.jsonl` holds one JSON object per line, append-only:

```json
{"ts": "2026-10-25T14:02:11Z", "task": "03-review-off-by-one", "config": "baseline", "run": 1,
 "caught_bug": true, "skills_ok": true, "tokens": 48210, "wall_s": 312.0, "rework": 1,
 "rubric_pass": true, "notes": "verifier cited pager.py:8"}
```

`caught_bug` is `null` when the task has no seeded defect. The ledger is gitignored. To keep a
comparison, paste the `report` output into the plan step's evidence.

## Reading the report

```sh
python3 $E/run_eval.py report
```

It prints one row per task × config: runs, rubric pass rate, caught rate, skills-ok rate, mean
tokens, wall time and rework. It then prints per-config totals. Flags:

- `FLIPPED:<metric>` means runs of the same task and config disagree. **Inspect these first.** Open
  both transcripts and find where they diverged (which agent was dispatched, what the brief said,
  what the reviewer missed). A flip is a reliability finding even when the average looks fine.
- `FEW-RUNS` means fewer than 2 runs. The row doesn't count toward a fold decision yet.

To decide a fold, compare the two configs task by task. Look first at `rubric_pass` and `caught_bug`
(quality must not drop), then at tokens + rework (a cheaper tier that needs rework isn't cheaper).
Equal or better on quality with lower cost means fold. Worse on any seeded-bug task means keep.

## Self-tests

`tests/test_agent_evals.py` checks that every task file has its required sections, that every
fixture's own tests pass at HEAD, and that each oracle fails at HEAD where a fix is needed and
passes on the hidden reference solution. Run it after editing any task or fixture.
