# 07 · Spec conformance: one Acceptance bullet silently unmet

| Field | Value |
|---|---|
| id | `07-spec-unmet-acceptance` |
| category | spec-conformance |
| risk tier | standard |
| fixture | `fixtures/07-spec-unmet-acceptance/` (base + step commit; review `HEAD~1..HEAD`) |
| test command | `python3 -m unittest -q` |
| oracle at HEAD | fail |

## Prompt

> Plan step "Add export_orders CSV export" was implemented in the last commit
> (`HEAD~1..HEAD`); the implementer says all acceptance criteria are met and tests are
> green. Review it and get the step to done.
>
> ✅ Acceptance:
> - Output starts with the header row `id,date,total`.
> - Totals are formatted with exactly two decimals.
> - Rows are sorted by `date` ascending, regardless of input order.
> - The input list is not mutated.

## Seeded defect

The code is clean and its tests pass, but bullet 3 is not implemented:
`export.py:11` iterates `orders` in input order (`orders.SAMPLE` is unsorted). No test
covers ordering. The commit message claims everything is met. This is the case the
`scout` spec pass exists for; it measures whether folding that pass into `verifier`
keeps the catch.

**A correct reviewer must report:** Acceptance bullet 3 NOT MET (no sort,
`export.py:11`), with evidence (e.g. output for `SAMPLE` starts with id 3). A fix that
sorts in place (`orders.sort`) would break bullet 4. Flag it if proposed.

## Expected agents and skills

- **baseline:** `scout` spec pass → NOT MET on bullet 3; `verifier` quality pass.
- **spec-merged:** one `verifier` pass that received the Acceptance list and reports
  per-bullet MET / NOT MET.
- Fix: `executor` or `mech-executor`; re-review.

## Rubric (final result)

- PASS: `run_eval.py grade 07 <dir>` prints PASS (sorted, unmutated).
- PASS: an ordering test was added.
- FAIL: reviewer verdict CONFIRMED / all-MET on the unfixed step.
