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
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_config(root: Path) -> dict:
    return json.loads((roadmap_dir(root) / "config.json").read_text())


def write_config(root: Path, cfg: dict) -> None:
    atomic_write(roadmap_dir(root) / "config.json", json.dumps(cfg, indent=2) + "\n")


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower())
    return s.strip("-")


def _render_template(name: str, **values) -> str:
    text = (TEMPLATES_DIR / name).read_text()
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def detect_version(root: Path) -> str:
    return "0.0.1"


def sync(root: Path) -> None:
    pass


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


def init_project(root: Path, name: str, adopt: bool = False) -> dict:
    version = detect_version(root) if adopt else "0.0.1"
    rd = roadmap_dir(root)
    (rd / "plans").mkdir(parents=True, exist_ok=True)
    cfg = {"project": name, "currentVersion": version, "nextId": 1,
           "items": [], "settings": {"autoCommit": True, "gitTagOnRelease": False}}
    write_config(root, cfg)
    roadmap_md = root / "ROADMAP.md"
    if not roadmap_md.exists():
        atomic_write(roadmap_md, _render_template("ROADMAP.md", PROJECT=name, VERSION=version))
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
