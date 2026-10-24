"""roadmap plan parsing — read plan .md files (checklist steps, frontmatter).
Pure/leaf layer: depends only on rmcore."""
from __future__ import annotations
import re
from pathlib import Path
from rmlib.core import read_config, roadmap_dir


STEP_RE = re.compile(r"^(\s*[-*]\s+)\[( |x|X)\](.*)$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

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
    steps = []
    in_fence = False
    for line in text.splitlines():
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        sm = STEP_RE.match(line)
        if sm:
            steps.append((sm.group(2).lower() == "x", sm.group(3).strip()))
    body = text[m.end():] if m else text
    result = {"meta": meta, "steps": steps, "rulings": parse_rulings(body),
              "foundDuringBuild": parse_found(body)}
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
