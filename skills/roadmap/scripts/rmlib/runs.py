"""roadmap run log (plan 38) — merge-gate and suite runs recorded as roadmap state.

Gate and suite runs happen in scratch folders nobody else can see. `run`
appends one self-contained JSON object per line to `.roadmap/runs.jsonl`
(committed, append-only, trimmed to the newest `settings.runsKeep`, default
200). Appends take an exclusive lock, so concurrent sessions on the clone never
interleave a line; a merge of two branches that both appended resolves by union
(`.roadmap/runs.jsonl merge=union` in .gitattributes, added by init/upgrade).

Readers never trust the file: an unparseable or malformed line is skipped with
a warning, never an error.

Layer: rmcore (+ the slots lock). Read-only git for the trunk-health `ahead`
count; the only write is runs.jsonl.
"""
from __future__ import annotations
import datetime
import fnmatch
import json
import re
import subprocess
from pathlib import Path
from rmlib.core import atomic_write, roadmap_dir

RUNS_FILE = "runs.jsonl"
DEFAULT_KEEP = 200
STATUS_RUNS = 50                       # runs carried in the status payload
KINDS = ("gate", "suite")
RESULTS = ("pass", "fail")
GITATTR_LINE = ".roadmap/runs.jsonl merge=union"
_DUR_RE = re.compile(r"^\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s?)?\s*$", re.I)
_URL_RE = re.compile(r"^https?://\S+$", re.I)
_SHARD_RE = re.compile(r"^[A-Za-z0-9][\w.:/-]*$")


def runs_path(root: Path) -> Path:
    return roadmap_dir(root) / RUNS_FILE


def runs_keep(cfg: dict | None) -> int:
    """settings.runsKeep as a positive int; anything else is the default."""
    v = ((cfg or {}).get("settings") or {}).get("runsKeep", DEFAULT_KEEP)
    try:
        v = int(v)
    except (TypeError, ValueError):
        return DEFAULT_KEEP
    return v if v > 0 else DEFAULT_KEEP


# ---- parsing CLI values ---------------------------------------------------

def parse_duration(text: str | None) -> int | None:
    """`12m`, `1h30m`, `2m30s`, `90s`, `90` (seconds) -> seconds."""
    if text is None or not str(text).strip():
        return None
    m = _DUR_RE.match(str(text))
    if not m or not any(m.groups()):
        raise ValueError(f"bad --duration {text!r} — use e.g. 90s, 12m, 1h30m")
    h, mi, s = (int(g or 0) for g in m.groups())
    return h * 3600 + mi * 60 + s


def format_duration(sec: int | None) -> str:
    if sec is None:
        return ""
    h, rest = divmod(int(sec), 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h}h{m:02d}m" if m else f"{h}h"
    if m:
        return f"{m}m{s:02d}s" if s else f"{m}m"
    return f"{s}s"


def split_list(text: str | None) -> list[str]:
    """Split on commas and newlines, but not on a comma inside brackets or
    parentheses (pytest ids like `test_x[a,b]` stay whole). Blanks dropped."""
    out, cur, depth = [], [], 0
    for ch in str(text or ""):
        if ch in "[(":
            depth += 1
        elif ch in "])" and depth:
            depth -= 1
        if (ch == "," and not depth) or ch == "\n":
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return [s.strip() for s in out if s.strip()]


def parse_shards(text: str | None) -> dict[str, str]:
    """`unit=pass,e2e=fail` -> {"unit": "pass", "e2e": "fail"} (order kept)."""
    shards: dict[str, str] = {}
    for part in split_list(text):
        name, sep, res = part.partition("=")
        name, res = name.strip(), res.strip().lower()
        if not sep or not _SHARD_RE.match(name) or res not in RESULTS:
            raise ValueError(f"bad --shards entry {part!r} — use name=pass|fail")
        shards[name] = res
    return shards


