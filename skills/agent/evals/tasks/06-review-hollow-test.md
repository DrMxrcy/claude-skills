# 06 · Review a step whose test asserts nothing

| Field | Value |
|---|---|
| id | `06-review-hollow-test` |
| category | seeded-bug |
| risk tier | standard |
| fixture | `fixtures/06-review-hollow-test/` (base + step commit; review `HEAD~1..HEAD`) |
| test command | `python3 -m unittest -q` |
| oracle at HEAD | fail |

## Prompt

> Plan step "Add unique_slug with numeric suffixes" was implemented in the last commit
> (`HEAD~1..HEAD`); tests are green. Review it and get the step to done.
>
> ✅ Acceptance:
> - `unique_slug(text, existing)` returns `slugify(text)` when unused.
> - Otherwise returns the first free of `<slug>-2`, `<slug>-3`, ...
> - A test asserts the exact suffixed value.

## Seeded defect

`test_slug.py:16` `self.assertTrue(result)` passes for any non-empty string, so the
suffix test checks nothing. It hides a real bug: `slug.py:14` starts at `n = 1`, so
`unique_slug("Hello", {"hello"})` returns `hello-1`, not `hello-2`.

**A correct reviewer must report:** the hollow assertion at `test_slug.py:16` (the
last Acceptance bullet is NOT MET). Full credit also names the `n = 1` suffix bug at
`slug.py:14`; `caught_bug = y` requires at least the hollow test.

## Expected agents and skills

- **baseline:** `scout` spec pass should mark bullet 3 NOT MET; `verifier` should flag
  the hollow test and ideally run a probe that exposes `hello-1`.
- **spec-merged:** single `verifier` pass must find both.
- Fix: `executor` or `mech-executor` with an exact spec; re-review.

## Rubric (final result)

- PASS: `run_eval.py grade 06 <dir>` prints PASS.
- PASS: suffix test now asserts exact values (`hello-2`, and `hello-3` when `-2` is taken).
- FAIL: only the test was strengthened to match buggy output (`hello-1`).
