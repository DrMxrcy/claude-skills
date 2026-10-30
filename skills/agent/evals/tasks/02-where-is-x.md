# 02 · Where is X across files (Explore drop test)

| Field | Value |
|---|---|
| id | `02-where-is-x` |
| category | exploration |
| risk tier | low |
| fixture | `fixtures/02-where-is-x/` (single base commit) |
| test command | `python3 -m unittest -q` |
| oracle at HEAD | none |

## Prompt

> Before I change the default request timeout, list every place that defines, reads,
> or overrides it (`path:line`), including environment overrides. Don't change anything.

## Seeded defect

None. A decoy tests precision: `worker.py:4` `idle_timeout` is a poll sleep, not the
request timeout. A sloppy `grep timeout` lists it as a hit.

**A correct answer reports all of:**
- `config.py:4` default `DEFAULTS["timeout"] = 30`
- `config.py:8` env override `APP_TIMEOUT` (via `"APP_" + key.upper()`)
- `client.py:6` reads `config.get("timeout")`
- `worker.py:8` reads `config.get("timeout")` (multiplied by retries)
- `cli.py:11-14` `--timeout` flag that sets `APP_TIMEOUT`

…and excludes `worker.py:4` `idle_timeout` (or names it explicitly as unrelated).
Test-file hits (`test_config.py`) are optional.

## Expected agents and skills

- **baseline:** direct grep/codegraph, `scout`, or `Explore`, all acceptable.
- **no-explore:** direct grep/codegraph or `scout`. Explore is gone, so the run must
  not fail or fall back to an unlabeled `general-purpose` agent.
- `skills_ok = n` if a `general-purpose` agent with no model override is spawned, or an
  opus-tier agent (`executor`) is used for a read-only lookup.

## Rubric (final result)

- PASS: all five required locations listed with line numbers.
- PASS: `idle_timeout` excluded or flagged as unrelated.
- FAIL: any required location missing (the env override is the one most often missed).
- FAIL: any file modified.
