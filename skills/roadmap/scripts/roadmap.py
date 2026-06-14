#!/usr/bin/env python3
"""roadmap — deterministic CLI for the roadmap skill (Python 3 stdlib only)."""
from __future__ import annotations
import argparse, datetime, json, os, re, subprocess, sys, tempfile
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
AUTO_START = "<!-- roadmap:auto:start -->"
AUTO_END = "<!-- roadmap:auto:end -->"


def roadmap_dir(root: Path) -> Path:
    return root / ".roadmap"


def find_root(start: Path) -> Path:
    start = start.resolve()
    for d in [start, *start.parents]:
        if (d / ".roadmap").is_dir():
            return d
    for d in [start, *start.parents]:
        if (d / ".git").exists():
            return d
    return start


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_config(root: Path) -> dict:
    return json.loads((roadmap_dir(root) / "config.json").read_text(encoding="utf-8"))


def write_config(root: Path, cfg: dict) -> None:
    atomic_write(roadmap_dir(root) / "config.json", json.dumps(cfg, indent=2) + "\n")


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower())
    return s.strip("-")


def _render_template(name: str, **values) -> str:
    text = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def _version_from_pyproject(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    try:
        import tomllib
        data = tomllib.loads(text)
        project = data.get("project")
        if isinstance(project, dict) and isinstance(project.get("version"), str):
            return project["version"]
        poetry = data.get("tool", {}).get("poetry") if isinstance(data.get("tool"), dict) else None
        if isinstance(poetry, dict) and isinstance(poetry.get("version"), str):
            return poetry["version"]
        return None
    except ModuleNotFoundError:
        # Python < 3.11: best-effort regex fallback
        m = re.search(r'(?m)^\s*version\s*=\s*["\']([^"\']+)["\']', text)
        return m.group(1) if m else None


def detect_version(root: Path) -> str:
    pkg = root / "package.json"
    if pkg.exists():
        try:
            v = json.loads(pkg.read_text(encoding="utf-8")).get("version")
            if v:
                return str(v)
        except json.JSONDecodeError:
            pass
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        v = _version_from_pyproject(pyproject)
        if v:
            return v
    try:
        out = subprocess.run(["git", "describe", "--tags", "--abbrev=0"],
                             cwd=str(root), capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip().lstrip("v")
    except FileNotFoundError:
        pass
    return "0.0.1"


def derive_status(done: int, total: int) -> str:
    if total > 0 and done == total:
        return "done"
    if done > 0:
        return "active"
    return "planned"


def _set_frontmatter(path: Path, key: str, value: str) -> None:
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(rf"(?m)^{key}:.*$", f"{key}: {value}", text, count=1)
    if n:
        atomic_write(path, new)


def _version_key(v: str):
    try:
        return (0, tuple(int(p) for p in v.split(".")))
    except ValueError:
        return (1, v)


def render_region(cfg: dict, progress: dict) -> str:
    by_version: dict[str, list] = {}
    for item in cfg["items"]:
        by_version.setdefault(item["version"], []).append(item)
    lines = ["## 📊 Versions", ""]
    for version in sorted(by_version, key=_version_key):
        items = by_version[version]
        done_total = [progress.get(i["id"], (0, 0)) for i in items]
        d = sum(x for x, _ in done_total)
        t = sum(y for _, y in done_total)
        pct = round(100 * d / t) if t else 0
        marker = "x" if t and d == t else " "
        lines.append(f"### [{marker}] v{version} — {pct}%")
        for item in items:
            done, total = progress.get(item["id"], (0, 0))
            ipct = round(100 * done / total) if total else 0
            box = "x" if total and done == total else " "
            lines.append(f"- [{box}] **#{item['id']} {item['title']}** "
                         f"`{item['type']}` — {ipct}% "
                         f"([plan](.roadmap/{item['file']}))")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def sync(root: Path) -> None:
    cfg = read_config(root)
    progress = {}
    for item in cfg["items"]:
        path = roadmap_dir(root) / item["file"]
        if path.exists():
            done, total = count_progress(path)
            progress[item["id"]] = (done, total)
            _set_frontmatter(path, "status", derive_status(done, total))
    body = render_region(cfg, progress) if cfg["items"] else \
        "_No items yet. Use the roadmap skill to add one._\n"
    region = f"**Current version: v{cfg['currentVersion']}**\n\n{body}"
    rm_path = root / "ROADMAP.md"
    if not rm_path.exists():
        raise ValueError(f"ROADMAP.md not found at {rm_path}; run init first")
    text = rm_path.read_text(encoding="utf-8")
    if (text.count(AUTO_START) != 1 or text.count(AUTO_END) != 1
            or text.index(AUTO_START) > text.index(AUTO_END)):
        raise ValueError(
            "ROADMAP.md has missing or malformed roadmap:auto markers; restore "
            "exactly one '<!-- roadmap:auto:start -->' before "
            "'<!-- roadmap:auto:end -->'")
    before = text.split(AUTO_START)[0]
    after = text.split(AUTO_END)[1]
    atomic_write(rm_path, f"{before}{AUTO_START}\n{region}{AUTO_END}{after}")


STEP_RE = re.compile(r"^(\s*[-*]\s+)\[( |x|X)\](.*)$")


def _is_fence(line: str) -> bool:
    return line.lstrip().startswith("```")


def parse_plan(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta = {}
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
    steps = []
    in_fence = False
    for line in text.splitlines():
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        sm = STEP_RE.match(line)
        if sm:
            steps.append((sm.group(2).lower() == "x", sm.group(3).strip()))
    return {"meta": meta, "steps": steps}


def count_progress(path: Path) -> tuple[int, int]:
    steps = parse_plan(path)["steps"]
    return sum(1 for done, _ in steps if done), len(steps)


def _plan_path(root: Path, plan_id: int) -> Path:
    for item in read_config(root)["items"]:
        if item["id"] == plan_id:
            return roadmap_dir(root) / item["file"]
    raise ValueError(f"no plan with id {plan_id}")


def check_step(root: Path, plan_id: int, step: int | None,
               undo: bool = False, all_done: bool = False) -> None:
    path = _plan_path(root, plan_id)
    box = "[ ]" if undo else "[x]"
    out, n, in_fence = [], 0, False
    for line in path.read_text(encoding="utf-8").splitlines():
        if _is_fence(line):
            in_fence = not in_fence
            out.append(line)
            continue
        sm = None if in_fence else STEP_RE.match(line)
        if sm:
            n += 1
            if all_done or n == step:
                line = re.sub(r"\[( |x|X)\]", box, line, count=1)
        out.append(line)
    if step is not None and not all_done and (step < 1 or step > n):
        raise ValueError(f"plan {plan_id} step {step} out of range (1..{n})")
    atomic_write(path, "\n".join(out) + "\n")
    sync(root)


TEMPLATE_BY_TYPE = {"feature": "feature-plan.md", "chore": "feature-plan.md",
                    "bug": "bug-investigation.md", "refactor": "refactor-debt.md"}


def new_item(root: Path, type_: str, title: str, version: str | None = None) -> Path:
    if type_ not in TEMPLATE_BY_TYPE:
        raise ValueError(f"unknown type {type_!r}; choose from {sorted(TEMPLATE_BY_TYPE)}")
    cfg = read_config(root)
    item_id = cfg["nextId"]
    version = version or cfg["currentVersion"]
    slug = slugify(title)
    if not slug:
        raise ValueError(f"title {title!r} produces an empty slug; use alphanumeric characters")
    fname = f"plans/{item_id:03d}-{slug}.md"
    path = roadmap_dir(root) / fname
    atomic_write(path, _render_template(
        TEMPLATE_BY_TYPE[type_], ID=item_id, TITLE=title, TYPE=type_,
        VERSION=version, DATE=datetime.date.today().isoformat()))
    cfg["nextId"] += 1
    cfg["items"].append({"id": item_id, "slug": slug, "title": title,
                         "type": type_, "version": version, "file": fname})
    write_config(root, cfg)
    sync(root)
    return path


def release(root: Path, version: str, tag: bool = False) -> None:
    cfg = read_config(root)
    cfg["currentVersion"] = version
    write_config(root, cfg)
    sync(root)
    if tag or cfg["settings"].get("gitTagOnRelease"):
        result = subprocess.run(["git", "tag", f"v{version}"], cwd=str(root), check=False)
        if result.returncode != 0:
            print(f"Warning: 'git tag v{version}' failed (exit {result.returncode}); "
                  "version recorded in config but not tagged.", file=sys.stderr)


def status(root: Path) -> dict:
    cfg = read_config(root)
    items = []
    for item in cfg["items"]:
        path = roadmap_dir(root) / item["file"]
        done, total = count_progress(path) if path.exists() else (0, 0)
        pct = round(100 * done / total) if total else 0
        items.append({**item, "done": done, "total": total, "pct": pct,
                      "status": derive_status(done, total)})
    return {"project": cfg["project"], "currentVersion": cfg["currentVersion"],
            "items": items}


def import_file(root: Path, src: Path) -> list[Path]:
    extracted = []
    for line in src.read_text(encoding="utf-8").splitlines():
        sm = STEP_RE.match(line)
        if sm:
            extracted.append((sm.group(2).lower() == "x", sm.group(3).strip()))
    if not extracted:
        return []
    title = src.stem.replace("_", " ").replace("-", " ").title()
    path = new_item(root, "feature", f"Imported: {title}")
    text = path.read_text(encoding="utf-8")
    checklist = "\n".join(f"- [{'x' if done else ' '}] {txt}" for done, txt in extracted)
    text = re.sub(r"(## .*Checklist.*\n)(?:.*\n?)*", rf"\1{checklist}\n", text, count=1)
    atomic_write(path, text)
    sync(root)
    return [path]


def init_project(root: Path, name: str, adopt: bool = False) -> dict:
    rd = roadmap_dir(root)
    (rd / "plans").mkdir(parents=True, exist_ok=True)
    if (rd / "config.json").exists():
        cfg = read_config(root)                      # idempotent: keep items/version
    else:
        version = detect_version(root) if adopt else "0.0.1"
        cfg = {"project": name, "currentVersion": version, "nextId": 1,
               "items": [], "settings": {"autoCommit": True, "gitTagOnRelease": False}}
        write_config(root, cfg)
    roadmap_md = root / "ROADMAP.md"
    if not roadmap_md.exists():
        atomic_write(roadmap_md, _render_template("ROADMAP.md", PROJECT=cfg["project"]))
    elif AUTO_START not in roadmap_md.read_text(encoding="utf-8"):
        existing = roadmap_md.read_text(encoding="utf-8").rstrip()
        atomic_write(roadmap_md, f"{existing}\n\n{AUTO_START}\n{AUTO_END}\n")
    sync(root)
    return cfg


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="roadmap")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--name", default="My Project")
    p_init.add_argument("--adopt", action="store_true")

    p_new = sub.add_parser("new")
    p_new.add_argument("--type", required=True)
    p_new.add_argument("--title", required=True)
    p_new.add_argument("--version")

    p_check = sub.add_parser("check")
    p_check.add_argument("--plan", type=int, required=True)
    p_check.add_argument("--step", type=int)
    p_check.add_argument("--undo", action="store_true")
    p_check.add_argument("--all-done", action="store_true", dest="all_done")

    p_rel = sub.add_parser("release")
    p_rel.add_argument("--version", required=True)
    p_rel.add_argument("--tag", action="store_true")

    p_st = sub.add_parser("status")
    p_st.add_argument("--json", action="store_true", dest="as_json")

    sub.add_parser("sync")

    p_imp = sub.add_parser("import")
    p_imp.add_argument("path")

    args = parser.parse_args(argv)
    root = find_root(Path.cwd())
    if args.command == "init":
        init_project(root, args.name, adopt=args.adopt)
        print(f"Initialized roadmap at {root}")
        return 0
    if args.command == "new":
        path = new_item(root, args.type, args.title, args.version)
        print(path)
        return 0
    if args.command == "check":
        check_step(root, args.plan, args.step, undo=args.undo, all_done=args.all_done)
        return 0
    if args.command == "release":
        release(root, args.version, tag=args.tag)
        return 0
    if args.command == "sync":
        sync(root)
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
                print(f"  #{it['id']} {it['title']} [{it['type']}] "
                      f"{it['pct']}% ({it['status']})")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
