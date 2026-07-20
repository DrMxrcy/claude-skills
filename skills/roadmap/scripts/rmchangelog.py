"""roadmap changelog & audience — public/internal changelog rendering, note
linting, and public/internal audience routing. Layer: rmcore + rmparse."""
from __future__ import annotations
import re
from rmcore import read_config, roadmap_dir, _norm_version, _version_key
from rmparse import count_progress


TYPE_SECTION = {"feature": "✨ New", "bug": "🐛 Fixed",
                "refactor": "⚡ Improved", "chore": "⚡ Improved"}
SECTION_ORDER = ["✨ New", "🐛 Fixed", "⚡ Improved"]

# Unset `audience` falls back to this per-type default. The AI sets `audience` explicitly
# via the roadmap commands; this is only the safety net at render time.
DEFAULT_AUDIENCE = {"feature": "public", "bug": "public",
                    "refactor": "internal", "chore": "internal"}
# One-line stand-in shown in the PUBLIC changelog when a version shipped internal-only
# work, instead of listing it.
ROLLUP_LINE = "_Plus behind-the-scenes performance and reliability work._"

# Internal "tells" come in two tiers, matched case-insensitively as whole words.
#
# WARN tier = WORDING problems. The feature may still be public; the note just reads like it
# was written for engineers — rephrase, don't reclassify. (vendor/tool names, dev jargon,
# mechanism phrasing, plus file paths / issue refs detected by regex in lint_note.)
WARN_VENDORS = [
    "convex", "sentry", "aptabase", "codex", "eas", "clerk", "supabase", "firebase",
    "vercel", "netlify", "cloudflare", "r2", "s3", "docker", "kubernetes", "k8s",
    "redis", "postgres", "postgresql", "mysql", "mongodb", "stripe", "github actions",
    "expo", "webpack", "vite", "prisma", "graphql", "grpc",
]
WARN_JARGON = [
    "refactor", "schema", "migration", "mutation", "endpoint", "backend", "frontend",
    "polling", "cron", "webhook", "ci", "lint", "linter", "env var",
    "environment variable", "api key", "n+1", "regression",
    "under the hood", "data feed", "data feeds", "headliner index", "walk-through",
    "walkthrough index", "audit", "audits", "ota", "de-slop",
]
WARN_TELLS = [*WARN_VENDORS, *WARN_JARGON]

# DEMOTE tier = WRONG-AUDIENCE / self-incriminating. The *work* is internal, not just the
# wording. An item with no explicit audience that trips any of these auto-routes to
# CHANGELOG.internal.md (an explicit `audience --to public` still wins). Grouped by reason:
DEMOTE_ADMIN = [        # operator-only surfaces — staff read these, not end users
    "admin", "admins", "admin panel", "admin console", "admin area", "admin dashboard",
    "moderation", "moderator", "moderators", "audit trail", "audit log", "role-gated", "cms",
]
DEMOTE_COMPLIANCE = [   # legal/regulatory gates — required, not a feature anyone chose
    "compliance", "coppa", "gdpr", "age gate", "age-gate", "age verification", "13-and-up",
    "13 and up", "underage", "minimum age", "eula", "terms acceptance", "community guidelines",
]
DEMOTE_SECURITY = [     # security fixes that disclose a past hole — never advertise the weakness
    "hardening", "hardened", "privilege", "spam/abuse", "closed gaps", "vulnerability",
    "exploit", "public url", "public urls", "expiring link", "expiring links", "signed url",
    "signed urls",
]
DEMOTE_PLUMBING = [     # SEO/infra plumbing & internal milestones — no user-visible payoff
    "groundwork", "groundwork for", "reusable", "static-page", "sitemap", "robots rules",
    "robots.txt", "structured data", "metadata", "search-optimized", "search optimized", "seo",
    "scaffolding", "boilerplate", "rearchitect", "re-architect", "pre-launch", "prelaunch",
]
DEMOTE_TELLS = [*DEMOTE_ADMIN, *DEMOTE_COMPLIANCE, *DEMOTE_SECURITY, *DEMOTE_PLUMBING]

_PATH_RE = re.compile(r"\b[\w.-]+\.(?:ts|tsx|js|jsx|mjs|cjs|py|go|rs|java|rb|php|"
                      r"json|ya?ml|toml|sql|sh|css|scss|md|swift|kt)\b")  # foo/bar.ts
