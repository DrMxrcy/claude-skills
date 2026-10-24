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
import hashlib
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


def _entry(root: Path, owner: str | None) -> dict:
    path = stamp_path(root)
    entry = _read_stamps(path).get(_stamp_key(root, owner)) if path else None
    return entry if isinstance(entry, dict) else {}


def read_stamp(root: Path, key: str = "digest",
               owner: str | None = None) -> datetime.datetime | None:
    """When this owner last ran digest (or orient, key="orient") here."""
    return _parse_iso(_entry(root, owner).get(key))


def read_snapshot(root: Path, key: str = "digest",
                  owner: str | None = None) -> dict | None:
    """The state seen at that run (snapshot_now's shape, int ids), or None."""
    snap = _entry(root, owner).get(key + "Snapshot")
    if not isinstance(snap, dict) or not isinstance(snap.get("items"), dict):
        return None
    try:
        items = {int(k): v for k, v in snap["items"].items()}
    except (TypeError, ValueError):
        return None
    if not all(isinstance(v, dict) and isinstance(v.get("done"), list)
               for v in items.values()):
        return None                       # unknown shape: use the git baseline
    return {"items": items, "ideas": list(snap.get("ideas") or [])}


def write_stamp(root: Path, key: str = "digest", owner: str | None = None,
                when: datetime.datetime | None = None,
                snapshot: dict | None = None) -> Path | None:
    """Record `when` (default now) for this owner, and the state seen then
    (`snapshot`), so the next `last` diffs against exactly what this run saw —
    uncommitted changes included. Never raises; None when there is no git dir
    to hold it (nothing is ever written in the tree)."""
    try:
        path = stamp_path(root)
        if path is None:
            return None
        data = _read_stamps(path)
        entry = data.get(_stamp_key(root, owner))
        entry = entry if isinstance(entry, dict) else {}
        entry[key] = iso(when or rmowners.now())
        if snapshot is not None:
            entry[key + "Snapshot"] = snapshot
        else:
            entry.pop(key + "Snapshot", None)
        data[_stamp_key(root, owner)] = entry
        atomic_write(path, json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")
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


def _step_key(text: str) -> str:
    """A short stable key for a step's text (snapshots stay small)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def _item_state(steps, stage: str | None, verdict: str | None) -> dict:
    """What a snapshot keeps per item: claim stage/verdict, whether every step
    was ticked, and the keys of the ticked steps."""
    return {"stage": stage, "verdict": verdict,
            "allDone": bool(steps) and all(d for d, _ in steps),
            "done": [_step_key(t) for d, t in steps if d]}


def baseline(root: Path, sha: str) -> dict:
    """{items: {id: _item_state}, ideas: [bullet bodies]}
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
        snap[i["id"]] = _item_state(steps, meta.get("claim_stage") or None,
                                    meta.get("claim_verdict") or None)
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
    more = f" +{len(bad) - 4} more" if len(bad) > 4 else ""
    return [{"kind": "trunk", "text": "trunk suite failing"
             + (f": {', '.join(bad[:4])}{more}" if bad else "")}]


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

def _newly_ticked(then_done: list[str], now: list[tuple[bool, str]]) -> list[str]:
    """Texts of steps ticked now that were not ticked at the baseline
    (`then_done`: step keys; matched by text, so inserted or reordered steps
    do not count)."""
    was = Counter(then_done)
    out = []
    for done, text in now:
        if not done:
            continue
        key = _step_key(text)
        if was[key]:
            was[key] -= 1
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
            st: dict | None = None, conflicts: bool = False,
            base_snapshot: dict | None = None) -> dict:
    """The digest for [since, now]. `st` reuses a status payload in hand;
    `conflicts` asks status for branch conflict risk (costly on a cold cache).
    `base_snapshot` (the state a previous run saw) replaces the git baseline.
    The result carries `_snapshot`, the state seen now, for the caller to stamp."""
    root = Path(root)
    now = _utc(now or rmowners.now())
    since = _utc(since)
    cfg = read_config(root)
    if st is None:
        st = status(root, conflicts=conflicts)
    head = _git_text(root, "rev-parse", "--verify", "-q", "HEAD")
    history = bool(head)
    if base_snapshot is not None and history:
        snap, base_info = base_snapshot, {"sha": None, "date": iso(since)}
    else:
        base = baseline_commit(root, since) if head else None
        snap = baseline(root, base[0]) if base else {"items": {}, "ideas": []}
        base_info = {"sha": base[0][:7], "date": base[1]} if base else None
    out = {"project": st.get("project"), "since": iso(since), "until": iso(now),
           "git": history, "baseline": base_info}
    seen: dict[int, dict] = {}
    completed, ticked, claims, stalled, new_plans = [], [], [], [], []
    stale_days = _stale_days(cfg)
    for it in st.get("items") or []:
        ref = {"id": it["id"], "displayId": it.get("displayId") or display_id(it),
               "title": it.get("title")}
        claim = it.get("claim") or {}
        stage, verdict = claim.get("stage"), claim.get("verdict")
        path = roadmap_dir(root) / it["file"]
        now_steps = parse_plan(path)["steps"] if path.exists() else []
        seen[it["id"]] = _item_state(now_steps, stage, verdict)
        branch = it.get("branch") or {}
        last = _parse_iso(branch.get("lastDate"))
        if it.get("lane") == "stale" and last is not None and \
                since <= last + datetime.timedelta(days=stale_days) <= now:
            stalled.append({**ref, "reason": "stale",
                            "detail": f"{branch.get('name')}, last commit "
                                      f"{(now - last).days}d ago"})
        if not history:
            continue
        was = snap["items"].get(it["id"])
        if was is None:
            new_plans.append({**ref, "type": it.get("type"), "version": it.get("version")})
        if it.get("lane") == "done" and not (was or {}).get("allDone"):
            completed.append({**ref, "version": it.get("version")})
        new = _newly_ticked((was or {}).get("done") or [], now_steps)
        if new:
            ticked.append({**ref, "count": len(new), "steps": new,
                           "done": it.get("done"), "total": it.get("total")})
        if it.get("lane") == "done":
            continue                       # a done item's claim ends with it
        before = ((was or {}).get("stage"), (was or {}).get("verdict"))
        became_blocked = stage == "blocked" and before[0] != "blocked"
        if became_blocked:
            stalled.append({**ref, "reason": "blocked", "detail": claim.get("note") or ""})
        if (stage, verdict) != before and not (became_blocked and verdict == before[1]):
            claims.append({**ref, "from": {"stage": before[0], "verdict": before[1]},
                           "to": {"stage": stage, "verdict": verdict}})
    runs = []
    try:
        for r in rmruns.read_runs(root)[0]:
            at = _parse_iso(r.get("at"))
            if at is not None and since <= at <= now + datetime.timedelta(minutes=1):
                runs.append(r)
    except Exception:  # noqa: BLE001 — a broken run log never breaks the digest
        runs = []
    now_ideas = [b["body"] for b in list_incubator_bullets(root)
                 if b["body"] != IDEA_PLACEHOLDER]
    ideas = []
    if history:
        was_ideas = Counter(snap["ideas"])
        for body in now_ideas:
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
    out["_snapshot"] = {"items": seen, "ideas": now_ideas}
    return out


