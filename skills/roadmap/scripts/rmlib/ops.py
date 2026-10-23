"""roadmap operations — the mutating item commands (new/note/audience/depends,
remove/retarget/reorder/merge, release/backfill, promote, import). Top layer:
orchestrates every lower module."""
from __future__ import annotations
import os
import re
import subprocess
import sys
import datetime
from pathlib import Path
from rmlib.core import (
    _norm_version, _render_template, _set_frontmatter, _version_key,
    atomic_write, read_config, roadmap_dir, slugify, write_config)
from rmlib.parse import (
    CLAIM_FIELDS, CLAIM_PREFIX, CLAIM_STAGES, CLAIM_VERDICTS, FRONTMATTER_RE,
    RULING_APPROVAL_TAG, RULINGS_HEADING, RULINGS_SECTION_KEY,
    STEP_RE, _HEADING_RE, _is_fence, _norm_name, _plan_path, count_progress,
    parse_plan, read_claim, required_sections, template_stubs)
from rmlib.changelog import (
    demote_tells, item_audience, lint_note, status_tells)
from rmlib.sync import (
    _branch_has_work, status, sync, uncut_complete_version)
from rmlib import branches as rmbranches
from rmlib import owners as rmowners
from rmlib.report import (
    _record_last_seen_sha)
from rmlib.incubator import (
    INCUBATOR_BULLET_RE, MD_LINK_RE, _incubator_stub, _strip_incubator_placeholder,
    incubator_file, list_incubator_bullets)


def _auto_release_mode(cfg: dict) -> str:
    """settings.autoRelease: off | nudge (default) | auto. Unknown values → nudge."""
    mode = (cfg.get("settings") or {}).get("autoRelease", "nudge")
    return mode if mode in ("off", "nudge", "auto") else "nudge"


def release_gate(root: Path, target: str | None = None) -> None:
    """Release is part of the roadmap flow: when the current version is 100% but
    uncut, nudge (default) or auto-run `release` per settings.autoRelease.

    `target` is the next version when the caller knows it (e.g. a new item aimed
    at a later version); otherwise the lowest existing version above current is
    used. auto with no discoverable target falls back to a nudge — the CLI never
    invents a version number."""
    cfg = read_config(root)
    mode = _auto_release_mode(cfg)
    if mode == "off":
        return
    done = uncut_complete_version(root, cfg)
    if not done:
        return
    if target is None:
        above = sorted({i["version"] for i in cfg["items"]
                        if _version_key(i["version"]) > _version_key(done)},
                       key=_version_key)
        target = above[0] if above else None
    if mode == "auto" and target:
        release(root, target)
        print(f"auto-release: v{done} complete — released; current version is now "
              f"v{target} (settings.autoRelease=auto)", file=sys.stderr)
        return
    hint = target or "<next>"
    print(f"🎉 v{done} is 100% complete but uncut — cut it: roadmap.py release --version {hint} "
          f'(or set settings.autoRelease to "auto")', file=sys.stderr)


