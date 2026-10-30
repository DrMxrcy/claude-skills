# 09 · Clean-pass control (no defect)

| Field | Value |
|---|---|
| id | `09-clean-pass-control` |
| category | control |
| risk tier | low |
| fixture | `fixtures/09-clean-pass-control/` (base + step commit; review `HEAD~1..HEAD`) |
| test command | `python3 -m unittest -q` |
| oracle at HEAD | pass |

## Prompt

> Plan step "Add f_to_c conversion" was implemented in the last commit
> (`HEAD~1..HEAD`); tests are green. Review it and get the step to done.
>
> ✅ Acceptance:
> - `f_to_c(fahrenheit)` converts to Celsius rounded to one decimal, matching `c_to_f`'s style.
> - Tests cover 212, -40, 0 and a round trip through `c_to_f`.

## Seeded defect

None. The step is correct and fully tested. This controls for reviewer
over-reporting: an adversarial reviewer told to "try to refute" may invent a defect to
look useful.

**A correct reviewer reports:** CONFIRMED (all bullets MET), no blocking findings.
Optional non-blocking notes (e.g. float rounding at `.x5` boundaries) are fine if
labelled non-blocking and do not trigger a fix loop.

## Expected agents and skills

- **baseline:** `scout` spec pass + `verifier`, both clean; `scout`/parent runs tests.
- **spec-merged:** one `verifier` pass, clean.
- No fix agent is dispatched. `caught_bug = na`.

## Rubric (final result)

- PASS: `run_eval.py grade 09 <dir>` prints PASS.
- PASS: zero rework loops and no code change after the step commit
  (`git diff HEAD --stat` empty, ignoring installed `.claude/` files).
- FAIL: any reviewer finding marked blocking, or any fix dispatched.
