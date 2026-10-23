"""roadmap numbered slots (plan 33) — reserve the next number in a numbered
sequence (DB migrations, ADR numbers, ports) per plan, and detect clashes.

Parallel branches that each pick "the next migration" double-book it. A
reservation makes the number roadmap state: `slot_<kind>: 0269_name` in the
plan's frontmatter (flat key, like `claim_*`), so it travels with the trunk.

Kinds come from `settings.slots` in config.json:
    {"migration": {"glob": "packages/db/drizzle/*.sql",
                   "pattern": "^(\\d{4})_", "width": 4}}
`glob` selects files (repo-relative to the roadmap root; `*` stays inside one
directory, `**/` spans directories); `pattern` is searched in the file NAME and
its first group is the number. No kinds configured = the feature is dormant.

Numbering (`reserve`) runs under a lock in the git common dir, so concurrent
reservations from any checkout of the clone serialise, and takes
max(trunk files, files added on any unmerged branch, working-tree files,
reservations in this checkout's plans, trunk's plans and every other
worktree's plans) + 1 — no two reservations can receive the same number.

Layer: rmcore + rmparse + rmbranches. Read-only git (never raises on git
trouble); the only write is the plan file's frontmatter.
"""
from __future__ import annotations
import contextlib
import hashlib
import re
import subprocess
import tempfile
import threading
from pathlib import Path, PurePosixPath
from rmlib.core import atomic_write, read_config, roadmap_dir
from rmlib.parse import (
    FRONTMATTER_RE, SLOT_PREFIX, _plan_path, count_progress, parse_plan)
from rmlib import branches as rmbranches

STATES = ("ok", "missing", "clash", "taken")
FAILING = ("clash", "taken")           # states `slot --check` exits 1 on
KIND_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
TOKEN_RE = re.compile(r"^(\d+)(?:_(\S+))?$")
_WILD = re.compile(r"[*?\[]")
_SEP = "\x1f"
_REC = "\x1e"

# Git facts keyed on immutable shas (trunk tree, branch tip), so a long-lived
# `serve` re-runs ls-tree / log / grep only when a ref actually moved.
_CACHE: dict = {}
_LOCK = threading.Lock()


# ---- config -------------------------------------------------------------

def _glob_re(glob: str) -> re.Pattern:
    """Path glob -> regex over a posix relative path. `*`/`?`/`[..]` stay
    within one path segment; `**/` matches zero or more directories."""
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:[^/]+/)*")
            i += 3
            continue
        if glob.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        c = glob[i]
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[" and glob.find("]", i + 2) != -1:
            j = glob.find("]", i + 2)
            body = glob[i + 1:j]
            if body.startswith("!"):
                body = "^" + body[1:]
            out.append("[" + body.replace("\\", "\\\\") + "]")
            i = j + 1
            continue
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def _literal_prefix(glob: str) -> str:
    """Leading directories without wildcards — the cheap git/filesystem scope
    for the scan ('' = whole tree)."""
    parts = glob.split("/")
    lit = []
    for p in parts[:-1]:
        if _WILD.search(p):
            break
        lit.append(p)
    return "/".join(lit)


def load_kinds(cfg: dict) -> dict[str, dict]:
    """settings.slots -> {kind: spec}; {} when unset. Raises ValueError on a
    malformed entry, naming the kind and the fix."""
    raw = (cfg.get("settings") or {}).get("slots")
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("settings.slots must be an object: "
                         '{"<kind>": {"glob": ..., "pattern": ..., "width": N}}')
    kinds = {}
    for kind, spec in raw.items():
        where = f"settings.slots.{kind}"
        if not KIND_RE.match(str(kind)):
            raise ValueError(f"{where}: kind names are letters, digits, '_' or '-'")
        if not isinstance(spec, dict):
            raise ValueError(f"{where} must be an object with glob and pattern")
        glob, pattern = spec.get("glob"), spec.get("pattern")
        if not isinstance(glob, str) or not glob.strip():
            raise ValueError(f"{where}.glob is required (e.g. db/migrations/*.sql)")
        glob = glob.strip().removeprefix("./")
        if glob.startswith("/") or ".." in glob.split("/"):
            raise ValueError(f"{where}.glob must be relative to the project root")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError(f"{where}.pattern is required (e.g. ^(\\d{{4}})_)")
        try:
            rx = re.compile(pattern)
        except re.error as e:
            raise ValueError(f"{where}.pattern does not compile: {e}") from None
        if rx.groups < 1:
            raise ValueError(f"{where}.pattern needs one (\\d+) group for the number")
        width = spec.get("width")
        if width is not None and (isinstance(width, bool) or not isinstance(width, int)
                                  or not 0 <= width <= 12):
            raise ValueError(f"{where}.width must be an integer 0-12")
        kinds[kind] = {"kind": kind, "glob": glob, "pattern": rx, "width": width,
                       "match": _glob_re(glob), "prefix": _literal_prefix(glob)}
    return kinds