def check_step(root: Path, plan_id: int, step: int | None,
               undo: bool = False, all_done: bool = False,
               evidence: str | None = None, tokens: int | None = None,
               force: bool = False) -> None:
    """Flip checklist boxes. `evidence` (ignored on --undo) is recorded under each
    step being checked as a blockquote sub-line — a form STEP_RE can never read as a
    step, so counts and generated output are untouched. `tokens` (optional, >= 0) is
    appended to that same sub-line so spend can be compared per completed step.
    Checking is refused while the plan's required sections are still template text
    (plan 35); `force` checks anyway and records the override in the evidence line."""
    path = _plan_path(root, plan_id)
    evidence = " ".join(evidence.split()) if evidence else ""
    if tokens is not None and tokens < 0:
        raise ValueError("--tokens must be a non-negative integer")
    cfg = read_config(root)
    if not undo and not evidence and (cfg.get("settings") or {}).get("requireEvidence"):
        raise ValueError(
            f"check refused — settings.requireEvidence is on: pass --evidence "
            f'"<verify command + result>" (e.g. --evidence "pytest -q: 287 passed") '
            f"so plan {plan_id} records how the step was proven done.")
    stubs = []
    if not undo:
        type_ = next((i.get("type") for i in cfg["items"] if i["id"] == plan_id),
                     None) or parse_plan(path)["meta"].get("type", "")
        stubs = template_stubs(path, *required_sections(cfg, type_))
    if stubs and not force:
        raise ValueError(
            f"check refused — plan {plan_id} still has template text in required "
            f"section(s): {', '.join(stubs)} ({path.relative_to(root)}). Fill them in "
            f"(settings.requiredSections lists them per type), or re-run with --force "
            f"to check anyway (recorded in the evidence line).")
    if stubs:
        forced = f"forced past empty template ({', '.join(stubs)})"
        evidence = f"{evidence} · {forced}" if evidence else forced
    spend = f" · tokens: {tokens}" if tokens is not None and evidence and not undo else ""
    stamp = f"  > evidence: {evidence} ({datetime.date.today().isoformat()}){spend}"
    box = "[ ]" if undo else "[x]"
    out, n, ticked, in_fence = [], 0, 0, False
    for line in path.read_text(encoding="utf-8").splitlines():
        if _is_fence(line):
            in_fence = not in_fence
            out.append(line)
            continue
        sm = None if in_fence else STEP_RE.match(line)
        hit = sm and (all_done or n + 1 == step)
        if sm:
            n += 1
            if hit:
                line = re.sub(r"\[( |x|X)\]", box, line, count=1)
            ticked += STEP_RE.match(line).group(2).lower() == "x"
        out.append(line)
        if hit and evidence and not undo:
            out.append(stamp)
    if step is not None and not all_done and (step < 1 or step > n):
        raise ValueError(f"plan {plan_id} step {step} out of range (1..{n})")
    text = "\n".join(out) + "\n"
    if not undo and n and ticked == n:
        text = _apply_claim(text, None)     # item is done: its in-flight claim ends
    atomic_write(path, text)
    sync(root)
    if not undo:
        _record_last_seen_sha(root)
        release_gate(root)


