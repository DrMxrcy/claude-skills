#!/usr/bin/env python3
"""roadmap — deterministic CLI for the roadmap skill (Python 3 stdlib only)."""
from __future__ import annotations
import argparse, datetime, json, os, re, subprocess, sys, tempfile
from pathlib import Path

# Submodules live beside this file; ensure this dir is importable whether we are
# run as a script or imported under another name (tests load us via importlib).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rmcore import (  # noqa: E402  (re-exported so callers/tests keep roadmap.X)
    TEMPLATES_DIR, AUTO_START, AUTO_END, RULES_START, RULES_END, RULES_BLOCK,
    RULES_FILES, get_version, roadmap_dir, find_root, atomic_write, read_config,
    write_config, slugify, _render_template, _version_from_pyproject,
    detect_version, derive_status, _set_frontmatter, _norm_version, _version_key)


from rmsync import (  # noqa: E402
    _incomplete_deps, _item_done, _next_current_version, _progress_map,
    _version_complete, incomplete_deps, next_item, render_region,
    roadmap_health, status, sync, warn_incomplete_deps, MAX_ROADMAP_LINES,
    MAX_FREEFORM_LINES, MAX_FREEFORM_CHARS)








from rmparse import (  # noqa: E402
    STEP_RE, _is_fence, parse_plan, count_progress, _plan_path)


def check_step(root: Path, plan_id: int, step: int | None,
               undo: bool = False, all_done: bool = False) -> None:
    path = _plan_path(root, plan_id)
    box = "[ ]" if undo else "[x]"
    out, n, in_fence = [], 0, False
    for line in path.read_text(encoding="utf-8").splitlines():
        if _is_fence(line):
            in_fence = not in_fence
            out.append(line)
            continue
        sm = None if in_fence else STEP_RE.match(line)
        if sm:
            n += 1
            if all_done or n == step:
                line = re.sub(r"\[( |x|X)\]", box, line, count=1)
        out.append(line)
    if step is not None and not all_done and (step < 1 or step > n):
        raise ValueError(f"plan {plan_id} step {step} out of range (1..{n})")
    atomic_write(path, "\n".join(out) + "\n")
    sync(root)
    if not undo:
        _record_last_seen_sha(root)


TEMPLATE_BY_TYPE = {"feature": "feature-plan.md", "chore": "feature-plan.md",
                    "bug": "bug-investigation.md", "refactor": "refactor-debt.md"}


def _refuse_status_note(item: dict, note: str, force: bool) -> None:
    """Refuse (ValueError) a note that would render PUBLIC but is structurally a
    status/progress dump. `item` may be a candidate dict (new item / new note applied) —
    audience is judged with the candidate note so auto-demoted items pass through
    untouched (they render internal anyway)."""
    if force or not note or item_audience(item) != "public":
        return
    tells = status_tells(note)
    if tells:
        raise ValueError(
            f"note refused — this reads like a status/progress dump, not a release note "
            f"({', '.join(tells)}). CHANGELOG.md is pasted into the App Store \"What's New\": "
            f"write ONE plain sentence of user benefit — no dates, step numbers, version "
            f"refs, file paths, issue refs, or ALL-CAPS status words. Progress notes belong "
            f"in the plan file, not the changelog. Alternatively mark the item internal "
            f"(roadmap audience --plan {item.get('id', '<id>')} --to internal) or re-run "
            f"with --force if this text really should ship to end users.")


def new_item(root: Path, type_: str, title: str, version: str | None = None,
             note: str = "", audience: str | None = None, force: bool = False) -> Path:
    if type_ not in TEMPLATE_BY_TYPE:
        raise ValueError(f"unknown type {type_!r}; choose from {sorted(TEMPLATE_BY_TYPE)}")
    cfg = read_config(root)
    item_id = cfg["nextId"]
    _refuse_status_note({"id": item_id, "title": title, "type": type_,
                         "note": note, "audience": audience}, note, force)
    version = _norm_version(version or cfg["currentVersion"])
    slug = slugify(title)
    if not slug:
        raise ValueError(f"title {title!r} produces an empty slug; use alphanumeric characters")
    fname = f"plans/{item_id:03d}-{slug}.md"
    path = roadmap_dir(root) / fname
    atomic_write(path, _render_template(
        TEMPLATE_BY_TYPE[type_], ID=item_id, TITLE=title, TYPE=type_,
        VERSION=version, DATE=datetime.date.today().isoformat()))
    cfg["nextId"] += 1
    item = {"id": item_id, "slug": slug, "title": title,
            "type": type_, "version": version, "file": fname}
    if note:
        item["note"] = note            # user-facing changelog line (optional)
    if audience in ("public", "internal"):
        item["audience"] = audience    # else falls back to DEFAULT_AUDIENCE by type
    cfg["items"].append(item)
    write_config(root, cfg)
    sync(root)
    return path


