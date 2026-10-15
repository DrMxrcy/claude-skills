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
# Agent-native forms: Claude Code uses /roadmap:<cmd>, Grok uses /roadmap-<cmd>,
# and Codex invokes the skill as $roadmap <cmd>.
# This block is the always-on harness: same discipline for Claude, Grok, Codex, etc.
RULES_BLOCK = """<!-- roadmap:rules:start -->
## Roadmap tracking
This project uses the **roadmap** skill to stay on-task and ship **high-quality** code. Truth lives in **git** — `ROADMAP.md` + `.roadmap/` (plans, config) + `CHANGELOG*.md` — written by the `roadmap.py` CLI only. This block is the compact core; load the long-form files below when you need the detail.

### Core rules
- **Orient first:** run `roadmap.py orient` (or roadmap status, or read `ROADMAP.md`) before writing code. A SessionStart hook may do it for you.
- **Nothing off-roadmap:** features/bugs get a plan first (`/roadmap:plan` **·** `/roadmap-plan`); park stray ideas (`/roadmap:idea` **·** `/roadmap-idea`) instead of building them.
- **One item at a time**, with an active plan file in `.roadmap/plans/` — no functional code without one, no multitasking across features/bugs. The plan's Spec / ✅ Acceptance is the definition of done; the checklist is only the tracker.
- **Test before you check:** run the real build/tests for a step, then `roadmap.py check`.
- **Micro-commit** code + roadmap together right after every checked step, so an interrupted session loses at most the in-flight step.
- **Never hand-edit `ROADMAP.md`** or `.roadmap/` state — CLI only (`/roadmap:done` **·** `/roadmap-done`); never keep a private plan outside `.roadmap/`.
- **Quality-first build** (default for `/roadmap:build` **·** `/roadmap-build`, including `--auto`): per step, one `executor` implementer (opus) → **spec review** by `scout` (haiku, acceptance list) → **one** `verifier` quality review (opus; second pass only for high-risk steps) → parent runs the tests → `check`. Never spawn an unlabeled `general-purpose` child — it inherits the frontier model. **Workers unavailable or prohibited** (Codex, Gemini, Kimi, Copilot, restricted sessions — session rules win over routing): the parent continues the authorized work as sole writer, then runs a separate spec-compliance pass and a separate code-quality pass itself, using permitted read-only reviewers where offered; record in the evidence which passes were independent and which were self-review, never claim a review that did not happen; same scope, test gates, and micro-commits; worker unavailability alone never blocks or justifies abandoning the task; stay in the host's native tools, never switch coders mid-task. The parent owns every `roadmap.py` call; `--auto` skips *user* pauses only, never reviews or tests.

### Invoking it
- **Resolve the CLI once:** probe `.claude|.grok|.agents` skills paths (project, then `$HOME`) for `skills/roadmap/scripts/roadmap.py`.
- **Slash names differ per agent:** Claude Code `/roadmap:build`, Grok Build **hyphen only** `/roadmap-build`, Codex `$roadmap build`. **Never quote colon-only names to a Grok user** — they do not appear in its menu; write `/roadmap:build` **·** `/roadmap-build` or the bare `/roadmap build`.
- **`--auto` is a `build` flag only.** **`next` has no `--auto`** — it does exactly one item and stops; chain items with `build --auto`.

### Long-form (load on demand, don't inline here)
- Build protocol, agent switching / rate-limit resume, incubator hygiene, release + changelog flow: the roadmap skill's `SKILL.md` and `references/quality-build.md`.
- Files, config settings, and invariants: the skill's `references/state-model.md`.
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


TYPE_PREFIX = {"feature": "FEAT", "bug": "BUG", "refactor": "REF", "chore": "CHORE"}


def display_id(item: dict) -> str:
    """Human-readable id (FEAT-12, BUG-7) for CLI/dashboard output only. The int
    `id` stays the source of truth in config.json, ROADMAP.md, and changelogs."""
    return f"{TYPE_PREFIX.get(item.get('type'), 'ITEM')}-{item['id']}"


ID_HELP = "item id — 7, #7 or BUG-7"
IDS_HELP = "comma-separated item ids — 7,#8,BUG-9"
_ID_RE = re.compile(r"^(?:#|(?P<prefix>[A-Za-z]+)-)?(?P<num>\d+)$")


def resolve_id(cfg: dict, token: str | int) -> int:
    """Turn a user-typed item id (`7`, `#7`, `BUG-7`, case-insensitive) into the
    int id. A typed prefix must match the item's actual type; `ITEM-` matches any.
    Unknown numbers pass through so the caller raises its own 'no plan' error."""
    if isinstance(token, int):
        return token
    m = _ID_RE.match(str(token).strip())
    if not m:
        raise ValueError(f"bad item id {token!r} — use 7, #7 or BUG-7")
    num = int(m.group("num"))
    prefix = (m.group("prefix") or "").upper()
    if not prefix or prefix == "ITEM":
        return num
    want = next((t for t, p in TYPE_PREFIX.items() if p == prefix), None)
    if want is None:
        raise ValueError(f"unknown id prefix {prefix!r} — use "
                         + "/".join(TYPE_PREFIX.values()) + " or ITEM")
    item = next((i for i in cfg.get("items", []) if i.get("id") == num), None)
    if item is None:
        raise ValueError(f"no plan with id {num}")
    if item.get("type") != want:
        raise ValueError(f"no {want} #{num} — did you mean {display_id(item)}?")
    return num


def resolve_ids(cfg: dict, tokens: str) -> list[int]:
    """Same as resolve_id for a comma-separated list (empty string -> [])."""
    return [resolve_id(cfg, t) for t in tokens.split(",") if t.strip()]


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