_SEG_RE = re.compile(r"\b\w+(?:/\w+){2,}\b")                          # a/b/c paths
_REF_RE = re.compile(r"#\d+")                                        # issue refs (#77)

# STATUS tier = status-dump tells — progress-report text (date stamps, plan-step refs,
# version numbers, shouted status words) that belongs in the plan file or a commit message,
# never in a release note. Any hit is structural evidence the note wasn't written for end
# users, so `note` / `new --note` REFUSE to save it on a public item (override: --force).
_STATUS_RES = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),                 # ISO date stamps (2026-07-15)
    re.compile(r"\bStep\s+\d+\b"),                        # plan-step refs ("Step 9")
    re.compile(r"\bv\d+\.\d+(?:\.\d+)?\b"),               # version refs (v1.6.0)
    re.compile(r"\b(?:DONE|WIP|TODO|BLOCKED|DEFERRED|DESCOPED|DESCOPE|ACCEPTED|"
               r"SHIPPED|MERGED|FIXED|QA|TBD)\b"),        # shouted status words
]


def _word_hits(text: str, terms: list[str]) -> list[str]:
    low = text.lower()
    return [t for t in terms if re.search(r"\b" + re.escape(t.lower()) + r"\b", low)]


def _dedupe(seq: list[str]) -> list[str]:
    seen, out = set(), []
    for h in seq:
        if h.lower() not in seen:
            seen.add(h.lower())
            out.append(h)
    return out


def status_tells(text: str) -> list[str]:
    """Structural status-dump evidence in a would-be PUBLIC note: issue refs, source/doc
    paths, ISO dates, plan-step refs, version numbers, shouted status words. Unlike the
    advisory word lists, any hit here means the text is a progress report rather than a
    release note, so `note` / `new --note` refuse to save it on a public item (--force
    overrides)."""
    hits = _REF_RE.findall(text) + _PATH_RE.findall(text) + _SEG_RE.findall(text)
    for rx in _STATUS_RES:
        hits += rx.findall(text)
    return _dedupe(hits)


def lint_note(text: str, extra_terms: list[str] | None = None) -> list[str]:
    """Every internal tell in a would-be PUBLIC note, for display/warnings — status-dump
    tells (issue refs, paths, dates, step/version refs, shouted status), vendor/jargon
    (warn tier), and scope/disclosure words (demote tier). Empty list == looks clean.
    Advisory here; the status-dump subset also hard-blocks in `note` / `new --note`."""
    hits = status_tells(text)
    hits += _word_hits(text, [*WARN_TELLS, *DEMOTE_TELLS, *(extra_terms or [])])
    return _dedupe(hits)


def demote_tells(text: str) -> list[str]:
    """Only the high-confidence WRONG-AUDIENCE tells (admin / compliance / security-disclosure
    / plumbing). Drives auto-routing of an unclassified item to the internal changelog."""
    return _dedupe(_word_hits(text, DEMOTE_TELLS))


def item_audience(item: dict) -> str:
    """An item's effective audience. An explicit `audience` always wins. Otherwise an item
    whose note/title trips a high-confidence demote tell auto-routes to `internal`; failing
    that, it falls back to the per-type default."""
    a = item.get("audience")
    if a in ("public", "internal"):
        return a
    if demote_tells(f"{item.get('note', '')} {item.get('title', '')}"):
        return "internal"
    return DEFAULT_AUDIENCE.get(item["type"], "internal")


def _changelog_versions(root: Path) -> list[tuple[str, str, list[dict]]]:
    """Shared scaffold for both changelog renderers. Returns (version, header, rows) per
    version (newest first), where each row is {'item', 'complete'} and `header` is the
    '## v.. — ..' line. A version is dated once all its items reach 100% (date persisted in
    config.versionDates); otherwise it renders '(in progress)'."""
    cfg = read_config(root)
    version_dates = cfg.get("versionDates", {})
    by_version: dict[str, list] = {}
    for item in cfg["items"]:
        by_version.setdefault(item["version"], []).append(item)
    blocks = []
    for version in sorted(by_version, key=_version_key, reverse=True):
        rows, done_all = [], True
        for it in sorted(by_version[version], key=lambda i: i["id"]):
            p = roadmap_dir(root) / it["file"]
            done, total = count_progress(p) if p.exists() else (0, 0)
            complete = total > 0 and done == total
            done_all = done_all and complete
            rows.append({"item": it, "complete": complete})
        date = version_dates.get(version)
        if done_all and date:
            header = f"## v{version} — {date}"
        elif done_all:
            header = f"## v{version}"
        else:
            header = f"## v{version} — (in progress)"
        blocks.append((version, header, rows))
    return blocks


