"""roadmap branch conflict risk (plan 41) — which open item branches change
the same files, and which of those would actually conflict.

For every unmerged item branch: the files it changes vs trunk
(`git diff --name-only trunk...branch`). Two branches sharing changed files
form an overlap; with `git merge-tree --write-tree` (git >= 2.38) the pair is
merged in memory for an exact answer:

  high    merge-tree reports a conflict between the two tips
  medium  file overlap only (no merge-tree, or it could not decide)
  low     shared files, but merge-tree merges the tips cleanly

Cost: every git answer here is a pure function of commit shas, so it is
cached on them — changed files on (trunk tip, branch tip), merge results on
the two tips. Unchanged refs cost zero git calls; a moved tip recomputes only
that branch and its pairs. merge-tree --write-tree writes only loose objects:
no branch, index, worktree or HEAD is ever touched.
Layer: rmcore + rmbranches (read-only, never raises on git trouble).
"""
from __future__ import annotations
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from rmlib import branches as rmbranches

MAX_FILES = 10            # shared files shown per pair
WORKERS = 8               # parallel git calls on a cold cache
_CACHE_MAX = 4096         # per-dict entry cap; oldest evicted first
RISKS = ("high", "medium", "low")
_RANK = {r: i for i, r in enumerate(RISKS)}

_LOCK = threading.Lock()
# (root, trunk sha, tip sha) -> changed paths, sorted
_FILES: dict[tuple[str, str, str], tuple[str, ...]] = {}
# (root, sha, sha) sorted -> conflicted paths (empty = merges cleanly)
_PAIRS: dict[tuple[str, str, str], tuple[str, ...]] = {}
_MT: dict[str, bool] = {}  # "supported" -> git merge-tree --write-tree available


