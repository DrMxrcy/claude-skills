#!/usr/bin/env python3
"""roadmap — deterministic CLI for the roadmap skill (Python 3 stdlib only)."""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, tempfile
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


def _render_template(name: str, **vars) -> str:
    text = (TEMPLATES_DIR / name).read_text()
    for k, v in vars.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def detect_version(root: Path) -> str:
    return "0.0.1"


def sync(root: Path) -> None:
    pass


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

    args = parser.parse_args(argv)
    root = find_root(Path.cwd())
    if args.command == "init":
        init_project(root, args.name, adopt=args.adopt)
        print(f"Initialized roadmap at {root}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