def _grouped_lines(entries: dict[str, list[tuple[bool, str]]]) -> list[str]:
    """Render section-grouped '- label' / '- (pending) label' lines from {section: [(complete, label)]}."""
    lines = []
    for section in SECTION_ORDER:
        items = entries.get(section)
        if not items:
            continue
        lines.append(f"### {section}")
        lines += [f"- {label}" if complete else f"- (pending) {label}"
                  for complete, label in items]
        lines.append("")
    return lines


def render_public_changelog(root: Path) -> tuple[str, list[str]]:
    """Render the PUBLIC CHANGELOG.md: only audience=public items, rendered from their
    user-facing `note` ONLY (never the raw title). A public item with no note is skipped;
    if it has already shipped (complete) that omission is returned as a warning and the
    item is covered by the roll-up line, so a shipped version never vanishes from the
    public changelog. The roll-up line appears ONLY when a version has nothing public to
    show — versions with real public bullets stay clean (less is more); internal work
    remains fully logged in CHANGELOG.internal.md. Returns (markdown, warnings)."""
    warnings: list[str] = []
    summaries = read_config(root).get("releaseNotes", {})
    out = ["# Changelog", ""]
    for version, header, rows in _changelog_versions(root):
        blurb = summaries.get(version)
        if blurb:
            # A curated per-version blurb IS the public release notes — item bullets
            # (and their missing-note warnings) don't apply; detail lives internally.
            out += [header, "", blurb, ""]
            continue
        sections: dict[str, list[tuple[bool, str]]] = {}
        rolled_up = False
        for row in rows:
            it = row["item"]
            if item_audience(it) != "public":
                rolled_up = True
                continue
            note = it.get("note")
            if not note:
                if row["complete"]:
                    warnings.append(
                        f"#{it['id']} \"{it['title']}\" is public but has no note; "
                        f"rolled up as behind-the-scenes work in CHANGELOG.md. Add one: "
                        f"roadmap note --plan {it['id']} --text \"...\"")
                    rolled_up = True
                continue
            section = TYPE_SECTION.get(it["type"], "⚡ Improved")
            sections.setdefault(section, []).append((row["complete"], note))
        lines = _grouped_lines(sections)
        if rolled_up and not lines:
            lines += [ROLLUP_LINE, ""]
        if not lines:
            continue                       # nothing public to show for this version
        out += [header, "", *lines]
    return "\n".join(out).rstrip() + "\n", warnings


def changelog_json(root: Path) -> list[dict]:
    """Structured public changelog for app builds (in-app changelog screens, "What's
    New" popups). Same selection rules as render_public_changelog — public audience,
    note text only — but as data: one object per version, newest first. Callers
    filtering for a popup should keep `released == true` versions only."""
    cfg = read_config(root)
    version_dates = cfg.get("versionDates", {})
    summaries = cfg.get("releaseNotes", {})
    out = []
    for version, _header, rows in _changelog_versions(root):
        blurb = summaries.get(version)
        sections: dict[str, list[dict]] = {}
        rollup = False
        released = bool(rows) and all(r["complete"] for r in rows)
        for row in rows:
            it = row["item"]
            if item_audience(it) != "public" or not it.get("note"):
                rollup = True
                continue
            section = TYPE_SECTION.get(it["type"], "⚡ Improved")
            # strip the emoji prefix for machine keys: "✨ New" -> "New"
            key = section.split(" ", 1)[1] if " " in section else section
            sections.setdefault(key, []).append(
                {"text": it["note"], "pending": not row["complete"]})
        if not sections and not rollup and not blurb:
            continue
        # `notes` is the curated per-version blurb; when present it supersedes
        # `sections` for user-facing display (mirrors CHANGELOG.md).
        out.append({"version": version, "date": version_dates.get(version),
                    "released": released, "notes": blurb,
                    "sections": {} if blurb else sections,
                    "rollup": False if blurb else rollup})
    return out