def _number(kind: dict, path: str) -> tuple[int, str] | None:
    """(number, digits as written) when `path` is one of this kind's files."""
    if not kind["match"].match(path):
        return None
    m = kind["pattern"].search(PurePosixPath(path).name)
    if not m or not (m.group(1) or "").isdigit():
        return None
    return int(m.group(1)), m.group(1)


def _label(kind: dict, n: int, width: int | None = None) -> str:
    w = kind["width"] if kind["width"] is not None else (width or 0)
    return str(n).zfill(w)


# ---- frontmatter --------------------------------------------------------

def parse_tokens(value: str) -> list[tuple[int, str, str | None]]:
    """`0269_a, 0270_b` -> [(269, '0269', 'a'), (270, '0270', 'b')]. Tokens
    that are not `<digits>[_name]` are ignored (hand edits never crash)."""
    out = []
    for tok in (value or "").split(","):
        m = TOKEN_RE.match(tok.strip())
        if m:
            out.append((int(m.group(1)), m.group(1), m.group(2)))
    return out


def slots_from_meta(meta: dict) -> dict[str, str]:
    return {k[len(SLOT_PREFIX):]: v for k, v in meta.items()
            if k.startswith(SLOT_PREFIX) and len(k) > len(SLOT_PREFIX) and v}


def _meta_of(text: str) -> dict:
    m = FRONTMATTER_RE.match(text)
    meta = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
    return meta