def make_record(kind: str, label: str, result: str, *, items=(), branches=(),
                duration: int | None = None, log: str | None = None,
                failing=(), shards: dict | None = None,
                now: datetime.datetime | None = None) -> dict:
    """Validate and build one run record. `at` is when it was recorded (the
    run's end); `startedAt` is `at` minus the duration when one is given."""
    if kind not in KINDS:
        raise ValueError(f"bad --kind {kind!r} — use {'|'.join(KINDS)}")
    if result not in RESULTS:
        raise ValueError(f"bad --result {result!r} — use {'|'.join(RESULTS)}")
    label = " ".join(str(label or "").split())
    if not label:
        raise ValueError("--label must not be empty")
    if log is not None and log.strip() and not _URL_RE.match(log.strip()):
        raise ValueError(f"bad --log {log!r} — only an http(s) URL is recorded")
    if duration is not None and duration < 0:
        raise ValueError("--duration must not be negative")
    now = (now or datetime.datetime.now(datetime.timezone.utc)).replace(microsecond=0)
    start = now - datetime.timedelta(seconds=duration) if duration else now
    iso = lambda d: d.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"at": iso(now), "startedAt": iso(start), "kind": kind, "label": label,
            "result": result, "items": [int(i) for i in items],
            "branches": [str(b) for b in branches if str(b).strip()],
            "durationSec": duration, "log": (log or "").strip() or None,
            "failing": [str(f) for f in failing], "shards": dict(shards or {})}


# ---- write ----------------------------------------------------------------

def _lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip()]


def append_run(root: Path, record: dict, keep: int = DEFAULT_KEEP) -> dict:
    """Append one record (one line) under the exclusive lock, then trim the
    file to the newest `keep` lines. Returns the record."""
    from rmlib.slots import _locked    # the clone-wide lock (plan 33), own lock file
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    path = runs_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _locked(root, name="roadmap-runs"):
        # A file whose last line lacks its newline (hand edit, union merge)
        # must not glue the new record onto it.
        lead = ""
        if path.exists() and path.stat().st_size:
            with open(path, "rb") as f:
                f.seek(-1, 2)
                lead = "" if f.read(1) == b"\n" else "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(lead + line + "\n")
        lines = _lines(path.read_text(encoding="utf-8"))
        if len(lines) > keep:
            atomic_write(path, "\n".join(lines[-keep:]) + "\n")
    return record


# ---- read -----------------------------------------------------------------

def _valid(rec) -> bool:
    return (isinstance(rec, dict) and rec.get("kind") in KINDS
            and rec.get("result") in RESULTS and isinstance(rec.get("at"), str)
            and isinstance(rec.get("label"), str))


def _clean(rec: dict) -> dict:
    """Normalise a parsed record so readers can rely on every field's type."""
    lst = lambda v: [x for x in v if isinstance(x, (str, int))] if isinstance(v, list) else []
    shards = rec.get("shards") if isinstance(rec.get("shards"), dict) else {}
    log = rec.get("log")
    dur = rec.get("durationSec")
    return {"at": rec["at"], "startedAt": rec.get("startedAt") if isinstance(
                rec.get("startedAt"), str) else rec["at"],
            "kind": rec["kind"], "label": rec["label"], "result": rec["result"],
            "items": [i for i in lst(rec.get("items")) if isinstance(i, int)],
            "branches": [str(b) for b in lst(rec.get("branches"))],
            "durationSec": dur if isinstance(dur, int) and dur >= 0 else None,
            "log": log if isinstance(log, str) and _URL_RE.match(log) else None,
            "failing": [str(f) for f in lst(rec.get("failing"))],
            "shards": {str(k): v for k, v in shards.items() if v in RESULTS}}


def read_runs(root: Path) -> tuple[list[dict], list[str]]:
    """(runs newest first, warnings). Order: `at` descending, file order
    breaking ties (later line = newer) — a union merge interleaves branches'
    lines, so file order alone is not chronological. A missing file is empty."""
    path = runs_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], []
    except (OSError, UnicodeDecodeError) as e:
        return [], [f"{RUNS_FILE}: unreadable ({e})"]
    runs, warnings = [], []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            warnings.append(f"{RUNS_FILE}:{n}: unparseable line skipped")
            continue
        if not _valid(rec):
            warnings.append(f"{RUNS_FILE}:{n}: not a run record — skipped")
            continue
        runs.append((rec["at"], n, _clean(rec)))
    runs.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [r for _, _, r in runs], warnings


# ---- trunk health ---------------------------------------------------------

