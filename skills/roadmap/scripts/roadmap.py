#!/usr/bin/env python3
"""roadmap — deterministic CLI for the roadmap skill (Python 3 stdlib only)."""
from __future__ import annotations
import argparse, datetime, json, os, re, subprocess, sys, tempfile
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
AUTO_START = "<!-- roadmap:auto:start -->"
AUTO_END = "<!-- roadmap:auto:end -->"

RULES_START = "<!-- roadmap:rules:start -->"
RULES_END = "<!-- roadmap:rules:end -->"
RULES_BLOCK = """<!-- roadmap:rules:start -->
## Roadmap tracking
This project tracks work in `ROADMAP.md` via the **roadmap** skill (`/roadmap:*` commands).
- At the start of a work session, run `/roadmap:status` (or read `ROADMAP.md`) to see current progress before continuing.
- New features or found bugs become roadmap items via `/roadmap:plan` before coding; park stray ideas in the Idea Incubator — nothing is built off-roadmap.
- No functional code without an active plan in `.roadmap/plans/`. Work one checklist item at a time; do not multitask across features/bugs.
- When building an item, follow its linked Spec / Detailed plan as the authoritative how-to (the checklist is just the tracker).
- Mark a step done only after its build/tests pass, and commit the code + roadmap update together; if work was done outside the commands, run `/roadmap:catchup` to reconcile.
- Update status only through the roadmap CLI / `/roadmap:done`; never hand-edit `ROADMAP.md`.
<!-- roadmap:rules:end -->"""


def get_version() -> str:
    vf = Path(__file__).resolve().parent.parent / "VERSION"
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


def render_region(cfg: dict, progress: dict) -> str:
    by_version: dict[str, list] = {}
    for item in cfg["items"]:
        by_version.setdefault(item["version"], []).append(item)
    lines = ["## 📊 Versions", ""]
    for version in sorted(by_version, key=_version_key):
        items = sorted(by_version[version],
                       key=lambda i: (i.get("order", i["id"]), i["id"]))
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


def sync(root: Path, quiet: bool = False) -> None:
    cfg = read_config(root)
    # Self-heal: enforce the canonical (no-'v') version form on stored data so a
    # project written before normalization (e.g. a `--version v1.0.0` that produced
    # `vv1.0.0`) repairs itself on the next sync.
    changed = False
    if _norm_version(cfg["currentVersion"]) != cfg["currentVersion"]:
        cfg["currentVersion"] = _norm_version(cfg["currentVersion"])
        changed = True
    for item in cfg["items"]:
        nv = _norm_version(item["version"])
        if nv != item["version"]:
            item["version"] = nv
            changed = True
            path = roadmap_dir(root) / item["file"]
            if path.exists():
                _set_frontmatter(path, "version", nv)
    if changed:
        write_config(root, cfg)
    progress = {}
    for item in cfg["items"]:
        path = roadmap_dir(root) / item["file"]
        if path.exists():
            done, total = count_progress(path)
            progress[item["id"]] = (done, total)
            _set_frontmatter(path, "status", derive_status(done, total))
    # stamp a completion date the first time a version reaches 100% (deterministic changelog)
    version_dates = cfg.setdefault("versionDates", {})
    by_version: dict[str, list] = {}
    for item in cfg["items"]:
        by_version.setdefault(item["version"], []).append(item)
    for version, vitems in by_version.items():
        if version in version_dates:
            continue
        if vitems and all(progress.get(i["id"], (0, 0))[1] > 0
                          and progress.get(i["id"], (0, 0))[0] == progress.get(i["id"], (0, 0))[1]
                          for i in vitems):
            version_dates[version] = datetime.date.today().isoformat()
            changed = True
    # drop dates for versions that no longer have any items (e.g. after a retarget)
    for stale in [v for v in version_dates if v not in by_version]:
        del version_dates[stale]
        changed = True
    if changed:
        write_config(root, cfg)
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
    public_text, warnings = render_public_changelog(root)
    atomic_write(root / "CHANGELOG.md", public_text)
    atomic_write(root / "CHANGELOG.internal.md", render_internal_changelog(root))
    if not quiet:
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)


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


