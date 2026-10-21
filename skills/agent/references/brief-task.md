# Subagent brief — task part

Everything variable. Fill the placeholders and append this after `brief-common.md`.
Inline the plan body and acceptance lines; pass a file path instead only when the file
is over roughly 300 lines.

## Task

- Role: {{role}} (executor | verifier | scout | mech-executor | security-executor)
- Repo: {{repo_path}}
- Branch / worktree: {{branch_or_worktree}}
- Plan: {{plan_id}} — {{plan_title}} ({{plan_path}})
- Step: {{step_number}} — {{step_text}}

## Plan body (inline)

{{plan_body_excerpt}}

## Acceptance

{{acceptance_lines}}

## Files to touch

{{files}}

## Commands

- Test: `{{test_command}}`
- Build / typecheck / lint: `{{build_command}}`

## Review scope (reviewers only)

- Diff range: `{{diff_range}}` (e.g. `git diff <baseline-sha>`; on a re-verification,
  the baseline is the tree at the last verdict, so only the fix is in scope)
- Findings sent back last round: {{prior_findings}}

## Constraints

{{constraints}}
