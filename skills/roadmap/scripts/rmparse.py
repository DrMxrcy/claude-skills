"""roadmap plan parsing — read plan .md files (checklist steps, frontmatter).
Pure/leaf layer: depends only on rmcore."""
from __future__ import annotations
import re
from pathlib import Path
from rmcore import read_config, roadmap_dir


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
