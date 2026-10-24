---
name: roadmap
description: >
  Keep AI coders (Claude Code, Grok Build, others) on-task while shipping high-quality code.
  Use when planning features/bugs/refactors, tracking a project roadmap, breaking work into
  trackable units, building with quality-first multi-agent review, marking done, or cutting a
  version. Maintains versioned ROADMAP.md + .roadmap/ via a deterministic CLI. Triggers on
  "roadmap", "plan this feature", "track this", "build the next item", "mark done", "cut a
  version", $roadmap, /roadmap, /roadmap-next, /roadmap-build, /roadmap-status.
argument-hint: "[status|next|build|plan|idea|init|done|review|release|sync|…] [args]"
---

# Roadmap

**Mission:** keep AI coders on-task and ship high-quality code — on Claude Code, Grok Build,
or any agent that loads this skill. Plans and checklists are the rails; subagent implement +
dual review is the default build quality bar; the CLI is the only way the dashboard moves.

A persistent tracking layer on top of your planning skills. You decide WHAT; the
`roadmap.py` CLI makes every mechanical edit so the dashboard never drifts.

**Always mutate state through the CLI — never hand-edit ROADMAP.md.** The `roadmap.py` CLI
ships with the skill under the host agent's skills dir (`.claude`, `.grok`, `.agents`, or
Antigravity plugins — project-level or home) — **do not search or glob for it**; probe those fixed candidates.
Resolve it once and reuse `$RM` (run from the project root):

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents" "$HOME/.gemini/config/plugins/roadmap" ".agents/plugins/roadmap"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
python3 "$RM" <command>
```

## Invocation (agent-specific names)

| Action | Claude Code | Grok Build | OpenAI Codex | Antigravity (`agy`) |
|---|---|---|---|---|
| Init | `/roadmap-init` | `/roadmap-init` | `$roadmap init` | `/roadmap-init` |
| Plan | `/roadmap-plan …` | `/roadmap-plan …` | `$roadmap plan …` | `/roadmap-plan …` |
| Next item | `/roadmap-next` | `/roadmap-next` | `$roadmap next` | `/roadmap-next` |
| Build | `/roadmap-build …` | `/roadmap-build …` | `$roadmap build …` | `/roadmap-build …` |
| Status | `/roadmap-status` | `/roadmap-status` | `$roadmap status` | `/roadmap-status` |
| (rest) | `/roadmap:<cmd>` | `/roadmap-<cmd>` | `$roadmap <cmd>` | `/roadmap-<cmd>` |

**When recommending a command to the user, always list hyphen (Grok / AGY) and/or bare form —
never colon-only.** Grok and AGY only discover flat `commands/roadmap-*.md`; nested
`commands/roadmap-next.md` → `/roadmap-next` does **not** show in Grok's menu.
`--auto` only on **build** (not next).

Codex has a fixed built-in slash-command list; skills do not add dynamic slash commands.
Use `$roadmap <cmd>` or select Roadmap from Codex's skills UI.

**Also works on Claude/Grok:** invoke this skill with a subcommand as the argument —
`/roadmap next`, `/roadmap build 1.0.0`, `/roadmap status` — and route exactly like the
dedicated command. On Codex, use the equivalent `$roadmap next`, `$roadmap build 1.0.0`,
or `$roadmap status`.

## Subcommand routing (when invoked with arguments)

If the user message / `$ARGUMENTS` starts with one of these verbs, run that flow and stop
(do not fall through to generic phase detection):

| First token | Do this |
|---|---|
| `status` | `roadmap.py status` (+ summarize) |
| `serve` | `roadmap.py serve` — local live web dashboard (SSE push, read-only; one per project): full-text search, version pages, dependency graph, keyboard shortcuts (`?`) and a `Ctrl/⌘ K` palette, copy-command buttons on plan pages; `serve --all` (the default outside any project) — one home page for every registered project |
| `projects` | `roadmap.py projects [--forget NAME] [--json]` — list / prune the per-user project registry `serve --all` shows |
| `sync` | `roadmap.py sync` |
| `next` | Build the lowest-id unfinished item in the **current** version (same as `/roadmap-next`) |
| `handoff` | Multi-coder switch brief (sync state when leaving Claude for Grok or vice versa) |
| `build` | Build the rest of the args (id / version / empty / flags) — same as `/roadmap-build` |
| `plan` | Brainstorm remaining args into a tracked plan |
| `idea` | Park remaining args in the Idea Incubator |
| `bug` | Route a bug: `roadmap.py bug "<title>" [--found-in ID] [--observed TEXT]` — never the incubator |
| `init` | Initialize / adopt |
| `done` | Mark step/item done |
| `remove` / `retarget` / `review` / `release` / `changelog` / `catchup` / `reevaluate` / `tidy` / `upgrade` | Follow that command's flow |

If the user explicitly invokes bare `$roadmap` with no task text, print this compact menu
and stop; Codex skill mentions do not provide nested autocomplete:

```text
$roadmap status                 Show roadmap progress
$roadmap next                   Build one unfinished item
$roadmap build [id|version]     Build an item or version (`--auto` chains items)
$roadmap plan <idea>            Create a tracked plan
$roadmap idea <idea>            Park an idea
$roadmap review [version]       Review completed work
```

If there are no args on bare `/roadmap` in Claude/Grok, use **Phase routing** below.

## Working guardrails (apply whenever this skill is active)
> `init`/`upgrade` inject a **compact core** of these rules into `CLAUDE.md` + `AGENTS.md`
> (between the `roadmap:rules` markers) to keep per-session context small. The long form is
> here and in [`references/quality-build.md`](references/quality-build.md) /
> [`references/state-model.md`](references/state-model.md) — read them on demand.

- At the start of a session, run `roadmap.py orient` / `handoff` (or status) before writing code.
- New features or found bugs become roadmap items (`/roadmap-plan`) before coding; park stray ideas in the Idea Incubator — nothing is built off-roadmap.
- **Bugs never go in the incubator** (nothing tracks them there): `roadmap.py bug "<title>" --found-in <id> [--observed TEXT]`. Found during an in-flight item's build → a `Fix:` step on that plan (claim stage `fixing`), no new item; found in shipped work → a `bug` item linked to its origin. `idea` refuses titles that read like bug reports (`--force` overrides).
- **Incubator hygiene — ROADMAP.md stays skimmable.** One bullet per parked idea, added via
  `roadmap.py idea --title "..."`. Long-form content — brainstorm output, deferred review
  findings, phase sketches, option analyses — goes to a linked `.roadmap/notes/` file
  (`idea --body/--body-file`) or a spec under `docs/`, and gets ONE linked bullet; never
  paste prose walls into ROADMAP.md. `orient` and `tidy` warn when the free-form region
  (everything outside the auto block) outgrows these bounds; groom it back with `/roadmap-tidy` · `/roadmap-tidy` (`roadmap.py tidy` prints the
  report — the only sanctioned direct edit of the free-form region, never the auto region).
  The incubator itself may live in an external file (`settings.incubatorFile`, usually
  `.roadmap/IDEAS.md` via `tidy --externalize`) — the CLI resolves the location; groom
  and read ideas wherever it points.
- One trackable item at a time. No multitasking across features/bugs.
- No functional code without an active plan file in `.roadmap/plans/`.
- Run the build/tests for a step BEFORE you `check` it.
- Commit code + roadmap updates together in one micro-commit.

## Switching between AI coders (Claude ↔ Grok ↔ …)

The **git repo** is the shared brain — not chat history. **`handoff` is optional** (a
nicer brief). Rate limits, crashes, and hard kills usually mean you never ran it — that
is fine if you micro-committed along the way.

| Shared in git | Owner |
|---|---|
| `ROADMAP.md`, `.roadmap/`, `CHANGELOG*.md` | CLI only |
| Plan checklists / progress | CLI `check` |
| `CLAUDE.md` + `AGENTS.md` rules block | `init` / `upgrade` |

**Ideal leave (when you can):** micro-commit after each checked step; optional
`python3 "$RM" handoff` + push. Never keep a private parallel plan outside `.roadmap/` —
another agent cannot read it.

**Abrupt leave (rate limit / kill — no handoff):**

1. Open the other agent in the **same repo**.
2. `git status` — commit anything the previous agent left (code + roadmap if present).
3. `python3 "$RM" orient` or `handoff` (SessionStart orient often already ran).
4. Drift warning → `/roadmap-catchup` after tests for steps done but not checked.
5. Read the active plan’s **next unchecked step** — continue quality-first build.
   Do **not** re-derive the plan from the dead chat.

**Why this works:** every `check` + micro-commit moves truth into git. The dead session’s
context is disposable; unfinished work is either committed or still in the working tree.

Install both agents at the same skill version: `./install.sh --global --both`.

## Phase routing
On invocation, detect state and pick a phase:

1. **No `.roadmap/` directory?** → Initialize.
   - If the repo already has code: `roadmap.py init --adopt --name "<name>"`, then survey
     existing structure (use codegraph/MCP if present, else Glob/Grep) and ingest any
     `TODO.md` / README roadmap / existing `ROADMAP.md` via `roadmap.py import <path>`.
   - Greenfield: `roadmap.py init --name "<name>"`.

2. **User brings an idea/plan** → Break it down.
   - Not ready to build yet? Park it instead: `roadmap.py idea --title "<one-liner>"
     [--body-file <write-up>]` — one incubator bullet, long content in a linked notes file.
   - Classify **type**: feature | bug | refactor | chore (this picks the template).
   - Choose the **target version** by semver — type drives the bump:
     bug fix → **patch** (x.y.**Z**); backward-compatible feature → **minor** (x.**Y**.0);
     breaking change or a whole new phase → **major** (**X**.0.0). Assign with `--version`
     (omit to use the current version).
   - Research: use **context7** for library/API docs; use project **MCPs** (e.g. codegraph)
     for impact analysis. Degrade gracefully if unavailable.
   - Defer the deep design to **superpowers `brainstorming`/`writing-plans` if installed**;
     otherwise design inline.
   - `roadmap.py new --type <T> --title "<title>" [--version <V>] --note "<user-facing one-liner>" [--audience public|internal]`
     scaffolds the plan file; then fill in scope/blueprint/✅ Acceptance (real pass/fail criteria, not the placeholders)/checklist (tiny testable steps).
     **Titles and notes are artifacts, not chat**: write the `--title` in normal concise
     prose (≤ ~70 chars — it becomes the plan filename slug), **one concern per item** —
     never cram multiple findings into one title; make one item each (or one item with
     checklist steps). Session brevity/persona styles (caveman, terse modes) never apply
     to titles, notes, or any roadmap/changelog text.
     The `--note` is plain-language, benefit-focused (no vendor/tool names, file paths, or
     issue refs) — it becomes the **public** CHANGELOG / App Store "What's New" line.
     `--audience` routes the item: `public` → curated `CHANGELOG.md`, `internal` →
     `CHANGELOG.internal.md`. **Audience is fail-closed**: every type defaults to
     `internal`, and passing `--note` without `--audience` is **refused** — decide where
     the text ships when you write it. Nothing reaches the public changelog without an
     explicit `--audience public`. The CLI auto-runs `sync`. A public note is **refused**
     when it is structurally a **status dump** (ISO dates, "Step N", version refs,
     file/spec paths, issue refs, ALL-CAPS status words like DONE/DESCOPED/ACCEPTED) or
     trips a **wrong-audience tell** (admin/staff surfaces, compliance gates,
     security-disclosure or "now enforced / harder to abuse" phrasing, ops limits,
     dev/API surface) — rewrite it as one plain benefit sentence, mark the item
     internal, or pass `--force`.

3. **Working an item** → Execute (**quality-first multi-agent**).
   - Read the plan file. If it links a **Spec** or **Detailed plan** (e.g. paths under
     `docs/`), open and follow those as the authoritative implementation guide — the
     checklist is the tracking unit; the detailed plan has the how. If the plan has an
     **✅ Acceptance** section, treat those pass/fail criteria as the definition of done and
     pass them to the spec- and quality-review subagents to check the work against.
   - **Default protocol** (also used by `/roadmap-build … --auto`): one item at a time;
     per checklist step → `scout` research **only if the plan doesn't name the files** →
     **one** `executor` implementer (opus) → **spec review** by `scout` (haiku, acceptance
     list → MET / NOT MET) → **one** `verifier` quality review (sonnet, a different model than the author;
     opus or cross-provider second pass only for high-risk steps) → parent runs real tests → only then `roadmap.py check` + commit.
     Never spawn an unlabeled `general-purpose` child — it inherits the frontier model.
     **Workers unavailable or prohibited** (Codex, Gemini, Kimi, Copilot, restricted
     sessions — session rules win over routing): parent continues as sole writer, then runs a
     separate spec-compliance pass and a separate code-quality pass itself (permitted read-only
     reviewers where offered); record which passes were independent vs self-review in the
     evidence, never claim a review that did not happen; same scope, test gates, micro-commits;
     unavailability alone never blocks the task; stay in the host's native tools. Full text:
     `references/quality-build.md` → "Worker availability and review fallback". Parent owns all roadmap CLI; children never
     edit `ROADMAP.md`. Do **not** parallelize implementers on the same tree; `--auto`
     skips user pauses between items, **not** reviews. Full write-up:
     [`references/quality-build.md`](references/quality-build.md).
   - Prefer superpowers **`subagent-driven-development`** when installed; else native
     subagents (Grok `spawn_subagent`, Claude Task). Fallback: `executing-plans` or
     direct TDD with the same gates.
   - `settings.buildRoles` in `.roadmap/config.json` (optional; absent = today's behavior)
     maps build-loop roles to models/agents — `{"implementer": "...", "specReviewer": "...",
     "qualityReviewer": "...", "explorer": "..."}`. Values are free-form host-specific names
     (Claude model, Grok agent, …) and are never validated. When set, `orient`/`handoff`
     print a `Roles:` line and the parent applies the mapping when spawning those
     subagents, best-effort (ignore a role the host cannot honor).
   - After each step passes its test: `roadmap.py check --plan <id> --step <n> --evidence
     "<command>: <real result>"` (the actual test output, not a guess), then commit code +
     roadmap together.
   - Per-item builds run on branch `roadmap/<id>` with `(plan N)` commit tags; the parent records `claim <id> --stage …` as review, fixing, gating, or blocked starts (see `references/quality-build.md` → "In-flight claims").

4. **A version's items are all done** → Review, then release.
   - Verify the phase against its specs + code-review the work (`/roadmap-review`) before
     shipping — confirm every item is genuinely implemented and matches its spec.
   - Confirm each completed item's **audience** (`roadmap.py audience --plan <id> --to
     public|internal`) and give every *public* item a clear user-facing `note`
     (`roadmap.py note --plan <id> --text "<plain-language summary>"`). Items with a
     high-confidence internal tell (admin/operator, compliance, security-disclosure, SEO
     plumbing) **auto-route to the internal changelog** unless you explicitly set them public;
     softer wording tells only warn, but `note` **refuses** a public note that is a status
     dump (dates, step/version refs, paths, shouted status words) unless `--force` — status
     text belongs in the plan checklist, never the changelog. `/roadmap-changelog` audits
     the version and reports
     auto-routings, public items missing a note, and notes worded internally.
   - Give each released version a short public **release-notes blurb**:
     `roadmap.py summary --version <v> --text "..."` — the App Store "What's New" text.
     Keep it stupid simple but friendly: two or three warm sentences for patches ("This
     update smooths out the ride — we've fixed a few display issues and squashed some minor
     bugs."), a warm intro + 3–5 highlights with a friendly closer for big releases.
     When a version has a blurb, `CHANGELOG.md` renders it INSTEAD of item bullets — the
     per-item detail stays in the internal log.
   - Two changelogs render automatically on every `sync`: **`CHANGELOG.md`** (public — each
     version's curated blurb when set; otherwise `audience: public` items, from their `note`
     only, never the raw title; versions with
     internal-only work get one "behind-the-scenes" roll-up line) and
     **`CHANGELOG.internal.md`** (every item, title fallback — the full dev log). Items appear
     once they hit 100%, grouped by version. `release` is **optional** — use it to pin a new
     current version or `git tag` (`--tag`); it no longer owns the changelog. Run
     `roadmap.py changelog [--internal]` anytime to print the latest.
   - After `release` pins a newer current version, shipped versions **collapse to one
     summary line** on the dashboard (count + ship date + changelog pointer) — full detail
     stays in `CHANGELOG.internal.md` and `.roadmap/plans/`. Opt out with
     `settings.collapseShipped: false` in `.roadmap/config.json`.

## Command reference
Anywhere a command takes `--plan ID` (or an id list), the id may be `7`, `#7`, or its typed display id `FEAT-7` / `BUG-7` / `REF-7` / `CHORE-7` (case-insensitive; `ITEM-7` matches any type).
- `init [--name N] [--adopt]` — scaffold (adopt = existing repo, non-destructive)
- `new --type T --title "..." [--version V] [--note "..."] [--audience public|internal]` — scaffold + register a plan
- `idea --title "..." [--body "..." | --body-file PATH] [--force]` — park an idea: one incubator bullet; a body becomes a linked `.roadmap/notes/` file. A title that reads like a bug report (crashes, broken, fails, doesn't work, wrong, missing from, clips, exception, returns 500, …) is refused with a `bug` suggestion; `--force` parks it anyway
- `promote [--match T | --index N] [--type T] …` — lift an incubator bullet into a tracked plan (`--type` defaults to `bug` for a bullet that reads like a bug report, else `feature`)
- `bug "<title>" [--found-in ID] [--observed TEXT] [--version X] [--target FILES]` — route a bug (plan 47): an origin that is not done gets `- [ ] Step N: Fix: <title> -> target: <FILES|TBD>` after its last step plus a dated bullet under `## 🐞 Found during build`, and its claim stage becomes `fixing` (verdict kept; a not-yet-started origin gets no claim) — no new item; a done origin or no `--found-in` files a new `bug` item (same path as `new --type bug`) with Observed pre-filled and `foundIn`/`bugsFound` frontmatter linking both plans
- `note --plan ID --text "..." [--force]` — set an item's user-facing changelog line (lints public notes; refuses status-dump text on public items)
- `ruling ID --text "..." [--by owner|NAME] [--approval]` — append a dated decision to the plan's `## ⚖️ Rulings` section (plan file only; never the changelog or ROADMAP.md); `--approval` marks an owner sign-off, which clears a plan's `approval: required` marker (see `references/state-model.md` → "Rulings")
- `summary --version V --text "..." [--clear] [--force]` — set a version's public release-notes blurb; renders instead of item bullets in CHANGELOG.md (keep it stupid simple)
- `audience --plan ID --to public|internal [--force]` — route an item to the public or internal changelog. Fail-closed: unset audience renders internal-only for every type, and `note`/`new --note` refuse until the audience is explicit. `--to public` refuses high-confidence internal tells — admin/compliance/security-disclosure/plumbing/dev-surface words and disclosure-shaped phrasing — unless `--force`; the same gate applies to `new --audience public` and to saving a note on a public item.
- `check --plan ID --step N [--undo] [--all-done] [--evidence "..."] [--tokens N] [--force]` — flip checkboxes (+ records `last_seen_sha`). `--tokens` writes the token spend beside the evidence line (needs `--evidence`; omit it and the line format is unchanged).
  `--evidence` records how the step was proven done (verify command + result) as a dated
  sub-line under the step — under every step with `--all-done`, ignored with `--undo`.
  `settings.requireEvidence: true` in `.roadmap/config.json` (default `false`) makes a bare
  `check` refuse until you pass it. `check` also refuses while the plan's required sections
  (bug: Observed/Root Cause/Acceptance; others: Core objective/Acceptance —
  `settings.requiredSections`) are still template text, and — with `settings.requireAcceptance`
  on — when the check would complete the item while a ✅ Acceptance criterion is not marked
  met (the refusal lists them); `--force` overrides either gate and records it.
- `accept ID [--line N --evidence "..." [--fail]] [--json]` — the acceptance ledger: bare `accept ID`
  lists the ✅ Acceptance bullets with their number and state (open / met / failed / guard);
  `--line N --evidence` marks bullet N met (`--fail` failed) as a dated `> accepted:` / `> failed:`
  sub-line under it, replacing an earlier marker. `Fails if:` guards are never marked. The spec
  review marks each criterion it finds MET.
- `next [--version V] [--force] [--json]` — next unfinished item (skips incomplete `dependsOn`, and items held by another owner)
- `deps-check --plan ID [--force]` — warn if dependencies are incomplete
- `remove --plan ID` — archive a plan, drop it, demote it to the Idea Incubator
- `depends --plan ID --on IDS [--clear]` — set dependency ordering (`next`/`build` honor it)
- `reorder --version V --order IDS` — set display/build order within a version
- `merge --into KEEP --from IDS` — fold duplicate items into one keeper
- `retarget --to V (--from VERS | --plan IDS)` — re-stamp items onto another version; `retarget ID --version V --split` keeps the ticked steps (the item completes where it is) and moves only the open ones into a linked follow-up item in V
- `wait ID --step N --until DATE|24h|7d [--reason R]` (or `--clear`) — mark a step that can only be verified after time passes (soak, propagation); never done, lane `waiting` once the rest is ticked, due steps listed first by `orient`/`next`/`status`; tick it with `check --step N` once verified. Hours (`24h`, `72h`) set a UTC due time and count down in hours under 2 days. `--on "<person or team>"` waits on someone (user testing, sign-off): without `--until` it is never due or overdue, `orient`/`status`/the digest/the dashboard list it every day as `awaiting <who> (since <date>, N days)`, and it needs attention after `settings.waitNudgeDays` (default 7)
- `orient [--json] [--hook]` — session orientation (project, progress, next item, drift)
- `handoff [--json]` — multi-coder switch brief (orient + git dirty + checklist)
- `handoff --plan ID --pending "<decision>"` — record an open decision in `.roadmap/notes/<id>-handoff.md`; a plain `handoff` refuses while it is open
- `handoff --plan ID --resolve` — close the open decision for that plan
- `orient` also reports the branch, dirty files and the last 5 commits (in handoff mode)
- `drift-check` — nudge if commits landed without a check-off
- `digest [--since 3h|1d|2w|<date>|last] [--format md] [--json] [--conflicts]` — catch up after a break: items completed, steps ticked, claims that moved stage or verdict, items that went stale or blocked, new plans and branches, gate/suite runs and ideas added in the window, an **Awaiting** list (open-ended `wait --on` steps), plus a **needs attention** list (due waiting steps, waits on someone open `settings.waitNudgeDays` or longer, REFUTED verdicts, blocked claims, failing trunk suite, WIP over limit, slot clashes, high-risk conflicts with `--conflicts`, in-flight plans with template text). Read-only; `--since last` (the default) covers changes since your previous digest, `orient` prints a 3-line version since your last session, and the dashboard has a `#/digest` page (see `references/state-model.md` → "Digest")
- `tidy [--json] [--externalize [PATH]]` — report-only free-form/incubator hygiene analysis (long bullets, nested blocks, dupes vs tracked items, bug-like bullets, stray prose, unfinished plans whose required sections are still template); `--externalize` moves the incubator into a linked external file (default `.roadmap/IDEAS.md`; `idea`/`promote`/`remove` follow via `settings.incubatorFile`); `/roadmap-tidy` applies the grooming + idea curation
- `sync` — recompute progress + re-render ROADMAP.md **and both changelogs** (safe anytime)
- `upgrade` — refresh this project's `CLAUDE.md` + `AGENTS.md` rules to the installed skill version
- `changelog [--internal] [--backfill] [--json]` — print the public (or `--internal`) changelog + audit warnings; `--backfill` dates past versions from git tags; `--json` emits structured data (versions, dates, sections, pending flags) for in-app changelog screens / What's New popups
- `release --version V [--tag] [--force] [--with-waiting]` — bump version (optional; changelog is automatic). `--with-waiting` ships items whose only open steps are waiting steps and moves those steps into linked follow-up items in V.
  The CLI watches for a finished-but-uncut version: when every item in the current version
  is 100%, `check`/`next`/`orient` print a release nudge, and starting work on a later
  version (`new`/`promote` targeting it) triggers the gate too. `settings.autoRelease` in
  `.roadmap/config.json` controls it: `"nudge"` (default) prints the reminder, `"auto"`
  runs the release itself (target = the later version being started, else the lowest
  existing version above current; never invents a number), `"off"` disables the gate.
- `claim ID [ID…] --stage {review,fixing,gate-ready,gating,blocked,landed} [--verdict V] [--note "..."] [--branch B]` (or `ID… --clear`) — record the in-flight build stage in plan frontmatter, several ids all-or-nothing; trunk checkboxes stay the only done source (see `references/state-model.md`)
- `claim ID [ID…] [--owner NAME] [--take]` — every claim records its owner (default `$ROADMAP_OWNER`, else the git user name, else the agent name); an item held by another owner (refreshed within `settings.claimTtlHours`, default 12) is refused, naming the owner and age, unless `--take` (applies to `--clear` too); `--owner` alone opens an owner-only claim that holds the item while it builds. `next` skips held items; `orient` lists yours. `settings.wipLimit` makes `status`/`next`/`orient` warn when more items are in flight (see `references/state-model.md` → "Claim owners")
- `claim [ID…] --landed SHA` — move items whose branch tip SHA (e.g. the integration branch) contains to `landed`, recording the sha
- `check --landed [--evidence "..."] [--yes]` — dry-run list (or with `--yes`, tick every step) of `landed` items whose landing sha and branch tip trunk now contains; clears their claims
- `slot ID --kind K [--name N] [--add]` (or `ID --kind K --release`, or `[ID] --check`) — reserve the next number of a numbered sequence from `settings.slots` (e.g. a DB migration) for an item and print it; `--check` exits 1 when a reservation clashes or is taken (merge gate; see `references/state-model.md` → "Numbered slots")
- `run --kind gate|suite --label L --result pass|fail [--items IDS] [--branches B,B] [--duration 12m] [--log URL] [--failing "names"] [--shards "unit=pass,e2e=fail"] [--json]` — record a merge-gate or suite run in `.roadmap/runs.jsonl` (append-only, locked, trimmed to `settings.runsKeep`, default 200; `--log` must be http(s)). The merge gate records one per batch (see `references/quality-build.md` → "Merge gate")
- `status [--type T] [--version V] [--status S] [--open] [--in-flight] [--slots] [--runs] [--worktrees] [--conflicts] [--drift] [--json]` — print current state (items grouped under a version header carrying its forecast — steps left, pace, finish date and range, target grade — see `settings.forecastDays` / `versionTargets` in the state model; shows lane, branch, and `blocked by […]` when deps incomplete; `--slots` prints slot reservations and their match state instead; `--runs` prints recorded runs newest first plus trunk health); `--worktrees` prints the linked-worktree table — dirty and unmerged counts, item, lane, stage, age — and the `git worktree remove` command for each safe one, never running it; `--conflicts` lists open item branches that change the same files, by risk (high = `git merge-tree` finds a conflict, medium = file overlap only, low = merges cleanly), with a suggested merge order, never touching a branch; `--drift` lists open item branches that change files outside their plan's declared paths (blueprint `Files …:` bullets and `-> target:` parts; tests, lockfiles and `.roadmap/` always allowed, extend with `settings.scopeAllow`), and plans with no declared scope — report-only; all given filters must match, and they narrow the item list only; `--json` also includes `counts` (`byType`/`byStatus`/`byVersion`) computed across all items regardless of filters
- `serve [--port N] [--no-open] [--verbose] [--all]` — local live dashboard; `--all` (also the default when run outside any roadmap project, and what a bare `claude-roadmap` does there) serves `#/projects`: one card per registered project (version, progress, in-flight / blocked / waiting counts, last activity, alerts: REFUTED verdicts, slot clashes, WIP over limit, overdue waiting steps, failing trunk suite); a card opens that project's normal pages under `#/p/<name>/…` on the same port. One per user (port 4690+); see `references/state-model.md` → "Project registry"
- `projects [--forget NAME] [--json]` — list the per-user project registry (name, last seen, path; missing paths flagged); `--forget` removes one by name, slug or path
- `search <text> [--json]` — case-insensitive substring search across item titles, item note lines, plan bodies and the Idea Incubator (linked `.roadmap/notes/` files are not scanned)
- `import PATH` — extract checklist lines from a file into a plan

## Optional automation
- **Stop** (`hooks/roadmap-sync.sh`): `sync` + `drift-check` each turn — safety net + catchup nudge.

## Routing for parallel and isolated builds
- One item → `build <id> --worktree` (branch `roadmap/<id>`); one orchestrator per item. See `references/quality-build.md` → "Orchestration per item".
- A whole version → `build <version> --worktree` (branch `roadmap/v<version>`, one shared worktree).
- Parallel `--auto` is **opt-in** and not yet built (plan 27). Serial `build --auto` remains the default.
- **SessionStart** (`hooks/roadmap-orient.sh`): injects current version + next item into context.
Both are opt-in via the installer (`--no-hook` / `--no-orient`). CLI mutations already `sync`.