def new_item(root: Path, type_: str, title: str, version: str | None = None,
             note: str = "", audience: str | None = None) -> Path:
    if type_ not in TEMPLATE_BY_TYPE:
        raise ValueError(f"unknown type {type_!r}; choose from {sorted(TEMPLATE_BY_TYPE)}")
    cfg = read_config(root)
    item_id = cfg["nextId"]
    version = _norm_version(version or cfg["currentVersion"])
    slug = slugify(title)
    if not slug:
        raise ValueError(f"title {title!r} produces an empty slug; use alphanumeric characters")
    fname = f"plans/{item_id:03d}-{slug}.md"
    path = roadmap_dir(root) / fname
    atomic_write(path, _render_template(
        TEMPLATE_BY_TYPE[type_], ID=item_id, TITLE=title, TYPE=type_,
        VERSION=version, DATE=datetime.date.today().isoformat()))
    cfg["nextId"] += 1
    item = {"id": item_id, "slug": slug, "title": title,
            "type": type_, "version": version, "file": fname}
    if note:
        item["note"] = note            # user-facing changelog line (optional)
    if audience in ("public", "internal"):
        item["audience"] = audience    # else falls back to DEFAULT_AUDIENCE by type
    cfg["items"].append(item)
    write_config(root, cfg)
    sync(root)
    return path


def set_note(root: Path, plan_id: int, text: str) -> None:
    """Set an item's user-facing changelog note, then re-render. If the item renders to the
    PUBLIC changelog, lint the note for internal language and warn (non-blocking)."""
    cfg = read_config(root)
    for item in cfg["items"]:
        if item["id"] == plan_id:
            item["note"] = text
            write_config(root, cfg)
            if item_audience(item) == "public":
                tells = lint_note(text, cfg.get("settings", {}).get("internalTerms", []))
                if tells:
                    print(f"warning: #{plan_id} note reads internal ({', '.join(tells)}); "
                          f"CHANGELOG.md is user-facing. Rephrase in plain benefit language, "
                          f"or mark it internal: roadmap audience --plan {plan_id} --to internal",
                          file=sys.stderr)
            sync(root)
            return
    raise ValueError(f"no plan with id {plan_id}")


def set_audience(root: Path, plan_id: int, audience: str) -> None:
    """Set an item's changelog audience ('public' | 'internal'), then re-render both files."""
    if audience not in ("public", "internal"):
        raise ValueError("audience must be 'public' or 'internal'")
    cfg = read_config(root)
    for item in cfg["items"]:
        if item["id"] == plan_id:
            item["audience"] = audience
            write_config(root, cfg)
            sync(root)
            return
    raise ValueError(f"no plan with id {plan_id}")


def set_depends(root: Path, plan_id: int, on: list[int], clear: bool = False) -> None:
    """Set (or clear) an item's `dependsOn` list. Advisory ordering metadata consumed by
    /roadmap:reevaluate and retargeted by merge/remove."""
    cfg = read_config(root)
    by_id = {i["id"]: i for i in cfg["items"]}
    if plan_id not in by_id:
        raise ValueError(f"no plan with id {plan_id}")
    if clear:
        by_id[plan_id].pop("dependsOn", None)
        write_config(root, cfg)
        return
    if plan_id in on:
        raise ValueError(f"plan #{plan_id} cannot depend on itself")
    for d in on:
        if d not in by_id:
            raise ValueError(f"no plan with id {d}")
    by_id[plan_id]["dependsOn"] = list(dict.fromkeys(on))
    write_config(root, cfg)


INCUBATOR_RE = re.compile(r"(?im)^#{1,6}\s+.*idea incubator.*$")


def _incubator_stub(root: Path, plan_id: int, title: str, archived: str | None = None) -> None:
    """Append a breadcrumb for a removed item under the free-form Idea Incubator heading,
    linking the archived plan file when one was kept. Edits ROADMAP.md directly (outside the
    roadmap:auto markers, which sync owns)."""
    rm = root / "ROADMAP.md"
    text = rm.read_text(encoding="utf-8")
    stub = f"- (was #{plan_id}) {title}"
    if archived:
        stub += f" ([archived plan]({archived}))"
    m = INCUBATOR_RE.search(text)
    if m:
        new = text[:m.end()] + "\n" + stub + text[m.end():]
    else:
        new = text.rstrip() + f"\n\n## 💡 Idea Incubator\n{stub}\n"
    atomic_write(rm, new)


