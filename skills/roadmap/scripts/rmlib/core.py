"""roadmap core — shared primitives (paths, config, versions, templates).
Lowest layer; imports only the stdlib so every other module can depend on it."""
from __future__ import annotations
import json, os, re, subprocess, tempfile
from pathlib import Path


# core.py lives in scripts/rmlib/, so templates/ and VERSION are three levels up.
TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
AUTO_START = "<!-- roadmap:auto:start -->"
AUTO_END = "<!-- roadmap:auto:end -->"

RULES_START = "<!-- roadmap:rules:start -->"
RULES_END = "<!-- roadmap:rules:end -->"
# Dual slash forms: Claude Code uses /roadmap:<cmd>; Grok (and other flat-command
# agents) use /roadmap-<cmd>. Bare /roadmap <cmd> also routes via the skill.
# This block is the always-on harness: same discipline for Claude, Grok, Codex, etc.
RULES_BLOCK = """<!-- roadmap:rules:start -->
## Roadmap tracking
This project uses the **roadmap** skill so AI coders (Claude Code, Grok Build, and others) stay **on-task** and ship **high-quality** code — not ad-hoc thrash. Living truth is **git**: `ROADMAP.md` + `.roadmap/` (plans, config) + `CHANGELOG*.md` via the deterministic CLI only.

### Surfaces (every agent)
- **Slash names — always offer BOTH when recommending a command** (agents mix these up):
  - Claude Code discovers **colon**: `/roadmap:status`, `/roadmap:build`, `/roadmap:next`
  - Grok Build discovers **hyphen only**: `/roadmap-status`, `/roadmap-build`, `/roadmap-next`
  - Bare space form works on either: `/roadmap status`, `/roadmap build 3`, `/roadmap next`
  - **Never tell a Grok user only `/roadmap:…`** — those do not appear in Grok's slash menu. Prefer writing `/roadmap:build` **·** `/roadmap-build` (or the bare form).
- **`--auto` is only for build** (item/version/empty selection), e.g. `/roadmap-build 1.2.0 --auto` or `/roadmap build 80 --auto`. **`next` has no `--auto`** — it always does exactly one item then stops. To chain items use `build` with `--auto`, not `next --auto`.
- **CLI resolve once:** probe `.claude|.grok|.agents` skills paths (project then `$HOME`); never hand-edit `ROADMAP.md`.

### Always on-task
- **Orient first:** at session start run `roadmap.py orient` (or `/roadmap:status` / `/roadmap-status`, or read `ROADMAP.md`) before writing code. SessionStart orient may inject this automatically.
- **Nothing off-roadmap:** features/bugs → `/roadmap:plan` / `/roadmap-plan` before coding; park ideas with `/roadmap:idea` / `/roadmap-idea` (one bullet; long write-ups → linked `.roadmap/notes/`). Promote with `/roadmap:promote` / `/roadmap-promote`.
- **Incubator hygiene:** the Idea Incubator may live in `ROADMAP.md` or an external file (`settings.incubatorFile`, usually `.roadmap/IDEAS.md`) — the CLI resolves it; never hardcode the location. When it gets messy, groom with `/roadmap:tidy` / `/roadmap-tidy` (prose → notes files, curate ideas vs the roadmap; `tidy --externalize` moves it out of `ROADMAP.md`).
- **One item at a time.** Active plan in `.roadmap/plans/` required for functional code. No multitasking across features/bugs. Respect `dependsOn` (`roadmap.py next` skips blocked items).
- **Specs are law:** follow each plan's linked Spec / Detailed plan; the checklist is the tracker, not the design.

### Quality-first build (default for `/roadmap:build` / `/roadmap-build`, including `--auto`)
- Per checklist step: optional **explore** research → **one** implementer subagent → **spec review** subagent → **quality review** subagent → parent runs real build/tests → only then `roadmap.py check` → **micro-commit code+roadmap immediately** (one commit per checked step).
- **Parent owns all `roadmap.py` calls**; children never edit `ROADMAP.md` or run `check`.
- **No parallel implementers** on the same working tree by default (conflicts hide bugs).
- **`--auto`** skips *user* pauses between items only — **never** skip reviews or tests.
- Prefer superpowers `subagent-driven-development` when available; else native subagents (Grok `spawn_subagent`, Claude Task).

### Multi-coder sync & rate limits
- **Git is the shared brain** across Claude ↔ Grok ↔ any agent. Chat memory is not a plan.
- **Formal `handoff` is optional.** Rate limits, crashes, and killed sessions are normal.
- **Micro-commit after every successful `check`** so a rate-limit loses at most the in-flight step, never a whole item.
- **Abrupt switch / resume (no prior handoff):** open the other agent in the same repo → `git status` (commit any left code+roadmap) → `roadmap.py orient` or `handoff` (SessionStart orient counts) → if drift, `/roadmap:catchup` / `/roadmap-catchup` after tests → continue from the **next unchecked plan step** via `/roadmap:next` / `/roadmap-next` or build. Do **not** re-derive the plan from the dead chat.
- **Ideal leave (when you can):** after a checked step commit is already done; optional `roadmap.py handoff` + `git push`.
- **Never** maintain a private parallel plan outside `.roadmap/`.

### Integrity
- **Never hand-edit `ROADMAP.md`.** Use CLI / `/roadmap:done` / `/roadmap-done`.
- **Catchup** only after verifying tests for steps done outside the loop.
- **Ship clean:** before release, `/roadmap:review` / `/roadmap-review` (spec + code review); curate public notes via changelog/audience.
<!-- roadmap:rules:end -->"""

# Agent-neutral project instruction files that receive the same rules block.
RULES_FILES = ("CLAUDE.md", "AGENTS.md")


def get_version() -> str:
    vf = Path(__file__).resolve().parent.parent.parent / "VERSION"
    return vf.read_text(encoding="utf-8").strip() if vf.exists() else "unknown"


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


def _norm_version(v: str) -> str:
    """Canonical internal version form: trimmed, no leading 'v' (renderers add it)."""
    v = v.strip()
    if v[:1] in ("v", "V"):
        v = v[1:]
    return v


def _version_key(v: str):
    try:
        return (0, tuple(int(p) for p in v.split(".")))
    except ValueError:
        return (1, v)