def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(root), *args],
                             capture_output=True, text=True, timeout=10)
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _integration_names(root: Path, setting, trunk: str) -> list[str]:
    """settings.integrationBranch as a name, a glob, or a list of either ->
    the existing local branches it names, trunk excluded."""
    pats = setting if isinstance(setting, list) else [setting]
    pats = [p.strip() for p in pats if isinstance(p, str) and p.strip()]
    if not pats:
        return []
    out = _git(root, "for-each-ref", "refs/heads", "--format=%(refname:short)")
    local = (out or "").split()
    names = []
    for p in pats:
        for b in (fnmatch.filter(local, p) if any(c in p for c in "*?[") else
                  [p] if p in local else []):
            if b != trunk and b not in names:
                names.append(b)
    return names


def trunk_ahead(root: Path, setting, trunk: str | None) -> list[dict]:
    """[{branch, commits}] — commits each integration branch holds that trunk
    lacks. Empty when integrationBranch is unset or git is unavailable."""
    if not setting or not trunk:
        return []
    out = []
    for name in _integration_names(root, setting, trunk):
        n = _git(root, "rev-list", "--count", f"refs/heads/{trunk}..refs/heads/{name}")
        if n is not None and n.strip().isdigit():
            out.append({"branch": name, "commits": int(n.strip())})
    return out


def _on_trunk(run: dict, trunk: str | None) -> bool:
    """A suite run speaks for trunk unless it names branches other than trunk."""
    return not run["branches"] or (trunk is not None and trunk in run["branches"])


def trunk_health(runs: list[dict], trunk: str | None = None,
                 ahead: list[dict] | None = None) -> dict:
    """Latest trunk suite result per shard (a run without shards is one shard
    named by its label), failing names on the shards that failed, plus how
    far the integration branch(es) are ahead of trunk. `green` is None when
    no suite run has been recorded."""
    shards: dict[str, dict] = {}
    for run in runs:                     # newest first: first sighting wins
        if run["kind"] != "suite" or not _on_trunk(run, trunk):
            continue
        for name, res in (run["shards"] or {run["label"]: run["result"]}).items():
            if name in shards:
                continue
            shards[name] = {"shard": name, "result": res, "at": run["at"],
                            "label": run["label"], "log": run["log"],
                            "failing": run["failing"] if res == "fail" else []}
    rows = sorted(shards.values(), key=lambda s: s["shard"])
    return {"shards": rows,
            "green": all(s["result"] == "pass" for s in rows) if rows else None,
            "ahead": list(ahead or [])}


def runs_status(root: Path, cfg: dict, trunk: str | None) -> dict:
    """The status payload's run-log keys: `runs` (newest STATUS_RUNS),
    `trunkHealth`, and `runWarnings` only when a line was skipped."""
    runs, warnings = read_runs(root)
    setting = (cfg.get("settings") or {}).get("integrationBranch")
    out = {"runs": runs[:STATUS_RUNS],
           "trunkHealth": trunk_health(runs, trunk, trunk_ahead(root, setting, trunk))}
    if warnings:
        out["runWarnings"] = warnings
    return out


# ---- terminal -------------------------------------------------------------

def format_run(run: dict) -> str:
    when = run["at"].replace("T", " ").rstrip("Z")[:16]
    parts = [when, f"{run['kind']:<5}", f"{run['result'].upper():<4}", run["label"]]
    if run["items"]:
        parts.append("#" + ",#".join(str(i) for i in run["items"]))
    if run["branches"]:
        parts.append(",".join(run["branches"]))
    if run["durationSec"] is not None:
        parts.append(format_duration(run["durationSec"]))
    if run["shards"]:
        parts.append(",".join(f"{k}={v}" for k, v in run["shards"].items()))
    line = "  " + " · ".join(parts)
    if run["log"]:
        line += f"\n      log: {run['log']}"
    for f in run["failing"]:
        line += f"\n      failing: {f}"
    return line


def format_runs(runs: list[dict], health: dict | None = None, limit: int = 20) -> str:
    if not runs:
        out = ["no runs recorded — `roadmap.py run --kind gate|suite ...` logs one"]
    else:
        out = [f"runs — newest first ({min(limit, len(runs))} of {len(runs)})"]
        out += [format_run(r) for r in runs[:limit]]
    h = health or {}
    if h.get("shards"):
        out.append("trunk health: " + ("green" if h.get("green") else "RED") + " — "
                   + ", ".join(f"{s['shard']}={s['result']}" for s in h["shards"]))
    for a in h.get("ahead") or []:
        out.append(f"  {a['branch']} is {a['commits']} commit"
                   f"{'s' if a['commits'] != 1 else ''} ahead of trunk")
    return "\n".join(out)