def remove_item(root: Path, plan_id: int) -> None:
    """Remove a tracked item: archive its plan file, drop it from the registry, clear any
    dependency that pointed at it, and demote it to the Idea Incubator. Reversible."""
    cfg = read_config(root)
    by_id = {i["id"]: i for i in cfg["items"]}
    if plan_id not in by_id:
        raise ValueError(f"no plan with id {plan_id}")
    item = by_id[plan_id]
    dependents = [i["id"] for i in cfg["items"] if plan_id in (i.get("dependsOn") or [])]
    if dependents:
        print(f"Warning: #{dependents} depended on #{plan_id}; clearing that link.",
              file=sys.stderr)
    src = roadmap_dir(root) / item["file"]
    archived = None
    if src.exists():
        dest = roadmap_dir(root) / "archive" / Path(item["file"]).name
        atomic_write(dest, src.read_text(encoding="utf-8"))
        src.unlink()
        archived = str(dest.relative_to(root))
    cfg["items"] = [i for i in cfg["items"] if i["id"] != plan_id]
    for i in cfg["items"]:
        deps = i.get("dependsOn")
        if deps and plan_id in deps:
            new = [d for d in deps if d != plan_id]
            if new:
                i["dependsOn"] = new
            else:
                i.pop("dependsOn", None)
    write_config(root, cfg)
    _incubator_stub(root, plan_id, item["title"], archived)
    sync(root)


def retarget(root: Path, to: str, from_versions: list[str] | None = None,
             plan_ids: list[int] | None = None) -> None:
    """Re-stamp existing items onto version `to`. Select either by source versions
    (`from_versions`) or by item ids (`plan_ids`) — exactly one. Used to consolidate work
    spread across versions (e.g. fold v1.0.0–v1.6.0 into a single v1.0.0 on a release branch).
    Leaves currentVersion untouched; the git branch is the caller's workflow."""
    if bool(from_versions) == bool(plan_ids):
        raise ValueError("pass exactly one of from_versions / plan_ids")
    to = _norm_version(to)
    cfg = read_config(root)
    by_id = {i["id"]: i for i in cfg["items"]}
    if plan_ids:
        for pid in plan_ids:
            if pid not in by_id:
                raise ValueError(f"no plan with id {pid}")
        selected = [by_id[pid] for pid in plan_ids]
    else:
        wanted = {_norm_version(v) for v in from_versions}
        present = {i["version"] for i in cfg["items"]}
        for v in wanted - present:
            print(f"Warning: no items in version {v}; skipping.", file=sys.stderr)
        selected = [i for i in cfg["items"] if i["version"] in wanted]
    if not selected:
        raise ValueError("retarget selected no items")
    for item in selected:
        item["version"] = to
        path = roadmap_dir(root) / item["file"]
        if path.exists():
            _set_frontmatter(path, "version", to)
    write_config(root, cfg)
    sync(root)


def reorder(root: Path, version: str, ids: list[int]) -> None:
    """Set explicit display/build order for items within a version."""
    version = _norm_version(version)
    cfg = read_config(root)
    in_version = {i["id"] for i in cfg["items"] if i["version"] == version}
    stray = [i for i in ids if i not in in_version]
    if stray:
        raise ValueError(f"id(s) {stray} are not in version {version}")
    pos = {iid: n for n, iid in enumerate(ids)}
    for item in cfg["items"]:
        if item["id"] in pos:
            item["order"] = pos[item["id"]]
    write_config(root, cfg)
    sync(root)


