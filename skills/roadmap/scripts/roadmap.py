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
    countdown, due_waiting, format_due,
    format_worktrees, worktree_payload, conflicts_payload,
    warn_incomplete_deps, MAX_ROADMAP_LINES,
    MAX_FREEFORM_LINES, MAX_FREEFORM_CHARS)


from rmlib.parse import (  # noqa: E402
    STEP_RE, _is_fence, parse_plan, count_progress, _plan_path,
    CLAIM_STAGES, CLAIM_VERDICTS, CLAIM_FIELDS, read_claim, needs_approval,
    parse_rulings, waiting_steps)


from rmlib.ops import (  # noqa: E402
    TEMPLATE_BY_TYPE, _incomplete_items, _refuse_status_note, add_ruling,
    backfill_changelog, check_landed, check_step, claim_landed, clear_claim,
    clear_claims,
    import_file, merge_items, new_item,
    promote_idea, release, release_gate, remove_item, reorder, retarget,
    set_audience, set_claim, set_claims, set_depends, set_note, set_release_summary,
    create_follow_up, parse_until, wait_step)
from rmlib.ops import accept, list_acceptance  # noqa: E402  (plan 43)


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

from rmlib import slots as rmslots  # noqa: E402  (plan 33: numbered slots)
from rmlib.ops import file_bug  # noqa: E402  (plan 47: bug routing)
from rmlib.incubator import bug_tells  # noqa: E402  (plan 47)
from rmlib import forecast as rmforecast  # noqa: E402  (plan 44: version forecast)
from rmlib import conflicts as rmconflicts  # noqa: E402  (plan 41: conflict risk)
from rmlib import runs as rmruns  # noqa: E402  (plan 38: run log)
from rmlib import owners as rmowners  # noqa: E402  (plan 40: claim owners, WIP limit)
from rmlib import digest as rmdigest  # noqa: E402  (plan 45: digest since a time)


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
    'countdown', 'due_waiting', 'format_due',
    'format_worktrees', 'worktree_payload', 'conflicts_payload', 'uncut_complete_version', 'warn_incomplete_deps', 'MAX_ROADMAP_LINES', 'MAX_FREEFORM_LINES',
    'MAX_FREEFORM_CHARS', 'STEP_RE', '_is_fence', 'parse_plan',
    'count_progress', '_plan_path', 'CLAIM_STAGES', 'CLAIM_VERDICTS',
    'CLAIM_FIELDS', 'read_claim', 'needs_approval', 'parse_rulings',
    'waiting_steps', 'create_follow_up', 'parse_until', 'wait_step', 'set_claim', 'clear_claim', 'set_claims',
    'clear_claims', 'claim_landed', 'check_landed', 'add_ruling', 'TEMPLATE_BY_TYPE',
    '_incomplete_items', '_refuse_status_note', 'backfill_changelog',
    'check_step', 'import_file', 'merge_items', 'new_item', 'promote_idea',
    'release', 'release_gate', 'remove_item', 'reorder', 'retarget', 'set_audience',
    'set_depends', 'set_note', 'set_release_summary', 'accept', 'list_acceptance',
    'DUPLICATE_RATIO',
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
    'ensure_project_rules', 'init_project', 'upgrade', 'serve', 'main',
    'file_bug', 'bug_tells',   # plan 47
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
        discover_branches=rmbranches.discover,
        worktree_facts=rmbranches.worktree_facts,
        worktree_payload=worktree_payload,
        conflicts_payload=conflicts_payload,
        digest=rmdigest.digest, digest_sections=rmdigest.sections,   # plan 45
        default_owner=rmowners.default_owner,
        # plan 49: full-text search + version-page changelog preview
        search=search, render_public_changelog=render_public_changelog,
        render_internal_changelog=render_internal_changelog)


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


