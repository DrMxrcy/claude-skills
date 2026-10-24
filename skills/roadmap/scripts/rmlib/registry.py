"""Per-user project registry (plan 48): every roadmap project this user has run
`orient`, `status`, `serve` or `check` in, so `serve --all` can show them all
on one page with zero setup.

Lives at `~/.roadmap/projects.json` ($ROADMAP_HOME overrides the directory —
tests point it at a temp dir). Written atomically; every failure is silent:
a registry that cannot be read is treated as empty, and one that cannot be
written is skipped, so no command ever fails because of it.

    {"version": 1, "projects": {"/abs/root": {"name": "Demo",
                                              "lastSeen": "2026-10-24T09:00:00Z"}}}
"""
from __future__ import annotations
import datetime
import hashlib
import json
import os
import re
from pathlib import Path

from .core import atomic_write, roadmap_dir

REGISTRY_FILE = "projects.json"
TOUCH_EVERY = 60   # seconds: a busy project rewrites the file at most once a minute


def home_dir() -> Path:
    """The registry directory: $ROADMAP_HOME, else ~/.roadmap."""
    env = os.environ.get("ROADMAP_HOME")
    return Path(env).expanduser() if env else Path.home() / ".roadmap"


def registry_path() -> Path:
    return home_dir() / REGISTRY_FILE


def is_registry_dir(d: Path) -> bool:
    """True when `d` (a `.roadmap` directory) is the registry home rather than
    a project's roadmap — it has no config.json and is where the registry
    lives. find_root uses this so ~/.roadmap never makes $HOME a project."""
    try:
        if (d / "config.json").exists():
            return False
        return d.resolve() == home_dir().resolve()
    except OSError:
        return False


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s) -> datetime.datetime | None:
    try:
        return datetime.datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


def load() -> dict:
    """{abs path: {"name", "lastSeen"}} — empty on a missing, unreadable or
    malformed file; malformed entries are dropped one by one."""
    try:
        data = json.loads(registry_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    projects = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projects, dict):
        return {}
    out = {}
    for path, e in projects.items():
        if isinstance(path, str) and path and isinstance(e, dict):
            out[path] = {"name": str(e.get("name") or Path(path).name),
                         "lastSeen": e.get("lastSeen") if isinstance(
                             e.get("lastSeen"), str) else None}
    return out


def _save(projects: dict) -> bool:
    try:
        atomic_write(registry_path(),
                     json.dumps({"version": 1, "projects": projects},
                                indent=2, sort_keys=True) + "\n")
        return True
    except Exception:  # noqa: BLE001 — the registry never fails a command
        return False


def main_checkout(root: Path) -> Path:
    """The main checkout of `root` when it is a linked git worktree that shares
    the main checkout's roadmap, else `root` — so a repo with 20 worktrees is one
    project. Pure file reads (no git subprocess)."""
    try:
        dotgit = root / ".git"
        if not dotgit.is_file():
            return root
        m = re.match(r"gitdir:\s*(.+)", dotgit.read_text(encoding="utf-8").strip())
        if not m:
            return root
        gitdir = Path(m.group(1).strip())
        if not gitdir.is_absolute():
            gitdir = (root / gitdir)
        common = gitdir
        cd = gitdir / "commondir"
        if cd.is_file():
            c = Path(cd.read_text(encoding="utf-8").strip())
            common = c if c.is_absolute() else gitdir / c
        main = common.resolve().parent
        if (roadmap_dir(main) / "config.json").is_file():
            return main
    except (OSError, ValueError):
        pass
    return root


def _project_name(root: Path) -> str:
    try:
        cfg = json.loads((roadmap_dir(root) / "config.json").read_text(encoding="utf-8"))
        name = cfg.get("project") if isinstance(cfg, dict) else None
        if isinstance(name, str) and name.strip():
            return name.strip()
    except (OSError, ValueError):
        pass
    return root.name or str(root)


def touch(root: Path) -> bool:
    """Record `root` (its main checkout) as seen now. No-op outside a roadmap
    project and when the entry was refreshed in the last TOUCH_EVERY seconds.
    Returns whether the file was written; never raises."""
    try:
        root = main_checkout(Path(root).resolve())
        if not (roadmap_dir(root) / "config.json").is_file():
            return False
        key, name = str(root), _project_name(root)
        projects = load()
        cur = projects.get(key)
        seen = _parse_iso((cur or {}).get("lastSeen"))
        now = datetime.datetime.now(datetime.timezone.utc)
        if (cur and cur.get("name") == name and seen is not None
                and 0 <= (now - seen).total_seconds() < TOUCH_EVERY):
            return False
        projects[key] = {"name": name, "lastSeen": _now()}
        return _save(projects)
    except Exception:  # noqa: BLE001
        return False


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-.")
    return s or "project"


def entries() -> list[dict]:
    """Registry rows sorted by name: {slug, name, path, lastSeen, exists}.
    `slug` is unique and URL-safe (the `#/p/<slug>/` key and the name
    `projects --forget` takes); clashing names get a short path hash."""
    rows = [{"name": e["name"], "path": p, "lastSeen": e["lastSeen"]}
            for p, e in load().items()]
    count: dict[str, int] = {}
    for r in rows:
        count[_slug(r["name"])] = count.get(_slug(r["name"]), 0) + 1
    for r in rows:
        s = _slug(r["name"])
        if count[s] > 1:
            s += "-" + hashlib.md5(r["path"].encode("utf-8")).hexdigest()[:4]
        r["slug"] = s
        try:
            r["exists"] = (roadmap_dir(Path(r["path"])) / "config.json").is_file()
        except OSError:
            r["exists"] = False
    return sorted(rows, key=lambda r: (r["name"].lower(), r["path"]))


def forget(token: str) -> list[str]:
    """Drop every entry whose slug, name or path is `token`; returns the
    removed paths (empty when nothing matched or the write failed)."""
    gone = [r["path"] for r in entries()
            if token in (r["slug"], r["name"], r["path"])]
    if not gone:
        return []
    projects = load()
    for p in gone:
        projects.pop(p, None)
    return gone if _save(projects) else []


def format_entries(rows: list[dict]) -> str:
    if not rows:
        return (f"no projects registered yet ({registry_path()}) — run "
                "`roadmap.py status` in a project to add it")
    w = max(len(r["slug"]) for r in rows)
    lines = []
    for r in rows:
        tail = "" if r["exists"] else "  (missing — roadmap.py projects --forget "\
            + r["slug"] + ")"
        lines.append(f"{r['slug']:<{w}}  {r['lastSeen'] or '-':<20}  {r['path']}{tail}")
    return "\n".join(lines)