def merge_items(root: Path, keep_id: int, source_ids: list[int]) -> None:
    """Combine `source_ids` into `keep_id`: append their checklist steps to the keeper's
    plan, delete the source plans, drop them from the registry, and retarget any
    dependency that pointed at a source to the keeper. Used to dedupe/consolidate."""
    if keep_id in source_ids:
        raise ValueError(f"keeper #{keep_id} cannot be in the sources")
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("duplicate source ids")
    cfg = read_config(root)
    by_id = {i["id"]: i for i in cfg["items"]}
    for iid in [keep_id, *source_ids]:
        if iid not in by_id:
            raise ValueError(f"no plan with id {iid}")
    keep_path = roadmap_dir(root) / by_id[keep_id]["file"]
    appended = []
    for sid in source_ids:
        src = by_id[sid]
        sp = roadmap_dir(root) / src["file"]
        if sp.exists():
            steps = parse_plan(sp)["steps"]
            appended.append(f"\n## Merged from #{sid} {src['title']}\n")
            appended += [f"- [{'x' if done else ' '}] {txt}" for done, txt in steps]
            sp.unlink()
    if appended:
        atomic_write(keep_path, keep_path.read_text(encoding="utf-8").rstrip()
                     + "\n" + "\n".join(appended) + "\n")
    drop = set(source_ids)
    cfg["items"] = [i for i in cfg["items"] if i["id"] not in drop]
    for item in cfg["items"]:                       # retarget dependencies to the keeper
        deps = item.get("dependsOn")
        if deps:
            new = [keep_id if d in drop else d for d in deps]
            new = [d for d in dict.fromkeys(new) if d != item["id"]]
            if new:
                item["dependsOn"] = new
            else:
                item.pop("dependsOn", None)
    write_config(root, cfg)
    sync(root)


def _incomplete_items(root: Path, version: str) -> list[dict]:
    out = []
    for item in read_config(root)["items"]:
        if item["version"] == version:
            p = roadmap_dir(root) / item["file"]
            done, total = count_progress(p) if p.exists() else (0, 0)
            if not (total > 0 and done == total):
                out.append(item)
    return out


# type → user-facing changelog section (App Store / website friendly)
TYPE_SECTION = {"feature": "✨ New", "bug": "🐛 Fixed",
                "refactor": "⚡ Improved", "chore": "⚡ Improved"}
SECTION_ORDER = ["✨ New", "🐛 Fixed", "⚡ Improved"]

# Unset `audience` falls back to this per-type default. The AI sets `audience` explicitly
# via the roadmap commands; this is only the safety net at render time.
DEFAULT_AUDIENCE = {"feature": "public", "bug": "public",
                    "refactor": "internal", "chore": "internal"}
# One-line stand-in shown in the PUBLIC changelog when a version shipped internal-only
# work, instead of listing it.
ROLLUP_LINE = "_Plus behind-the-scenes performance and reliability work._"

# Internal "tells" that should never appear in a PUBLIC note. Matched case-insensitively
# as whole words; the vendor list is extendable via settings.internalTerms.
INTERNAL_VENDORS = [
    "convex", "sentry", "aptabase", "codex", "eas", "clerk", "supabase", "firebase",
    "vercel", "netlify", "cloudflare", "r2", "s3", "docker", "kubernetes", "k8s",
    "redis", "postgres", "postgresql", "mysql", "mongodb", "stripe", "github actions",
    "expo", "webpack", "vite", "prisma", "graphql", "grpc",
]
INTERNAL_JARGON = [
    "refactor", "schema", "migration", "mutation", "endpoint", "backend", "frontend",
    "polling", "cron", "webhook", "ci", "lint", "linter", "env var",
    "environment variable", "api key", "n+1", "regression",
]
# Softer "dev summary" phrasing — process, security, and architecture words that read like a
# changelog written for engineers, not users. These are the tells a vendor/path scan misses
# (e.g. "pre-launch hardening pass", "lays the groundwork", "privilege misuse").
INTERNAL_PHRASING = [
    "hardening", "hardened", "groundwork", "pre-launch", "prelaunch", "privilege",
    "spam/abuse", "reusable", "scaffolding", "boilerplate", "rearchitect", "re-architect",
    "static-page", "sitemap", "robots rules", "robots.txt", "closed gaps", "headliner index",
    "walk-through", "walkthrough index", "data feed", "data feeds", "groundwork for",
    "public url", "public urls", "expiring link", "expiring links", "signed url",
    "signed urls", "vulnerability", "exploit", "under the hood",
    "structured data", "metadata", "search-optimized", "search optimized", "seo",
]
# Wrong-audience tells: admin/operator-only surfaces, and compliance/legal gates. These are
# "user-facing" to staff or to regulators — not to the end users who read a public changelog.
INTERNAL_SCOPE = [
    "admin", "admins", "admin panel", "admin console", "admin area", "admin dashboard",
    "moderation", "moderator", "moderators", "audit trail", "audit log", "role-gated", "cms",
    "compliance", "coppa", "gdpr", "age gate", "age-gate", "age verification", "13-and-up",
    "13 and up", "underage", "minimum age", "eula", "terms acceptance", "community guidelines",
]