# ---- output ------------------------------------------------------------------

def _when(iso_text: str) -> str:
    return iso_text.replace("T", " ")[:16] + "Z" if iso_text else "?"


def _stage(s: str | None, empty: str) -> str:
    return s or empty


def _row(key: str, r: dict) -> str:
    ref = _ref(r) if r.get("id") is not None else ""
    if key == "completed":
        return f"{ref} (v{r['version']})" if r.get("version") else ref
    if key == "ticked":
        n = r["count"]
        return f"{ref} — +{n} step{'s' if n != 1 else ''} ({r['done']}/{r['total']})"
    if key == "claims":
        f, t = r["from"], r["to"]
        parts = []
        if f["stage"] != t["stage"]:
            parts.append(f"{_stage(f['stage'], 'unclaimed')} → {_stage(t['stage'], 'cleared')}")
        if f["verdict"] != t["verdict"]:
            parts.append(f"verdict {_stage(f['verdict'], '—')} → {_stage(t['verdict'], '—')}")
        return f"{ref} — {' · '.join(parts)}"
    if key == "stalled":
        return f"{ref} — {r['reason']}" + (f" ({r['detail']})" if r.get("detail") else "")
    if key == "newPlans":
        return f"{ref} [{r['type']}] → v{r['version']}"
    if key == "newBranches":
        who = f" ({_ref(r)})" if r.get("id") is not None else ""
        return f"{r['name']}{who} · +{r['ahead']} since {_when(r['firstCommit'])}"
    if key == "runs":
        return rmruns.format_run(r).strip().splitlines()[0]
    if key == "ideas":
        return r["title"]
    return r.get("text", "")


def _runs_tally(runs: list[dict]) -> str:
    c = Counter((r["kind"], r["result"]) for r in runs)
    return ", ".join(f"{n} {k} {res}" for (k, res), n in sorted(c.items()))


def format_digest(d: dict, md: bool = False) -> str:
    """Terminal text, or Markdown for pasting into chat (`md`)."""
    head = (f"Digest: {d.get('project')} — since {_when(d['since'])}"
            + (f" ({d['label']})" if d.get("label") else "")
            + (f" · baseline {d['baseline']['sha']}"
               if (d.get("baseline") or {}).get("sha") else ""))
    lines = [("## " if md else "") + head]
    if not d.get("git"):
        lines.append(("_" if md else "") + "not a git repo — only runs and attention "
                     "can be reported" + ("_" if md else ""))
    shown = 0
    for key, title in SECTIONS:
        rows = d.get(key) or []
        if not rows:
            continue
        shown += 1
        extra = f": {_runs_tally(rows)}" if key == "runs" else ""
        if md:
            lines += ["", f"### {title} ({len(rows)}){extra}"]
            lines += [f"- {_row(key, r)}" for r in rows]
        else:
            lines.append(f"{title} ({len(rows)}){extra}")
            mark = "⚠ " if key == "attention" else ""
            lines += [f"  {mark}{_row(key, r)}" for r in rows]
    if not shown:
        lines += ([""] if md else []) + ["Nothing changed in the window."]
    return "\n".join(lines)