def render_internal_changelog(root: Path) -> str:
    """Render the INTERNAL CHANGELOG.internal.md: every item, every section, using each
    item's `note` and falling back to the raw title — the full dev-facing work log."""
    out = ["# Changelog (internal)", "",
           "_Full work log — every item, including internal/dev work. "
           "The curated public changelog is CHANGELOG.md._", ""]
    for _version, header, rows in _changelog_versions(root):
        sections: dict[str, list[tuple[bool, str]]] = {}
        for row in rows:
            it = row["item"]
            section = TYPE_SECTION.get(it["type"], "⚡ Improved")
            sections.setdefault(section, []).append(
                (row["complete"], it.get("note") or it["title"]))
        lines = _grouped_lines(sections)
        if lines:
            out += [header, "", *lines]
    return "\n".join(out).rstrip() + "\n"


def audit_public_notes(root: Path) -> list[str]:
    """Full pre-release audit of the public changelog: flag every public item missing a
    note, and lint existing public notes for internal language. Used by /roadmap:changelog."""
    cfg = read_config(root)
    extra = cfg.get("settings", {}).get("internalTerms", [])
    summaries = cfg.get("releaseNotes", {})
    msgs = []
    # Completed versions still rendering raw item bullets: suggest a curated blurb —
    # the public changelog should read like App Store "What's New", not an item list.
    for version, _header, rows in _changelog_versions(root):
        if rows and all(r["complete"] for r in rows) and not summaries.get(version):
            msgs.append(f"v{version} has no release-notes summary — the public changelog "
                        f"lists raw item bullets. Write one short user-facing blurb: "
                        f"roadmap summary --version {version} --text \"...\"")
    # Orphaned blurbs: a summary for a version no items target (usually after retarget/
    # remove) renders nowhere — clear it or move it to the absorbing version.
    live = {i["version"] for i in cfg["items"]}
    for version in sorted(set(summaries) - live, key=_version_key):
        msgs.append(f"v{version} has a release-notes summary but no items target it "
                    f"(retargeted away?) — it renders nowhere. Clear it: "
                    f"roadmap summary --version {version} --clear")
    for it in sorted(cfg["items"], key=lambda i: i["id"]):
        if summaries.get(it["version"]):
            continue   # version ships a curated blurb; per-item notes are internal-only
        explicit = it.get("audience")
        blob = f"{it.get('note', '')} {it['title']}"
        eff = item_audience(it)
        # Auto-routed: no explicit audience, would be public by type, demoted by a high-conf tell.
        if explicit is None and DEFAULT_AUDIENCE.get(it["type"]) == "public" and eff == "internal":
            msgs.append(f"#{it['id']} \"{it['title']}\" auto-routed to internal "
                        f"({', '.join(demote_tells(blob))}); if it really is user-facing, "
                        f"override: roadmap audience --plan {it['id']} --to public")
            continue
        if eff != "public":
            continue
        # Explicitly marked public but matches a high-confidence internal signal — likely wrong.
        d = demote_tells(blob)
        if explicit == "public" and d:
            msgs.append(f"#{it['id']} is marked PUBLIC but matches high-confidence internal "
                        f"signals ({', '.join(d)}) — likely miscategorized: \"{it['title']}\"")
        note = it.get("note")
        if not note:
            msgs.append(f"#{it['id']} \"{it['title']}\" (public) has no note — "
                        f"add one, or mark it internal: roadmap audience --plan {it['id']} --to internal")
            continue
        tells = lint_note(note, extra)
        if tells:
            msgs.append(f"#{it['id']} note reads internal ({', '.join(tells)}): \"{note}\"")
        # The note may read clean while the work is actually admin-only, a compliance gate, or
        # otherwise internal — the planning title usually still carries that signal.
        title_only = [t for t in lint_note(it["title"], extra) if t not in tells]
        if title_only:
            msgs.append(f"#{it['id']} note looks clean but its title suggests internal/admin "
                        f"scope ({', '.join(title_only)}) — confirm it's really public: \"{it['title']}\"")
    return msgs