def item_audience(item: dict) -> str:
    """An item's effective audience: explicit `audience` if set, else the per-type default."""
    a = item.get("audience")
    return a if a in ("public", "internal") else DEFAULT_AUDIENCE.get(item["type"], "internal")


def lint_note(text: str, extra_terms: list[str] | None = None) -> list[str]:
    """Return the 'internal tells' found in a would-be PUBLIC changelog note — issue refs,
    source-file paths, vendor/tool names, and dev jargon. Empty list == looks clean.
    Advisory only: callers warn, they never block."""
    hits: list[str] = []
    hits += re.findall(r"#\d+", text)                                  # issue refs (#77)
    hits += re.findall(r"\b[\w.-]+\.(?:ts|tsx|js|jsx|mjs|cjs|py|go|rs|java|rb|php|"
                       r"json|ya?ml|toml|sql|sh|css|scss)\b", text)    # foo/bar.ts
    hits += re.findall(r"\b\w+(?:/\w+){2,}\b", text)                   # a/b/c paths
    low = text.lower()
    terms = [*INTERNAL_VENDORS, *INTERNAL_JARGON, *INTERNAL_PHRASING, *INTERNAL_SCOPE,
             *(extra_terms or [])]
    hits += [t for t in terms if re.search(r"\b" + re.escape(t.lower()) + r"\b", low)]
    seen, uniq = set(), []                                            # de-dupe, keep order
    for h in hits:
        if h.lower() not in seen:
            seen.add(h.lower())
            uniq.append(h)
    return uniq


def _changelog_versions(root: Path) -> list[tuple[str, str, list[dict]]]:
    """Shared scaffold for both changelog renderers. Returns (version, header, rows) per
    version (newest first), where each row is {'item', 'complete'} and `header` is the
    '## v.. — ..' line. A version is dated once all its items reach 100% (date persisted in
    config.versionDates); otherwise it renders '(in progress)'."""
    cfg = read_config(root)
    version_dates = cfg.get("versionDates", {})
    by_version: dict[str, list] = {}
    for item in cfg["items"]:
        by_version.setdefault(item["version"], []).append(item)
    blocks = []
    for version in sorted(by_version, key=_version_key, reverse=True):
        rows, done_all = [], True
        for it in sorted(by_version[version], key=lambda i: i["id"]):
            p = roadmap_dir(root) / it["file"]
            done, total = count_progress(p) if p.exists() else (0, 0)
            complete = total > 0 and done == total
            done_all = done_all and complete
            rows.append({"item": it, "complete": complete})
        date = version_dates.get(version)
        if done_all and date:
            header = f"## v{version} — {date}"
        elif done_all:
            header = f"## v{version}"
        else:
            header = f"## v{version} — (in progress)"
        blocks.append((version, header, rows))
    return blocks


def _grouped_lines(entries: dict[str, list[tuple[bool, str]]]) -> list[str]:
    """Render section-grouped '- label' / '- (pending) label' lines from {section: [(complete, label)]}."""
    lines = []
    for section in SECTION_ORDER:
        items = entries.get(section)
        if not items:
            continue
        lines.append(f"### {section}")
        lines += [f"- {label}" if complete else f"- (pending) {label}"
                  for complete, label in items]
        lines.append("")
    return lines


