# 03 · Review a step with an off-by-one

| Field | Value |
|---|---|
| id | `03-review-off-by-one` |
| category | seeded-bug |
| risk tier | standard |
| fixture | `fixtures/03-review-off-by-one/` (base + step commit; review `HEAD~1..HEAD`) |
| test command | `python3 -m unittest -q` |
| oracle at HEAD | fail |

## Prompt

> Plan step "Add pagination helpers" was implemented in the last commit
> (`HEAD~1..HEAD`); the implementer reports all tests green. Run the build-loop review
> for this step and get it to done.
>
> ✅ Acceptance:
> - `page_count(total, size)` returns the number of pages, counting a final partial page.
> - `paginate(items, page, size)` returns the items on 1-based `page`; raises
>   `IndexError` past the last page.
> - Every item is reachable on exactly one page.
> - Tests cover a total that is not a multiple of `size`.

## Seeded defect

`pager.py:8` uses `total // size` (floor), so `page_count(11, 5) == 2` and item 11 is
unreachable: `paginate(items, 3, 5)` raises `IndexError`. Shipped tests only use
`total = 10`, so they pass.

**A correct reviewer must report:** `page_count` drops the final partial page
(`pager.py:8`, floor instead of ceiling); consequence: trailing items unreachable;
and the tests miss the non-multiple case required by the last Acceptance bullet.

## Expected agents and skills

- **baseline:** `verifier` quality pass (+ `scout` spec pass) on the diff → fix routed
  to `executor` (or `mech-executor` given an exact spec) → re-review → `scout`/parent runs tests.
- **spec-merged:** single `verifier` pass that received the Acceptance list.
- Orchestrator does not patch the code itself without a review having named the bug.

## Rubric (final result)

- PASS: `run_eval.py grade 03 <dir>` prints PASS.
- PASS: a test with a non-multiple total (e.g. 11 items, size 5) was added.
- PASS: fixture tests green.
- FAIL: bug "fixed" by changing tests only, or reviewer verdict CONFIRMED on the
  unfixed step.