def set_note(root: Path, plan_id: int, text: str, force: bool = False) -> None:
    """Set an item's user-facing changelog note, then re-render. A note that would render
    PUBLIC but is structurally a status dump (dates, step/version refs, paths, shouted
    status words) is REFUSED unless --force; softer internal wording only warns."""
    cfg = read_config(root)
    for item in cfg["items"]:
        if item["id"] == plan_id:
            _refuse_status_note({**item, "note": text}, text, force)
            item["note"] = text
            write_config(root, cfg)
            blob = f"{text} {item['title']}"
            if item.get("audience") is None and demote_tells(blob):
                print(f"warning: #{plan_id} auto-routed to the internal changelog "
                      f"({', '.join(demote_tells(blob))}); if it really is user-facing, "
                      f"override: roadmap audience --plan {plan_id} --to public", file=sys.stderr)
            elif item_audience(item) == "public":
                tells = lint_note(text, cfg.get("settings", {}).get("internalTerms", []))
                if tells:
                    print(f"warning: #{plan_id} note reads internal ({', '.join(tells)}); "
                          f"CHANGELOG.md is user-facing. Rephrase in plain benefit language, "
                          f"or mark it internal: roadmap audience --plan {plan_id} --to internal",
                          file=sys.stderr)
            sync(root)
            return
    raise ValueError(f"no plan with id {plan_id}")


def set_release_summary(root: Path, version: str, text: str | None = None,
                        clear: bool = False, force: bool = False) -> None:
    """Set (or clear) a version's public release-notes blurb. When a version has a blurb,
    the PUBLIC changelog renders it INSTEAD of per-item bullets — the blurb is the App
    Store "What's New" text; per-item detail stays in CHANGELOG.internal.md. Same
    status-dump gate as item notes (--force overrides); softer wording only warns."""
    version = _norm_version(version)
    cfg = read_config(root)
    summaries = cfg.setdefault("releaseNotes", {})
    if clear:
        summaries.pop(version, None)
        write_config(root, cfg)
        sync(root)
        return
    if text is None:
        raise ValueError("pass --text (or --clear to remove the summary)")
    known = {i["version"] for i in cfg["items"]}
    if version not in known and version not in summaries:
        raise ValueError(f"no items target version {version} "
                         f"(known: {', '.join(sorted(known, key=_version_key))})")
    if not force:
        tells = status_tells(text)
        if tells:
            raise ValueError(
                f"summary refused — reads like a status/progress dump, not release notes "
                f"({', '.join(tells)}). The blurb ships verbatim to end users: keep it a "
                f"short, warm 'What's New' — no dates, step numbers, version refs, paths, "
                f"issue refs, or ALL-CAPS status words (the version header is added for "
                f"you). Re-run with --force if the text really should ship as-is.")
    summaries[version] = text.strip()
    write_config(root, cfg)
    tells = lint_note(text, cfg.get("settings", {}).get("internalTerms", []))
    if tells:
        print(f"warning: v{version} summary has internal-sounding wording "
              f"({', '.join(tells)}); it ships verbatim to end users — consider rephrasing.",
              file=sys.stderr)
    sync(root)


def set_audience(root: Path, plan_id: int, audience: str) -> None:
    """Set an item's changelog audience ('public' | 'internal'), then re-render both files."""
    if audience not in ("public", "internal"):
        raise ValueError("audience must be 'public' or 'internal'")
    cfg = read_config(root)
    for item in cfg["items"]:
        if item["id"] == plan_id:
            item["audience"] = audience
            write_config(root, cfg)
            sync(root)
            return
    raise ValueError(f"no plan with id {plan_id}")


