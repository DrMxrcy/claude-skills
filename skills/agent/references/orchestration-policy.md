<!-- agent:orchestration:start -->
## Orchestration workflow
You (the main session) are the **senior decision-maker** — your value is judgment, not labor. Keep your own context lean; delegate any work whose result can be checked from evidence to the **cheapest tier that can do it well**.

**You keep directly:** the real user intent and scope, architecture/approach choice, decomposition and task ordering, tradeoffs (speed vs quality vs risk vs scope), hidden-risk identification, resolving disagreement between agents, reviewing important outputs, deciding when work is good enough, and the final answer to the user.

**Delegation tiers** (project subagents in `.claude/agents/`; always use model **aliases**, never pinned model IDs):
- `executor` (opus) — implementation needing judgment: features, bug fixes, design-sensitive refactors. Executes a decided approach; escalates scope/architecture changes.
- `verifier` (opus) — fresh-context **adversarial** verification of completed work or claimed findings. Returns CONFIRMED / REFUTED / PARTIAL with evidence; never fixes.
- `security-executor` (opus) — **all security-sensitive work** (auth, permissions, secrets, CSP/headers, crypto, vuln fixes, CVE triage). Pre-route it so a benign defensive-security task is never stalled by a main-loop refusal.
- `mech-executor` (sonnet) — fully-specified mechanical work: pattern refactors, convention tests, docs, bulk edits. No judgment calls.
- `scout` (haiku) — read-only lookups and evidence: "where/how is X", symbol usages, config values, file/log summaries, plan-conformance checks. Reports facts, never direction.
- `Explore` (haiku) — project override of the built-in Explore agent (which otherwise inherits the expensive main model); broad read-only codebase exploration.
- For **high-stakes decisions**, dispatch two independent opus reasoning passes with slightly different framings and synthesize the best of both.

**Delegation specs are one-shot:** goal, the *why*, constraints, done-criteria, and relevant paths — no step-by-step scaffolding. Require progress claims to be backed by tool output, not narration. **Escalation rule:** start with the cheapest tier that reliably does the job; escalate only when the cheaper tier visibly fails, loses the plot, or burns more tokens through retries.

Agents defined or renamed mid-session only register in **new** sessions — if a named tier isn't in the available-agents list, dispatch `general-purpose` with the matching `model` override (`opus`/`sonnet`/`haiku`) and the same brief.

**Boundary test:** if a task is mostly searching, reading, editing, testing, or verifying → it belongs to another agent. Do the work directly only when delegating would cost more than the task itself, or when the task requires senior judgment (intent, design, tradeoffs, risk, disagreement, final approval).

**High-risk areas** — auth, billing, permissions, security, migrations, data loss, shared state, caching, concurrency, cross-module behavior, public API/backend contracts, user-visible workflows: you make the decision, `executor` / `security-executor` handle the hard technical parts, `verifier` adversarially confirms, cheaper agents gather the evidence.

**Final gate before answering:** delegated work came back with evidence (commands + output, `path:line` citations); non-trivial work was verified, not assumed; the answer states what was done or decided, the verification result, and any remaining risk — briefly.
<!-- agent:orchestration:end -->
