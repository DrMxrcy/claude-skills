#!/usr/bin/env python3
"""roadmap — deterministic CLI for the roadmap skill (Python 3 stdlib only)."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

# Submodules live beside this file; ensure this dir is importable whether we are
# run as a script or imported under another name (tests load us via importlib).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rmlib.core import (  # noqa: E402  (re-exported so callers/tests keep roadmap.X)
    TEMPLATES_DIR, AUTO_START, AUTO_END, RULES_START, RULES_END, RULES_BLOCK,
    RULES_FILES, get_version, roadmap_dir, find_root, atomic_write, read_config,
    write_config, slugify, _render_template, _version_from_pyproject,
    detect_version, derive_status, display_id, TYPE_PREFIX, resolve_id,
    resolve_ids, ID_HELP, IDS_HELP, _set_frontmatter,
    _norm_version, _version_key)


from rmlib.sync import (  # noqa: E402
    _incomplete_deps, _item_done, _next_current_version, _progress_map,
    _version_complete, incomplete_deps, next_item, render_region,
    roadmap_health, status, sync, uncut_complete_version,
    derive_lane, is_in_flight, lane_counts, lane_label,
    warn_incomplete_deps, MAX_ROADMAP_LINES,
    MAX_FREEFORM_LINES, MAX_FREEFORM_CHARS)


from rmlib.parse import (  # noqa: E402
    STEP_RE, _is_fence, parse_plan, count_progress, _plan_path,
    CLAIM_STAGES, CLAIM_VERDICTS, CLAIM_FIELDS, read_claim)


from rmlib.ops import (  # noqa: E402
    TEMPLATE_BY_TYPE, _incomplete_items, _refuse_status_note,
    backfill_changelog, check_step, clear_claim, import_file, merge_items, new_item,
    promote_idea, release, release_gate, remove_item, reorder, retarget,
    set_audience, set_claim, set_depends, set_note, set_release_summary)


from rmlib.incubator import (  # noqa: E402
    DUPLICATE_RATIO, INCUBATOR_BULLET_RE, INCUBATOR_HEADING, INCUBATOR_RE,
    MAX_BULLET_CHARS, MD_LINK_RE, _freeform_lines, _incubator_append,
    _incubator_stub, _norm_title, _strip_incubator_placeholder, add_idea,
    externalize_incubator, format_tidy, incubator_file,
    list_incubator_bullets, tidy_report)


# type → user-facing changelog section (App Store / website friendly)
from rmlib.changelog import (  # noqa: E402
    TYPE_SECTION, SECTION_ORDER, DEFAULT_AUDIENCE, ROLLUP_LINE,
    WARN_VENDORS, WARN_JARGON, WARN_TELLS, DEMOTE_ADMIN, DEMOTE_COMPLIANCE,
    DEMOTE_SECURITY, DEMOTE_PLUMBING, DEMOTE_TELLS, _PATH_RE, _SEG_RE,
    _REF_RE, _STATUS_RES, _word_hits, _dedupe, status_tells, lint_note,
    demote_tells, item_audience, _changelog_versions, _grouped_lines,
    render_public_changelog, changelog_json, render_internal_changelog,
    audit_public_notes)


from rmlib.report import (  # noqa: E402
    _git_dirty, _git_head, _record_last_seen_sha, drift_check,
    format_orient, format_search, handoff, orient, search)

from rmlib.handoff_note import (  # noqa: E402
    open_decision, resolve_pending, write_pending)


from rmlib.project import (  # noqa: E402
    _apply_rules_block, ensure_claude_md_rules, ensure_project_rules,
    init_project, upgrade)


__all__ = [  # public facade: names re-exported for callers/tests/hooks (roadmap.X)
    'TEMPLATES_DIR', 'AUTO_START', 'AUTO_END', 'RULES_START', 'RULES_END',
    'RULES_BLOCK', 'RULES_FILES', 'get_version', 'roadmap_dir',
    'find_root', 'atomic_write', 'read_config', 'write_config', 'slugify',
    '_render_template', '_version_from_pyproject', 'detect_version',
    'derive_status', 'display_id', 'TYPE_PREFIX', 'resolve_id', 'resolve_ids',
    'ID_HELP', 'IDS_HELP', '_set_frontmatter',
    '_norm_version', '_version_key',
    '_incomplete_deps', '_item_done', '_next_current_version',
    '_progress_map', '_version_complete', 'incomplete_deps', 'next_item',
    'render_region', 'roadmap_health', 'status', 'sync',
    'derive_lane', 'is_in_flight', 'lane_counts', 'lane_label',
    'uncut_complete_version', 'warn_incomplete_deps', 'MAX_ROADMAP_LINES', 'MAX_FREEFORM_LINES',
    'MAX_FREEFORM_CHARS', 'STEP_RE', '_is_fence', 'parse_plan',
    'count_progress', '_plan_path', 'CLAIM_STAGES', 'CLAIM_VERDICTS',
    'CLAIM_FIELDS', 'read_claim', 'set_claim', 'clear_claim', 'TEMPLATE_BY_TYPE',
    '_incomplete_items', '_refuse_status_note', 'backfill_changelog',
    'check_step', 'import_file', 'merge_items', 'new_item', 'promote_idea',
    'release', 'release_gate', 'remove_item', 'reorder', 'retarget', 'set_audience',
    'set_depends', 'set_note', 'set_release_summary', 'DUPLICATE_RATIO',
    'INCUBATOR_BULLET_RE', 'INCUBATOR_HEADING', 'INCUBATOR_RE',
    'MAX_BULLET_CHARS', 'MD_LINK_RE', '_freeform_lines',
    '_incubator_append', '_incubator_stub', '_norm_title',
    '_strip_incubator_placeholder', 'add_idea', 'externalize_incubator',
    'format_tidy', 'incubator_file', 'list_incubator_bullets',
    'tidy_report', 'TYPE_SECTION', 'SECTION_ORDER', 'DEFAULT_AUDIENCE',
    'ROLLUP_LINE', 'WARN_VENDORS', 'WARN_JARGON', 'WARN_TELLS',
    'DEMOTE_ADMIN', 'DEMOTE_COMPLIANCE', 'DEMOTE_SECURITY',
    'DEMOTE_PLUMBING', 'DEMOTE_TELLS', '_PATH_RE', '_SEG_RE', '_REF_RE',
    '_STATUS_RES', '_word_hits', '_dedupe', 'status_tells', 'lint_note',
    'demote_tells', 'item_audience', '_changelog_versions',
    '_grouped_lines', 'render_public_changelog', 'changelog_json',
    'render_internal_changelog', 'audit_public_notes', '_git_dirty',
    '_git_head', '_record_last_seen_sha', 'drift_check', 'format_orient',
    'format_search', 'search',
    'handoff', 'orient', '_apply_rules_block', 'ensure_claude_md_rules',
    'ensure_project_rules', 'init_project', 'upgrade', 'serve', 'main'
]


def _dashboard_api():
    """The small read-only interface the dashboard reads all data through —
    passed explicitly so it never has to import (or find in sys.modules) this
    module."""
    import types
    from rmlib import branches as rmbranches
    return types.SimpleNamespace(
        status=status, read_config=read_config, roadmap_dir=roadmap_dir,
        parse_plan=parse_plan, changelog_json=changelog_json,
        incubator_file=incubator_file,
        list_incubator_bullets=list_incubator_bullets,
        discover_branches=rmbranches.discover)


def serve(root: Path, port: int | None = None, open_browser: bool = True,
          verbose: bool = False) -> int:
    """Delegate to the dashboard module (loaded from the sibling dashboard.py).
    Loaded lazily and by file path so it works both when roadmap.py is run as a
    script and when it is imported under a different module name (tests)."""
    import importlib.util
    path = Path(__file__).resolve().parent / "rmlib" / "dashboard.py"
    spec = importlib.util.spec_from_file_location("roadmap_dashboard", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.serve(_dashboard_api(), root, port=port, open_browser=open_browser,
                     verbose=verbose)


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
    p_note.add_argument("--plan", required=True, help=ID_HELP)
    p_note.add_argument("--text", required=True)
    p_note.add_argument("--force", action="store_true",
                        help="save a public note even if it reads like a status dump")

    p_aud = sub.add_parser("audience")
    p_aud.add_argument("--plan", required=True, help=ID_HELP)
    p_aud.add_argument("--to", required=True, choices=["public", "internal"])
    p_aud.add_argument("--force", action="store_true",
                       help="set public even if the item trips wrong-audience tells")

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
    p_check.add_argument("--plan", required=True, help=ID_HELP)
    p_check.add_argument("--step", type=int)
    p_check.add_argument("--undo", action="store_true")
    p_check.add_argument("--all-done", action="store_true", dest="all_done")
    p_check.add_argument("--tokens", type=int,
                         help="optional token spend for this check, recorded beside the "
                              "evidence line (needs --evidence)")
    p_check.add_argument("--evidence",
                         help="how the step was proven done (verify command + result); "
                              "recorded date-stamped under the step in the plan file. "
                              "With --all-done the same text is recorded under every "
                              "step; ignored with --undo. Required when "
                              "settings.requireEvidence is true.")

    def claim_stage(value: str) -> str:
        v = value.strip().lower()
        if v == "building":
            raise argparse.ArgumentTypeError(
                "'building' is a derived lane, not a claim stage — an item with a "
                "branch or (plan N) commits and no claim already shows as building; "
                "use --clear to drop a claim and return to it")
        if v not in CLAIM_STAGES:
            raise argparse.ArgumentTypeError(
                f"invalid choice: {value!r} (choose from {', '.join(CLAIM_STAGES)})")
        return v

    p_claim = sub.add_parser(
        "claim", help="record an item's in-flight stage/verdict (what git cannot know) "
                      "in its plan frontmatter; --clear removes it")
    p_claim.add_argument("id", help=ID_HELP)
    p_claim.add_argument("--stage", type=claim_stage, metavar="{" + ",".join(CLAIM_STAGES) + "}",
                         help="build-loop stage (required for a new claim)")
    p_claim.add_argument("--verdict", type=str.upper, choices=CLAIM_VERDICTS,
                         help="latest review verdict")
    p_claim.add_argument("--note", help="short free-text note ('' removes it)")
    p_claim.add_argument("--branch",
                         help="branch override (default: the discovered branch)")
    p_claim.add_argument("--clear", action="store_true",
                         help="remove the claim (lane reverts to the derived one)")

    p_rel = sub.add_parser("release")
    p_rel.add_argument("--version", required=True)
    p_rel.add_argument("--tag", action="store_true")
    p_rel.add_argument("--force", action="store_true")

    p_st = sub.add_parser("status")
    p_st.add_argument("--json", action="store_true", dest="as_json")
    p_st.add_argument("--type", choices=sorted(TYPE_PREFIX),
                      help="only items of this type")
    p_st.add_argument("--version", help="only items targeting this version")
    p_st.add_argument("--status", choices=["planned", "active", "done"],
                      help="only items with this progress status")
    p_st.add_argument("--open", action="store_true", dest="open_only",
                      help="hide done items (and with them every shipped version)")
    p_st.add_argument("--in-flight", action="store_true", dest="in_flight",
                      help="only unfinished items with a branch or a claim")

    p_search = sub.add_parser(
        "search", help="case-insensitive substring search across item titles/notes, "
                       "plan bodies and Idea Incubator bullets")
    p_search.add_argument("text", help="substring to look for (no regex/fuzzy)")
    p_search.add_argument("--json", action="store_true", dest="as_json")

    p_srv = sub.add_parser("serve",
                           help="local live web dashboard (SSE push, read-only)")
    p_srv.add_argument("--port", type=int, default=None,
                       help="fixed port; default auto-scans from 4700")
    p_srv.add_argument("--no-open", action="store_false", dest="open_browser",
                       help="do not open a browser window")
    p_srv.add_argument("--verbose", action="store_true",
                       help="print one line per checkout on every refresh "
                            "(default: one summary line with the URL)")

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
    p_handoff.add_argument("--plan", help=ID_HELP + " (required with --pending/--resolve)")
    p_handoff.add_argument("--pending", metavar="TEXT",
                           help="record an OPEN decision in .roadmap/notes/<id>-handoff.md")
    p_handoff.add_argument("--resolve", action="store_true",
                           help="close the open decision for --plan")

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
    p_deps.add_argument("--plan", required=True, help=ID_HELP)
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
    p_re.add_argument("--order", required=True, help=IDS_HELP)

    p_mg = sub.add_parser("merge")
    p_mg.add_argument("--into", required=True, help=ID_HELP)
    p_mg.add_argument("--from", dest="sources", required=True, help=IDS_HELP)

    p_dep = sub.add_parser("depends")
    p_dep.add_argument("--plan", required=True, help=ID_HELP)
    p_dep.add_argument("--on", default="", help=IDS_HELP)
    p_dep.add_argument("--clear", action="store_true")

    p_rm = sub.add_parser("remove")
    p_rm.add_argument("--plan", required=True, help=ID_HELP)

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
    p_rt.add_argument("--plan", dest="plan_ids", default="", help=IDS_HELP)

    args = parser.parse_args(argv)
    root = find_root(Path.cwd())

    def rid(token: str) -> int:      # one shared resolver for every id-taking arg
        return resolve_id(read_config(root), token)

    def rids(tokens: str) -> list[int]:
        return resolve_ids(read_config(root), tokens)

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
            set_note(root, rid(args.plan), args.text, force=args.force)
            return 0
        if args.command == "audience":
            set_audience(root, rid(args.plan), args.to, force=args.force)
            return 0
        if args.command == "summary":
            set_release_summary(root, args.version, text=args.text,
                                clear=args.clear, force=args.force)
            return 0
        if args.command == "check":
            check_step(root, rid(args.plan), args.step, undo=args.undo,
                       all_done=args.all_done, evidence=args.evidence,
                       tokens=args.tokens)
            return 0
        if args.command == "claim":
            plan_id = rid(args.id)
            if args.clear:
                if any(v is not None for v in
                       (args.stage, args.verdict, args.note, args.branch)):
                    p_claim.error("--clear takes no other options")
                cleared = clear_claim(root, plan_id)
                print(f"#{plan_id}: claim cleared" if cleared
                      else f"#{plan_id}: no claim to clear")
                return 0
            c = set_claim(root, plan_id, stage=args.stage, verdict=args.verdict,
                          note=args.note, branch=args.branch)
            print(f"#{plan_id}: " + " · ".join(f"{f}={c[f]}" for f in CLAIM_FIELDS
                                                if c.get(f)))
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
            reorder(root, args.version, rids(args.order))
            return 0
        if args.command == "merge":
            merge_items(root, rid(args.into), rids(args.sources))
            return 0
        if args.command == "depends":
            set_depends(root, rid(args.plan), rids(args.on), clear=args.clear)
            return 0
        if args.command == "remove":
            remove_item(root, rid(args.plan))
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
                if not args.version:
                    release_gate(root)
                return 0
            if args.as_json:
                print(json.dumps(item, indent=2))
            else:
                print(f"{item['displayId']} {item['title']} [{item['type']}] "
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
            if args.pending is not None or args.resolve:
                if not args.plan:
                    print("handoff --pending/--resolve need --plan <id>", file=sys.stderr)
                    return 2
                plan_id = rid(args.plan)
                if args.pending is not None:
                    path = write_pending(root, plan_id, args.pending)
                    print(f"open decision recorded: {path.relative_to(root)}")
                    return 0
                if not resolve_pending(root, plan_id):
                    print(f"no open decision for plan {args.plan}", file=sys.stderr)
                    return 1
                print(f"decision resolved for plan {args.plan}")
                return 0
            payload = handoff(root)
            if payload is None:
                print("No .roadmap/ here — nothing to hand off.")
                return 0
            open_items = [i for i in (payload.get("next") and [payload["next"]] or [])
                          if open_decision(root, i["id"])]
            if open_items:
                i = open_items[0]
                print(f"refusing handoff: decision still open for {display_id(i)} — "
                      f"{open_decision(root, i['id'])}\n"
                      f"resolve it first: roadmap.py handoff --plan {i['id']} --resolve",
                      file=sys.stderr)
                return 1
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
            plan_id = rid(args.plan)
            blocked = warn_incomplete_deps(root, plan_id, force=args.force)
            if args.force or not blocked:
                print(f"#{plan_id}: ok" + (" (force)" if args.force and blocked else ""))
            return 0
        if args.command == "retarget":
            retarget(root, args.to,
                     from_versions=[v for v in args.from_versions.split(",") if v.strip()] or None,
                     plan_ids=rids(args.plan_ids) or None)
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
            # Filters only narrow the item list (AND); the header stays global.
            ver = _norm_version(args.version) if args.version else None
            st["items"] = [i for i in st["items"]
                           if (args.type is None or i["type"] == args.type)
                           and (ver is None or i["version"] == ver)
                           and (args.status is None or i["status"] == args.status)
                           and (not args.open_only or i["lane"] != "done")
                           and (not args.in_flight or is_in_flight(i))]
            if args.as_json:
                print(json.dumps(st, indent=2))
            else:
                lc = st["counts"]["lanes"]
                active = f" · {lc['active']} active" if lc["active"] else ""
                print(f"{st['project']} — v{st['currentVersion']} · {lc['done']} done"
                      f" · {lc['inFlight']} in-flight{active} · {lc['planned']} planned")
                for it in st["items"]:
                    block = (f" blocked by {it['blockedBy']}"
                             if it.get("blockedBy") else "")
                    lane = f" — {lane_label(it)}" if is_in_flight(it) else ""
                    print(f"  {it['displayId']} {it['title']} [{it['type']}] "
                          f"{it['pct']}% ({it['status']}){lane}{block}")
            for w in roadmap_health(root):
                print(f"warning: {w}", file=sys.stderr)
            return 0
        if args.command == "search":
            if not args.text.strip():
                parser.error("search text must not be empty")
            hits = search(root, args.text.strip())
            if args.as_json:
                print(json.dumps(hits, indent=2))
            else:
                print(format_search(hits, args.text.strip()))
            return 0
        if args.command == "serve":
            return serve(root, port=args.port, open_browser=args.open_browser,
                         verbose=args.verbose)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