def _print_check_landed(res: dict, applied: bool) -> int:
    """Render check_landed() for the terminal. Exit 1 when an item was refused."""
    trunk = res["trunk"]
    if not res["ready"] and not res["waiting"]:
        print("no items in the landed lane")
        return 0
    print(f"check --landed — trunk {trunk}" + ("" if applied else " (dry run)"))
    def line(tag, e, tail):
        n = e["steps"]
        print(f"  {tag:<10} {e['displayId']} {e['title']} — "
              f"{n} step{'s' if n != 1 else ''} · {tail}")
    if applied:
        for e in res["ticked"]:
            line("ticked", e, e["reason"])
        for e in res["refused"]:
            line("refused", e, e["reason"])
    else:
        for e in res["ready"]:
            line("would tick", e, f"landed @{e['sha'][:7]}, in {trunk}")
    for e in res["waiting"]:
        line("waiting", e, e["reason"])
    if not applied and res["ready"]:
        n = len(res["ready"])
        print(f"{n} item{'s' if n != 1 else ''} ready — re-run with --yes to tick "
              f"{'them' if n != 1 else 'it'} and clear the claim{'s' if n != 1 else ''}")
    return 1 if res["refused"] else 0


def _slot_cmd(root: Path, args, p_slot, rid) -> int:
    """`slot ID --kind K [--name N] [--add]`, `slot ID --kind K --release`,
    `slot [ID] --check` (plan 33)."""
    if args.check:
        if args.release or args.add or args.name:
            p_slot.error("--check takes only an optional ID (and --json)")
        plan_id = rid(args.id) if args.id else None
        payload = status(root).get("slots")
        bad = rmslots.check_failures(payload, plan_id)
        if args.as_json:
            print(json.dumps({"slots": payload, "failures": bad}, indent=2))
        else:
            print(rmslots.format_slots(payload, plan_id))
            if bad:
                print(f"slot check: {len(bad)} clash(es) — "
                      + "; ".join(f"#{b['plan']} {b['kind']} {b['state']}: {b['detail']}"
                                  for b in bad))
            elif payload and not payload.get("error"):
                print("slot check: no clashes")
        return 1 if bad or (payload or {}).get("error") else 0
    if not args.id or not args.kind:
        p_slot.error("reserve/release need an ID and --kind (or use --check)")
    plan_id = rid(args.id)
    if args.release:
        if args.add or args.name:
            p_slot.error("--release takes no --name/--add")
        freed = rmslots.release(root, plan_id, args.kind)
        print(f"#{plan_id}: released {args.kind} {freed}" if freed
              else f"#{plan_id}: no {args.kind} reservation to release")
        return 0
    res = rmslots.reserve(root, plan_id, args.kind, name=args.name, add=args.add)
    if args.as_json:
        print(json.dumps({"plan": plan_id, **res}))
    else:
        print(res["token"] if res["new"] else res["value"])
        if not res["new"]:
            print(f"#{plan_id} already holds {args.kind} {res['value']} "
                  f"(--add reserves another)", file=sys.stderr)
    return 0


def _run_cmd(root: Path, args, rids) -> int:
    """`run --kind gate|suite --label L --result pass|fail [...]` (plan 38)."""
    rec = rmruns.make_record(
        args.kind, args.label, args.result,
        items=rids(args.items or ""),
        branches=rmruns.split_list(args.branches),
        duration=rmruns.parse_duration(args.duration), log=args.log,
        failing=rmruns.split_list(args.failing),
        shards=rmruns.parse_shards(args.shards))
    rmruns.append_run(root, rec, keep=rmruns.runs_keep(read_config(root)))
    if args.as_json:
        print(json.dumps(rec))
    else:
        print("recorded:" + rmruns.format_run(rec)[1:])
    return 0