def sections(d: dict) -> list[dict]:
    """Non-empty sections as display rows — [{key, title, rows: [{id,
    displayId, text}]}] — the dashboard digest page renders these as-is."""
    out = []
    for key, title in SECTIONS:
        rows = d.get(key) or []
        if rows:
            out.append({"key": key, "title": title + (f": {_runs_tally(rows)}"
                                                       if key == "runs" else ""),
                        "rows": [{"id": r.get("id") if key != "runs" else None,
                                  "displayId": r.get("displayId"),
                                  "text": _row(key, r)} for r in rows]})
    return out


def summary_line(d: dict) -> str:
    """`1 completed · 4 steps ticked · 2 claims moved ...` (empty: no changes)."""
    c = d.get("counts") or {}
    plural = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    parts = [f"{c['completed']} completed" if c.get("completed") else "",
             plural(c["stepsTicked"], "step") + " ticked" if c.get("stepsTicked") else "",
             plural(c["claims"], "claim") + " moved" if c.get("claims") else "",
             f"{c['stalled']} stale/blocked" if c.get("stalled") else "",
             plural(c["newPlans"], "new plan") if c.get("newPlans") else "",
             plural(c["newBranches"], "new branch").replace("branchs", "branches")
             if c.get("newBranches") else "",
             plural(c["runs"], "run") if c.get("runs") else "",
             plural(c["ideas"], "idea") + " added" if c.get("ideas") else ""]
    return " · ".join(p for p in parts if p)


def digest(root: Path, since: str = "last", *, conflicts: bool = False,
           owner: str | None = None, now: datetime.datetime | None = None,
           record: bool = False) -> dict:
    """Resolve `since` (incl. `last`), collect, and — when `record` — stamp the
    window's end as this owner's last digest run (the CLI records; the
    dashboard and tests do not)."""
    return _run(root, since, "digest", owner, now, record, conflicts=conflicts)


def _run(root: Path, since: str, key: str, owner: str | None,
         now: datetime.datetime | None, record: bool, conflicts: bool = False) -> dict:
    when, label = resolve_since(root, since, key, owner, now)
    last = str(since).strip().lower() == "last" and label == "last run"
    d = collect(root, when, now=now, conflicts=conflicts,
                base_snapshot=read_snapshot(root, key, owner) if last else None)
    snap = d.pop("_snapshot")
    d["label"] = label
    if record:
        write_stamp(root, key, owner, _parse_iso(d["until"]), snapshot=snap)
    return d


# ---- orient (3 lines since the last session) -----------------------------------

ORIENT_ATTENTION = 2          # attention items named on orient's line


def orient_digest(root: Path, owner: str | None = None,
                  now: datetime.datetime | None = None, record: bool = True) -> dict | None:
    """Compact digest since this owner's previous orient (DEFAULT_SINCE the
    first time), then — when `record` — restamp. None outside git or on any
    trouble: orient runs from a SessionStart hook and must never fail."""
    try:
        if stamp_path(root) is None:
            return None
        d = _run(root, "last", "orient", owner, now, record)
    except Exception:  # noqa: BLE001
        return None
    return {"since": d["since"], "until": d["until"],
            "label": "last session" if d["label"] == "last run" else d["label"],
            "summary": summary_line(d), "counts": d["counts"],
            "attention": [a["text"] for a in d["attention"]]}


def orient_lines(o: dict | None) -> list[str]:
    """At most three lines: what changed, what needs attention, the command."""
    if not o:
        return []
    since = o["since"]
    try:
        secs = int((_parse_iso(o["until"]) - _parse_iso(since)).total_seconds())
    except TypeError:
        secs = 0
    ago = next((f"{secs // n}{u}" for u, n in (("w", 604800), ("d", 86400),
                                               ("h", 3600), ("m", 60)) if secs >= n), "now")
    head = f"Since {o['label']} ({ago} ago)" if o["label"] == "last session" \
        else f"Since {o['label']}"
    att = o.get("attention") or []
    if not o.get("summary") and not att:
        return [f"{head}: no roadmap changes"]
    lines = [f"{head}: {o.get('summary') or 'no roadmap changes'}"]
    if att:
        more = len(att) - ORIENT_ATTENTION
        lines.append(f"⚠ Needs attention ({len(att)}): " + " · ".join(att[:ORIENT_ATTENTION])
                     + (f" · +{more} more" if more > 0 else ""))
    lines.append(f"Details: roadmap.py digest --since {since}")
    return lines
