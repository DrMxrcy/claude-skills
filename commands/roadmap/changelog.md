---
description: Curate the public changelog (and backfill user-facing notes from git history)
argument-hint: <version | empty for current>
---

Curate the changelog via the **roadmap** skill. Target: $ARGUMENTS (default: current version).

There are **two** changelogs, both rendered deterministically by the CLI:
- `CHANGELOG.md` — **public**. Only `audience: public` items, rendered from each item's
  user-facing `note` (never the raw title). Ready to paste into the App Store "What's New"
  or a website changelog. Versions that also shipped internal-only work get one rolled-up
  "behind-the-scenes" line instead of listing it.
- `CHANGELOG.internal.md` — **internal**. Every item, with the raw title as a fallback —
  the full dev-facing work log.

**Show / copy:** `python3 <roadmap.py> changelog` prints the public file; add `--internal`
for the full log. If the section is already curated, it's ready to paste.

**Curate (your real job here) — classify, then phrase:**
1. Run `python3 <roadmap.py> changelog` and read the warnings it prints. They flag two
   problems: public items with **no note** (silently dropped from `CHANGELOG.md`), and notes
   that **read internal** (vendor/tool names, file paths, issue refs, dev jargon).
2. For each item, decide its **audience** with judgment — would a user notice or care?
   - User-visible → `python3 <roadmap.py> audience --plan <id> --to public`
   - Backend/infra/tooling/CI/dev-only → `--to internal`
   The type default (`feature`/`bug` → public, `refactor`/`chore` → internal) is only a
   safety net; you are the real gate.
3. For every **public** item, write a plain-language, benefit-focused one-liner — what the
   user can now do, in their words:
   `python3 <roadmap.py> note --plan <id> --text "<user-facing summary>"`.
   No vendor names (Convex, Sentry, Codex, EAS…), no file paths, no `#123`, no
   "refactor/schema/backend/polling". The CLI re-lints and warns if it still reads internal.
4. Re-run `python3 <roadmap.py> changelog` until it prints no warnings, then preview both
   files. `/roadmap:release` stamps the dated section; this command just gets it clean.

**What "public" actually means.** The public changelog is a **marketing surface — a What's
New for end users, not a complete record.** An item is `public` only if it is *net-new*,
*end-user-visible*, *worth announcing*, and *safe to announce*. Before writing a note, run it
past these exclusions — each sends the item to `internal` even if it shipped real work:

- **Admin / operator-only** — admin panels, dashboards, user management, moderation, the
  CMS/markdown editor, "…on the web" tools that only staff use. The people who read a public
  changelog are end users, not your admins. *(A note can read perfectly user-facing and still
  be admin-only — judge by who actually uses the feature; the audit also flags admin/CMS words
  in the item's title.)*
- **Security fixes that disclose a past hole** — "now protected by expiring links instead of
  public URLs", "closed a privilege gap". Announcing the fix tells users (and attackers) they
  were exposed. Keep these `internal`; never describe the prior weakness.
- **Compliance / legal gates** — age gates (13+), terms/EULA acceptance, COPPA/GDPR, account
  deletion required by policy. Required, not a feature anyone chose. `internal`.
- **Foundational / launch / table-stakes** — "you can sign up", "choose a @username", core
  navigation, "the app has a dark theme". Baseline, not *new*. Don't list the product's
  existence as a highlight — even at v1.0.0, lead with the headline experience, not every
  brick that makes the app an app.
- **Trivial housekeeping / cosmetic / minor nav** — "the Settings screen now matches the
  theme", "moved Search to an easier-to-reach spot", "a Settings screen with sign out". Real,
  but nobody reads a changelog for these. Fold them into the behind-the-scenes roll-up.

Litmus test: *"Would we proudly put this in the App Store 'What's New', and be glad a
competitor read it?"* If it's plumbing, admin-only, a fixed embarrassment, a legal checkbox,
cosmetic housekeeping, or just "the app works" — it's `internal`.

**Collapse a campaign into one line.** When many items are the same initiative, the public
changelog gets **one headline**, not every variant — mark the rest `internal`. A version that
shipped six SEO items ("static-page builder", "per-park web pages", "news web pages",
"sitemap.xml", "structured data", "search-optimized homepage") gets *one* public line —
"Parks, rides, and news now show up when you search Google" — and the plumbing stays internal.
Same for five "responsive web layout" items → "Parkboxd now has a proper desktop web layout."
The public changelog is the highlight reel; the internal log keeps the full list.

**Writing voice — public vs internal.** This is the part to get right:

- **Public note** = what the *user* gains, in *their* words. One sentence, lead with the
  benefit or the new ability. Name features the user sees, not the systems behind them.
  Forbidden in public notes: vendor/tool names (Convex, Sentry, Aptabase, Codex, EAS, Clerk,
  R2, Stripe…), file paths (`convex/lib/r2.ts`), issue/PR refs (`#77`), and engineer jargon
  (refactor, schema, mutation, endpoint, backend, polling, CI, migration). The CLI lints for
  these and warns — treat a warning as "rewrite it."
- **Internal note** (or no note → falls back to the title) = whatever a developer needs.
  Technical detail, vendor names, file paths, and ticket refs are all fine here.
- Decide audience by impact, not by type: a feature the user can't perceive is `internal`;
  a fix or refactor the user *feels* (faster, fewer crashes, lower battery) can be `public`
  with a benefit-worded note. When unsure whether a user would notice → `internal`.

**Default these whole categories to `internal`** — they read as dev summaries even when
genuinely shipped. Make them public *only* if there's a concrete benefit the user directly
feels, and then write *only that benefit*, never the mechanism:

- **Security / abuse hardening** — "hardened security", "closed gaps", "privilege misuse",
  "spam/abuse", "pre-launch hardening pass" → internal. The exception is a control the user
  *operates*: "You can now block other users" is public; the audit-trail/permissions plumbing
  behind it is not.
- **SEO / discoverability plumbing** — "lays the groundwork", "reusable static-page builder",
  "sitemap.xml", "robots rules", "structured data" → internal. Collapse the whole effort into
  at most one public payoff line: "Parks and rides now show up when you search Google."
- **Internal milestones / architecture** — "Phase 1 foundation", "pre-launch", "rearchitected
  X", "scaffolding" → internal.
- **Algorithm internals** — "truncated headliner index", "walk-through filtering", "data-feed
  verification" → describe the *result* ("crowd levels are more accurate now"), not the method.

The lint flags this softer phrasing too (hardening, groundwork, privilege, sitemap, reusable,
headliner index…), so a warning here usually means "reclassify as internal, or rewrite to the
pure benefit."

Translate, don't copy. Examples:

| Item (internal/title)                              | ❌ leaks internal                          | ✅ public note                                            |
|----------------------------------------------------|--------------------------------------------|-----------------------------------------------------------|
| Wire up Sentry + Aptabase analytics                | "Added Sentry crash reporting + Aptabase"  | *(internal — user sees nothing; mark `internal`)*         |
| Stop dev backend polling 24/7 (Convex cost)        | "Cut Convex polling to save cost"          | *(internal — infra; `internal`)*                          |
| Signed URLs for non-public images (convex/lib/r2)  | "Switch r2.ts reads to signed URLs (#42)"  | "Your private photos are now protected by secure, expiring links." |
| Park-closed gate fix in waitTimes.ts               | "Fixed hours gate in waitTimes.ts"         | "Closed parks no longer show phantom wait times."         |
| Pre-launch security & abuse hardening              | "Hardened security: closed privilege-misuse and spam/abuse gaps" | *(internal — plumbing; expose only user-operated controls like "block users")* |
| SEO: reusable static-page builder + sitemap/robots | "Lays the groundwork with a reusable static-page builder + robots rules" | "Parks and rides now show up when you search Google."     |
| Crowd index: truncated headliner index             | "Use a truncated headliner index over anchor rides" | "Crowd levels are more accurate — busy parks now read busy." |
| Apple Watch logging feature                        | —                                          | "Log the ride you just rode straight from your Apple Watch — no phone needed." |

**Backfill (adopted repo / missing notes):** reconstruct what shipped from git history —
`git log v<previous>..HEAD --oneline` (or `git log --oneline` with no tags) — map commits to
items by plan/title, then set each item's audience + note as above.

The CLI lives at `.claude/skills/roadmap/scripts/roadmap.py` (project) or
`~/.claude/skills/roadmap/scripts/roadmap.py` (global).