def set_depends(root: Path, plan_id: int, on: list[int], clear: bool = False) -> None:
    """Set (or clear) an item's `dependsOn` list. Consumed by `next` (skips blocked),
    `build` (warns), /roadmap:reevaluate, and retargeted by merge/remove."""
    cfg = read_config(root)
    by_id = {i["id"]: i for i in cfg["items"]}
    if plan_id not in by_id:
        raise ValueError(f"no plan with id {plan_id}")
    if clear:
        by_id[plan_id].pop("dependsOn", None)
        write_config(root, cfg)
        return
    if plan_id in on:
        raise ValueError(f"plan #{plan_id} cannot depend on itself")
    for d in on:
        if d not in by_id:
            raise ValueError(f"no plan with id {d}")
    # Reject trivial cycles (self already handled; A→B→A via one hop of existing edges)
    for d in on:
        if plan_id in (by_id[d].get("dependsOn") or []):
            raise ValueError(f"dependency cycle: #{plan_id} ↔ #{d}")
    by_id[plan_id]["dependsOn"] = list(dict.fromkeys(on))
    write_config(root, cfg)


from rmincubator import (  # noqa: E402
    DUPLICATE_RATIO, INCUBATOR_BULLET_RE, INCUBATOR_HEADING, INCUBATOR_RE,
    MAX_BULLET_CHARS, MD_LINK_RE, _freeform_lines, _incubator_append,
    _incubator_stub, _norm_title, _strip_incubator_placeholder, add_idea,
    externalize_incubator, format_tidy, incubator_file,
    list_incubator_bullets, tidy_report)












def remove_item(root: Path, plan_id: int) -> None:
    """Remove a tracked item: archive its plan file, drop it from the registry, clear any
    dependency that pointed at it, and demote it to the Idea Incubator. Reversible."""
    cfg = read_config(root)
    by_id = {i["id"]: i for i in cfg["items"]}
    if plan_id not in by_id:
        raise ValueError(f"no plan with id {plan_id}")
    item = by_id[plan_id]
    dependents = [i["id"] for i in cfg["items"] if plan_id in (i.get("dependsOn") or [])]
    if dependents:
        print(f"Warning: #{dependents} depended on #{plan_id}; clearing that link.",
              file=sys.stderr)
    src = roadmap_dir(root) / item["file"]
    archived = None
    if src.exists():
        dest = roadmap_dir(root) / "archive" / Path(item["file"]).name
        atomic_write(dest, src.read_text(encoding="utf-8"))
        src.unlink()
        archived = str(dest.relative_to(root))
    cfg["items"] = [i for i in cfg["items"] if i["id"] != plan_id]
    for i in cfg["items"]:
        deps = i.get("dependsOn")
        if deps and plan_id in deps:
            new = [d for d in deps if d != plan_id]
            if new:
                i["dependsOn"] = new
            else:
                i.pop("dependsOn", None)
    write_config(root, cfg)
    _incubator_stub(root, plan_id, item["title"], archived)
    sync(root)


def retarget(root: Path, to: str, from_versions: list[str] | None = None,
             plan_ids: list[int] | None = None) -> None:
    """Re-stamp existing items onto version `to`. Select either by source versions
    (`from_versions`) or by item ids (`plan_ids`) — exactly one. Used to consolidate work
    spread across versions (e.g. fold v1.0.0–v1.6.0 into a single v1.0.0 on a release branch).
    Leaves currentVersion untouched; the git branch is the caller's workflow."""
    if bool(from_versions) == bool(plan_ids):
        raise ValueError("pass exactly one of from_versions / plan_ids")
    to = _norm_version(to)
    cfg = read_config(root)
    by_id = {i["id"]: i for i in cfg["items"]}
    if plan_ids:
        for pid in plan_ids:
            if pid not in by_id:
                raise ValueError(f"no plan with id {pid}")
        selected = [by_id[pid] for pid in plan_ids]
    else:
        wanted = {_norm_version(v) for v in from_versions}
        present = {i["version"] for i in cfg["items"]}
        for v in wanted - present:
            print(f"Warning: no items in version {v}; skipping.", file=sys.stderr)
        selected = [i for i in cfg["items"] if i["version"] in wanted]
    if not selected:
        raise ValueError("retarget selected no items")
    for item in selected:
        item["version"] = to
        path = roadmap_dir(root) / item["file"]
        if path.exists():
            _set_frontmatter(path, "version", to)
    write_config(root, cfg)
    sync(root)


