# 05 · Security fix: path traversal

| Field | Value |
|---|---|
| id | `05-security-path-traversal` |
| category | security-fix |
| risk tier | high (security) |
| fixture | `fixtures/05-security-path-traversal/` (single base commit) |
| test command | `python3 -m unittest -q` |
| oracle at HEAD | fail |

## Prompt

> Bug report: `/download?name=../../etc/passwd` returns system files. Fix
> `read_upload(root, name)` in `files.py` so it can only ever read files inside the
> upload root; raise `PermissionError` for any name that resolves outside it. Add
> regression tests. Normal nested uploads (`a/x.txt`) must keep working.

## Seeded defect

The vulnerability is the task itself: `files.py:7` joins untrusted `name` onto `root`
with no containment check (`..`, absolute paths, and symlinks all escape).

**A correct fix/review must cover:** `..` traversal, absolute `name` (which
`os.path.join` lets replace `root`), symlinks inside root pointing outside (needs
`realpath`/`resolve`, not string normalisation), and the sibling-prefix trap
(`/uploads-evil` passes a naive `startswith("/uploads")` check; use `commonpath` or
`Path.is_relative_to`).

## Expected agents and skills

- Implementation: `security-executor`. Never the main loop, `executor`, or `mech-executor`.
- Review: `verifier`, plus a high-risk second pass (opus override or cross-provider).
- `skills_ok = n` if the fix is written by anything other than `security-executor`.

## Rubric (final result)

- PASS: `run_eval.py grade 05 <dir>` prints PASS (all five oracle cases).
- PASS: regression tests added that fail on the original `files.py`.
- FAIL: fix is a blacklist (`".." in name`) that misses absolute paths or symlinks.
- FAIL: `startswith` prefix check without a path-separator boundary.
