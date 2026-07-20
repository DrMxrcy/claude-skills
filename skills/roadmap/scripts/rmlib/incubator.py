"""roadmap idea incubator & tidy — parking ideas, listing bullets, externalizing,
and grooming the free-form region. Layer: rmcore + rmsync (health in tidy)."""
from __future__ import annotations
import datetime
import re
from pathlib import Path
from rmlib.sync import roadmap_health
from rmlib.core import (
    AUTO_END, AUTO_START, atomic_write, read_config, roadmap_dir, slugify,
    write_config)


INCUBATOR_RE = re.compile(r"(?im)^#{1,6}\s+.*idea incubator.*$")


INCUBATOR_HEADING = "## 💡 Idea Incubator"


def incubator_file(root: Path) -> Path:
    """Where Idea Incubator bullets live: ROADMAP.md by default, or the external file
    named by settings.incubatorFile (set by `tidy --externalize`)."""
    try:
        rel = read_config(root).get("settings", {}).get("incubatorFile")
    except (ValueError, FileNotFoundError):
        rel = None
    return (root / rel) if rel else (root / "ROADMAP.md")


def _incubator_append(root: Path, stub: str) -> None:
    """Append one bullet under the free-form Idea Incubator heading, creating the
    heading (or the external incubator file) if missing. Edits happen outside the
    roadmap:auto markers, which sync owns."""
    target = incubator_file(root)
    if not target.exists():
        atomic_write(target, f"{INCUBATOR_HEADING}\n{stub}\n")
        return
    text = target.read_text(encoding="utf-8")
    m = INCUBATOR_RE.search(text)
    if m:
        new = text[:m.end()] + "\n" + stub + text[m.end():]
    else:
        new = text.rstrip() + f"\n\n{INCUBATOR_HEADING}\n{stub}\n"
    atomic_write(target, new)


def _incubator_stub(root: Path, plan_id: int, title: str, archived: str | None = None) -> None:
    """Breadcrumb for a removed item, linking the archived plan file when one was kept."""
    stub = f"- (was #{plan_id}) {title}"
    if archived:
        stub += f" ([archived plan]({archived}))"
    _incubator_append(root, stub)


def _strip_incubator_placeholder(root: Path) -> None:
    """Remove the template placeholder bullet so real ideas stand alone."""
    target = incubator_file(root)
    if not target.exists():
        return
    text = target.read_text(encoding="utf-8")
    new = re.sub(r"(?m)^\s*[-*+]\s+\(add ideas here\)\s*\n?", "", text)
    if new != text:
        atomic_write(target, new)


def add_idea(root: Path, title: str, body: str | None = None) -> Path | None:
    """Park an idea as ONE incubator bullet. Long-form content (brainstorm output,
    deferred review findings, phase sketches) goes to a linked note file under
    .roadmap/notes/ so ROADMAP.md itself stays short."""
    title = title.strip()
    if not title:
        raise ValueError("idea title must not be empty")
    read_config(root)  # fail early with a clear error if not initialized
    _strip_incubator_placeholder(root)
    stub = f"- {title}"
    note_path = None
    if body and body.strip():
        slug = slugify(title) or "idea"
        notes = roadmap_dir(root) / "notes"
        base = f"{datetime.date.today().isoformat()}-{slug}"
        dest, n = notes / f"{base}.md", 2
        while dest.exists():
            dest, n = notes / f"{base}-{n}.md", n + 1
        atomic_write(dest, f"# {title}\n\n{body.strip()}\n")
        note_path = dest
        stub += f" ([notes]({dest.relative_to(root)}))"
    _incubator_append(root, stub)
    return note_path


MAX_BULLET_CHARS = 200


DUPLICATE_RATIO = 0.8


MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+\.md)\)")


