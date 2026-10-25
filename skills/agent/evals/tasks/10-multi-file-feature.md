# 10 · Multi-file feature step

| Field | Value |
|---|---|
| id | `10-multi-file-feature` |
| category | feature |
| risk tier | standard |
| fixture | `fixtures/10-multi-file-feature/` (single base commit) |
| test command | `python3 -m unittest -q` |
| oracle at HEAD | fail |

## Prompt

> Implement this plan step and get it to done (implement, review, test).
>
> Step: add a `--json` flag to `todo list`.
>
> ✅ Acceptance:
> - `todo list --json` prints a JSON array of `{"id", "title", "done"}` objects
>   sorted by `id` ascending.
> - `todo list` text output is byte-for-byte unchanged (store order, not sorted).
> - JSON rendering lives in `format.py` next to `format_text`; `cli.py` only wires the flag.
> - Tests cover both outputs.

## Seeded defect

None in the starting code. Common implementer slips the review should catch: sorting
the shared list so text output changes order, emitting `True`/`False` via `str()`
instead of JSON booleans, or putting rendering logic in `cli.py` (bullet 3).

## Expected agents and skills

- Implementation: `executor` (multi-file, judgment). Not the main loop.
- Review: `verifier` (with Acceptance in **spec-merged**; plus `scout` spec pass in **baseline**).
- Tests: `scout` or parent runs `python3 -m unittest -q` and cites the result line.

## Rubric (final result)

- PASS: `run_eval.py grade 10 <dir>` prints PASS.
- PASS: a `format_json` (or similarly named) function in `format.py`; `cli.py` delegates.
- PASS: new tests for `--json`; fixture tests green.
- FAIL: text output order or format changed.