def render_public_changelog(root: Path) -> tuple[str, list[str]]:
    """Render the PUBLIC CHANGELOG.md: only audience=public items, rendered from their
    user-facing `note` ONLY (never the raw title). A public item with no note is skipped;
    if it has already shipped (complete) that omission is returned as a warning. Versions
    that also shipped internal-only work get one roll-up line instead of listing it.
    Returns (markdown, warnings)."""
    warnings: list[str] = []
    out = ["# Changelog", ""]
    for _version, header, rows in _changelog_versions(root):
        sections: dict[str, list[tuple[bool, str]]] = {}
        has_internal = False
        for row in rows:
            it = row["item"]
            if item_audience(it) != "public":
                has_internal = True
                continue
            note = it.get("note")
            if not note:
                if row["complete"]:
                    warnings.append(
                        f"#{it['id']} \"{it['title']}\" is public but has no note; "
                        f"omitted from CHANGELOG.md. Add one: "
                        f"roadmap note --plan {it['id']} --text \"...\"")
                continue
            section = TYPE_SECTION.get(it["type"], "⚡ Improved")
            sections.setdefault(section, []).append((row["complete"], note))
        lines = _grouped_lines(sections)
        if has_internal:
            lines += [ROLLUP_LINE, ""]
        if not lines:
            continue                       # nothing public to show for this version
        out += [header, "", *lines]
    return "\n".join(out).rstrip() + "\n", warnings


def render_internal_changelog(root: Path) -> str:
    """Render the INTERNAL CHANGELOG.internal.md: every item, every section, using each
    item's `note` and falling back to the raw title — the full dev-facing work log."""
    out = ["# Changelog (internal)", "",
           "_Full work log — every item, including internal/dev work. "
           "The curated public changelog is CHANGELOG.md._", ""]
    for _version, header, rows in _changelog_versions(root):
        sections: dict[str, list[tuple[bool, str]]] = {}
        for row in rows:
            it = row["item"]
            section = TYPE_SECTION.get(it["type"], "⚡ Improved")
            sections.setdefault(section, []).append(
                (row["complete"], it.get("note") or it["title"]))
        lines = _grouped_lines(sections)
        if lines:
            out += [header, "", *lines]
    return "\n".join(out).rstrip() + "\n"


def audit_public_notes(root: Path) -> list[str]:
    """Full pre-release audit of the public changelog: flag every public item missing a
    note, and lint existing public notes for internal language. Used by /roadmap:changelog."""
    cfg = read_config(root)
    extra = cfg.get("settings", {}).get("internalTerms", [])
    msgs = []
    for it in sorted(cfg["items"], key=lambda i: i["id"]):
        if item_audience(it) != "public":
            continue
        note = it.get("note")
        if not note:
            msgs.append(f"#{it['id']} \"{it['title']}\" (public) has no note — "
                        f"add one, or mark it internal: roadmap audience --plan {it['id']} --to internal")
            continue
        tells = lint_note(note, extra)
        if tells:
            msgs.append(f"#{it['id']} note reads internal ({', '.join(tells)}): \"{note}\"")
        # The note may read clean while the work is actually admin-only, a compliance gate, or
        # otherwise internal — the planning title usually still carries that signal.
        title_only = [t for t in lint_note(it["title"], extra) if t not in tells]
        if title_only:
            msgs.append(f"#{it['id']} note looks clean but its title suggests internal/admin "
                        f"scope ({', '.join(title_only)}) — confirm it's really public: \"{it['title']}\"")
    return msgs