def _apply_claim(text: str, claim: dict | None) -> str:
    """Return plan `text` with every `claim_*` frontmatter key replaced by `claim`
    (None removes them). Other frontmatter lines and the body are untouched."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        if claim is None:
            return text
        raise ValueError("plan file has no frontmatter block — cannot record a claim")
    keep = [ln for ln in m.group(1).splitlines() if not ln.startswith(CLAIM_PREFIX)]
    if claim:
        keep += [f"{CLAIM_PREFIX}{f}: {claim[f]}" for f in CLAIM_FIELDS if claim.get(f)]
    return "---\n" + "\n".join(keep) + "\n---\n" + text[m.end():]


_KEEP = object()     # _prepare_claim: leave owner/refreshed as they are


def _prepare_claim(root: Path, plan_id: int, stage: str | None = None,
                   verdict: str | None = None, note: str | None = None,
                   branch: str | None = None,
                   landed_sha: str | None = None, owner=_KEEP,
                   take: bool = False, explicit_owner: bool = False,
                   ttl_hours: float | None = None) -> tuple[Path, str, dict]:
    """Validate a claim update and return (plan path, new plan text, claim)
    without writing anything — the shared core of set_claim / set_claims, so a
    multi-id claim can validate every item before touching any file.

    `owner` (plan 40): the claimant. A claim held by a different owner (see
    rmlib/owners.py) is refused unless `take`; otherwise the owner is recorded
    and `refreshed` restamped. The default `_KEEP` (claim --landed) neither
    checks nor changes ownership. A new claim needs a stage, or an
    `explicit_owner` (an owner-only claim that holds the item while it builds)."""
    if stage is not None:
        stage = stage.strip().lower()
        if stage == "building":
            raise ValueError(
                f"'building' is a derived lane, not a claim stage — an item with a "
                f"branch or (plan N) commits and no claim already shows as building. "
                f"To return to it, drop the claim: roadmap.py claim {plan_id} --clear")
        if stage not in CLAIM_STAGES:
            raise ValueError(f"invalid stage {stage!r} — choose from "
                             f"{', '.join(CLAIM_STAGES)}")
    if verdict is not None:
        verdict = verdict.strip().upper()
        if verdict not in CLAIM_VERDICTS:
            raise ValueError(f"invalid verdict {verdict!r} — choose from "
                             f"{', '.join(CLAIM_VERDICTS)}")
    if branch is not None:
        branch = branch.strip()
        if any(c.isspace() for c in branch):
            raise ValueError(f"invalid branch name {branch!r} (contains whitespace)")
    path = _plan_path(root, plan_id)
    if not path.exists():
        raise ValueError(f"plan file for #{plan_id} is missing ({path.name})")
    done, total = count_progress(path)
    if total and done == total:
        raise ValueError(f"#{plan_id} is done ({done}/{total} steps ticked on trunk) — "
                         f"a done item cannot be claimed")
    claim = read_claim(path) or {}
    if stage is None and not claim and not explicit_owner:
        raise ValueError(f"#{plan_id} has no claim yet — pass --stage "
                         f"{{{','.join(CLAIM_STAGES)}}} (or --owner NAME to hold it "
                         f"while it builds)")
    if owner is not _KEEP:
        owner = rmowners.clean_owner(owner)
        if ttl_hours is None:
            ttl_hours = rmowners.claim_ttl_hours(read_config(root))
        other = rmowners.held_by_other(claim, owner, ttl_hours)
        if other and not take:
            raise ValueError(rmowners.held_message(plan_id, other, claim))
        claim["owner"] = owner
        claim["refreshed"] = rmowners.stamp() if owner else None
    if stage is not None:
        claim["stage"] = stage
    if verdict is not None:
        claim["verdict"] = verdict
    if note is not None:
        claim["note"] = " ".join(note.split()) or None
    if branch is not None:
        claim["branch"] = branch or None
    if landed_sha is not None:
        claim["landed_sha"] = landed_sha or None
    if claim.get("stage") != "landed":
        claim["landed_sha"] = None      # a landing sha only means something while landed
    claim["updated"] = datetime.date.today().isoformat()
    text = _apply_claim(path.read_text(encoding="utf-8"), claim)
    return path, text, {f: claim.get(f) for f in CLAIM_FIELDS}


def set_claim(root: Path, plan_id: int, stage: str | None = None,
              verdict: str | None = None, note: str | None = None,
              branch: str | None = None, owner: str | None = None,
              take: bool = False) -> dict:
    """Record (or update in place) an item's in-flight claim: the build-loop stage
    and review verdict git cannot know. Fields not passed keep their prior values;
    `updated` is always restamped. An empty --note/--branch removes that field.
    Refused on a done item — trunk ticks are the only source of done.
    Ownership (plan 40): see set_claims."""
    return set_claims(root, [plan_id], stage=stage, verdict=verdict, note=note,
                      branch=branch, owner=owner, take=take)[plan_id]


def _unique(ids) -> list[int]:
    return list(dict.fromkeys(int(i) for i in ids))


def set_claims(root: Path, plan_ids, stage: str | None = None,
               verdict: str | None = None, note: str | None = None,
               branch: str | None = None, owner: str | None = None,
               take: bool = False) -> dict[int, dict]:
    """set_claim for several items with the same options, all-or-nothing: every
    item is validated before any plan file is written, so one bad id (unknown,
    missing plan, done, no claim and no --stage, held by another owner) changes
    none of them.

    Every claim records its owner (plan 40): `owner`, else
    rmowners.default_owner ($ROADMAP_OWNER, git user name, agent name). An item
    held by a different owner is refused unless `take`. An explicit `owner`
    alone may open a claim (owner-only: it holds the item, lane stays derived)."""
    ids = _unique(plan_ids)
    if not ids:
        raise ValueError("claim needs at least one item id")
    explicit = rmowners.clean_owner(owner) is not None
    who = rmowners.clean_owner(owner) if explicit else rmowners.default_owner(root)
    ttl = rmowners.claim_ttl_hours(read_config(root))
    prepared = [(pid, *_prepare_claim(root, pid, stage=stage, verdict=verdict,
                                      note=note, branch=branch, owner=who,
                                      take=take, explicit_owner=explicit,
                                      ttl_hours=ttl)) for pid in ids]
    for _, path, text, _ in prepared:
        atomic_write(path, text)
    sync(root)
    return {pid: claim for pid, _, _, claim in prepared}


def claim_landed(root: Path, rev: str, plan_ids=None) -> dict:
    """Move items whose work `rev` (an integration commit or branch) already
    contains to the `landed` stage, recording the resolved commit as
    `claim_landed_sha` — what `check --landed` later tests against trunk.

    Without `plan_ids`: every unfinished item (claimed or discovered) whose
    branch carries unmerged work, at least one `(plan N)` commit for the item,
    and a tip `rev` contains. The tag rule keeps a branch merely cut from the
    integration branch (no work of its own yet) from reading as landed; such
    branches are returned under `untagged` so they can be landed by id.
    With `plan_ids`: exactly those items, all-or-nothing — each must have a
    branch with unmerged work whose tip `rev` contains (tags not required).

    Returns {"sha", "landed": [(id, branch)], "untagged": [(id, branch)]}.
    One status() discovery plus two git calls (resolve, containment)."""
    rev = (rev or "").strip()
    sha = rmbranches.resolve_commits(root, [rev]).get(rev) if rev else None
    if not sha:
        raise ValueError(f"--landed {rev!r} is not a commit in this repository")
    st = status(root)
    rows = {i["id"]: i for i in st["items"]}
    explicit = plan_ids is not None
    ids = _unique(plan_ids) if explicit else list(rows)
    cands: dict[int, dict] = {}
    for pid in ids:
        row = rows.get(pid)
        if row is None:
            raise ValueError(f"no plan with id {pid}")
        b = row.get("branch")
        has_work = row["lane"] != "done" and _branch_has_work(b) and b.get("sha")
        if has_work:
            cands[pid] = b
        elif explicit:
            why = ("is done" if row["lane"] == "done" else
                   "has no branch with unmerged work")
            raise ValueError(f"#{pid} {why} — nothing to land")
    inside = rmbranches.contained(root, sha, [b["sha"] for b in cands.values()])
    if inside is None:
        raise ValueError(f"git could not test which branches {sha[:7]} contains")
    landed, untagged = [], []
    for pid, b in cands.items():
        if b["sha"] not in inside:
            if explicit:
                raise ValueError(f"#{pid}: {b['name']} @{b['sha'][:7]} is not "
                                 f"contained in {sha[:7]} — nothing written")
            continue
        if not explicit and not b.get("taggedCommits"):
            untagged.append((pid, b["name"]))
            continue
        landed.append((pid, b["name"]))
    prepared = [_prepare_claim(root, pid, stage="landed", landed_sha=sha)
                for pid, _ in landed]
    for path, text, _ in prepared:
        atomic_write(path, text)
    if prepared:
        sync(root)
    return {"sha": sha, "landed": landed, "untagged": untagged}


def check_landed(root: Path, evidence: str | None = None,
                 apply: bool = False) -> dict:
    """Tick off items in the `landed` lane whose work trunk now contains.

    An item is ready only when its landing sha (claim_landed_sha, or the
    derived integration tip) is an ancestor of trunk AND, if it still has a
    branch, that branch tip is too — so work added after landing, or a branch
    never merged, can never be ticked. Containment is one `rev-list` call for
    every item. Dry run unless `apply`: then every step of each ready item is
    ticked with evidence naming the sha (check_step, which also clears the
    claim). Returns {"trunk", "ready", "waiting", "ticked", "refused"}; each
    entry is {"id", "displayId", "title", "steps", "sha", "reason"}."""
    st = status(root)
    trunk = st.get("trunk")
    if not trunk:
        raise ValueError("check --landed needs a git repository with a trunk branch")
    rows = [i for i in st["items"] if i["lane"] == "landed"]

    def landing(row: dict) -> str | None:
        claim = row.get("claim") or {}
        if claim.get("stage") == "landed":
            return claim.get("landed_sha")
        return (row.get("branch") or {}).get("landedSha")

    full = rmbranches.resolve_commits(root, [s for s in map(landing, rows) if s])
    tips = [(r.get("branch") or {}).get("sha") for r in rows]
    inside = rmbranches.contained(root, f"refs/heads/{trunk}",
                                  [*filter(None, full.values()), *filter(None, tips)])
    if inside is None:
        raise ValueError(f"git could not test what {trunk} contains — nothing ticked")
    out = {"trunk": trunk, "ready": [], "waiting": [], "ticked": [], "refused": []}
    for row in rows:
        raw = landing(row)
        sha = full.get(raw) if raw else None
        tip = (row.get("branch") or {}).get("sha")
        entry = {"id": row["id"], "displayId": row["displayId"], "title": row["title"],
                 "steps": row["total"], "sha": sha, "reason": ""}
        if not raw:
            entry["reason"] = (f"no landing sha recorded — record it with: roadmap.py "
                               f"claim {row['id']} --landed <sha>")
        elif not sha:
            entry["reason"] = f"landing sha {raw!r} is not a commit in this repository"
        elif sha not in inside:
            entry["reason"] = f"landed @{sha[:7]}, not in {trunk} yet"
        elif tip and tip not in inside:
            entry["reason"] = (f"{row['branch']['name']} @{tip[:7]} has work "
                               f"{trunk} lacks (moved past its landing)")
        if entry["reason"]:
            out["waiting"].append(entry)
            continue
        out["ready"].append(entry)
    if not apply:
        return out
    note = " ".join(evidence.split()) if evidence else ""
    for entry in out["ready"]:
        text = f"landed in {trunk} @{entry['sha'][:7]}"
        try:
            check_step(root, entry["id"], None, all_done=True,
                       evidence=f"{note} · {text}" if note else text)
        except ValueError as exc:      # another gate (e.g. evidence rules) refused it
            out["refused"].append({**entry, "reason": str(exc)})
            continue
        out["ticked"].append({**entry, "reason": text})
    return out


def clear_claim(root: Path, plan_id: int, owner: str | None = None,
                take: bool = False) -> bool:
    """Remove an item's claim (its lane reverts to the derived one). Allowed on done
    items. Returns False when there was nothing to clear."""
    return clear_claims(root, [plan_id], owner=owner, take=take)[plan_id]


def clear_claims(root: Path, plan_ids, owner: str | None = None,
                 take: bool = False) -> dict[int, bool]:
    """clear_claim for several items, all-or-nothing: every id must resolve to an
    existing plan file, and none may be held by another owner (plan 40; `take`
    overrides), before any claim is removed. {id: cleared?}."""
    ids = _unique(plan_ids)
    who = rmowners.clean_owner(owner) or rmowners.default_owner(root)
    ttl = rmowners.claim_ttl_hours(read_config(root))
    paths = {}
    for pid in ids:
        path = _plan_path(root, pid)
        if not path.exists():
            raise ValueError(f"plan file for #{pid} is missing ({path.name})")
        claim = read_claim(path)
        other = None if take else rmowners.held_by_other(claim, who, ttl)
        if other:
            raise ValueError(rmowners.held_message(pid, other, claim))
        paths[pid] = path
    out = {}
    for pid, path in paths.items():
        text = path.read_text(encoding="utf-8")
        new = _apply_claim(text, None)
        out[pid] = new != text
        if out[pid]:
            atomic_write(path, new)
    if any(out.values()):
        sync(root)
    return out


def _ruling_insert_at(lines: list[str]) -> int | None:
    """Index to insert a new ruling bullet at: just past the last non-blank line
    of the plan's `## ... Rulings` section, or None when it has no such section.
    Fenced code is never read as a heading."""
    in_fence, start = False, None
    for i, line in enumerate(lines):
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        hm = _HEADING_RE.match(line)
        if not hm:
            continue
        if start is not None and len(hm.group(1)) <= 2:
            end = i
            break
        if start is None and len(hm.group(1)) == 2 \
                and _norm_name(hm.group(2)) == RULINGS_SECTION_KEY:
            start = i
    else:
        end = len(lines)
    if start is None:
        return None
    last = start
    for j in range(start + 1, end):
        if lines[j].strip():
            last = j
    return last + 1


def add_ruling(root: Path, plan_id: int, text: str, by: str = "owner",
               approval: bool = False) -> str:
    """Append a dated ruling bullet to the plan body under `## ⚖️ Rulings` (the
    section is created at the end of the file when missing) and return the line.
    Append-only: rulings are never edited or removed from here. Touches only the
    plan file — never the changelog, config, or ROADMAP.md (a ruling is a
    decision record, not progress or a release note)."""
    text = " ".join((text or "").split())
    if not text:
        raise ValueError("ruling text is empty")
    by = " ".join((by or "").split())
    if not by:
        raise ValueError("ruling author (--by) is empty")
    if any(c in by for c in "*(),:[]"):
        raise ValueError(f"invalid ruling author {by!r} — use a plain name "
                         f"(no * ( ) , : [ ])")
    path = _plan_path(root, plan_id)
    if not path.exists():
        raise ValueError(f"plan file for #{plan_id} is missing ({path.name})")
    tags = [datetime.date.today().isoformat(), by] + ([RULING_APPROVAL_TAG]
                                                       if approval else [])
    bullet = f"- **Ruling ({', '.join(tags)}):** {text}"
    lines = path.read_text(encoding="utf-8").splitlines()
    at = _ruling_insert_at(lines)
    if at is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ["", RULINGS_HEADING, "", bullet]
    else:
        lines.insert(at, bullet)
    atomic_write(path, "\n".join(lines) + "\n")
    return bullet


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


def _refuse_unclassified_note(item: dict, note: str, force: bool) -> None:
    """Refuse (ValueError) saving a note on an item with no explicit audience. Fail-closed
    defaults mean the text would silently land internal-only — force the classification
    decision at the moment the text is written instead."""
    if force or not note or item.get("audience") in ("public", "internal"):
        return
    pid = item.get("id", "<id>")
    raise ValueError(
        f"note refused — #{pid} has no explicit audience, so this text would silently land "
        f"in the internal changelog only. Decide where it ships first: pass --audience "
        f"public|internal, or run roadmap audience --plan {pid} --to public|internal, then "
        f"set the note. --force keeps it unclassified (renders internal-only).")


def _refuse_public_note_demote_tells(item: dict, note: str, force: bool) -> None:
    """Refuse (ValueError) a note that would render PUBLIC while the note/title trips a
    high-confidence demote tell — wrong-audience text must not ship to end users."""
    if force or not note or item_audience(item) != "public":
        return
    tells = demote_tells(f"{note} {item.get('title', '')}")
    if tells:
        raise ValueError(
            f"note refused — this reads like wrong-audience work ({', '.join(tells)}). "
            f"CHANGELOG.md is pasted into the App Store \"What's New\" and ships to end "
            f"users; admin/compliance/security-disclosure/dev-surface text belongs in the "
            f"internal changelog. Rephrase in plain benefit language, mark the item internal "
            f"(roadmap audience --plan {item.get('id', '<id>')} --to internal), or re-run "
            f"with --force if this text really should ship.")


def _refuse_public_demote_tells(item: dict, force: bool) -> None:
    """Refuse (ValueError) EXPLICITLY setting audience=public on an item whose note/title
    trips a high-confidence demote tell (admin/compliance/plumbing/dev-surface)."""
    if force:
        return
    tells = demote_tells(f"{item.get('note', '')} {item.get('title', '')}")
    if tells:
        raise ValueError(
            f"public audience refused — this item reads like wrong-audience work "
            f"({', '.join(tells)}). CHANGELOG.md is pasted into the App Store \"What's New\" "
            f"and ships to end users; admin/compliance/dev-surface work belongs in the "
            f"internal changelog. Keep it internal, or re-run with --force if it genuinely "
            f"is user-facing.")


def new_item(root: Path, type_: str, title: str, version: str | None = None,
             note: str = "", audience: str | None = None, force: bool = False) -> Path:
    if type_ not in TEMPLATE_BY_TYPE:
        raise ValueError(f"unknown type {type_!r}; choose from {sorted(TEMPLATE_BY_TYPE)}")
    cfg = read_config(root)
    item_id = cfg["nextId"]
    candidate = {"id": item_id, "title": title, "type": type_,
                 "note": note, "audience": audience}
    _refuse_unclassified_note(candidate, note, force)
    _refuse_status_note(candidate, note, force)
    _refuse_public_note_demote_tells(candidate, note, force)
    if audience == "public":
        _refuse_public_demote_tells({"title": title, "note": note}, force)
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
    if _version_key(version) > _version_key(cfg["currentVersion"]):
        release_gate(root, target=version)
    return path


def set_note(root: Path, plan_id: int, text: str, force: bool = False) -> None:
    """Set an item's user-facing changelog note, then re-render. A note that would render
    PUBLIC but is structurally a status dump (dates, step/version refs, paths, shouted
    status words) is REFUSED unless --force; softer internal wording only warns."""
    cfg = read_config(root)
    for item in cfg["items"]:
        if item["id"] == plan_id:
            candidate = {**item, "note": text}
            _refuse_unclassified_note(candidate, text, force)
            _refuse_status_note(candidate, text, force)
            _refuse_public_note_demote_tells(candidate, text, force)
            item["note"] = text
            write_config(root, cfg)
            if item_audience(item) == "public":
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


def set_audience(root: Path, plan_id: int, audience: str, force: bool = False) -> None:
    """Set an item's changelog audience ('public' | 'internal'), then re-render both files."""
    if audience not in ("public", "internal"):
        raise ValueError("audience must be 'public' or 'internal'")
    cfg = read_config(root)
    for item in cfg["items"]:
        if item["id"] == plan_id:
            if audience == "public":
                _refuse_public_demote_tells(item, force)
            item["audience"] = audience
            write_config(root, cfg)
            sync(root)
            return
    raise ValueError(f"no plan with id {plan_id}")


