"""roadmap digest (plan 45) — what landed, moved, stalled and got blocked since a
given time, plus what needs attention right now.

The window's start is a *baseline*: the newest first-parent commit at or
before `since`. Its `.roadmap/` tree (config + every plan, and the incubator
file) is read in one `git cat-file --batch` and compared with the working tree
now, so completions, ticked steps, claim moves, new plans and new ideas are
snapshot diffs — three git calls however many commits the window holds. A repo
younger than the window has an empty baseline (everything in it is new);
outside git there is no history and only the run log and the attention list
report. Runs come from the run log by timestamp; staleness and new branches
from branch discovery dates. The "needs attention" list reads the current
status payload only (ATTENTION: one entry per check).

`--since last` reads a per-user stamp kept in the git common dir
(`<.git>/roadmap-digest.json` — never tracked, shared by every worktree of the
clone, keyed by roadmap root and owner). The CLI rewrites it on each digest
run; `orient` keeps its own key in the same file. Nothing here writes a file
git tracks.
Layer: rmcore + rmparse + rmsync + rmincubator + rmruns + rmslots + rmowners
(read-only apart from the stamp).
"""
from __future__ import annotations
import datetime
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from rmlib.core import atomic_write, display_id, read_config, roadmap_dir
from rmlib.parse import (
    FRONTMATTER_RE, STEP_RE, _is_fence, parse_plan, required_sections,
    template_stubs)
from rmlib.sync import status
from rmlib.incubator import (
    INCUBATOR_BULLET_RE, INCUBATOR_RE, bullet_title, incubator_file,
    list_incubator_bullets)
from rmlib import branches as rmbranches
from rmlib import owners as rmowners
from rmlib import runs as rmruns
from rmlib import slots as rmslots

STAMP_FILE = "roadmap-digest.json"
DEFAULT_SINCE = "1d"          # `last` with no stamp yet
IDEA_PLACEHOLDER = "(add ideas here)"
_REL_RE = re.compile(r"^(\d+)\s*(m|min|h|d|w)$", re.I)
_UNIT = {"m": "minutes", "min": "minutes", "h": "hours", "d": "days", "w": "weeks"}
SECTIONS = (  # (key, heading) in print order
    ("completed", "Completed"), ("ticked", "Steps ticked"),
    ("claims", "Claims moved"), ("stalled", "Stale or blocked"),
    ("newPlans", "New plans"), ("newBranches", "New branches"),
    ("runs", "Runs"), ("ideas", "Ideas added"),
    ("attention", "Needs attention"))


def _utc(when: datetime.datetime) -> datetime.datetime:
    return when.astimezone(datetime.timezone.utc).replace(microsecond=0)


def iso(when: datetime.datetime) -> str:
    return _utc(when).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(text: str | None) -> datetime.datetime | None:
    if not text:
        return None
    try:
        when = datetime.datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.astimezone()   # naive = local time


# ---- window ---------------------------------------------------------------

def parse_since(text: str, now: datetime.datetime | None = None) -> datetime.datetime:
    """`30m` / `3h` / `1d` / `2w`, a date (`2026-10-20`, local midnight) or an
    ISO datetime (naive = local) -> an aware UTC datetime. `last` is resolved by
    the caller (resolve_since). Raises ValueError on anything else or a time
    in the future."""
    now = now or rmowners.now()
    raw = str(text or "").strip()
    m = _REL_RE.match(raw)
    if m:
        when = now - datetime.timedelta(**{_UNIT[m.group(2).lower()]: int(m.group(1))})
    else:
        when = _parse_iso(raw)
        if when is None:
            raise ValueError(f"bad --since {text!r} — use 3h, 1d, 2w, a date "
                             f"(2026-10-20), an ISO time, or last")
    if when > now + datetime.timedelta(minutes=1):
        raise ValueError(f"--since {text!r} is in the future")
    return _utc(when)


