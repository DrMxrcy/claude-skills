# 08 · Mechanical bulk rename

| Field | Value |
|---|---|
| id | `08-mech-bulk-rename` |
| category | mechanical |
| risk tier | low |
| fixture | `fixtures/08-mech-bulk-rename/` (single base commit) |
| test command | `python3 -m unittest -q` |
| oracle at HEAD | fail |

## Prompt

> Rename `get_usr` to `get_user` everywhere: definition, every caller, tests, and
> `README.md`. No compatibility alias, no behavior change. Tests must stay green.

## Seeded defect

None. The task is fully specified across 5 files (`store.py`, `views.py`,
`report.py`, `test_store.py`, `README.md`), including a `store.get_usr` attribute
call and two prose mentions. This measures whether the cheap mechanical tier finishes
it without rework.

## Expected agents and skills

- **baseline / spec-merged / no-explore:** `mech-executor` (haiku) does the edit;
  a sonnet override is acceptable after one stall. A reviewer pass is optional here.
- **mech-folded:** whatever tier the folded policy names; compare tokens + rework
  against baseline (the mech-executor hold-or-fold decision reads this task).
- `skills_ok = n` if `executor`/`security-executor` (opus) writes the rename.

## Rubric (final result)

- PASS: `run_eval.py grade 08 <dir>` prints PASS (no `\bget_usr\b` left in the five
  files; `get_user` works for all callers; README updated).
- PASS: fixture tests green.
- FAIL: an alias `get_usr = get_user` left in place, or unrelated edits in the diff.
