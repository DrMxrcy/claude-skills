# 04 · Review a step that forgot the auth check

| Field | Value |
|---|---|
| id | `04-review-missing-auth` |
| category | seeded-bug (security) |
| risk tier | high (permissions) |
| fixture | `fixtures/04-review-missing-auth/` (base + step commit; review `HEAD~1..HEAD`) |
| test command | `python3 -m unittest -q` |
| oracle at HEAD | fail |

## Prompt

> Plan step "Add a delete_project admin route" was implemented in the last commit
> (`HEAD~1..HEAD`); tests are green. Review it and get the step to done.
>
> ✅ Acceptance:
> - `handle(actor, "delete_project", name)` deletes the project for admins (204) and
>   returns 404 for an unknown project.
> - Non-admins and unknown actors get 403 and the project is not deleted.
> - Tests cover the forbidden case.

## Seeded defect

`api.py:22` `delete_project` never calls `require_admin(actor)` (`delete_user` does, at
`api.py:17`). Any actor, including unknown ones, can delete any project. The step's
tests only exercise the admin path.

**A correct reviewer must report:** missing `require_admin` in `delete_project`
(`api.py:22-26`), so non-admins can delete projects; no negative test for the forbidden
case. Rating it a style nit or "consider adding" is not a catch.

## Expected agents and skills

- Reviewer: `verifier` (receives Acceptance in **spec-merged**; `scout` spec pass also in **baseline**).
- Fix: routed to `security-executor` (permissions = high-risk), not `executor` or the main loop.
- High-risk second pass: `verifier` with an opus override (or cross-provider reviewer) on the fix.
- `skills_ok = n` if the fix goes to `executor`/`mech-executor`, or no second pass runs.

## Rubric (final result)

- PASS: `run_eval.py grade 04 <dir>` prints PASS (non-admin and unknown actor → 403,
  project kept; admin still 204).
- PASS: a forbidden-case test was added to `test_api.py`.
- NOTE (recorded in `--notes`, not pass/fail): whether the check runs before the
  existence check, so non-admins cannot enumerate projects via 404 vs 403.
- FAIL: authorization added only in tests or only in `handle` for this one action
  name with a hard-coded string compare.
