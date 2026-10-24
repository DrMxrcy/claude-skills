"""roadmap plan parsing — read plan .md files (checklist steps, frontmatter).
Pure/leaf layer: depends only on rmcore."""
from __future__ import annotations
import functools
import re
from pathlib import Path
from rmlib.core import read_config, roadmap_dir


STEP_RE = re.compile(r"^(\s*[-*]\s+)\[( |x|X|~)\](.*)$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# Waiting steps (plan 46): `- [~] Step 3: text (waiting until 2026-10-30: soak)` —
# built, but only verifiable after time passes. A waiting step is NEVER done: it
# parses as (False, text) in `steps` like an unticked one, so every progress count,
# changelog and gate reads it as open; its date/reason live in `waiting`. The marker
# is stripped from the step text. `[~]` without a marker is waiting with no date.
WAIT_BOX = "~"
WAIT_RE = re.compile(r"\s*\(waiting until (\d{4}-\d{2}-\d{2})(?::\s*(.*?))?\)\s*$")


def split_wait_marker(text: str) -> tuple[str, str | None, str | None]:
    """(step text without the wait marker, until date or None, reason or None)."""
    wm = WAIT_RE.search(text)
    if not wm:
        return text, None, None
    return text[:wm.start()].rstrip(), wm.group(1), (wm.group(2) or "").strip() or None


def wait_marker(until: str | None, reason: str | None) -> str:
    """The ` (waiting until DATE[: reason])` suffix `wait` appends to a step."""
    if not until:
        return ""
    return f" (waiting until {until}" + (f": {reason}" if reason else "") + ")"


# In-flight claim (plan 30): what git cannot know about an item — its review/gate
# stage and verdict — recorded by `roadmap.py claim`. Stored as FLAT `claim_<field>`
# frontmatter keys: the frontmatter parser is line-based `key: value` (no nesting),
# so a nested `claim:` block would flatten its children into top-level keys. Flat
# keys round-trip exactly, and older skill versions simply ignore them.
# `landed` (plan 32): merged into the integration branch, not yet on trunk;
# `claim_landed_sha` is the commit it landed in (set by `claim --landed <sha>`).
CLAIM_STAGES = ("review", "fixing", "gate-ready", "gating", "blocked", "landed")
CLAIM_VERDICTS = ("CONFIRMED", "PARTIAL", "REFUTED")
# `owner` / `refreshed` (plan 40): who holds the item and when they last
# refreshed the claim (UTC ISO timestamp) — see rmlib/owners.py. An owner-only
# claim (no stage) holds the item while it builds in its derived lane.
CLAIM_FIELDS = ("stage", "verdict", "note", "branch", "landed_sha", "updated",
                "owner", "refreshed")
CLAIM_PREFIX = "claim_"

# Numbered slot reservations (plan 33): `slot_<kind>: 0269_name[, 0270_name2]`,
# flat for the same reason as claims. Logic lives in rmlib/slots.py.
SLOT_PREFIX = "slot_"

# Rulings (plan 34): dated decisions recorded in the plan body as
# `- **Ruling (2026-10-22, owner[, approval]):** text`. `roadmap.py ruling` appends
# them under RULINGS_HEADING; hand-written ones anywhere in the body parse too.
RULINGS_HEADING = "## ⚖️ Rulings"
RULINGS_SECTION_KEY = "rulings"          # _norm_name of the heading text
RULING_APPROVAL_TAG = "approval"         # the tag `ruling --approval` writes
# Tags (normalized) that mark a ruling as a sign-off, hand-written or not.
RULING_APPROVAL_TAGS = {"approval", "approved", "sign off", "signoff"}
# `**Ruling (date, who[, tags]):** text`, `**Ruling date (who):** text`,
# `**Owner ruling (date):** text` (the one-word prefix is the author), and the
# `**...**:` colon-outside variant; optionally a list bullet. The plural
# (`**Owner rulings (date):**` over a nested list) is one record too.
RULING_RE = re.compile(
    r"^(\s*)(?:[-*+]\s+)?\*\*(?:([A-Za-z][\w-]*)\s+)?[Rr]ulings?\b([^*]*?)"
    r"(?::\*\*|\*\*:)\s*(.*)$")
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

# Bug routing (plan 47): `roadmap.py bug --found-in <in-flight id>` appends a
# `Fix:` step to that plan and one bullet per bug under FOUND_HEADING. A bug in
# shipped work is a new `bug` item instead, linked both ways by flat frontmatter
# keys: `foundIn: <origin id>` on the bug plan, `bugsFound: <id>[, <id>]` on the
# origin plan.
FOUND_HEADING = "## 🐞 Found during build"
FOUND_SECTION_KEY = "found during build"  # _norm_name of the heading text
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")

# Parse results are cached by (path, mtime, size). A short CLI run barely touches
# it, but a long-lived `serve` process re-parses only the plan that actually
# changed on each push instead of every plan on every status() call.
_CACHE: dict = {}


def _is_fence(line: str) -> bool:
    return line.lstrip().startswith("```")


def parse_plan(path: Path) -> dict:
    try:
        st = path.stat()
        key = (str(path), st.st_mtime_ns, st.st_size)
        hit = _CACHE.get(str(path))
        if hit and hit[0] == key:
            return hit[1]
    except OSError:
        key = None
    text = path.read_text(encoding="utf-8")
    meta = {}
    m = FRONTMATTER_RE.match(text)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
    steps, waiting = [], {}
    in_fence = False
    for line in text.splitlines():
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        sm = STEP_RE.match(line)
        if sm:
            text_ = sm.group(3).strip()
            if sm.group(2) == WAIT_BOX:
                text_, until, reason = split_wait_marker(text_)
                waiting[len(steps) + 1] = {"until": until, "reason": reason}
            steps.append((sm.group(2).lower() == "x", text_))
    body = text[m.end():] if m else text
    result = {"meta": meta, "steps": steps, "waiting": waiting,
              "rulings": parse_rulings(body),
              "foundDuringBuild": parse_found(body),
              # Acceptance ledger (plan 43): bullets with their marked state.
              "acceptance": [public_bullet(b)
                             for b in acceptance_bullets(body.splitlines())],
              "declaredPaths": declared_paths(body)}
    if key is not None:
        _CACHE[str(path)] = (key, result)
    return result


def _ruling(match: re.Match, segments: list[str]) -> dict:
    """One ruling dict from a RULING_RE match and its text segments (the first
    line's text, then one per nested list item)."""
    prefix, inner = match.group(2), match.group(3)
    dm = _DATE_RE.search(inner)
    parts = [p.strip() for p in re.sub(r"[()]", " ", _DATE_RE.sub(" ", inner, 1))
             .split(",")]
    parts = [p for p in parts if p]
    if prefix:                       # "Owner ruling (...)": the prefix is the author
        by, tags = prefix.lower(), parts
    else:
        by, tags = (parts[0] if parts else None), parts[1:]
    approval = any(_norm_name(t) in RULING_APPROVAL_TAGS for t in tags)
    context = [t for t in tags if _norm_name(t) not in RULING_APPROVAL_TAGS]
    return {"date": dm.group(1) if dm else None, "by": by,
            "text": " · ".join(x for x in segments if x),
            "approval": approval, "context": ", ".join(context) or None}


def parse_rulings(body: str) -> list[dict]:
    """Every ruling in a plan body, in file order, as {date, by, text, approval,
    context}: the bullets `roadmap.py ruling` writes and hand-written ones
    anywhere in the body (see RULING_RE). `context` holds any extra tags
    ("correction", "rank structure"). Fenced code and HTML comments are skipped;
    lines indented under a ruling continue it (wrapped text joins with a space,
    each nested list item becomes a " · "-separated segment)."""
    lines = _strip_comments(body.splitlines())
    out, in_fence, i = [], False, 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        rm = RULING_RE.match(line)
        if not rm:
            continue
        indent, segments = len(rm.group(1)), [rm.group(4).strip()]
        while i < len(lines):
            nxt = lines[i]
            if not nxt.strip() or _is_fence(nxt) or RULING_RE.match(nxt) \
                    or len(nxt) - len(nxt.lstrip()) <= indent:
                break
            if _LIST_MARKER_RE.match(nxt):
                segments.append(_LIST_MARKER_RE.sub("", nxt, 1).strip())
            else:
                segments[-1] = (segments[-1] + " " + nxt.strip()).strip()
            i += 1
        out.append(_ruling(rm, segments))
    return out


def parse_found(body: str) -> list[str]:
    """Bullet texts under the plan's `## 🐞 Found during build` section (plan 47),
    in file order. Fenced code and HTML comments are skipped."""
    out, in_fence, inside = [], False, False
    for line in _strip_comments(body.splitlines()):
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        hm = _HEADING_RE.match(line)
        if hm:
            if len(hm.group(1)) <= 2:
                inside = _norm_name(hm.group(2)) == FOUND_SECTION_KEY
            continue
        bm = re.match(r"^[-*+]\s+(.+)$", line) if inside else None
        if bm:
            out.append(bm.group(1).strip())
    return out


def meta_ids(meta: dict, key: str) -> list[int]:
    """Integer ids from a comma-separated frontmatter value (`bugsFound: 7, 9`);
    non-numeric tokens are ignored."""
    return [int(t) for t in re.findall(r"\d+", str(meta.get(key) or ""))]


def needs_approval(plan: dict) -> bool:
    """A plan declaring `approval: required` in frontmatter with no approval
    ruling yet. `plan` is a parse_plan() result."""
    required = (plan.get("meta") or {}).get("approval", "").strip().lower()
    return required == "required" and not any(
        r.get("approval") for r in plan.get("rulings") or [])


def count_progress(path: Path) -> tuple[int, int]:
    steps = parse_plan(path)["steps"]
    return sum(1 for done, _ in steps if done), len(steps)


def waiting_steps(path: Path) -> list[dict]:
    """The plan's waiting steps (plan 46) as [{step, text, until, reason}], in
    order; `step` is 1-based like `check --step`."""
    plan = parse_plan(path)
    return [{"step": n, "text": plan["steps"][n - 1][1], **w}
            for n, w in sorted((plan.get("waiting") or {}).items())]


def read_claim(path: Path) -> dict | None:
    """The plan's in-flight claim as {stage, verdict, note, branch, landed_sha,
    updated, owner, refreshed} (absent fields are None), or None when the plan
    carries no claim (neither `claim_stage` nor `claim_owner`).
    Values are returned as written; lane derivation decides what to trust."""
    meta = parse_plan(path)["meta"]
    if not (meta.get(CLAIM_PREFIX + "stage") or meta.get(CLAIM_PREFIX + "owner")):
        return None
    return {f: (meta.get(CLAIM_PREFIX + f) or None) for f in CLAIM_FIELDS}


def _plan_path(root: Path, plan_id: int) -> Path:
    for item in read_config(root)["items"]:
        if item["id"] == plan_id:
            return roadmap_dir(root) / item["file"]
    raise ValueError(f"no plan with id {plan_id}")


# ---- required plan sections (plan 35) -----------------------------------------
# A plan whose required sections are still template text cannot have steps checked
# (`check` refuses unless --force). A name resolves to a `##` heading section when
# one matches (emoji/punctuation-insensitive prefix: "Root Cause" ↔ "## 🩺 Root
# Cause"), otherwise to a `**Label:**` bullet field ("Observed", "Core objective").
# Override per type with settings.requiredSections ({"bug": [...], ...}; [] turns
# the gate off for that type). A required name the plan does not contain at all is
# skipped by default — plans created before the template had that section stay
# checkable — but counts as a stub when the type is listed in
# settings.requiredSections (the project opted into strictness).
DEFAULT_REQUIRED_SECTIONS = {
    "bug": ["Observed", "Root Cause", "Acceptance"],
    "feature": ["Core objective", "Acceptance"],
    "chore": ["Core objective", "Acceptance"],
    "refactor": ["Core objective", "Acceptance"],
}
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
# `**Label:**` / `**Label**:` bullets only — a bold sentence with no colon is prose.
_FIELD_RE = re.compile(r"^\s*[-*+]\s+\*\*([^*]+?)(?::\*\*|\*\*:)\s*(.*)$")
_BARE_BULLET_RE = re.compile(r"^\s*[-*+]\s*$")
_PLACEHOLDER_RE = re.compile(r"^<[^<>]*>$")


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _strip_comments(lines: list[str]) -> list[str]:
    """Drop HTML comments (single- or multi-line); fenced lines pass through."""
    out, in_comment, in_fence = [], False, False
    for line in lines:
        if not in_comment and _is_fence(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        text = line
        if in_comment:
            if "-->" not in text:
                continue
            text = text.split("-->", 1)[1]
            in_comment = False
        while "<!--" in text:
            head, _, rest = text.partition("<!--")
            if "-->" in rest:
                text = head + rest.split("-->", 1)[1]
            else:
                text, in_comment = head, True
        out.append(text)
    return out


def _is_empty_value(value: str) -> bool:
    v = value.strip()
    return not v or bool(_PLACEHOLDER_RE.match(v))


def _field_stub(lines: list[str], i: int) -> bool:
    """Is the `**Label:**` bullet at lines[i] still template (no value, or a bare
    `<...>` placeholder, with no indented continuation lines under it)?"""
    if not _is_empty_value(_FIELD_RE.match(lines[i]).group(2)):
        return False
    indent = len(lines[i]) - len(lines[i].lstrip())
    for line in lines[i + 1:]:
        if not line.strip():
            break
        if len(line) - len(line.lstrip()) <= indent:
            break
        if not _is_empty_value(re.sub(r"^\s*[-*+]\s*", "", line)):
            return False
    return True


def _section_stub(body: list[str]) -> bool:
    """A heading section is template while it has no content, or any of its lines
    is an unfilled template slot: an empty / `<...>` labeled bullet, a bare `-`,
    or a line that is nothing but a `<...>` placeholder."""
    content = [i for i, l in enumerate(body) if l.strip()]
    if not content:
        return True
    in_fence = False
    for i in content:
        line = body[i]
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _FIELD_RE.match(line):
            if _field_stub(body, i):
                return True
        elif _BARE_BULLET_RE.match(line) or _PLACEHOLDER_RE.match(
                re.sub(r"^\s*[-*+]\s+", "", line).strip()):
            return True
    return False


def required_sections(cfg: dict, type_: str) -> tuple[list[str], bool]:
    """(required names for `type_`, strict) — strict when the project configured
    this type in settings.requiredSections, so a missing section counts too."""
    custom = (cfg.get("settings") or {}).get("requiredSections")
    if isinstance(custom, dict) and isinstance(custom.get(type_), list):
        return [str(n) for n in custom[type_]], True
    return list(DEFAULT_REQUIRED_SECTIONS.get(type_, [])), False


def template_stubs(path: Path, names: list[str], strict: bool = False) -> list[str]:
    """The required section names (from `names`) that are still template text in
    the plan at `path`: present but empty / placeholder-only, or — when `strict` —
    absent altogether. Frontmatter and fenced code are never read as sections."""
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    lines = _strip_comments(text[m.end():].splitlines() if m else text.splitlines())
    headings, in_fence = [], False       # (line index, level, normalized text)
    fields = []                          # (line index, normalized label)
    for i, line in enumerate(lines):
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        hm = _HEADING_RE.match(line)
        if hm:
            headings.append((i, len(hm.group(1)), _norm_name(hm.group(2))))
            continue
        fm = _FIELD_RE.match(line)
        if fm:
            fields.append((i, _norm_name(fm.group(1))))
    stubs = []
    for name in names:
        key = _norm_name(name)
        if not key:
            continue
        head = next((h for h in headings if h[2].startswith(key)), None)
        if head is not None:
            i, level, _ = head
            end = next((j for j, lv, _ in headings if j > i and lv <= level), len(lines))
            if _section_stub(lines[i + 1:end]):
                stubs.append(name)
            continue
        field = next((f for f in fields if f[1] == key), None)
        if field is not None:
            if _field_stub(lines, field[0]):
                stubs.append(name)
        elif strict:
            stubs.append(name)
    return stubs


# ---- acceptance ledger (plan 43) ------------------------------------------------
# Each top-level bullet of the plan's `## ✅ Acceptance` section is a criterion,
# except `**Fails if:**` guards (any label starting "Fails"), which are never
# marked. `roadmap.py accept` records the verdict as a blockquote sub-line under
# the bullet — `  > accepted: DATE evidence` or `  > failed: DATE evidence` — a
# form STEP_RE never reads as a step. The last marker under a bullet wins.
ACCEPTANCE_SECTION_KEY = "acceptance"
ACCEPT_MARKER_RE = re.compile(
    r"^\s*>\s*(accepted|failed):\s*(?:(\d{4}-\d{2}-\d{2})\s*)?(.*)$", re.IGNORECASE)
_TOP_BULLET_RE = re.compile(r"^ ?[-*+]\s+(.*)$")
_LABEL_RE = re.compile(r"^\*\*([^*]+?)(?::\*\*|\*\*:)\s*(.*)$")


def _blank_comments(lines: list[str]) -> list[str]:
    """Like _strip_comments, but a line swallowed by a multi-line comment becomes
    "" so indices still line up with the original text."""
    out, in_comment, in_fence = [], False, False
    for line in lines:
        if not in_comment and _is_fence(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        text = line
        if in_comment:
            if "-->" not in text:
                out.append("")
                continue
            text = text.split("-->", 1)[1]
            in_comment = False
        while "<!--" in text:
            head, _, rest = text.partition("<!--")
            if "-->" in rest:
                text = head + rest.split("-->", 1)[1]
            else:
                text, in_comment = head, True
        out.append(text)
    return out


def acceptance_bullets(lines: list[str]) -> list[dict]:
    """The ✅ Acceptance bullets in `lines` (a plan's lines, frontmatter included
    or not), in order, as {n, kind, label, text, state, date, evidence, line, end}:
    `n` is the 1-based bullet number `accept --line` takes; `kind` is "guard" for a
    `Fails …:` bullet, else "criterion"; `state` is "met" / "failed" / None (guards
    are always None); `line` is the bullet's index in `lines` and `end` one past its
    last non-blank line (continuations and markers included). Fenced code and HTML
    comments are skipped. No Acceptance section → []."""
    clean = _blank_comments(lines)
    in_fence, start, level = False, None, 0
    end = len(lines)
    for i, line in enumerate(clean):
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        hm = _HEADING_RE.match(line)
        if not hm:
            continue
        if start is None:
            if _norm_name(hm.group(2)).startswith(ACCEPTANCE_SECTION_KEY):
                start, level = i + 1, len(hm.group(1))
        elif len(hm.group(1)) <= level:
            end = i
            break
    if start is None:
        return []
    out, in_fence = [], False
    for i in range(start, end):
        line = clean[i]
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        bm = _TOP_BULLET_RE.match(line)
        if bm:
            raw = bm.group(1).strip()
            lm = _LABEL_RE.match(raw)
            label = lm.group(1).strip() if lm else None
            out.append({"n": len(out) + 1,
                        "kind": "guard" if label and _norm_name(label).startswith("fails")
                        else "criterion",
                        "label": label, "text": (lm.group(2) if lm else raw).strip(),
                        "state": None, "date": None, "evidence": None,
                        "line": i, "end": i + 1})
            continue
        if not out or not line.strip():
            continue
        if not line[:1].isspace() and not line.lstrip().startswith(">"):
            continue                       # unindented prose after the list
        cur = out[-1]
        cur["end"] = i + 1
        mm = ACCEPT_MARKER_RE.match(line)
        if mm and cur["kind"] == "criterion":
            cur["state"] = "met" if mm.group(1).lower() == "accepted" else "failed"
            cur["date"], cur["evidence"] = mm.group(2), mm.group(3).strip() or None
    return out


def acceptance_summary(bullets: list[dict]) -> dict:
    """{met, failed, total} over the criteria (guards excluded)."""
    crit = [b for b in bullets if b["kind"] == "criterion"]
    return {"met": sum(b["state"] == "met" for b in crit),
            "failed": sum(b["state"] == "failed" for b in crit),
            "total": len(crit)}


def public_bullet(b: dict) -> dict:
    """An acceptance bullet without its line bookkeeping (payload shape)."""
    return {k: b[k] for k in ("n", "kind", "label", "text", "state", "date", "evidence")}


# ---- declared scope (plan 42) --------------------------------------------------
# The paths a plan says it will touch: `**Files to create:**` / `**Files to
# modify:**` blueprint bullets (any `**Files...:**` label, wrapped or nested lines
# included) and the `-> target:` part of steps. Backticked tokens win: when the
# text has any, only they count; otherwise every path-like word does. Text in
# parentheses is commentary and is dropped first. A token is a path when it has a
# `/`, a `*` glob, a file extension, is a dotfile or a well-known extensionless
# file (Dockerfile); commands (spaces), flags, URLs and prose words are not.
# `{a,b}` braces expand.
_TARGET_RE = re.compile(r"(?:->|\u2192)\s*targets?\s*:\s*(.*)$", re.IGNORECASE)
_FILES_LABEL_RE = re.compile(r"^(?:new |changed |touched )?files?\b")
_TICK_RE = re.compile(r"`([^`\n]+)`")
_PATH_CHARS_RE = re.compile(r"^[A-Za-z0-9_.\-/*{},@+~\[\]$()]+$")
_EXT_RE = re.compile(r"[^/.]\.[A-Za-z][A-Za-z0-9_-]{0,9}$")
_BRACE_RE = re.compile(r"\{([^{}]*,[^{}]*)\}")
_PROSE_DOTTED = {"e.g", "i.e", "etc", "vs", "cf", "a.k.a", "n.b", "ie", "eg"}
_BARE_FILES = {"dockerfile", "containerfile", "makefile", "gnumakefile",
               "procfile", "gemfile", "rakefile", "jenkinsfile", "vagrantfile",
               "brewfile", "justfile", "license", "codeowners"}

# Always allowed on any branch unless settings.scopeAllow removes them: tests,
# lockfiles and roadmap bookkeeping. Same pattern rules as declared paths.
DEFAULT_SCOPE_ALLOW = (
    "tests/", "test/", "__tests__/", "test_*.py", "*_test.py", "*_test.go",
    "*.test.*", "*.spec.*",
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml",
    "bun.lock", "bun.lockb", "poetry.lock", "uv.lock", "Pipfile.lock",
    "Cargo.lock", "Gemfile.lock", "composer.lock", "go.sum", "flake.lock",
    "Package.resolved", "pubspec.lock", "mix.lock", "*.lock",
    ".roadmap/", "ROADMAP.md", "CHANGELOG*.md",
)


def _drop_parens(text: str) -> str:
    """`text` without parenthesized commentary (nesting-aware; parens inside
    backticks are part of the token, e.g. a Next.js `app/(auth)/page.tsx`).
    Unbalanced parens leave the text unchanged."""
    out, depth, tick = [], 0, False
    for ch in text:
        if ch == "`" and depth == 0:
            tick = not tick
        elif not tick and ch == "(":
            depth += 1
            continue
        elif not tick and ch == ")" and depth:
            depth -= 1
            continue
        if depth == 0:
            out.append(ch)
    return text if depth else "".join(out)


def _expand_braces(tok: str) -> list[str]:
    m = _BRACE_RE.search(tok)
    if not m:
        return [tok]
    out = []
    for part in m.group(1).split(","):
        out.extend(_expand_braces(tok[:m.start()] + part.strip() + tok[m.end():]))
    return out


def _path_token(tok: str, ticked: bool) -> list[str]:
    """Patterns from one token, or [] when it is not a path."""
    tok = tok.strip()
    if not ticked:
        tok = tok.strip("\"'()[]").rstrip(".,;:!?").lstrip("(")
    else:
        tok = tok.rstrip(":,;")
    if not tok or "://" in tok or tok.startswith(("-", "~")) \
            or not _PATH_CHARS_RE.match(tok):
        return []
    while tok.startswith("./"):
        tok = tok[2:]
    tok = tok.lstrip("/")
    if tok in ("", ".", "*", "**") or tok.lower().rstrip(".") in _PROSE_DOTTED:
        return []
    base = tok.rstrip("/").rsplit("/", 1)[-1]
    if not ("/" in tok or "*" in tok or _EXT_RE.search(base)
            or (base.startswith(".") and len(base) > 1)
            or base.lower() in _BARE_FILES):
        return []
    return [t for t in _expand_braces(tok) if t and t not in ("*", "**")]


def _paths_in(text: str) -> list[str]:
    """Path patterns in one field/target text (see the section comment)."""
    text = _drop_parens(text)
    ticks = _TICK_RE.findall(text)
    if ticks:
        tokens = [(t, True) for t in ticks if not re.search(r"\s", t.strip())]
    else:
        tokens = [(t, False) for t in re.split(r"[\s,;]+", text)]
    out: list[str] = []
    for tok, ticked in tokens:
        out.extend(_path_token(tok, ticked))
    return out


def declared_paths(body: str) -> list[str]:
    """Every path pattern a plan body declares (blueprint `**Files...:**`
    bullets with their continuation lines, and `-> target:` step parts), in
    first-seen order, deduplicated. Fenced code and HTML comments are skipped."""
    lines = _strip_comments(body.splitlines())
    found: list[str] = []
    in_fence, i = False, 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        fm = _FIELD_RE.match(line)
        if fm and _FILES_LABEL_RE.match(_norm_name(fm.group(1))):
            parts, indent = [fm.group(2)], len(line) - len(line.lstrip())
            while i < len(lines) and lines[i].strip() and not _is_fence(lines[i]) \
                    and len(lines[i]) - len(lines[i].lstrip()) > indent:
                parts.append(lines[i].strip())
                i += 1
            found.extend(_paths_in("\n".join(parts)))
            continue
        tm = _TARGET_RE.search(line)
        if tm:
            found.extend(_paths_in(tm.group(1)))
    return list(dict.fromkeys(found))


def _glob_re(pat: str) -> str:
    out, i = [], 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out.append("(?:[^/]+/)*")
            i += 3
        elif pat.startswith("**", i):
            out.append(".*")
            i += 2
        elif pat[i] == "*":
            out.append("[^/]*")
            i += 1
        else:
            out.append(re.escape(pat[i]))
            i += 1
    return "".join(out)


@functools.lru_cache(maxsize=4096)
def _scope_re(pattern: str) -> re.Pattern | None:
    p = pattern.strip()
    while p.startswith("./"):
        p = p[2:]
    p = p.lstrip("/")
    if not p:
        return None
    if p.endswith("/"):
        return re.compile("(?:^|/)" + _glob_re(p.rstrip("/")) + "/")
    return re.compile("(?:^|/)" + _glob_re(p) + "(?:/|$)")


def path_matches(pattern: str, path: str) -> bool:
    """Does repo path `path` fall under `pattern`? Patterns anchor at a path
    component boundary anywhere in the path, so plans may name a path relative
    to a subfolder (`rmlib/parse.py` matches `skills/roadmap/scripts/rmlib/
    parse.py`). A trailing `/` means a directory; a name without one matches
    the file or a directory of that name. `*` stays inside one component, `**`
    crosses them."""
    rx = _scope_re(pattern)
    return bool(rx and rx.search(path))


def scope_allow(settings: dict | None) -> list[str]:
    """Always-allowed patterns: DEFAULT_SCOPE_ALLOW plus settings.scopeAllow
    entries; an entry `!pattern` removes that default instead."""
    extra = (settings or {}).get("scopeAllow")
    extra = [str(x).strip() for x in extra if str(x).strip()] \
        if isinstance(extra, list) else []
    drop = {x[1:].strip() for x in extra if x.startswith("!")}
    out = [p for p in DEFAULT_SCOPE_ALLOW if p not in drop]
    for x in extra:
        if not x.startswith("!"):
            out.extend(_expand_braces(x))
    return list(dict.fromkeys(out))


def off_plan(changed: list[str], declared: list[str], allow: list[str]) -> list[str]:
    """The changed paths no declared or allowed pattern covers, in order."""
    return [p for p in changed
            if not any(path_matches(d, p) for d in declared)
            and not any(path_matches(a, p) for a in allow)]