def reorder(root: Path, version: str, ids: list[int]) -> None:
    """Set explicit display/build order for items within a version."""
    version = _norm_version(version)
    cfg = read_config(root)
    in_version = {i["id"] for i in cfg["items"] if i["version"] == version}
    stray = [i for i in ids if i not in in_version]
    if stray:
        raise ValueError(f"id(s) {stray} are not in version {version}")
    pos = {iid: n for n, iid in enumerate(ids)}
    for item in cfg["items"]:
        if item["id"] in pos:
            item["order"] = pos[item["id"]]
    write_config(root, cfg)
    sync(root)


def merge_items(root: Path, keep_id: int, source_ids: list[int]) -> None:
    """Combine `source_ids` into `keep_id`: append their checklist steps to the keeper's
    plan, delete the source plans, drop them from the registry, and retarget any
    dependency that pointed at a source to the keeper. Used to dedupe/consolidate."""
    if keep_id in source_ids:
        raise ValueError(f"keeper #{keep_id} cannot be in the sources")
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("duplicate source ids")
    cfg = read_config(root)
    by_id = {i["id"]: i for i in cfg["items"]}
    for iid in [keep_id, *source_ids]:
        if iid not in by_id:
            raise ValueError(f"no plan with id {iid}")
    keep_path = roadmap_dir(root) / by_id[keep_id]["file"]
    appended = []
    for sid in source_ids:
        src = by_id[sid]
        sp = roadmap_dir(root) / src["file"]
        if sp.exists():
            steps = parse_plan(sp)["steps"]
            appended.append(f"\n## Merged from #{sid} {src['title']}\n")
            appended += [f"- [{'x' if done else ' '}] {txt}" for done, txt in steps]
            sp.unlink()
    if appended:
        atomic_write(keep_path, keep_path.read_text(encoding="utf-8").rstrip()
                     + "\n" + "\n".join(appended) + "\n")
    drop = set(source_ids)
    cfg["items"] = [i for i in cfg["items"] if i["id"] not in drop]
    for item in cfg["items"]:                       # retarget dependencies to the keeper
        deps = item.get("dependsOn")
        if deps:
            new = [keep_id if d in drop else d for d in deps]
            new = [d for d in dict.fromkeys(new) if d != item["id"]]
            if new:
                item["dependsOn"] = new
            else:
                item.pop("dependsOn", None)
    write_config(root, cfg)
    sync(root)


def _incomplete_items(root: Path, version: str) -> list[dict]:
    out = []
    for item in read_config(root)["items"]:
        if item["version"] == version:
            p = roadmap_dir(root) / item["file"]
            done, total = count_progress(p) if p.exists() else (0, 0)
            if not (total > 0 and done == total):
                out.append(item)
    return out


# type → user-facing changelog section (App Store / website friendly)
from rmchangelog import (  # noqa: E402
    TYPE_SECTION, SECTION_ORDER, DEFAULT_AUDIENCE, ROLLUP_LINE,
    WARN_VENDORS, WARN_JARGON, WARN_TELLS, DEMOTE_ADMIN, DEMOTE_COMPLIANCE,
    DEMOTE_SECURITY, DEMOTE_PLUMBING, DEMOTE_TELLS, _PATH_RE, _SEG_RE,
    _REF_RE, _STATUS_RES, _word_hits, _dedupe, status_tells, lint_note,
    demote_tells, item_audience, _changelog_versions, _grouped_lines,
    render_public_changelog, changelog_json, render_internal_changelog,
    audit_public_notes)