def _accept_cmd(root: Path, args, p_accept, rid) -> int:
    """`accept ID [--line N --evidence E [--fail]] [--json]` (plan 43)."""
    plan_id = rid(args.id)
    if args.line is None:
        if args.evidence or args.fail:
            p_accept.error("--evidence/--fail need --line N")
        bullets = list_acceptance(root, plan_id)
        if args.as_json:
            print(json.dumps(bullets))
            return 0
        if not bullets:
            print(f"#{plan_id}: no ✅ Acceptance bullets")
        for b in bullets:
            state = "guard" if b["kind"] == "guard" else (b["state"] or "open")
            label = f"{b['label']}: " if b["label"] else ""
            print(f"{b['n']:>2}. [{state}] {label}{b['text']}")
            if b["state"]:
                print(f"      {b['date'] or ''} {b['evidence'] or ''}".rstrip())
        return 0
    b = accept(root, plan_id, args.line, args.evidence, fail=args.fail)
    if args.as_json:
        print(json.dumps(b))
    else:
        print(f"#{plan_id} acceptance {b['n']}: {b['state']} — {b['evidence']}")
    return 0


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
    p_check.add_argument("--plan", help=ID_HELP + " (required unless --landed)")
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
    p_check.add_argument("--force", action="store_true",
                         help="check even though the plan's required sections are "
                              "still template text, or (settings.requireAcceptance) "
                              "acceptance bullets are not marked met — recorded in "
                              "the evidence line")
    p_check.add_argument("--landed", action="store_true",
                         help="tick every step of each item in the landed lane whose "
                              "landing sha (and branch tip) trunk now contains, record "
                              "evidence naming the sha, and clear its claim; dry run "
                              "unless --yes")
    p_check.add_argument("--yes", action="store_true",
                         help="with --landed: apply instead of listing")

    p_wait = sub.add_parser(
        "wait", help="mark a step as waiting on time (soak, propagation, review): "
                     "not done, but the item reads `waiting` once its other steps "
                     "are ticked; `check --step N` ticks it once verified")
    p_wait.add_argument("plan", help=ID_HELP)
    p_wait.add_argument("--step", type=int, required=True)
    p_wait.add_argument("--until", help="due date: 2026-10-30, or relative 7d / 2w")
    p_wait.add_argument("--reason", help="what is being waited on (e.g. soak)")
    p_wait.add_argument("--clear", action="store_true",
                        help="end the wait: the step goes back to unticked")

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
        "claim", help="record in-flight stage/verdict (what git cannot know) in the "
                      "plan frontmatter of one or more items; --clear removes it")
    p_claim.add_argument("ids", nargs="*", metavar="id",
                         help=ID_HELP + "; several ids (or 7,8,9) get the same options, "
                              "all-or-nothing")
    p_claim.add_argument("--stage", type=claim_stage, metavar="{" + ",".join(CLAIM_STAGES) + "}",
                         help="build-loop stage (required for a new claim)")
    p_claim.add_argument("--verdict", type=str.upper, choices=CLAIM_VERDICTS,
                         help="latest review verdict")
    p_claim.add_argument("--note", help="short free-text note ('' removes it)")
    p_claim.add_argument("--branch",
                         help="branch override (default: the discovered branch)")
    p_claim.add_argument("--clear", action="store_true",
                         help="remove the claim (lane reverts to the derived one)")
    p_claim.add_argument("--owner",
                         help="who holds the item (default: $ROADMAP_OWNER, else the "
                              "git user name, else the agent name); --owner alone "
                              "opens an owner-only claim")
    p_claim.add_argument("--take", action="store_true",
                         help="take over (or clear) an item held by another owner")
    p_claim.add_argument("--landed", metavar="SHA",
                         help="move items whose branch tip SHA (a commit or branch, "
                              "e.g. the integration branch) contains to stage "
                              "'landed', recording the sha; no ids = every tagged "
                              "in-flight item it contains, ids = exactly those")

    p_ruling = sub.add_parser(
        "ruling", help="append a dated decision to a plan's '## ⚖️ Rulings' section "
                       "(plan file only — never the changelog or ROADMAP.md)")
    p_ruling.add_argument("id", help=ID_HELP)
    p_ruling.add_argument("--text", required=True, help="the decision, one line")
    p_ruling.add_argument("--by", default="owner",
                          help="who ruled (default: owner)")
    p_ruling.add_argument("--approval", action="store_true",
                          help="mark it as a sign-off (satisfies 'approval: required')")

    p_accept = sub.add_parser(
        "accept", help="mark a ✅ Acceptance bullet met (or --fail) with evidence; "
                       "with no --line, list the bullets and their state")
    p_accept.add_argument("id", help=ID_HELP)
    p_accept.add_argument("--line", type=int, metavar="N",
                          help="the bullet number (as `accept ID` lists them)")
    p_accept.add_argument("--evidence",
                          help="how it was verified (command + result); required "
                               "with --line")
    p_accept.add_argument("--fail", action="store_true",
                          help="record a failure instead of a pass")
    p_accept.add_argument("--json", action="store_true", dest="as_json")

    p_slot = sub.add_parser(
        "slot", help="reserve the next number of a numbered sequence (settings.slots, "
                     "e.g. migrations) for an item, release it, or --check for clashes")
    p_slot.add_argument("id", nargs="?", help=ID_HELP + " (optional with --check)")
    p_slot.add_argument("--kind", help="slot kind configured in settings.slots")
    p_slot.add_argument("--name", help="suffix recorded with the number (0269_<name>)")
    p_slot.add_argument("--add", action="store_true",
                        help="reserve one more number for an item that already holds one")
    p_slot.add_argument("--release", action="store_true",
                        help="free the item's reservation of --kind")
    p_slot.add_argument("--check", action="store_true",
                        help="exit 1 when any reservation (or the item's) clashes or is taken")
    p_slot.add_argument("--json", action="store_true", dest="as_json")

    p_run = sub.add_parser(
        "run", help="record a merge-gate or suite run in .roadmap/runs.jsonl "
                    "(shown by status --runs and the dashboard)")
    p_run.add_argument("--kind", required=True, choices=list(rmruns.KINDS))
    p_run.add_argument("--label", required=True, help="what ran, e.g. 'merge 38+39'")
    p_run.add_argument("--result", required=True, choices=list(rmruns.RESULTS))
    p_run.add_argument("--items", help=IDS_HELP + " — items the run gated")
    p_run.add_argument("--branches", help="comma-separated branches the run covered")
    p_run.add_argument("--duration", help="how long it took: 90s, 12m, 1h30m")
    p_run.add_argument("--log", help="http(s) URL of the run's log")
    p_run.add_argument("--failing", help="failing test names, comma- or newline-separated")
    p_run.add_argument("--shards", help="per-shard results: unit=pass,e2e=fail")
    p_run.add_argument("--json", action="store_true", dest="as_json")

    p_rel = sub.add_parser("release")
    p_rel.add_argument("--version", required=True)
    p_rel.add_argument("--tag", action="store_true")
    p_rel.add_argument("--force", action="store_true")
    p_rel.add_argument("--with-waiting", action="store_true", dest="with_waiting",
                       help="ship items whose only open steps are waiting steps; each "
                            "waiting step moves into a linked follow-up item in --version")

    p_st = sub.add_parser("status")
    p_st.add_argument("--json", action="store_true", dest="as_json")
    p_st.add_argument("--type", choices=sorted(TYPE_PREFIX),
                      help="only items of this type")
    p_st.add_argument("--version", help="only items targeting this version")
    p_st.add_argument("--status", choices=["planned", "active", "done"],
                      help="only items with this progress status")
    p_st.add_argument("--open", action="store_true", dest="open_only",
                      help="hide done items (and with them every shipped version)")
    p_st.add_argument("--slots", action="store_true",
                      help="numbered slot reservations per kind: trunk highest, "
                           "each reservation's plan, lane and match state")
    p_st.add_argument("--runs", action="store_true",
                      help="recorded gate/suite runs, newest first, and trunk health")
    p_st.add_argument("--in-flight", action="store_true", dest="in_flight",
                      help="only unfinished items with a branch or a claim")
    p_st.add_argument("--worktrees", action="store_true",
                      help="linked worktrees: branch, item and lane, dirty and "
                           "unmerged counts, claim stage, age, and which are safe "
                           "to remove (the command is printed, never run)")
    p_st.add_argument("--conflicts", action="store_true",
                      help="open item branches that change the same files, by "
                           "risk (merge-tree check on git >= 2.38), and a "
                           "suggested merge order; never touches a branch")

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

    p_digest = sub.add_parser(
        "digest", help="what completed, moved, stalled and got blocked since a time, "
                       "and what needs attention now (read-only)")
    p_digest.add_argument("--since", default="last",
                          help="3h | 1d | 2w | a date (2026-10-20) | an ISO time | "
                               "last (default: since your previous digest run; "
                               "1d the first time)")
    p_digest.add_argument("--format", choices=["text", "md"], default="text",
                          help="md: Markdown for pasting into chat")
    p_digest.add_argument("--json", action="store_true", dest="as_json")
    p_digest.add_argument("--conflicts", action="store_true",
                          help="also flag high-risk branch conflicts (one git diff "
                               "per open branch on a cold cache)")

    p_promote = sub.add_parser("promote", help="lift an Idea Incubator bullet into a plan")
    p_promote.add_argument("--match", help="substring match against incubator bullet title")
    p_promote.add_argument("--index", type=int, help="1-based index into incubator bullets")
    p_promote.add_argument("--type", default=None,
                           help="item type (default: bug when the bullet reads like a "
                                "bug report, else feature)")
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
    p_idea.add_argument("--force", action="store_true",
                        help="park it even though the title reads like a bug report")

    p_bug = sub.add_parser(
        "bug", help="route a bug: a Fix step on an in-flight item's plan (--found-in), "
                    "else a new bug item linked to its origin — never the incubator")
    p_bug.add_argument("title")
    p_bug.add_argument("--found-in", dest="found_in", metavar="ID",
                       help=ID_HELP + " — the item the bug was found in")
    p_bug.add_argument("--observed", help="what was observed (pre-fills Observed / "
                                          "the Found during build note)")
    p_bug.add_argument("--version", help="target version for a new bug item "
                                         "(default: current; ignored for a Fix step)")
    p_bug.add_argument("--target", help="files for the Fix step's '-> target:' "
                                        "(default: TBD)")
    p_bug.add_argument("--owner", help="claimant for the fixing claim (default: as claim)")
    p_bug.add_argument("--take", action="store_true",
                       help="fix an in-flight item held by another owner anyway")

    p_cl = sub.add_parser("changelog")
    p_cl.add_argument("--backfill", action="store_true")
    p_cl.add_argument("--internal", action="store_true",
                      help="print CHANGELOG.internal.md instead of the public CHANGELOG.md")
    p_cl.add_argument("--json", action="store_true", dest="as_json",
                      help="emit the public changelog as structured JSON "
                           "(for in-app changelog screens / What's New popups)")

    p_rt = sub.add_parser("retarget")
    p_rt.add_argument("ids", nargs="*", metavar="id",
                      help=ID_HELP + " (same as --plan)")
    p_rt.add_argument("--to", "--version", dest="to", required=True)
    p_rt.add_argument("--from", dest="from_versions", default="")
    p_rt.add_argument("--plan", dest="plan_ids", default="", help=IDS_HELP)
    p_rt.add_argument("--split", action="store_true",
                      help="keep the ticked steps in the item's version (it completes "
                           "there) and move only the open steps into a new linked "
                           "follow-up item in --to")

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
            if args.landed:
                if (args.plan, args.step, args.tokens) != (None, None, None) \
                        or args.undo or args.all_done:
                    p_check.error("--landed takes only --evidence and --yes")
                return _print_check_landed(
                    check_landed(root, evidence=args.evidence, apply=args.yes),
                    args.yes)
            if args.yes:
                p_check.error("--yes only applies with --landed")
            if args.plan is None:
                p_check.error("the following arguments are required: --plan "
                              "(or use --landed)")
            check_step(root, rid(args.plan), args.step, undo=args.undo,
                       all_done=args.all_done, evidence=args.evidence,
                       tokens=args.tokens, force=args.force)
            return 0
        if args.command == "wait":
            if args.clear and (args.until or args.reason):
                p_wait.error("--clear takes no --until/--reason")
            if not args.clear and not args.until:
                p_wait.error("--until is required (or --clear)")
            plan_id = rid(args.plan)
            w = wait_step(root, plan_id, args.step, until=args.until,
                          reason=args.reason, clear=args.clear)
            if args.clear:
                print(f"#{plan_id} step {w['step']}: no longer waiting")
            else:
                print(f"#{plan_id} step {w['step']}: waiting until {w['until']}"
                      + (f" ({w['reason']})" if w["reason"] else ""))
            return 0
        if args.command == "claim":
            if args.clear and any(v is not None for v in
                                  (args.stage, args.verdict, args.note, args.branch,
                                   args.landed)):
                p_claim.error("--clear takes only --owner and --take")
            if args.landed is not None and (args.take or any(
                    v is not None for v in (args.stage, args.verdict, args.note,
                                            args.branch, args.owner))):
                p_claim.error("--landed takes no other options (the stage is 'landed')")
            plan_ids = [n for tok in args.ids for n in rids(tok)]
            if args.landed is not None:
                res = claim_landed(root, args.landed, plan_ids or None)
                short = res["sha"][:7]
                for plan_id, name in res["landed"]:
                    print(f"#{plan_id}: landed @{short} ({name})")
                for plan_id, name in res["untagged"]:
                    print(f"#{plan_id}: skipped — {name} is contained in {short} but "
                          f"carries no (plan {plan_id}) commit; land it by id: "
                          f"roadmap.py claim {plan_id} --landed {short}",
                          file=sys.stderr)
                if not res["landed"]:
                    print(f"no in-flight item branch is contained in {short}")
                return 0
            if not plan_ids:
                p_claim.error("no item id given")
            if args.clear:
                for plan_id, cleared in clear_claims(root, plan_ids, owner=args.owner,
                                                     take=args.take).items():
                    print(f"#{plan_id}: claim cleared" if cleared
                          else f"#{plan_id}: no claim to clear")
                return 0
            claims = set_claims(root, plan_ids, stage=args.stage, verdict=args.verdict,
                                note=args.note, branch=args.branch, owner=args.owner,
                                take=args.take)
            for plan_id, c in claims.items():
                print(f"#{plan_id}: " + " · ".join(f"{f}={c[f]}" for f in CLAIM_FIELDS
                                                    if c.get(f)))
            return 0
        if args.command == "ruling":
            print(add_ruling(root, rid(args.id), args.text, by=args.by,
                             approval=args.approval))
            return 0
        if args.command == "accept":
            return _accept_cmd(root, args, p_accept, rid)
        if args.command == "slot":
            return _slot_cmd(root, args, p_slot, rid)
        if args.command == "run":
            return _run_cmd(root, args, rids)
        if args.command == "release":
            release(root, args.version, tag=args.tag, force=args.force,
                    with_waiting=args.with_waiting)
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
            note = add_idea(root, args.title, body, force=args.force)
            print(f"Parked idea: {args.title}" + (f" (notes: {note})" if note else ""))
            return 0
        if args.command == "bug":
            res = file_bug(root, args.title,
                           found_in=rid(args.found_in) if args.found_in else None,
                           observed=args.observed, version=args.version,
                           target=args.target, owner=args.owner, take=args.take)
            rel = res["path"].relative_to(root)
            if res["route"] == "fix-step":
                claim = (" · claim stage → fixing" if res["claim"]
                         else " · not started, no claim set")
                print(f"#{res['id']}: Step {res['step']} 'Fix: {args.title.strip()}' "
                      f"appended to {rel}{claim} — no new item")
                if res["ignoredVersion"]:
                    print(f"note: --version {res['ignoredVersion']} ignored — the fix "
                          f"ships with #{res['id']}", file=sys.stderr)
            else:
                link = f" (foundIn #{res['foundIn']}, linked both ways)" \
                    if res["foundIn"] is not None else ""
                print(f"#{res['id']}: new bug item{link}")
                print(res["path"])
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
            due = due_waiting(status(root)["items"])   # plan 46: due waits first
            if not args.as_json:
                for line in format_due(due):
                    print(line)
            if item is None:
                print("No unfinished unblocked items.")
                if not args.version:
                    release_gate(root)
                return 0
            if args.as_json:
                print(json.dumps({**item, "waitingDue": due}, indent=2))
            else:
                print(f"{item['displayId']} {item['title']} [{item['type']}] "
                      f"v{item['version']} — {item['pct']}% "
                      f"(.roadmap/{item['file']})")
            return 0
        if args.command == "orient":
            payload = orient(root)
            if payload is None:
                return 0
            # Plan 45: what changed since this owner's previous orient (stamped
            # in the git dir, never in the tree); absent outside git.
            dg = rmdigest.orient_digest(root, rmowners.default_owner(root))
            if dg is not None:
                payload["digest"] = dg
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
        if args.command == "digest":                            # plan 45
            d = rmdigest.digest(root, args.since, conflicts=args.conflicts,
                                owner=rmowners.default_owner(root), record=True)
            print(json.dumps(d, indent=2) if args.as_json
                  else rmdigest.format_digest(d, md=args.format == "md"))
            return 0
        if args.command == "deps-check":
            plan_id = rid(args.plan)
            blocked = warn_incomplete_deps(root, plan_id, force=args.force)
            if args.force or not blocked:
                print(f"#{plan_id}: ok" + (" (force)" if args.force and blocked else ""))
            return 0
        if args.command == "retarget":
            ids = [*rids(args.plan_ids), *(n for tok in args.ids for n in rids(tok))]
            made = retarget(
                root, args.to,
                from_versions=[v for v in args.from_versions.split(",") if v.strip()] or None,
                plan_ids=ids or None, split=args.split)
            for fu in made:
                print(f"#{fu['followUpOf']}: open steps → follow-up #{fu['id']} "
                      f"in v{fu['version']} (.roadmap/{fu['file']})")
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
            st = status(root, worktrees=args.worktrees, conflicts=args.conflicts)
            if args.conflicts:
                if args.as_json:
                    print(json.dumps({"conflicts": st["conflicts"]}, indent=2))
                else:
                    print(rmconflicts.format_conflicts(st["conflicts"]))
                return 0
            if args.worktrees:
                if args.as_json:
                    print(json.dumps({"worktrees": st["worktrees"]}, indent=2))
                else:
                    print(format_worktrees(st["worktrees"]))
                return 0
            if args.slots:
                if args.as_json:
                    print(json.dumps({"slots": st.get("slots")}, indent=2))
                else:
                    print(rmslots.format_slots(st.get("slots")))
                return 0
            if not args.as_json:
                for w in st.get("runWarnings") or []:
                    print(f"warning: {w}", file=sys.stderr)
                over = rmowners.wip_warning(st.get("wip"))      # plan 40
                if over:
                    print(f"warning: {over}", file=sys.stderr)
            if args.runs:
                if args.as_json:
                    print(json.dumps({k: st.get(k) for k in
                                      ("runs", "trunkHealth", "runWarnings")
                                      if k in st}, indent=2))
                else:
                    print(rmruns.format_runs(st.get("runs") or [], st.get("trunkHealth")))
                return 0
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
                waiting = f" · {lc['waiting']} waiting" if lc.get("waiting") else ""
                print(f"{st['project']} — v{st['currentVersion']} · {lc['done']} done"
                      f" · {lc['inFlight']} in-flight{active} · {lc['planned']} planned"
                      f"{waiting}")
                for line in format_due(st.get("waitingDue") or []):   # plan 46
                    print(line)
                # Items grouped under a version header carrying its forecast (plan 44).
                groups: dict[str, list] = {}
                for it in st["items"]:
                    groups.setdefault(it["version"], []).append(it)
                for ver, its in groups.items():
                    fc = rmforecast.summary((st.get("forecast") or {}).get(ver))
                    print(f"v{ver}" + (f" — {fc}" if fc else ""))
                    for it in its:
                        block = (f" blocked by {it['blockedBy']}"
                                 if it.get("blockedBy") else "")
                        lane = (f" — {lane_label(it)}"
                                if is_in_flight(it) or it["lane"] == "waiting" else "")
                        print(f"  {it['displayId']} {it['title']} [{it['type']}] "
                              f"{it['pct']}% ({it['status']}){lane}{block}")
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