def _freeform_lines(text: str) -> list[str]:
    """Lines of ROADMAP.md outside the roadmap:auto region."""
    out, in_auto = [], False
    for line in text.splitlines():
        if AUTO_START in line:
            in_auto = True
        elif AUTO_END in line:
            in_auto = False
        elif not in_auto:
            out.append(line)
    return out


def _norm_title(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", s.lower()).strip()


def externalize_incubator(root: Path, file: str = ".roadmap/IDEAS.md") -> Path:
    """Move the Idea Incubator region out of ROADMAP.md into `file` (verbatim,
    lossless), leave one linked bullet on the dashboard, and record
    settings.incubatorFile so idea/promote/remove target the new home."""
    cfg = read_config(root)
    settings = cfg.setdefault("settings", {})
    if settings.get("incubatorFile"):
        raise ValueError(f"incubator is already external: {settings['incubatorFile']}")
    dest = root / file
    if dest.exists():
        raise ValueError(f"{file} already exists — pick another path")
    rm = root / "ROADMAP.md"
    text = rm.read_text(encoding="utf-8") if rm.exists() else ""
    link = (f"- Parked ideas live in [{file}]({file}) — "
            "`roadmap.py idea` / `promote` target it.\n")
    kept, moved, in_region = [], [], False
    for ln in text.splitlines(keepends=True):
        if not in_region and INCUBATOR_RE.match(ln.rstrip("\n")):
            in_region = True
            kept.append(ln if ln.endswith("\n") else ln + "\n")
            kept.append(link)
            continue
        if in_region and (AUTO_START in ln or re.match(r"^#{1,6}\s", ln)):
            in_region = False
        (moved if in_region else kept).append(ln)
    if not any(INCUBATOR_RE.match(l.rstrip("\n")) for l in kept):
        kept.append(f"\n{INCUBATOR_HEADING}\n{link}")
    body = "".join(moved).strip("\n")
    atomic_write(dest, f"{INCUBATOR_HEADING}\n" + (body + "\n" if body else ""))
    atomic_write(rm, "".join(kept))
    settings["incubatorFile"] = file
    write_config(root, cfg)
    return dest


def tidy_report(root: Path) -> dict:
    """Analyze the free-form region of ROADMAP.md (Idea Incubator + surrounding prose,
    plus the external incubator file when settings.incubatorFile is set) and report
    what needs grooming. Report-only by design: scripts never rewrite the free-form
    region — the /roadmap:tidy command flow applies the judgment edits."""
    import difflib
    rm = root / "ROADMAP.md"
    report = {"clean": True, "warnings": [], "bullets": [],
              "prose": {"lines": 0, "leads": []}}
    if not rm.exists():
        return report
    report["warnings"] = roadmap_health(root)
    try:
        tracked = [(i["id"], i["title"]) for i in read_config(root)["items"]]
    except (ValueError, FileNotFoundError, KeyError):
        tracked = []

    src_lines = _freeform_lines(rm.read_text(encoding="utf-8"))
    inc = incubator_file(root)
    if inc != rm and inc.exists():
        src_lines += inc.read_text(encoding="utf-8").splitlines()

    bullets, prose = [], report["prose"]
    cur = None
    seen_h1 = in_comment = False
    for line in src_lines:
        stripped = line.strip()
        if in_comment:
            in_comment = "-->" not in stripped
            cur = None
            continue
        if stripped.startswith("<!--"):
            in_comment = "-->" not in stripped
            cur = None
            continue
        if not stripped:
            cur = None
            continue
        if re.match(r"^#\s", line):
            if not seen_h1:
                seen_h1 = True
                continue
        if re.match(r"^#{1,6}\s", line):
            cur = None
            if not INCUBATOR_RE.match(line):
                prose["leads"].append(stripped[:70])
            continue
        if re.match(r"^[-*+]\s", line):
            cur = {"index": len(bullets) + 1, "text": stripped[2:].strip(),
                   "chars": len(stripped), "children": 0}
            bullets.append(cur)
            continue
        if re.match(r"^\s+\S", line) and cur is not None:
            cur["chars"] += len(stripped)
            if re.match(r"^\s+[-*+]\s", line):
                cur["children"] += 1
            continue
        cur = None
        prose["lines"] += 1
        if stripped.startswith("**"):
            prose["leads"].append(stripped[:70])

    for b in bullets:
        title = re.sub(r"\s*\([^)]*\)\s*$", "", b["text"]).strip()
        title = re.sub(r"\s*\[[^\]]*\]\([^)]*\)\s*$", "", title).strip()
        entry = {"index": b["index"], "title": title[:100], "chars": b["chars"],
                 "children": b["children"],
                 "notesLink": bool(MD_LINK_RE.search(b["text"])), "flags": []}
        if b["children"]:
            entry["flags"].append("nested")
        if b["chars"] > MAX_BULLET_CHARS and not entry["notesLink"]:
            entry["flags"].append("long-no-link")
        elif b["chars"] > 2 * MAX_BULLET_CHARS:
            entry["flags"].append("long")
        norm = _norm_title(title)
        if norm and tracked:
            best = max(tracked, key=lambda t: difflib.SequenceMatcher(
                None, norm, _norm_title(t[1])).ratio())
            if difflib.SequenceMatcher(
                    None, norm, _norm_title(best[1])).ratio() >= DUPLICATE_RATIO:
                entry["flags"].append("duplicate")
                entry["duplicateOf"] = best[0]
        if entry["flags"]:
            report["bullets"].append(entry)

    report["clean"] = not (report["warnings"] or report["bullets"] or prose["lines"])
    return report


def format_tidy(report: dict) -> str:
    if report["clean"]:
        return "ROADMAP.md free-form region: clean — nothing to tidy."
    out = ["ROADMAP.md free-form region needs grooming:"]
    for w in report["warnings"]:
        out.append(f"  ! {w}")
    for b in report["bullets"]:
        detail = [f"{b['chars']} chars"]
        if b["children"]:
            detail.append(f"{b['children']} sub-bullets")
        if not b["notesLink"]:
            detail.append("no notes link")
        if "duplicate" in b["flags"]:
            detail.append(f"≈ tracked item #{b['duplicateOf']}")
        out.append(f"  - bullet {b['index']} “{b['title']}” — " + ", ".join(detail))
    if report["prose"]["lines"]:
        leads = "; ".join(report["prose"]["leads"][:5])
        out.append(f"  - {report['prose']['lines']} prose line(s) outside any bullet"
                   + (f" (sections: {leads})" if leads else ""))
    out.append("Groom with /roadmap:tidy · /roadmap-tidy — move bodies to linked "
               ".roadmap/notes/ files, one bullet per idea; drop bullets that "
               "duplicate tracked items (or promote them).")
    return "\n".join(out)


INCUBATOR_BULLET_RE = re.compile(r"^(\s*[-*+]\s+)(.+)$")


def list_incubator_bullets(root: Path) -> list[dict]:
    """Parse free-form Idea Incubator bullets (from ROADMAP.md, or the external
    incubator file when settings.incubatorFile is set)."""
    rm = incubator_file(root)
    if not rm.exists():
        return []
    text = rm.read_text(encoding="utf-8")
    m = INCUBATOR_RE.search(text)
    if not m:
        return []
    bullets = []
    for line in text[m.end():].splitlines():
        if re.match(r"^#{1,6}\s+", line):
            break
        bm = INCUBATOR_BULLET_RE.match(line)
        if not bm:
            continue
        body = bm.group(2).strip()
        # Title is the line without a trailing markdown link
        title = re.sub(r"\s*\([^)]*\)\s*$", "", body).strip()
        title = re.sub(r"\s*\[[^\]]*\]\([^)]*\)\s*$", "", title).strip()
        bullets.append({"line": line, "body": body, "title": title or body})
    return bullets