def backfill_changelog(root: Path) -> None:
    """For each version lacking a recorded date, adopt its matching git tag's commit date
    (git tag v<ver>). Versions without a tag stay undated. Then re-sync to re-render."""
    cfg = read_config(root)
    version_dates = cfg.setdefault("versionDates", {})
    changed = False
    for version in {i["version"] for i in cfg["items"]}:
        if version in version_dates:
            continue
        out = subprocess.run(["git", "log", "-1", "--format=%cs", f"v{version}"],
                             cwd=str(root), capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            version_dates[version] = out.stdout.strip()
            changed = True
    if changed:
        write_config(root, cfg)
    sync(root)


def release(root: Path, version: str, tag: bool = False, force: bool = False) -> None:
    version = _norm_version(version)
    cfg = read_config(root)
    outgoing = cfg["currentVersion"]
    incomplete = _incomplete_items(root, outgoing)
    if incomplete and not force:
        names = ", ".join(f"#{i['id']} {i['title']}" for i in incomplete)
        raise ValueError(
            f"v{outgoing} still has incomplete items: {names}. "
            f"Finish them (see /roadmap:review) or pass --force.")
    cfg["currentVersion"] = version
    write_config(root, cfg)
    sync(root)
    if tag or cfg["settings"].get("gitTagOnRelease"):
        result = subprocess.run(["git", "tag", f"v{version}"], cwd=str(root), check=False)
        if result.returncode != 0:
            print(f"Warning: 'git tag v{version}' failed (exit {result.returncode}); "
                  "version recorded in config but not tagged.", file=sys.stderr)
































from rmreport import (  # noqa: E402
    _git_dirty, _git_head, _record_last_seen_sha, drift_check,
    format_orient, handoff, orient)


















def promote_idea(root: Path, *, match: str | None = None, index: int | None = None,
                 type_: str = "feature", version: str | None = None,
                 note: str = "", audience: str | None = None,
                 force: bool = False) -> Path:
    """Lift one Idea Incubator bullet into a tracked plan item and remove that bullet.

    Select by 1-based --index or by --match substring against the bullet title.
    Exactly one selector required when multiple bullets exist; a single bullet can be
    promoted with no selector.
    """
    if match and index is not None:
        raise ValueError("pass only one of --match / --index")
    _strip_incubator_placeholder(root)
    bullets = list_incubator_bullets(root)
    if not bullets:
        raise ValueError("Idea Incubator is empty — nothing to promote")
    chosen = None
    if index is not None:
        if index < 1 or index > len(bullets):
            raise ValueError(f"--index {index} out of range (1..{len(bullets)})")
        chosen = bullets[index - 1]
    elif match:
        hits = [b for b in bullets if match.lower() in b["title"].lower()
                or match.lower() in b["body"].lower()]
        if not hits:
            raise ValueError(f"no incubator bullet matches {match!r}")
        if len(hits) > 1:
            raise ValueError(
                f"{len(hits)} bullets match {match!r}; use a tighter --match or --index")
        chosen = hits[0]
    elif len(bullets) == 1:
        chosen = bullets[0]
    else:
        listing = "\n".join(f"  {i}. {b['title']}" for i, b in enumerate(bullets, 1))
        raise ValueError(
            f"multiple incubator bullets — pass --index N or --match TEXT:\n{listing}")

    title = chosen["title"]
    path = new_item(root, type_, title, version=version, note=note, audience=audience,
                    force=force)

    # Remove only the chosen bullet from the incubator (free-form region).
    rm = incubator_file(root)
    text = rm.read_text(encoding="utf-8")
    new_lines, removed = [], False
    target = chosen["line"].rstrip("\n")
    for line in text.splitlines(keepends=True):
        if not removed and line.rstrip("\n") == target:
            removed = True
            continue
        if not removed and chosen["body"] in line and INCUBATOR_BULLET_RE.match(
                line.rstrip("\n")):
            removed = True
            continue
        new_lines.append(line)
    atomic_write(rm, "".join(new_lines))
    return path


def import_file(root: Path, src: Path) -> list[Path]:
    extracted = []
    in_fence = False
    for line in src.read_text(encoding="utf-8").splitlines():
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        sm = STEP_RE.match(line)
        if sm:
            extracted.append((sm.group(2).lower() == "x", sm.group(3).strip()))
    if not extracted:
        return []
    title = src.stem.replace("_", " ").replace("-", " ").title()
    path = new_item(root, "feature", f"Imported: {title}")
    text = path.read_text(encoding="utf-8")
    checklist = "\n".join(f"- [{'x' if done else ' '}] {txt}" for done, txt in extracted)
    new_text, n = re.subn(r"(## .*Checklist.*\n)(?:.*\n?)*",
                          lambda m: m.group(1) + checklist + "\n", text, count=1)
    if n == 0:
        raise ValueError("plan template has no Checklist section to populate")
    atomic_write(path, new_text)
    sync(root)
    return [path]


from rmproject import (  # noqa: E402
    _apply_rules_block, ensure_claude_md_rules, ensure_project_rules,
    init_project, upgrade)










def serve(root: Path, port: int | None = None, open_browser: bool = True) -> int:
    """Delegate to the dashboard module (loaded from the sibling dashboard.py).
    Loaded lazily and by file path so it works both when roadmap.py is run as a
    script and when it is imported under a different module name (tests)."""
    import importlib.util
    import types
    path = Path(__file__).resolve().parent / "dashboard.py"
    spec = importlib.util.spec_from_file_location("roadmap_dashboard", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # The dashboard reads all data through this small interface — passed
    # explicitly so it never has to import (or find in sys.modules) this module.
    rm = types.SimpleNamespace(
        status=status, read_config=read_config, roadmap_dir=roadmap_dir,
        parse_plan=parse_plan, changelog_json=changelog_json)
    return mod.serve(rm, root, port=port, open_browser=open_browser)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="roadmap")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--name", default="My Project")
    p_init.add_argument("--adopt", action="store_true")
    p_init.add_argument("--no-claude-md", action="store_false", dest="claude_md")

    p_new = sub.add_parser("new")
    p_new.add_argument("--type", required=True)
    p_new.add_argument("--title", required=True)
    p_new.add_argument("--version")
    p_new.add_argument("--note", default="")
    p_new.add_argument("--audience", choices=["public", "internal"])
    p_new.add_argument("--force", action="store_true",
                       help="save a public note even if it reads like a status dump")

    p_note = sub.add_parser("note")
    p_note.add_argument("--plan", type=int, required=True)
    p_note.add_argument("--text", required=True)
    p_note.add_argument("--force", action="store_true",
                        help="save a public note even if it reads like a status dump")

    p_aud = sub.add_parser("audience")
    p_aud.add_argument("--plan", type=int, required=True)
    p_aud.add_argument("--to", required=True, choices=["public", "internal"])

    p_sum = sub.add_parser("summary",
                           help="set a version's public release-notes blurb "
                                "(renders instead of item bullets in CHANGELOG.md)")
    p_sum.add_argument("--version", required=True)
    p_sum.add_argument("--text")
    p_sum.add_argument("--clear", action="store_true",
                       help="remove the blurb (fall back to item bullets)")
    p_sum.add_argument("--force", action="store_true",
                       help="save even if the text reads like a status dump")

    p_check = sub.add_parser("check")
    p_check.add_argument("--plan", type=int, required=True)
    p_check.add_argument("--step", type=int)
    p_check.add_argument("--undo", action="store_true")
    p_check.add_argument("--all-done", action="store_true", dest="all_done")

    p_rel = sub.add_parser("release")
    p_rel.add_argument("--version", required=True)
    p_rel.add_argument("--tag", action="store_true")
    p_rel.add_argument("--force", action="store_true")

    p_st = sub.add_parser("status")
    p_st.add_argument("--json", action="store_true", dest="as_json")

    p_srv = sub.add_parser("serve",
                           help="local live web dashboard (SSE push, read-only)")
    p_srv.add_argument("--port", type=int, default=None,
                       help="fixed port; default auto-scans from 4700")
    p_srv.add_argument("--no-open", action="store_false", dest="open_browser",
                       help="do not open a browser window")

    p_next = sub.add_parser("next", help="print the next unblocked unfinished item")
    p_next.add_argument("--version", help="target version (default: current)")
    p_next.add_argument("--json", action="store_true", dest="as_json")
    p_next.add_argument("--force", action="store_true",
                        help="ignore dependsOn blockers")

    p_orient = sub.add_parser("orient", help="session orientation (safe no-op without .roadmap/)")
    p_orient.add_argument("--json", action="store_true", dest="as_json")
    p_orient.add_argument("--hook", action="store_true",
                          help="emit Claude SessionStart additionalContext JSON")

    p_handoff = sub.add_parser(
        "handoff",
        help="multi-coder switch brief (orient + drift + git dirty + checklist)")
    p_handoff.add_argument("--json", action="store_true", dest="as_json")

    sub.add_parser("drift-check", help="nudge if commits landed without check-off")

    p_promote = sub.add_parser("promote", help="lift an Idea Incubator bullet into a plan")
    p_promote.add_argument("--match", help="substring match against incubator bullet title")
    p_promote.add_argument("--index", type=int, help="1-based index into incubator bullets")
    p_promote.add_argument("--type", default="feature")
    p_promote.add_argument("--version")
    p_promote.add_argument("--note", default="")
    p_promote.add_argument("--audience", choices=["public", "internal"])
    p_promote.add_argument("--force", action="store_true",
                           help="save a public note even if it reads like a status dump")

    p_deps = sub.add_parser("deps-check",
                            help="warn if a plan's dependsOn targets are incomplete")
    p_deps.add_argument("--plan", type=int, required=True)
    p_deps.add_argument("--force", action="store_true")

    sub.add_parser("sync")
    sub.add_parser("version")
    sub.add_parser("upgrade")

    p_tidy = sub.add_parser(
        "tidy", help="report free-form / Idea Incubator hygiene issues (report-only)")
    p_tidy.add_argument("--json", action="store_true", dest="as_json")
    p_tidy.add_argument("--externalize", nargs="?", const=".roadmap/IDEAS.md",
                        metavar="PATH",
                        help="move the Idea Incubator into PATH (default "
                             ".roadmap/IDEAS.md), leaving a link in ROADMAP.md")

    p_imp = sub.add_parser("import")
    p_imp.add_argument("path")

    p_re = sub.add_parser("reorder")
    p_re.add_argument("--version", required=True)
    p_re.add_argument("--order", required=True)

    p_mg = sub.add_parser("merge")
    p_mg.add_argument("--into", type=int, required=True)
    p_mg.add_argument("--from", dest="sources", required=True)

    p_dep = sub.add_parser("depends")
    p_dep.add_argument("--plan", type=int, required=True)
    p_dep.add_argument("--on", default="")
    p_dep.add_argument("--clear", action="store_true")

    p_rm = sub.add_parser("remove")
    p_rm.add_argument("--plan", type=int, required=True)

    p_idea = sub.add_parser("idea")
    p_idea.add_argument("--title", required=True)
    p_idea.add_argument("--body", help="long-form content -> .roadmap/notes/ file")
    p_idea.add_argument("--body-file", dest="body_file",
                        help="read long-form content from a file")

    p_cl = sub.add_parser("changelog")
    p_cl.add_argument("--backfill", action="store_true")
    p_cl.add_argument("--internal", action="store_true",
                      help="print CHANGELOG.internal.md instead of the public CHANGELOG.md")
    p_cl.add_argument("--json", action="store_true", dest="as_json",
                      help="emit the public changelog as structured JSON "
                           "(for in-app changelog screens / What's New popups)")

    p_rt = sub.add_parser("retarget")
    p_rt.add_argument("--to", required=True)
    p_rt.add_argument("--from", dest="from_versions", default="")
    p_rt.add_argument("--plan", dest="plan_ids", default="")

    args = parser.parse_args(argv)
    root = find_root(Path.cwd())
    try:
        if args.command == "init":
            init_project(root, args.name, adopt=args.adopt, claude_md=args.claude_md)
            print(f"Initialized roadmap at {root}")
            return 0
        if args.command == "new":
            path = new_item(root, args.type, args.title, args.version,
                            note=args.note, audience=args.audience, force=args.force)
            print(path)
            return 0
        if args.command == "note":
            set_note(root, args.plan, args.text, force=args.force)
            return 0
        if args.command == "audience":
            set_audience(root, args.plan, args.to)
            return 0
        if args.command == "summary":
            set_release_summary(root, args.version, text=args.text,
                                clear=args.clear, force=args.force)
            return 0
        if args.command == "check":
            check_step(root, args.plan, args.step, undo=args.undo, all_done=args.all_done)
            return 0
        if args.command == "release":
            release(root, args.version, tag=args.tag, force=args.force)
            return 0
        if args.command == "sync":
            sync(root)
            return 0
        if args.command == "version":
            print(get_version())
            return 0
        if args.command == "upgrade":
            upgrade(root)
            return 0
        if args.command == "tidy":
            if args.externalize:
                dest = externalize_incubator(root, args.externalize)
                print(f"Idea Incubator moved to {dest.relative_to(root)} — ROADMAP.md "
                      "keeps a link; idea/promote/remove now target it.")
                return 0
            rep = tidy_report(root)
            if args.as_json:
                print(json.dumps(rep, indent=2))
            else:
                print(format_tidy(rep))
            return 0
        if args.command == "reorder":
            reorder(root, args.version, [int(x) for x in args.order.split(",") if x.strip()])
            return 0
        if args.command == "merge":
            merge_items(root, args.into,
                        [int(x) for x in args.sources.split(",") if x.strip()])
            return 0
        if args.command == "depends":
            set_depends(root, args.plan,
                        [int(x) for x in args.on.split(",") if x.strip()],
                        clear=args.clear)
            return 0
        if args.command == "remove":
            remove_item(root, args.plan)
            return 0
        if args.command == "idea":
            body = args.body
            if args.body_file:
                body = Path(args.body_file).read_text(encoding="utf-8")
            note = add_idea(root, args.title, body)
            print(f"Parked idea: {args.title}" + (f" (notes: {note})" if note else ""))
            return 0
        if args.command == "promote":
            path = promote_idea(root, match=args.match, index=args.index,
                                type_=args.type, version=args.version,
                                note=args.note, audience=args.audience,
                                force=args.force)
            print(path)
            return 0
        if args.command == "next":
            item = next_item(root, version=args.version, force=args.force)
            if item is None:
                print("No unfinished unblocked items.")
                return 0
            if args.as_json:
                print(json.dumps(item, indent=2))
            else:
                print(f"#{item['id']} {item['title']} [{item['type']}] "
                      f"v{item['version']} — {item['pct']}% "
                      f"(.roadmap/{item['file']})")
            return 0
        if args.command == "orient":
            payload = orient(root)
            if payload is None:
                return 0
            text = format_orient(payload)
            if args.hook:
                # Claude Code SessionStart: inject as additionalContext
                print(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": text,
                    }
                }))
            elif args.as_json:
                print(json.dumps(payload, indent=2))
            else:
                print(text)
            return 0
        if args.command == "handoff":
            payload = handoff(root)
            if payload is None:
                print("No .roadmap/ here — nothing to hand off.")
                return 0
            if args.as_json:
                print(json.dumps(payload, indent=2))
            else:
                print(format_orient(payload, handoff=True))
            return 0
        if args.command == "drift-check":
            msg = drift_check(root)
            if msg:
                print(msg)
            return 0
        if args.command == "deps-check":
            blocked = warn_incomplete_deps(root, args.plan, force=args.force)
            if args.force or not blocked:
                print(f"#{args.plan}: ok" + (" (force)" if args.force and blocked else ""))
            return 0
        if args.command == "retarget":
            retarget(root, args.to,
                     from_versions=[v for v in args.from_versions.split(",") if v.strip()] or None,
                     plan_ids=[int(x) for x in args.plan_ids.split(",") if x.strip()] or None)
            return 0
        if args.command == "changelog":
            if args.backfill:
                backfill_changelog(root)
            else:
                sync(root, quiet=True)
            for m in audit_public_notes(root):
                print(f"warning: {m}", file=sys.stderr)
            if args.as_json:
                print(json.dumps(changelog_json(root), indent=2))
                return 0
            cl = root / ("CHANGELOG.internal.md" if args.internal else "CHANGELOG.md")
            if cl.exists():
                print(cl.read_text(encoding="utf-8"), end="")
            return 0
        if args.command == "import":
            created = import_file(root, Path(args.path))
            for p in created:
                print(p)
            return 0
        if args.command == "status":
            st = status(root)
            if args.as_json:
                print(json.dumps(st, indent=2))
            else:
                print(f"{st['project']} — v{st['currentVersion']}")
                for it in st["items"]:
                    block = (f" blocked by {it['blockedBy']}"
                             if it.get("blockedBy") else "")
                    print(f"  #{it['id']} {it['title']} [{it['type']}] "
                          f"{it['pct']}% ({it['status']}){block}")
            for w in roadmap_health(root):
                print(f"warning: {w}", file=sys.stderr)
            return 0
        if args.command == "serve":
            return serve(root, port=args.port, open_browser=args.open_browser)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
