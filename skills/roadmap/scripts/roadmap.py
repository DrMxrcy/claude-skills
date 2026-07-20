#!/usr/bin/env python3
"""roadmap — deterministic CLI for the roadmap skill (Python 3 stdlib only)."""
from __future__ import annotations
import argparse, json, sys
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


from rmops import (  # noqa: E402
    TEMPLATE_BY_TYPE, _incomplete_items, _refuse_status_note,
    backfill_changelog, check_step, import_file, merge_items, new_item,
    promote_idea, release, remove_item, reorder, retarget, set_audience,
    set_depends, set_note, set_release_summary)
















from rmincubator import (  # noqa: E402
    DUPLICATE_RATIO, INCUBATOR_BULLET_RE, INCUBATOR_HEADING, INCUBATOR_RE,
    MAX_BULLET_CHARS, MD_LINK_RE, _freeform_lines, _incubator_append,
    _incubator_stub, _norm_title, _strip_incubator_placeholder, add_idea,
    externalize_incubator, format_tidy, incubator_file,
    list_incubator_bullets, tidy_report)






















# type → user-facing changelog section (App Store / website friendly)
from rmchangelog import (  # noqa: E402
    TYPE_SECTION, SECTION_ORDER, DEFAULT_AUDIENCE, ROLLUP_LINE,
    WARN_VENDORS, WARN_JARGON, WARN_TELLS, DEMOTE_ADMIN, DEMOTE_COMPLIANCE,
    DEMOTE_SECURITY, DEMOTE_PLUMBING, DEMOTE_TELLS, _PATH_RE, _SEG_RE,
    _REF_RE, _STATUS_RES, _word_hits, _dedupe, status_tells, lint_note,
    demote_tells, item_audience, _changelog_versions, _grouped_lines,
    render_public_changelog, changelog_json, render_internal_changelog,
    audit_public_notes)




































from rmreport import (  # noqa: E402
    _git_dirty, _git_head, _record_last_seen_sha, drift_check,
    format_orient, handoff, orient)






















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