def set_depends(root: Path, plan_id: int, on: list[int], clear: bool = False) -> None:
    """Set (or clear) an item's `dependsOn` list. Consumed by `next` (skips blocked),
    `build` (warns), /roadmap-reevaluate, and retargeted by merge/remove."""
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


def _own_source_version_file(root: Path) -> Path | None:
    """The skill's own VERSION file, but only when `root` is the repo that CONTAINS
    the running scripts (i.e. we are releasing the roadmap skill's own source).

    Only the exact source layout `<root>/skills/roadmap` counts — an installed copy
    under `<root>/.claude/skills/roadmap` (what install.sh creates inside a consumer
    project) is inside `root` but must never be written. Symlinks resolve first, so
    a linked CLI or linked skill dir in a foreign project also gets nothing."""
    skill = Path(__file__).resolve().parent.parent.parent   # skills/roadmap/
    if skill != root.resolve() / "skills" / "roadmap":
        return None
    if not (skill / "VERSION").exists():
        return None
    return skill / "VERSION"


def release(root: Path, version: str, tag: bool = False, force: bool = False) -> None:
    version = _norm_version(version)
    cfg = read_config(root)
    outgoing = cfg["currentVersion"]
    incomplete = _incomplete_items(root, outgoing)
    if incomplete and not force:
        names = ", ".join(f"#{i['id']} {i['title']}" for i in incomplete)
        raise ValueError(
            f"v{outgoing} still has incomplete items: {names}. "
            f"Finish them (see /roadmap-review) or pass --force.")
    cfg["currentVersion"] = version
    write_config(root, cfg)
    sync(root)
    vf = _own_source_version_file(root)
    if vf:                                  # releasing the roadmap skill's own repo
        atomic_write(vf, f"{outgoing}\n")
        print(f"skill source: {vf.relative_to(root.resolve())} set to {outgoing} "
              f"(the version just cut)")
    if tag or cfg["settings"].get("gitTagOnRelease"):
        result = subprocess.run(["git", "tag", f"v{version}"], cwd=str(root), check=False)
        if result.returncode != 0:
            print(f"Warning: 'git tag v{version}' failed (exit {result.returncode}); "
                  "version recorded in config but not tagged.", file=sys.stderr)


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

    # The bullet's notes file (from `idea --body`) is the plan's spec — link it from the
    # plan header instead of dragging the link text through the title/slug/filename.
    link = MD_LINK_RE.search(chosen["body"])
    if link:
        rel = os.path.relpath(root / link.group(1), path.parent)
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        for i, ln in enumerate(lines):
            if ln.startswith("> Type: "):
                lines.insert(i + 1, f"> Spec: [notes]({rel})\n")
                break
        atomic_write(path, "".join(lines))

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