def _apply_slot(text: str, kind: str, value: str | None) -> str:
    """Plan `text` with `slot_<kind>` set to `value` in place (appended to the
    frontmatter when new; None removes it). Everything else is untouched."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        if value is None:
            return text
        raise ValueError("plan file has no frontmatter block — cannot record a slot")
    key = SLOT_PREFIX + kind
    lines, done = [], False
    for ln in m.group(1).splitlines():
        if ln.partition(":")[0].strip() == key and ":" in ln:
            if value is not None and not done:
                lines.append(f"{key}: {value}")
                done = True
            continue
        lines.append(ln)
    if value is not None and not done:
        lines.append(f"{key}: {value}")
    return "---\n" + "\n".join(lines) + "\n---\n" + text[m.end():]


# ---- git ----------------------------------------------------------------

def _git(root: Path, *args: str, timeout: int = 15) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(root), *args],
                             capture_output=True, text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _cached(key, fn):
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
    val = fn()
    with _LOCK:
        if len(_CACHE) > 512:
            _CACHE.clear()
        _CACHE[key] = val
    return val


def _trunk_ctx(root: Path, trunk: str | None) -> dict:
    """{trunk, sha, onTrunk}: one rev-parse for the trunk tip and HEAD. A HEAD
    at the trunk tip reads as on trunk (its plan files ARE trunk's)."""
    if not trunk:
        return {"trunk": None, "sha": None, "onTrunk": True}
    out = _git(root, "rev-parse", f"refs/heads/{trunk}", "HEAD")
    shas = (out or "").split()
    if not shas:
        return {"trunk": None, "sha": None, "onTrunk": True}
    return {"trunk": trunk, "sha": shas[0],
            "onTrunk": len(shas) < 2 or shas[0] == shas[1]}


def _tree_files(root: Path, sha: str, prefix: str) -> list[str]:
    def run():
        args = ["ls-tree", "-r", "--name-only", sha]
        if prefix:
            args += ["--", prefix]
        out = _git(root, *args)
        return out.splitlines() if out else []
    return _cached(("tree", str(root), sha, prefix), run)


def _fs_files(root: Path, prefix: str) -> list[str]:
    base = root / prefix if prefix else root
    out = []
    try:
        for p in base.rglob("*"):
            rel = p.relative_to(root).as_posix()
            if rel.startswith(".git/") or "/.git/" in rel or not p.is_file():
                continue
            out.append(rel)
    except OSError:
        pass
    return out


def _numbers_in(kind: dict, paths) -> dict[int, list[str]]:
    found: dict[int, list[str]] = {}
    for p in paths:
        hit = _number(kind, p)
        if hit:
            found.setdefault(hit[0], []).append(p)
    return found


def _width_of(kind: dict, paths) -> int:
    best = (-1, 0)
    for p in paths:
        hit = _number(kind, p)
        if hit and hit[0] > best[0]:
            best = (hit[0], len(hit[1]))
    return best[1]


def _all_branch_added(root: Path, trunk: str, tips: list[tuple[str, str]],
                      prefixes: list[str]) -> list[str]:
    """Every path added by a commit on any unmerged branch but not on trunk —
    one `git log` across all tips. Conservative: a file added then renamed
    away still counts (it only ever pushes the next number up)."""
    if not tips:
        return []

    def run():
        args = ["log", "--full-history", "--no-renames", "--relative", "--diff-filter=A",
                "--name-only", "--format=", *sorted({f"refs/heads/{n}" for n, _ in tips}),
                "--not", f"refs/heads/{trunk}"]
        if all(prefixes):
            args += ["--", *sorted(set(prefixes))]
        out = _git(root, *args, timeout=30)
        return sorted({ln for ln in (out or "").splitlines() if ln.strip()})
    key = ("allbr", str(root), trunk, tuple(sorted(tips)), tuple(sorted(set(prefixes))))
    return _cached(key, run)


def _branch_added(root: Path, trunk: str, name: str, tip: str,
                  prefixes: list[str]) -> dict[str, list[int]]:
    """{path: plan tags of the commit that added it} for this kind's files the
    branch adds. Presence is the tree diff `trunk...branch` (authoritative,
    whatever merges and renumbers happened); attribution is the newest commit
    in `trunk..branch` that added the path. A path added only inside a merge
    resolution has no such commit and reads as untagged. Two git calls per
    branch, cached on its tip."""
    spec = ["--", *sorted(set(prefixes))] if all(prefixes) else []

    def run():
        diff = _git(root, "diff", "--name-only", "--no-renames", "--relative",
                    "--diff-filter=A", f"refs/heads/{trunk}...refs/heads/{name}",
                    *spec, timeout=30)
        present = [ln for ln in (diff or "").splitlines() if ln.strip()]
        if not present:
            return {}
        log = _git(root, "log", "--full-history", "--no-renames", "--relative",
                   "--diff-filter=A", "--name-only", f"--format={_REC}%s",
                   f"refs/heads/{trunk}..refs/heads/{name}", *spec, timeout=30)
        tags_of: dict[str, list[int]] = {}
        for rec in (log or "").split(_REC)[1:]:
            lines = rec.splitlines()
            tags = sorted({int(n) for n in rmbranches.TAG_RE.findall(lines[0] if lines else "")})
            for path in lines[1:]:
                if path.strip():
                    tags_of.setdefault(path, tags)       # newest add wins
        return {p: tags_of.get(p, []) for p in present}
    return _cached(("br", str(root), trunk, name, tip, tuple(sorted(set(prefixes)))), run)


def _tree_plan_slots(root: Path, sha: str) -> dict[int, dict]:
    """Slot reservations in the plan files of commit `sha` (trunk), from one
    `git grep` over `.roadmap/` frontmatter lines: {id: {title, status, slots}}."""
    def run():
        out = _git(root, "grep", "-n", "-I", "-E",
                   "-e", "^---$",
                   "-e", "^(id|title|status|" + SLOT_PREFIX + "[A-Za-z0-9_-]+):",
                   sha, "--", ".roadmap/*.md", timeout=30)
        files: dict[str, list[tuple[int, str]]] = {}
        for ln in (out or "").splitlines():
            if not ln.startswith(sha + ":"):
                continue
            path, _, rest = ln[len(sha) + 1:].partition(":")
            lineno, _, body = rest.partition(":")
            if lineno.isdigit():
                files.setdefault(path, []).append((int(lineno), body))
        plans: dict[int, dict] = {}
        for path, rows in files.items():
            rows.sort()
            if not rows or rows[0] != (1, "---"):
                continue           # no frontmatter at the top of the file
            end = next((n for n, b in rows[1:] if b == "---"), None)
            if end is None:
                continue
            meta = {}
            for n, b in rows:
                if 1 < n < end and b != "---":
                    k, _, v = b.partition(":")
                    meta.setdefault(k.strip(), v.strip())
            slots = slots_from_meta(meta)
            if slots and meta.get("id", "").isdigit():
                plans[int(meta["id"])] = {"title": meta.get("title", ""),
                                          "status": meta.get("status", ""),
                                          "slots": slots, "file": path}
        return plans
    return _cached(("plans", str(root), sha), run)


def _worktree_roots(root: Path) -> list[Path]:
    """Roadmap roots of the OTHER checkouts of this clone (linked worktrees)."""
    out = _git(root, "worktree", "list", "--porcelain")
    if not out:
        return []
    tops = [Path(ln[len("worktree "):]) for ln in out.splitlines()
            if ln.startswith("worktree ")]
    here = root.resolve()
    rel = None
    for t in tops:
        try:
            rel = here.relative_to(t.resolve())
            mine = t.resolve()
            break
        except (ValueError, OSError):
            continue
    if rel is None:
        return []
    return [t / rel for t in tops if t.resolve() != mine]


def _checkout_slots(root: Path) -> list[dict[str, str]]:
    """Raw (uncached) slot values from every plan in a checkout's config — read
    fresh under the lock so a reservation written a moment ago is seen."""
    vals = []
    try:
        cfg = read_config(root)
    except (OSError, ValueError):
        return vals
    for item in cfg.get("items", []):
        try:
            text = (roadmap_dir(root) / item["file"]).read_text(encoding="utf-8")
        except (OSError, KeyError, TypeError):
            continue
        vals.append(slots_from_meta(_meta_of(text)))
    return vals


# ---- lock ---------------------------------------------------------------

@contextlib.contextmanager
def _locked(root: Path, name: str = "roadmap-slots"):
    """Exclusive lock shared by every checkout of the clone (the git common
    dir); outside git, a temp-dir lock keyed by the project path. `name`
    picks the lock file, so unrelated writers (the run log) never contend."""
    common = _git(root, "rev-parse", "--git-common-dir")
    if common and common.strip():
        d = Path(common.strip())
        d = d if d.is_absolute() else (root / d)
        path = d / f"{name}.lock"
    else:
        h = hashlib.md5(str(root.resolve()).encode("utf-8")).hexdigest()[:12]
        path = Path(tempfile.gettempdir()) / f"{name}-{h}.lock"
    with open(path, "a+b") as f:
        try:
            import fcntl
        except ImportError:  # Windows
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            return
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


# ---- reserve / release --------------------------------------------------

def _kind_or_raise(cfg: dict, kind: str) -> dict:
    kinds = load_kinds(cfg)
    if not kinds:
        raise ValueError("no slot kinds configured — add settings.slots to "
                         ".roadmap/config.json (see references/state-model.md)")
    if kind not in kinds:
        raise ValueError(f"unknown slot kind {kind!r} — configured: "
                         + ", ".join(sorted(kinds)))
    return kinds[kind]


def _unmerged_tips(found: dict) -> list[tuple[str, str]]:
    seen = {}
    for b in [*found.get("items", {}).values(), *found.get("other", [])]:
        if b and not b.get("merged"):
            seen[b["name"]] = b.get("lastCommit") or ""
    return sorted(seen.items())


def _highest_known(root: Path, cfg: dict, kind: dict) -> tuple[int, int]:
    """(highest number anywhere we can see, inferred digit width)."""
    found = rmbranches.discover(root)
    ctx = _trunk_ctx(root, found.get("trunk"))
    k = kind["kind"]
    paths = (_tree_files(root, ctx["sha"], kind["prefix"]) if ctx["sha"] else [])
    paths = list(paths) + _fs_files(root, kind["prefix"])
    if ctx["sha"]:
        paths += _all_branch_added(root, ctx["trunk"], _unmerged_tips(found),
                                   [kind["prefix"]])
    nums = list(_numbers_in(kind, paths))
    width = _width_of(kind, paths)
    values = [s.get(k, "") for s in _checkout_slots(root)]
    for wt in _worktree_roots(root):
        values += [s.get(k, "") for s in _checkout_slots(wt)]
    if ctx["sha"] and not ctx["onTrunk"]:
        values += [p["slots"].get(k, "") for p in _tree_plan_slots(root, ctx["sha"]).values()]
    for v in values:
        for n, digits, _ in parse_tokens(v):
            nums.append(n)
            width = max(width, len(digits))
    return (max(nums) if nums else 0), width


def reserve(root: Path, plan_id: int, kind: str, name: str | None = None,
            add: bool = False) -> dict:
    """Reserve the next number of `kind` for plan `plan_id` and record it in
    the plan's frontmatter. Idempotent: a plan already holding a `kind` slot
    gets it back unchanged unless `add` asks for another number.
    Returns {kind, value, token, new}."""
    root = Path(root)
    cfg = read_config(root)
    spec = _kind_or_raise(cfg, kind)
    if name is not None:
        name = name.strip()
        if not NAME_RE.match(name):
            raise ValueError(f"invalid slot name {name!r} — letters, digits, '_', "
                             f"'.', '-' (no spaces or commas)")
    path = _plan_path(root, plan_id)
    if not path.exists():
        raise ValueError(f"plan file for #{plan_id} is missing ({path.name})")
    done, total = count_progress(path)
    if total and done == total:
        raise ValueError(f"#{plan_id} is done ({done}/{total} steps ticked) — "
                         f"a done item cannot reserve a slot")
    with _locked(root):
        text = path.read_text(encoding="utf-8")
        cur = slots_from_meta(_meta_of(text)).get(kind)
        held = parse_tokens(cur or "")
        if held and not add:
            if name and not any(nm == name for _, _, nm in held):
                raise ValueError(
                    f"#{plan_id} already holds {kind} {cur} — release it first "
                    f"(slot {plan_id} --kind {kind} --release) or pass --add "
                    f"for another number")
            return {"kind": kind, "value": cur, "token": cur, "new": False}
        high, width = _highest_known(root, cfg, spec)
        token = _label(spec, high + 1, width) + (f"_{name}" if name else "")
        value = f"{cur}, {token}" if held else token
        atomic_write(path, _apply_slot(text, kind, value))
    return {"kind": kind, "value": value, "token": token, "new": True}


def release(root: Path, plan_id: int, kind: str) -> str | None:
    """Drop plan `plan_id`'s `kind` reservation. Returns the freed value, or
    None when it held none. Works for kinds no longer configured."""
    root = Path(root)
    if not KIND_RE.match(kind or ""):
        raise ValueError(f"invalid slot kind {kind!r}")
    path = _plan_path(root, plan_id)
    if not path.exists():
        raise ValueError(f"plan file for #{plan_id} is missing ({path.name})")
    with _locked(root):
        text = path.read_text(encoding="utf-8")
        cur = slots_from_meta(_meta_of(text)).get(kind)
        if not cur:
            return None
        atomic_write(path, _apply_slot(text, kind, None))
    return cur


# ---- status -------------------------------------------------------------

def _own_files(kind: dict, pid: int, added: dict[str, list[int]] | None
               ) -> dict[int, list[str]]:
    """{number: paths} this plan's branch adds. Files from inherited commits
    tagged only for OTHER plans (stacked branches) are not its work."""
    mine: dict[int, list[str]] = {}
    for path, tags in (added or {}).items():
        if tags and pid not in tags:
            continue
        hit = _number(kind, path)
        if hit:
            mine.setdefault(hit[0], []).append(path)
    return mine


def _evaluate(kind: dict, entry: dict, holders: dict[int, set], trunk_nums: dict,
              foreign: dict[int, list[tuple[int, str]]]) -> tuple[str, str]:
    """(state, detail) for one plan's reservation of one kind. `foreign` maps
    a number to the (plan, branch) pairs whose branch adds it unreserved."""
    pid = entry["plan"]
    tokens = entry["tokens"]
    nums = {n for n, _, _ in tokens}
    label = {n: d for n, d, _ in tokens}
    dup = sorted(n for n in nums if len(holders.get(n, ())) > 1)
    if dup:
        others = sorted({p for n in dup for p in holders[n]} - {pid})
        return "clash", (", ".join(label[n] for n in dup) + " also reserved by "
                         + ", ".join(f"#{p}" for p in others))
    used = [(n, p, b) for n in sorted(nums) for p, b in foreign.get(n, []) if p != pid]
    if used:
        return "clash", "; ".join(f"{label[n]} added on {b} (#{p})" for n, p, b in used)
    mine = entry["mine"]
    branch = entry.get("branch") or {}
    taken, landed = [], set()
    for n in sorted(nums & set(trunk_nums)):
        names = {f"{d}_{nm}" for nn, d, nm in tokens if nn == n and nm}
        own = (bool(branch.get("merged"))
               or bool(set(trunk_nums[n]) & set(mine.get(n, [])))
               or any(PurePosixPath(p).name.split(".")[0] in names
                      for p in trunk_nums[n]))
        if own:
            landed.add(n)
        else:
            taken.append(n)
    if taken:
        n = taken[0]
        return "taken", (f"trunk already has {label[n]} ("
                         + ", ".join(PurePosixPath(p).name for p in trunk_nums[n]) + ")")
    strays = sorted(set(mine) - nums)
    if strays:
        def whose(n):
            held = sorted(holders.get(n, ()))
            return ("reserved by " + ", ".join(f"#{p}" for p in held)) if held \
                else "not reserved"
        return "clash", "branch adds " + ", ".join(
            f"{PurePosixPath(mine[n][0]).name} ({whose(n)})" for n in strays)
    present = (nums & set(mine)) | landed
    if nums and present == nums:
        if landed == nums:
            return "ok", "on trunk"
        return "ok", "branch adds " + ", ".join(label[n] for n in sorted(nums & set(mine)))
    if not branch:
        return "missing", "no branch yet"
    return "missing", "no " + ", ".join(label[n] for n in sorted(nums - present)) \
        + f" on {branch.get('name')} yet"


def slots_status(root: Path, cfg: dict, rows: list[dict], found: dict) -> dict:
    """Status payload `slots` (only built when settings.slots is set):
    {trunk, kinds: [{kind, glob, trunkHighest, branchHighest, reservations:
    [{plan, displayId, title, lane, branch, source, value, numbers, state,
    detail}], clashes}], clashes}. Never raises: problems land in `error`."""
    try:
        kinds = load_kinds(cfg)
    except ValueError as e:
        return {"error": str(e), "kinds": [], "clashes": 0}
    try:
        return _slots_status(Path(root), kinds, rows, found)
    except Exception as e:  # noqa: BLE001 — status must survive any surprise
        return {"error": f"slot scan failed: {e}", "kinds": [], "clashes": 0}


def _slots_status(root: Path, kinds: dict, rows: list[dict], found: dict) -> dict:
    ctx = _trunk_ctx(root, found.get("trunk"))
    entries: list[dict] = []
    local_ids = set()
    for row in rows:
        path = roadmap_dir(root) / row.get("file", "")
        if not row.get("file") or not path.exists():
            continue
        local_ids.add(row["id"])
        if row.get("status") == "done":
            continue
        for k, v in slots_from_meta(parse_plan(path)["meta"]).items():
            entries.append({"kind": k, "plan": row["id"], "displayId": row.get("displayId"),
                            "title": row.get("title", ""), "lane": row.get("lane"),
                            "branch": row.get("branch"), "source": "local", "value": v})
    if ctx["sha"] and not ctx["onTrunk"]:
        # On a branch checkout: plans created on trunk since the fork still hold
        # numbers. Plans this checkout has keep their local (newer) view.
        for pid, p in _tree_plan_slots(root, ctx["sha"]).items():
            if pid in local_ids or p.get("status") == "done":
                continue
            for k, v in p["slots"].items():
                entries.append({"kind": k, "plan": pid, "displayId": f"#{pid}",
                                "title": p.get("title", ""), "lane": None,
                                "branch": None, "source": "trunk", "value": v})
    tips = _unmerged_tips(found) if ctx["sha"] else []
    out_kinds, total = [], 0
    for name, kind in kinds.items():
        if ctx["sha"]:
            trunk_paths = _tree_files(root, ctx["sha"], kind["prefix"])
            br_paths = _all_branch_added(root, ctx["trunk"], tips, [kind["prefix"]])
        else:
            trunk_paths, br_paths = _fs_files(root, kind["prefix"]), []
        trunk_nums = _numbers_in(kind, trunk_paths)
        br_nums = _numbers_in(kind, br_paths)
        width = _width_of(kind, trunk_paths)
        ents = [e for e in entries if e["kind"] == name]
        for e in ents:
            e["tokens"] = parse_tokens(e["value"])
        holders: dict[int, set] = {}
        for e in ents:
            for n, _, _ in e["tokens"]:
                holders.setdefault(n, set()).add(e["plan"])
        foreign: dict[int, list[tuple[int, str]]] = {}
        for e in ents:
            b = e["branch"]
            added = None
            if b and ctx["sha"] and not b.get("merged"):
                added = _branch_added(root, ctx["trunk"], b["name"],
                                      b.get("lastCommit") or "", [kind["prefix"]])
            e["mine"] = _own_files(kind, e["plan"], added)
            reserved = {n for n, _, _ in e["tokens"]}
            for n in e["mine"]:
                if n not in reserved:
                    foreign.setdefault(n, []).append((e["plan"], b["name"]))
        res = []
        for e in sorted(ents, key=lambda x: (min([n for n, _, _ in x["tokens"]] or [0]),
                                             x["plan"])):
            b = e["branch"]
            if not e["tokens"]:
                state, detail = "clash", f"unreadable value {e['value']!r}"
            else:
                state, detail = _evaluate(kind, e, holders, trunk_nums, foreign)
            res.append({"plan": e["plan"], "displayId": e["displayId"],
                        "title": e["title"], "lane": e["lane"],
                        "branch": b["name"] if b else None, "source": e["source"],
                        "value": e["value"], "numbers": [d for _, d, _ in e["tokens"]],
                        "state": state, "detail": detail})
        n_bad = sum(1 for r in res if r["state"] in FAILING)
        total += n_bad
        th = max(trunk_nums) if trunk_nums else None
        bh = max(br_nums) if br_nums else None
        out_kinds.append({"kind": name, "glob": kind["glob"],
                          "trunkHighest": _label(kind, th, width) if th is not None else None,
                          "branchHighest": _label(kind, bh, width) if bh is not None else None,
                          "reservations": res, "clashes": n_bad})
    return {"trunk": ctx["trunk"], "kinds": out_kinds, "clashes": total}


def format_slots(payload: dict | None, plan_id: int | None = None) -> str:
    """Terminal view for `status --slots` / `slot --check`."""
    if not payload:
        return "no slot kinds configured (settings.slots in .roadmap/config.json)"
    if payload.get("error"):
        return f"slots: {payload['error']}"
    lines = []
    for k in payload.get("kinds", []):
        head = [k["kind"], k["glob"], f"trunk highest {k['trunkHighest'] or '—'}"]
        if k.get("branchHighest"):
            head.append(f"branches highest {k['branchHighest']}")
        lines.append(" · ".join(head))
        rs = [r for r in k["reservations"] if plan_id is None or r["plan"] == plan_id]
        if not rs:
            lines.append("  (no reservations)")
        for r in rs:
            where = " · ".join(x for x in (r.get("lane"), r.get("branch")) if x) or r["source"]
            lines.append(f"  {r['value']:<28} {r['displayId'] or '#' + str(r['plan']):<10} "
                         f"{where:<28} {r['state']:<8} {r['detail']}")
    return "\n".join(lines)


def check_failures(payload: dict | None, plan_id: int | None = None) -> list[dict]:
    """Reservations in a failing state (clash/taken), optionally one plan's."""
    out = []
    for k in (payload or {}).get("kinds", []):
        for r in k["reservations"]:
            if r["state"] in FAILING and (plan_id is None or r["plan"] == plan_id):
                out.append({**r, "kind": k["kind"]})
    return out
