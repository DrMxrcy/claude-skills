"""roadmap plan parsing — read plan .md files (checklist steps, frontmatter).
Pure/leaf layer: depends only on rmcore."""
from __future__ import annotations
import re
from pathlib import Path
from rmlib.core import read_config, roadmap_dir


STEP_RE = re.compile(r"^(\s*[-*]\s+)\[( |x|X)\](.*)$")

# Parse results are cached by (path, mtime, size). A short CLI run barely touches
# it, but a long-lived `serve` process re-parses only the plan that actually
# changed on each push instead of every plan on every status() call.
_CACHE: dict = {}


def _is_fence(line: str) -> bool:
    return line.lstrip().startswith("```")


def parse_plan(path: Path) -> dict:
    try:
        st = path.stat()
        key = (str(path), st.st_mtime_ns, st.st_size)
        hit = _CACHE.get(str(path))
        if hit and hit[0] == key:
            return hit[1]
    except OSError:
        key = None
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
    result = {"meta": meta, "steps": steps}
    if key is not None:
        _CACHE[str(path)] = (key, result)
    return result


def count_progress(path: Path) -> tuple[int, int]:
    steps = parse_plan(path)["steps"]
    return sum(1 for done, _ in steps if done), len(steps)


def _plan_path(root: Path, plan_id: int) -> Path:
    for item in read_config(root)["items"]:
        if item["id"] == plan_id:
            return roadmap_dir(root) / item["file"]
    raise ValueError(f"no plan with id {plan_id}")