def _run(root: Path, *args: str) -> tuple[int, str] | None:
    """(exit code, stdout) of one git call; None when git cannot run."""
    try:
        out = subprocess.run(["git", "-C", str(root), *args],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.returncode, out.stdout


def _put(cache: dict, key, value) -> None:
    with _LOCK:
        cache[key] = value
        while len(cache) > _CACHE_MAX:
            cache.pop(next(iter(cache)))


def _key(root: Path) -> str:
    return str(Path(root).resolve())


def merge_tree_supported() -> bool:
    """git >= 2.38 (`merge-tree --write-tree`). One `git --version` per
    process; tests monkeypatch this to exercise the file-overlap fallback."""
    with _LOCK:
        hit = _MT.get("supported")
    if hit is not None:
        return hit
    res = _run(Path("."), "--version")
    m = re.search(r"(\d+)\.(\d+)", res[1]) if res and res[0] == 0 else None
    ok = bool(m) and (int(m.group(1)), int(m.group(2))) >= (2, 38)
    with _LOCK:
        _MT["supported"] = ok
    return ok


def changed_files_at(root: Path, trunk_sha: str, tip_sha: str) -> list[str] | None:
    """Paths `tip_sha` changes since its merge base with `trunk_sha`
    (`git diff --name-only trunk...tip`, renames as delete + add so both
    paths count). Cached on the two shas. None on git trouble."""
    key = (_key(root), trunk_sha, tip_sha)
    with _LOCK:
        hit = _FILES.get(key)
    if hit is not None:
        return list(hit)
    res = _run(root, "diff", "--name-only", "-z", "--no-renames",
               f"{trunk_sha}...{tip_sha}", "--")
    if res is None or res[0] != 0:
        return None
    files = tuple(sorted({p for p in res[1].split("\0") if p}))
    _put(_FILES, key, files)
    return list(files)


def changed_files(root: Path, branch: str, trunk: str | None = None,
                  integration=None, base: str | None = None) -> list[str] | None:
    """Files local `branch` changes vs trunk (default: main/master, as in
    rmbranches.discover) — the per-branch list plan 41 caches, for reuse
    (plan 42 scope drift). `base` names another local branch to diff from
    instead (`base...branch`: only the work since it forked from that base,
    e.g. a branch cut from an integration branch). Costs the cached ref scan
    (one for-each-ref) plus one `git diff` only when a tip moved. None when
    a branch or the trunk is unknown, or on git trouble."""
    scanned = rmbranches._scan_cached(Path(root), trunk, integration)
    if scanned is None:
        return None
    resolved, data = scanned
    tips = {b["name"]: b["sha"] for b in data["branches"]}
    tips[resolved] = data.get("trunkSha")
    frm, tip = tips.get(base or resolved), tips.get(branch)
    if not frm or not tip:
        return None
    return changed_files_at(Path(root), frm, tip)


def merge_conflicts(root: Path, sha_a: str, sha_b: str) -> list[str] | None:
    """Paths that conflict when merging the two commits (empty: clean), via
    `git merge-tree --write-tree` — in memory, never touching a branch, the
    index or a worktree. Cached on the sha pair. None when merge-tree is
    unavailable or cannot decide (unrelated histories, git trouble)."""
    a, b = sorted((sha_a, sha_b))
    key = (_key(root), a, b)
    with _LOCK:
        hit = _PAIRS.get(key)
    if hit is not None:
        return list(hit)
    if not merge_tree_supported():
        return None
    res = _run(root, "merge-tree", "--write-tree", "--name-only",
               "--no-messages", "-z", a, b)
    if res is None or res[0] not in (0, 1):
        return None
    parts = res[1].split("\0")
    paths = tuple(dict.fromkeys(p for p in parts[1:] if p)) if res[0] == 1 else ()
    _put(_PAIRS, key, paths)
    return list(paths)


def _who(c: dict) -> dict:
    return {k: c[k] for k in ("id", "displayId", "title", "branch", "items")}


def _each(fn, jobs: list) -> list:
    """fn over jobs; uncached git work fans out over a small thread pool
    (a lone job runs inline)."""
    if len(jobs) < 2:
        return [fn(j) for j in jobs]
    with ThreadPoolExecutor(max_workers=min(WORKERS, len(jobs))) as ex:
        return list(ex.map(fn, jobs))


def _group(candidates: list[dict]) -> list[dict]:
    """One node per branch: items sharing a branch (an integration branch
    carrying many landed items, say) are one merge, not N pairwise ones.
    The node takes the lowest item id; `items` lists every id on it."""
    nodes: dict[str, dict] = {}
    for c in sorted(candidates, key=lambda c: c["id"]):
        n = nodes.get(c["branch"])
        if n is None:
            nodes[c["branch"]] = {**c, "items": [c["id"]]}
        else:
            n["items"].append(c["id"])
    return list(nodes.values())


def overlaps(root: Path, trunk_sha: str | None, candidates: list[dict],
             max_files: int = MAX_FILES) -> dict:
    """Overlap report for `candidates`: [{id, displayId, title, branch, sha,
    landedIn}] — each item with its open branch; items on the same branch are
    one node (`items` = every id on it, `id` the lowest). Returns
    {"mergeTree", "checked", "unknown", "pairs", "counts", "order"}:
      checked — branches whose changed files were read
      pairs   — {a, b, risk, files (<= max_files), fileCount, conflictFiles},
                high first, then most shared files
      order   — every checked branch node, no overlaps first, then fewest
                overlaps (then fewest high-risk ones, then id): a suggested
                merge order
      unknown — branches whose changed files could not be read
    Two branches that landed in the same integration branch are skipped
    (their conflicts were already resolved there), as are two branches on the
    same tip. Never raises; no trunk sha means an empty report."""
    root = Path(root)
    supported = merge_tree_supported()
    out = {"mergeTree": supported, "checked": 0, "unknown": [], "pairs": [],
           "counts": {r: 0 for r in RISKS}, "order": []}
    if not trunk_sha:
        return out
    nodes = _group(candidates)
    got = _each(lambda c: changed_files_at(root, trunk_sha, c["sha"])
                if c.get("sha") else None, nodes)
    files: dict[int, set[str]] = {}
    checked: list[dict] = []
    for c, f in zip(nodes, got):
        if f is None:
            out["unknown"].append(c["branch"])
            continue
        files[c["id"]] = set(f)
        checked.append(c)
    overlapping = []
    for i, a in enumerate(checked):
        for b in checked[i + 1:]:
            if a["sha"] == b["sha"]:
                continue
            if a.get("landedIn") and a.get("landedIn") == b.get("landedIn"):
                continue
            shared = sorted(files[a["id"]] & files[b["id"]])
            if shared:
                overlapping.append((a, b, shared))
    hits = (_each(lambda ab: merge_conflicts(root, ab[0]["sha"], ab[1]["sha"]),
                  overlapping) if supported else [None] * len(overlapping))
    pairs = []
    for (a, b, shared), hit in zip(overlapping, hits):
        risk = "medium" if hit is None else ("high" if hit else "low")
        pairs.append({"a": _who(a), "b": _who(b), "risk": risk,
                      "files": shared[:max_files], "fileCount": len(shared),
                      "conflictFiles": (hit or [])[:max_files]})
    pairs.sort(key=lambda p: (_RANK[p["risk"]], -p["fileCount"],
                              p["a"]["id"], p["b"]["id"]))
    tally: dict[int, list[int]] = {c["id"]: [0, 0] for c in checked}
    for p in pairs:
        out["counts"][p["risk"]] += 1
        for side in ("a", "b"):
            t = tally[p[side]["id"]]
            t[0] += 1
            t[1] += p["risk"] == "high"
    out["checked"] = len(checked)
    out["pairs"] = pairs
    out["order"] = [{**_who(c), "overlaps": tally[c["id"]][0],
                     "high": tally[c["id"]][1]}
                    for c in sorted(checked, key=lambda c: (*tally[c["id"]], c["id"]))]
    return out


def format_conflicts(rep: dict | None) -> str:
    """Terminal text for `status --conflicts`: one line per overlapping pair
    (risk, the two items, shared files), then the suggested merge order."""
    rep = rep or {}
    counts = rep.get("counts") or {}
    pairs = rep.get("pairs") or []
    mode = ("merge-tree check" if rep.get("mergeTree")
            else "file overlap only (git < 2.38: no merge-tree)")
    lines = [f"conflicts: {rep.get('checked', 0)} open item branches · "
             f"{len(pairs)} overlapping pair{'s' if len(pairs) != 1 else ''} · "
             f"{counts.get('high', 0)} high · "
             f"{counts.get('medium', 0)} medium · {counts.get('low', 0)} low"
             f" — {mode}"]
    def tag(w: dict) -> str:
        more = len(w.get("items") or []) - 1
        return (f"{w['displayId'] or '#' + str(w['id'])}"
                f"{f' +{more}' if more > 0 else ''} ({w['branch']})")

    for p in pairs:
        more = p["fileCount"] - len(p["files"])
        shown = ", ".join(p["files"]) + (f", +{more} more" if more > 0 else "")
        lines.append(f"  {p['risk'].upper():<6} {tag(p['a'])} <-> {tag(p['b'])}"
                     f" · {p['fileCount']} shared: {shown}")
        if p["conflictFiles"]:
            lines.append(f"         conflicts: {', '.join(p['conflictFiles'])}")
    if rep.get("unknown"):
        lines.append(f"  unreadable: {', '.join(rep['unknown'])}")
    order = rep.get("order") or []
    if order:
        lines.append("suggested merge order (no overlaps first, then fewest):")
        for n, o in enumerate(order, 1):
            note = ("no overlaps" if not o["overlaps"] else
                    f"{o['overlaps']} overlap{'s' if o['overlaps'] != 1 else ''}"
                    + (f", {o['high']} high" if o["high"] else ""))
            lines.append(f"  {n}. {tag(o)} {o['title']} — {note}")
    return "\n".join(lines)