def backfill_changelog(root: Path) -> None:
    """For each version lacking a recorded date, adopt its matching git tag's commit date
    (git tag v<ver>). Versions without a tag stay undated. Then re-sync to re-render."""
    cfg = read_config(root)
    version_dates = cfg.setdefault("versionDates", {})
    changed = False
    for version in {i["version"] for i in cfg["items"]}:
        if version in version_dates:
            continue
        out = subprocess.run(["git", "log", "-1", "--format=%cs", f"v{version}"],
                             cwd=str(root), capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            version_dates[version] = out.stdout.strip()
            changed = True
    if changed:
        write_config(root, cfg)
    sync(root)


def release(root: Path, version: str, tag: bool = False, force: bool = False) -> None:
    version = _norm_version(version)
    cfg = read_config(root)
    outgoing = cfg["currentVersion"]
    incomplete = _incomplete_items(root, outgoing)
    if incomplete and not force:
        names = ", ".join(f"#{i['id']} {i['title']}" for i in incomplete)
        raise ValueError(
            f"v{outgoing} still has incomplete items: {names}. "
            f"Finish them (see /roadmap:review) or pass --force.")
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
    in_fence = False
    for line in src.read_text(encoding="utf-8").splitlines():
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        sm = STEP_RE.match(line)
        if sm:
            extracted.append((sm.group(2).lower() == "x", sm.group(3).strip()))
    if not extracted:
        return []
    title = src.stem.replace("_", " ").replace("-", " ").title()
    path = new_item(root, "feature", f"Imported: {title}")
    text = path.read_text(encoding="utf-8")
    checklist = "\n".join(f"- [{'x' if done else ' '}] {txt}" for done, txt in extracted)
    new_text, n = re.subn(r"(## .*Checklist.*\n)(?:.*\n?)*",
                          lambda m: m.group(1) + checklist + "\n", text, count=1)
    if n == 0:
        raise ValueError("plan template has no Checklist section to populate")
    atomic_write(path, new_text)
    sync(root)
    return [path]


def ensure_claude_md_rules(root: Path) -> Path:
    """Idempotently add the roadmap rules block to CLAUDE.md (creating it if absent).

    Runs on every init so the always-on guardrails land in the project regardless of
    how the skill was installed (install.sh, `npx skills add`, or a manual copy).
    """
    path = root / "CLAUDE.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if RULES_START in existing and RULES_END in existing:
        after = existing.split(RULES_END, 1)[1].lstrip("\n")
        new = existing.split(RULES_START)[0] + RULES_BLOCK + "\n" + after
    elif existing.strip():
        new = existing.rstrip() + "\n\n" + RULES_BLOCK + "\n"
    else:
        new = RULES_BLOCK + "\n"
    atomic_write(path, new)
    return path


def init_project(root: Path, name: str, adopt: bool = False, claude_md: bool = True) -> dict:
    rd = roadmap_dir(root)
    (rd / "plans").mkdir(parents=True, exist_ok=True)
    if (rd / "config.json").exists():
        cfg = read_config(root)                      # idempotent: keep items/version
    else:
        version = _norm_version(detect_version(root) if adopt else "0.0.1")
        cfg = {"project": name, "currentVersion": version, "nextId": 1,
               "items": [], "settings": {"autoCommit": True, "gitTagOnRelease": False}}
        write_config(root, cfg)
    roadmap_md = root / "ROADMAP.md"
    if not roadmap_md.exists():
        atomic_write(roadmap_md, _render_template("ROADMAP.md", PROJECT=cfg["project"]))
    elif AUTO_START not in roadmap_md.read_text(encoding="utf-8"):
        existing = roadmap_md.read_text(encoding="utf-8").rstrip()
        atomic_write(roadmap_md, f"{existing}\n\n{AUTO_START}\n{AUTO_END}\n")
    if claude_md:
        ensure_claude_md_rules(root)
    sync(root)
    return cfg


def upgrade(root: Path) -> None:
    """Project-level: refresh this project's CLAUDE.md rules block to the current skill
    version and resync. Run after updating the skill globally (the global install does
    not touch project CLAUDE.md files)."""
    cfg = read_config(root)
    old = cfg.get("skillVersion", "unknown")
    new = get_version()
    ensure_claude_md_rules(root)
    cfg["skillVersion"] = new
    write_config(root, cfg)
    sync(root)
    print(f"Refreshed roadmap rules in {root / 'CLAUDE.md'} ({old} → v{new})")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="roadmap")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--name", default="My Project")
    p_init.add_argument("--adopt", action="store_true")
    p_init.add_argument("--no-claude-md", action="store_false", dest="claude_md")

    p_new = sub.add_parser("new")
    p_new.add_argument("--type", required=True)
    p_new.add_argument("--title", required=True)
    p_new.add_argument("--version")
    p_new.add_argument("--note", default="")
    p_new.add_argument("--audience", choices=["public", "internal"])

    p_note = sub.add_parser("note")
    p_note.add_argument("--plan", type=int, required=True)
    p_note.add_argument("--text", required=True)

    p_aud = sub.add_parser("audience")
    p_aud.add_argument("--plan", type=int, required=True)
    p_aud.add_argument("--to", required=True, choices=["public", "internal"])

    p_check = sub.add_parser("check")
    p_check.add_argument("--plan", type=int, required=True)
    p_check.add_argument("--step", type=int)
    p_check.add_argument("--undo", action="store_true")
    p_check.add_argument("--all-done", action="store_true", dest="all_done")

    p_rel = sub.add_parser("release")
    p_rel.add_argument("--version", required=True)
    p_rel.add_argument("--tag", action="store_true")
    p_rel.add_argument("--force", action="store_true")

    p_st = sub.add_parser("status")
    p_st.add_argument("--json", action="store_true", dest="as_json")

    sub.add_parser("sync")
    sub.add_parser("version")
    sub.add_parser("upgrade")

    p_imp = sub.add_parser("import")
    p_imp.add_argument("path")

    p_re = sub.add_parser("reorder")
    p_re.add_argument("--version", required=True)
    p_re.add_argument("--order", required=True)

    p_mg = sub.add_parser("merge")
    p_mg.add_argument("--into", type=int, required=True)
    p_mg.add_argument("--from", dest="sources", required=True)

    p_dep = sub.add_parser("depends")
    p_dep.add_argument("--plan", type=int, required=True)
    p_dep.add_argument("--on", default="")
    p_dep.add_argument("--clear", action="store_true")

    p_rm = sub.add_parser("remove")
    p_rm.add_argument("--plan", type=int, required=True)

    p_cl = sub.add_parser("changelog")
    p_cl.add_argument("--backfill", action="store_true")
    p_cl.add_argument("--internal", action="store_true",
                      help="print CHANGELOG.internal.md instead of the public CHANGELOG.md")

    p_rt = sub.add_parser("retarget")
    p_rt.add_argument("--to", required=True)
    p_rt.add_argument("--from", dest="from_versions", default="")
    p_rt.add_argument("--plan", dest="plan_ids", default="")

    args = parser.parse_args(argv)
    root = find_root(Path.cwd())
    try:
        if args.command == "init":
            init_project(root, args.name, adopt=args.adopt, claude_md=args.claude_md)
            print(f"Initialized roadmap at {root}")
            return 0
        if args.command == "new":
            path = new_item(root, args.type, args.title, args.version,
                            note=args.note, audience=args.audience)
            print(path)
            return 0
        if args.command == "note":
            set_note(root, args.plan, args.text)
            return 0
        if args.command == "audience":
            set_audience(root, args.plan, args.to)
            return 0
        if args.command == "check":
            check_step(root, args.plan, args.step, undo=args.undo, all_done=args.all_done)
            return 0
        if args.command == "release":
            release(root, args.version, tag=args.tag, force=args.force)
            return 0
        if args.command == "sync":
            sync(root)
            return 0
        if args.command == "version":
            print(get_version())
            return 0
        if args.command == "upgrade":
            upgrade(root)
            return 0
        if args.command == "reorder":
            reorder(root, args.version, [int(x) for x in args.order.split(",") if x.strip()])
            return 0
        if args.command == "merge":
            merge_items(root, args.into,
                        [int(x) for x in args.sources.split(",") if x.strip()])
            return 0
        if args.command == "depends":
            set_depends(root, args.plan,
                        [int(x) for x in args.on.split(",") if x.strip()],
                        clear=args.clear)
            return 0
        if args.command == "remove":
            remove_item(root, args.plan)
            return 0
        if args.command == "retarget":
            retarget(root, args.to,
                     from_versions=[v for v in args.from_versions.split(",") if v.strip()] or None,
                     plan_ids=[int(x) for x in args.plan_ids.split(",") if x.strip()] or None)
            return 0
        if args.command == "changelog":
            if args.backfill:
                backfill_changelog(root)
            else:
                sync(root, quiet=True)
            for m in audit_public_notes(root):
                print(f"warning: {m}", file=sys.stderr)
            cl = root / ("CHANGELOG.internal.md" if args.internal else "CHANGELOG.md")
            if cl.exists():
                print(cl.read_text(encoding="utf-8"), end="")
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
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