def _git(root: Path, *args: str, stdin: bytes | None = None) -> bytes | None:
    try:
        out = subprocess.run(["git", "-C", str(root), *args], input=stdin,
                             capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def _git_text(root: Path, *args: str) -> str | None:
    out = _git(root, *args)
    return None if out is None else out.decode("utf-8", "replace")


# ---- per-user stamp (`--since last`) ----------------------------------------

def stamp_path(root: Path) -> Path | None:
    """`<git common dir>/roadmap-digest.json`, or None outside git."""
    common = (_git_text(root, "rev-parse", "--git-common-dir") or "").strip()
    if not common:
        return None
    d = Path(common)
    return (d if d.is_absolute() else Path(root) / d) / STAMP_FILE


def _stamp_key(root: Path, owner: str | None) -> str:
    prefix = (_git_text(root, "rev-parse", "--show-prefix") or "").strip()
    return f"{prefix}::{owner or ''}"


def _read_stamps(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def read_stamp(root: Path, key: str = "digest",
               owner: str | None = None) -> datetime.datetime | None:
    """When this owner last ran digest (or orient, key="orient") here."""
    path = stamp_path(root)
    if path is None:
        return None
    entry = _read_stamps(path).get(_stamp_key(root, owner))
    return _parse_iso(entry.get(key)) if isinstance(entry, dict) else None


def write_stamp(root: Path, key: str = "digest", owner: str | None = None,
                when: datetime.datetime | None = None) -> Path | None:
    """Record `when` (default now) for this owner. Never raises; None when
    there is no git dir to hold it (nothing is ever written in the tree)."""
    try:
        path = stamp_path(root)
        if path is None:
            return None
        data = _read_stamps(path)
        entry = data.get(_stamp_key(root, owner))
        entry = entry if isinstance(entry, dict) else {}
        entry[key] = iso(when or rmowners.now())
        data[_stamp_key(root, owner)] = entry
        atomic_write(path, json.dumps(data, indent=2, sort_keys=True) + "\n")
        return path
    except OSError:
        return None


def resolve_since(root: Path, text: str, key: str = "digest",
                  owner: str | None = None,
                  now: datetime.datetime | None = None) -> tuple[datetime.datetime, str]:
    """(since, label). `last` reads the stamp, falling back to DEFAULT_SINCE
    (label says so) when this owner has none yet."""
    if str(text).strip().lower() == "last":
        when = read_stamp(root, key, owner)
        if when is not None:
            return _utc(when), "last run"
        return parse_since(DEFAULT_SINCE, now), f"{DEFAULT_SINCE} (no previous run)"
    return parse_since(text, now), str(text).strip()


# ---- baseline snapshot ------------------------------------------------------

def baseline_commit(root: Path, since: datetime.datetime) -> tuple[str, str] | None:
    """(sha, committer date) of the newest first-parent commit at or before
    `since`, or None when HEAD has none that old."""
    out = _git_text(root, "rev-list", "-1", "--first-parent", "--format=%H %cI",
                    f"--before={iso(since)}", "HEAD")
    for line in (out or "").splitlines():
        parts = line.split()
        if len(parts) == 2 and not line.startswith("commit "):
            return parts[0], parts[1]
    return None


def _cat_files(root: Path, sha: str, paths: list[str]) -> dict[str, str]:
    """{path: text} for each repo-relative path present at `sha` — one call."""
    if not paths:
        return {}
    raw = _git(root, "cat-file", "--batch",
               stdin="".join(f"{sha}:{p}\n" for p in paths).encode("utf-8"))
    out: dict[str, str] = {}
    pos = 0
    for p in paths:
        if raw is None:
            break
        nl = raw.find(b"\n", pos)
        if nl < 0:
            break
        head = raw[pos:nl].decode("utf-8", "replace").split()
        pos = nl + 1
        if len(head) != 3 or head[1] == "missing":
            continue
        size = int(head[2])
        if head[1] == "blob":
            out[p] = raw[pos:pos + size].decode("utf-8", "replace")
        pos += size + 1                       # content + trailing newline
    return out


def _plan_text(text: str) -> tuple[dict, list[tuple[bool, str]]]:
    """(frontmatter, steps) of a plan's text — parse_plan's rules, no file."""
    meta: dict[str, str] = {}
    m = FRONTMATTER_RE.match(text)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
    steps, in_fence = [], False
    for line in text.splitlines():
        if _is_fence(line):
            in_fence = not in_fence
            continue
        sm = None if in_fence else STEP_RE.match(line)
        if sm:
            steps.append((sm.group(2).lower() == "x", sm.group(3).strip()))
    return meta, steps


def _bullets(text: str) -> list[str]:
    """Idea Incubator bullet bodies in `text` (list_incubator_bullets' rules)."""
    m = INCUBATOR_RE.search(text or "")
    if not m:
        return []
    out = []
    for line in text[m.end():].splitlines():
        if re.match(r"^#{1,6}\s+", line):
            break
        bm = INCUBATOR_BULLET_RE.match(line)
        if bm and bm.group(2).strip() != IDEA_PLACEHOLDER:
            out.append(bm.group(2).strip())
    return out


def baseline(root: Path, sha: str) -> dict:
    """{items: {id: {title, version, type, steps, stage, verdict}}, ideas}
    as of commit `sha` (empty when .roadmap/ did not exist yet)."""
    root = Path(root)
    prefix = (_git_text(root, "rev-parse", "--show-prefix") or "").strip()
    rm = f"{prefix}.roadmap/"
    cfg_text = _cat_files(root, sha, [rm + "config.json"]).get(rm + "config.json")
    try:
        cfg = json.loads(cfg_text) if cfg_text else {}
    except ValueError:
        cfg = {}
    items = [i for i in cfg.get("items") or [] if isinstance(i, dict) and "id" in i]
    inc = incubator_file(root)
    try:
        inc_rel = prefix + inc.relative_to(root).as_posix()
    except ValueError:
        inc_rel = None
    paths = [rm + i["file"] for i in items if i.get("file")]
    texts = _cat_files(root, sha, paths + ([inc_rel] if inc_rel else []))
    snap: dict[int, dict] = {}
    for i in items:
        meta, steps = _plan_text(texts.get(rm + (i.get("file") or ""), ""))
        snap[i["id"]] = {"title": i.get("title"), "version": i.get("version"),
                         "type": i.get("type"), "steps": steps,
                         "stage": meta.get("claim_stage") or None,
                         "verdict": meta.get("claim_verdict") or None}
    return {"items": snap, "ideas": _bullets(texts.get(inc_rel or "", ""))}


# ---- needs attention ----------------------------------------------------------
# One entry per check: fn(ctx) -> [{kind, id?, displayId?, text}]. ctx carries
# root, cfg and the status payload `st`. A check whose feature is absent from the
# payload (no slots configured, no wipLimit, no run log, ...) returns nothing.

def _ref(it: dict) -> str:
    return f"{it.get('displayId') or '#' + str(it['id'])} {it.get('title') or ''}".rstrip()


def _open_items(st: dict) -> list[dict]:
    return [i for i in st.get("items") or [] if i.get("lane") != "done"]


def _att_waiting(ctx: dict) -> list[dict]:
    """Waiting steps due today or overdue (plan 46's `waitingDue`)."""
    out = []
    for d in ctx["st"].get("waitingDue") or []:
        left = d.get("daysLeft")
        when = ("due today" if not left else f"{-left}d overdue") \
            if isinstance(left, int) else "due"
        out.append({"kind": "waiting", "id": d.get("id"), "displayId": d.get("displayId"),
                    "text": f"{_ref(d)} — step {d.get('step')} waiting, {when}"
                            + (f" ({d['reason']})" if d.get("reason") else "")})
    return out


def _att_refuted(ctx: dict) -> list[dict]:
    return [{"kind": "refuted", "id": i["id"], "displayId": i.get("displayId"),
             "text": f"{_ref(i)} — verdict REFUTED"
                     + (f" ({i['claim']['stage']})" if i["claim"].get("stage") else "")}
            for i in _open_items(ctx["st"])
            if (i.get("claim") or {}).get("verdict") == "REFUTED"]


def _att_blocked(ctx: dict) -> list[dict]:
    return [{"kind": "blocked", "id": i["id"], "displayId": i.get("displayId"),
             "text": f"{_ref(i)} — claim blocked"
                     + (f": {i['claim']['note']}" if i["claim"].get("note") else "")}
            for i in _open_items(ctx["st"])
            if (i.get("claim") or {}).get("stage") == "blocked"]


def _att_trunk(ctx: dict) -> list[dict]:
    health = ctx["st"].get("trunkHealth") or {}
    if health.get("green") is not False:
        return []
    bad = [s["shard"] for s in health.get("shards") or [] if s.get("result") == "fail"]
    return [{"kind": "trunk", "text": "trunk suite failing"
             + (f": {', '.join(bad)}" if bad else "")}]


def _att_wip(ctx: dict) -> list[dict]:
    msg = rmowners.wip_warning(ctx["st"].get("wip"))
    return [{"kind": "wip", "text": msg}] if msg else []


def _att_slots(ctx: dict) -> list[dict]:
    return [{"kind": "slots", "id": r.get("plan"), "displayId": r.get("displayId"),
             "text": f"slot {r['state']}: {r.get('value')} "
                     f"({r.get('displayId') or '#' + str(r.get('plan'))}, {r['kind']})"
                     + (f" — {r['detail']}" if r.get("detail") else "")}
            for r in rmslots.check_failures(ctx["st"].get("slots"))]


def _att_conflicts(ctx: dict) -> list[dict]:
    """High-risk branch pairs — only when the payload carries conflicts
    (`digest --conflicts`, or the dashboard's already-computed report)."""
    tag = lambda w: w.get("displayId") or "#" + str(w.get("id"))
    return [{"kind": "conflict", "id": p["a"].get("id"), "displayId": p["a"].get("displayId"),
             "text": f"high conflict risk: {tag(p['a'])} <-> {tag(p['b'])}"
                     + (f" ({', '.join(p.get('conflictFiles') or p.get('files') or [])})"
                        if p.get("conflictFiles") or p.get("files") else "")}
            for p in (ctx["st"].get("conflicts") or {}).get("pairs") or []
            if p.get("risk") == "high"]


def _att_stubs(ctx: dict) -> list[dict]:
    """In-flight or started items whose required sections are still template
    text — `check` would refuse them."""
    out = []
    for i in _open_items(ctx["st"]):
        if i.get("lane") == "planned" and not i.get("done"):
            continue
        path = roadmap_dir(Path(ctx["root"])) / i["file"]
        try:
            stubs = template_stubs(path, *required_sections(ctx["cfg"], i.get("type", "")))
        except OSError:
            continue
        if stubs:
            out.append({"kind": "stubs", "id": i["id"], "displayId": i.get("displayId"),
                        "text": f"{_ref(i)} — template text in {', '.join(stubs)}"})
    return out


ATTENTION = (_att_waiting, _att_refuted, _att_blocked, _att_trunk, _att_wip,
             _att_slots, _att_conflicts, _att_stubs)


def attention(root: Path, st: dict, cfg: dict | None = None) -> list[dict]:
    """Everything that needs a human now, in ATTENTION order. Never raises:
    a failing check is skipped."""
    ctx = {"root": root, "st": st, "cfg": cfg if cfg is not None else read_config(root)}
    out = []
    for check in ATTENTION:
        try:
            out.extend(check(ctx))
        except Exception:  # noqa: BLE001 — one broken check must not hide the rest
            continue
    return out


# ---- collect ---------------------------------------------------------------

def _newly_ticked(then: list[tuple[bool, str]], now: list[tuple[bool, str]]) -> list[str]:
    """Texts of steps ticked now that were not ticked at the baseline
    (matched by text, so inserted or reordered steps do not count)."""
    was = Counter(t for d, t in then if d)
    out = []
    for done, text in now:
        if not done:
            continue
        if was[text]:
            was[text] -= 1
        else:
            out.append(text)
    return out


def _stale_days(cfg: dict) -> int:
    try:
        return int((cfg.get("settings") or {}).get("staleDays", rmbranches.DEFAULT_STALE_DAYS))
    except (TypeError, ValueError):
        return rmbranches.DEFAULT_STALE_DAYS


def _new_branches(root: Path, cfg: dict, st: dict, since: datetime.datetime) -> list[dict]:
    """Unmerged branches whose first own commit falls in the window."""
    try:
        found = rmbranches.discover(root, [i["id"] for i in cfg["items"]])
    except Exception:  # noqa: BLE001
        return []
    by_id = {i["id"]: i for i in st.get("items") or []}
    out = []
    for b in [*found["items"].values(), *found["other"]]:
        commits = b.get("commits") or []
        if b.get("merged") or not b.get("ahead") or b["ahead"] > len(commits):
            continue
        first = _parse_iso(commits[-1].get("date"))
        if first is None or first < since:
            continue
        it = by_id.get(b.get("item"))
        out.append({"name": b["name"], "id": b.get("item"),
                    "displayId": it.get("displayId") if it else None,
                    "title": it.get("title") if it else None,
                    "ahead": b["ahead"], "firstCommit": iso(first)})
    return sorted(out, key=lambda b: b["firstCommit"])


def collect(root: Path, since: datetime.datetime, *, now: datetime.datetime | None = None,
            st: dict | None = None, conflicts: bool = False) -> dict:
    """The digest for [since, now]. `st` reuses a status payload in hand;
    `conflicts` asks status for branch conflict risk (costly on a cold cache)."""
    root = Path(root)
    now = _utc(now or rmowners.now())
    since = _utc(since)
    cfg = read_config(root)
    if st is None:
        st = status(root, conflicts=conflicts)
    head = _git_text(root, "rev-parse", "--verify", "-q", "HEAD")
    base = baseline_commit(root, since) if head else None
    snap = baseline(root, base[0]) if base else {"items": {}, "ideas": []}
    history = bool(head)
    out = {"project": st.get("project"), "since": iso(since), "until": iso(now),
           "git": history,
           "baseline": ({"sha": base[0][:7], "date": base[1]} if base else None)}
    completed, ticked, claims, stalled, new_plans = [], [], [], [], []
    stale_days = _stale_days(cfg)
    for it in st.get("items") or []:
        ref = {"id": it["id"], "displayId": it.get("displayId") or display_id(it),
               "title": it.get("title")}
        was = snap["items"].get(it["id"])
        claim = it.get("claim") or {}
        stage, verdict = claim.get("stage"), claim.get("verdict")
        if history:
            if was is None:
                new_plans.append({**ref, "type": it.get("type"), "version": it.get("version")})
            then_steps = was["steps"] if was else []
            then_done = bool(then_steps) and all(d for d, _ in then_steps)
            if it.get("lane") == "done" and not then_done:
                completed.append({**ref, "version": it.get("version")})
            path = roadmap_dir(root) / it["file"]
            now_steps = parse_plan(path)["steps"] if path.exists() else []
            new = _newly_ticked(then_steps, now_steps)
            if new:
                ticked.append({**ref, "count": len(new), "steps": new,
                               "done": it.get("done"), "total": it.get("total")})
            if it.get("lane") != "done":
                before = ((was or {}).get("stage"), (was or {}).get("verdict"))
                became_blocked = stage == "blocked" and before[0] != "blocked"
                if became_blocked:
                    stalled.append({**ref, "reason": "blocked",
                                    "detail": claim.get("note") or ""})
                if (stage, verdict) != before and not (became_blocked
                                                        and verdict == before[1]):
                    claims.append({**ref, "from": {"stage": before[0], "verdict": before[1]},
                                   "to": {"stage": stage, "verdict": verdict}})
        branch = it.get("branch") or {}
        last = _parse_iso(branch.get("lastDate"))
        if it.get("lane") == "stale" and last is not None and \
                since <= last + datetime.timedelta(days=stale_days) <= now:
            stalled.append({**ref, "reason": "stale",
                            "detail": f"{branch.get('name')}, last commit "
                                      f"{(now - last).days}d ago"})
    runs = []
    try:
        for r in rmruns.read_runs(root)[0]:
            at = _parse_iso(r.get("at"))
            if at is not None and since <= at <= now + datetime.timedelta(minutes=1):
                runs.append(r)
    except Exception:  # noqa: BLE001 — a broken run log never breaks the digest
        runs = []
    ideas = []
    if history:
        was_ideas = Counter(snap["ideas"])
        for b in list_incubator_bullets(root):
            body = b["body"]
            if body == IDEA_PLACEHOLDER:
                continue
            if was_ideas[body]:
                was_ideas[body] -= 1
            else:
                ideas.append({"title": bullet_title(body), "body": body})
    out.update({"completed": completed, "ticked": ticked, "claims": claims,
                "stalled": stalled, "newPlans": new_plans,
                "newBranches": _new_branches(root, cfg, st, since) if history else [],
                "runs": runs, "ideas": ideas,
                "attention": attention(root, st, cfg)})
    out["counts"] = {k: len(out[k]) for k, _ in SECTIONS}
    out["counts"]["stepsTicked"] = sum(t["count"] for t in ticked)
    return out
