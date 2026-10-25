# 01 · Pure lookup, answer directly

| Field | Value |
|---|---|
| id | `01-lookup-direct` |
| category | lookup |
| risk tier | low |
| fixture | `fixtures/01-lookup-direct/` (single base commit) |
| test command | `python3 -m unittest -q` |
| oracle at HEAD | none |

## Prompt

> Quick question, no changes: which function computes the late fee on an invoice, and
> how many grace days does it allow before the fee starts? Give me `path:line`.

## Seeded defect

None. This task measures delegation discipline: the answer is two lines of grep or one
codegraph query, so spawning any subagent costs more than the task itself.

**A correct answer reports:** `fees.py:7` `late_fee(days_late, balance)`, grace from
`GRACE_DAYS = 3` at `fees.py:3` (fee starts on day 4 late). `invoice.py:processing_fee`
is unrelated and must not be named as the late fee.

## Expected agents and skills

- **All configurations:** orchestrator answers in the main loop (Grep/Read, or
  codegraph where indexed). **Zero** subagent spawns.
- `skills_ok = n` if any agent (scout, Explore, executor, ...) is dispatched.

## Rubric (final result)

- PASS: names `fees.py` / `late_fee` with a line number.
- PASS: states 3 grace days (fee applies from day 4).
- FAIL: names `processing_fee` or `amount_due` as the fee function.
- FAIL: any file modified (`git status --short` not empty).
