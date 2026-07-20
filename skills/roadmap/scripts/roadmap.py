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
    collapse = cfg.get("settings", {}).get("collapseShipped", True)
    dates = cfg.get("versionDates", {})
    current = _norm_version(cfg["currentVersion"])
    lines = ["## 📊 Versions", ""]
    for version in sorted(by_version, key=_version_key):
        items = sorted(by_version[version],
                       key=lambda i: (i.get("order", i["id"]), i["id"]))
        done_total = [progress.get(i["id"], (0, 0)) for i in items]
        d = sum(x for x, _ in done_total)
        t = sum(y for _, y in done_total)
        pct = round(100 * d / t) if t else 0
        marker = "x" if t and d == t else " "
        # Collapse shipped history: fully-done versions strictly below the current
        # one render as a single summary line (details live in CHANGELOG.internal.md
        # and .roadmap/plans/). The current/future versions always render in full.
        if collapse and marker == "x" and _version_key(version) < _version_key(current):
            n = len(items)
            shipped = f" · shipped {dates[version]}" if version in dates else ""
            lines.append(f"### [x] v{version} — 100% · {n} item{'s' if n != 1 else ''}"
                         f"{shipped} ([history](CHANGELOG.internal.md))")
            lines.append("")
            continue
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


def _version_complete(vitems: list, progress: dict) -> bool:
    """A version is complete when it has items and every one is 100% done."""
    if not vitems:
        return False
    for i in vitems:
        done, total = progress.get(i["id"], (0, 0))
        if not (total > 0 and done == total):
            return False
    return True


def _next_current_version(cfg: dict, by_version: dict, progress: dict):
    """If the current version is fully shipped, the version current should point
    at next: the lowest later version that is not yet complete, or (if every
    later version is also complete) the newest one. None = leave current as-is.

    Only advances a *completed* current version, so a freshly `release`-d empty
    future version (no items yet) is never skipped."""
    cur = cfg["currentVersion"]
    if not _version_complete(by_version.get(cur, []), progress):
        return None
    above = sorted((v for v in by_version if _version_key(v) > _version_key(cur)),
                   key=_version_key)
    # Only follow the work forward once a *shipped* (100%) version sits above the
    # current one — i.e. current has fallen behind a completed release. A freshly
    # added, still-incomplete next version alone is left to release()/build flow,
    # so an explicit release isn't pre-empted.
    if not any(_version_complete(by_version[v], progress) for v in above):
        return None
    for v in above:
        if not _version_complete(by_version[v], progress):
            return v            # land on the lowest still-open version above
    return above[-1]            # everything above is shipped too → newest


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
    # Auto-advance currentVersion: once the current version ships 100%, current
    # should follow the work to the next unfinished version — no hand-editing,
    # no stale pointer. Opt out with settings.autoAdvanceVersion = false.
    if cfg.get("settings", {}).get("autoAdvanceVersion", True):
        nxt = _next_current_version(cfg, by_version, progress)
        if nxt and nxt != cfg["currentVersion"]:
            cfg["currentVersion"] = nxt
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
    if not undo:
        _record_last_seen_sha(root)


TEMPLATE_BY_TYPE = {"feature": "feature-plan.md", "chore": "feature-plan.md",
                    "bug": "bug-investigation.md", "refactor": "refactor-debt.md"}


def _refuse_status_note(item: dict, note: str, force: bool) -> None:
    """Refuse (ValueError) a note that would render PUBLIC but is structurally a
    status/progress dump. `item` may be a candidate dict (new item / new note applied) —
    audience is judged with the candidate note so auto-demoted items pass through
    untouched (they render internal anyway)."""
    if force or not note or item_audience(item) != "public":
        return
    tells = status_tells(note)
    if tells:
        raise ValueError(
            f"note refused — this reads like a status/progress dump, not a release note "
            f"({', '.join(tells)}). CHANGELOG.md is pasted into the App Store \"What's New\": "
            f"write ONE plain sentence of user benefit — no dates, step numbers, version "
            f"refs, file paths, issue refs, or ALL-CAPS status words. Progress notes belong "
            f"in the plan file, not the changelog. Alternatively mark the item internal "
            f"(roadmap audience --plan {item.get('id', '<id>')} --to internal) or re-run "
            f"with --force if this text really should ship to end users.")


def new_item(root: Path, type_: str, title: str, version: str | None = None,
             note: str = "", audience: str | None = None, force: bool = False) -> Path:
    if type_ not in TEMPLATE_BY_TYPE:
        raise ValueError(f"unknown type {type_!r}; choose from {sorted(TEMPLATE_BY_TYPE)}")
    cfg = read_config(root)
    item_id = cfg["nextId"]
    _refuse_status_note({"id": item_id, "title": title, "type": type_,
                         "note": note, "audience": audience}, note, force)
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


def set_note(root: Path, plan_id: int, text: str, force: bool = False) -> None:
    """Set an item's user-facing changelog note, then re-render. A note that would render
    PUBLIC but is structurally a status dump (dates, step/version refs, paths, shouted
    status words) is REFUSED unless --force; softer internal wording only warns."""
    cfg = read_config(root)
    for item in cfg["items"]:
        if item["id"] == plan_id:
            _refuse_status_note({**item, "note": text}, text, force)
            item["note"] = text
            write_config(root, cfg)
            blob = f"{text} {item['title']}"
            if item.get("audience") is None and demote_tells(blob):
                print(f"warning: #{plan_id} auto-routed to the internal changelog "
                      f"({', '.join(demote_tells(blob))}); if it really is user-facing, "
                      f"override: roadmap audience --plan {plan_id} --to public", file=sys.stderr)
            elif item_audience(item) == "public":
                tells = lint_note(text, cfg.get("settings", {}).get("internalTerms", []))
                if tells:
                    print(f"warning: #{plan_id} note reads internal ({', '.join(tells)}); "
                          f"CHANGELOG.md is user-facing. Rephrase in plain benefit language, "
                          f"or mark it internal: roadmap audience --plan {plan_id} --to internal",
                          file=sys.stderr)
            sync(root)
            return
    raise ValueError(f"no plan with id {plan_id}")


def set_release_summary(root: Path, version: str, text: str | None = None,
                        clear: bool = False, force: bool = False) -> None:
    """Set (or clear) a version's public release-notes blurb. When a version has a blurb,
    the PUBLIC changelog renders it INSTEAD of per-item bullets — the blurb is the App
    Store "What's New" text; per-item detail stays in CHANGELOG.internal.md. Same
    status-dump gate as item notes (--force overrides); softer wording only warns."""
    version = _norm_version(version)
    cfg = read_config(root)
    summaries = cfg.setdefault("releaseNotes", {})
    if clear:
        summaries.pop(version, None)
        write_config(root, cfg)
        sync(root)
        return
    if text is None:
        raise ValueError("pass --text (or --clear to remove the summary)")
    known = {i["version"] for i in cfg["items"]}
    if version not in known and version not in summaries:
        raise ValueError(f"no items target version {version} "
                         f"(known: {', '.join(sorted(known, key=_version_key))})")
    if not force:
        tells = status_tells(text)
        if tells:
            raise ValueError(
                f"summary refused — reads like a status/progress dump, not release notes "
                f"({', '.join(tells)}). The blurb ships verbatim to end users: keep it a "
                f"short, warm 'What's New' — no dates, step numbers, version refs, paths, "
                f"issue refs, or ALL-CAPS status words (the version header is added for "
                f"you). Re-run with --force if the text really should ship as-is.")
    summaries[version] = text.strip()
    write_config(root, cfg)
    tells = lint_note(text, cfg.get("settings", {}).get("internalTerms", []))
    if tells:
        print(f"warning: v{version} summary has internal-sounding wording "
              f"({', '.join(tells)}); it ships verbatim to end users — consider rephrasing.",
              file=sys.stderr)
    sync(root)


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
    """Set (or clear) an item's `dependsOn` list. Consumed by `next` (skips blocked),
    `build` (warns), /roadmap:reevaluate, and retargeted by merge/remove."""
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
    # Reject trivial cycles (self already handled; A→B→A via one hop of existing edges)
    for d in on:
        if plan_id in (by_id[d].get("dependsOn") or []):
            raise ValueError(f"dependency cycle: #{plan_id} ↔ #{d}")
    by_id[plan_id]["dependsOn"] = list(dict.fromkeys(on))
    write_config(root, cfg)


INCUBATOR_RE = re.compile(r"(?im)^#{1,6}\s+.*idea incubator.*$")
INCUBATOR_HEADING = "## 💡 Idea Incubator"


def incubator_file(root: Path) -> Path:
    """Where Idea Incubator bullets live: ROADMAP.md by default, or the external file
    named by settings.incubatorFile (set by `tidy --externalize`)."""
    try:
        rel = read_config(root).get("settings", {}).get("incubatorFile")
    except (ValueError, FileNotFoundError):
        rel = None
    return (root / rel) if rel else (root / "ROADMAP.md")


def _incubator_append(root: Path, stub: str) -> None:
    """Append one bullet under the free-form Idea Incubator heading, creating the
    heading (or the external incubator file) if missing. Edits happen outside the
    roadmap:auto markers, which sync owns."""
    target = incubator_file(root)
    if not target.exists():
        atomic_write(target, f"{INCUBATOR_HEADING}\n{stub}\n")
        return
    text = target.read_text(encoding="utf-8")
    m = INCUBATOR_RE.search(text)
    if m:
        new = text[:m.end()] + "\n" + stub + text[m.end():]
    else:
        new = text.rstrip() + f"\n\n{INCUBATOR_HEADING}\n{stub}\n"
    atomic_write(target, new)


def _incubator_stub(root: Path, plan_id: int, title: str, archived: str | None = None) -> None:
    """Breadcrumb for a removed item, linking the archived plan file when one was kept."""
    stub = f"- (was #{plan_id}) {title}"
    if archived:
        stub += f" ([archived plan]({archived}))"
    _incubator_append(root, stub)


def _strip_incubator_placeholder(root: Path) -> None:
    """Remove the template placeholder bullet so real ideas stand alone."""
    target = incubator_file(root)
    if not target.exists():
        return
    text = target.read_text(encoding="utf-8")
    new = re.sub(r"(?m)^\s*[-*+]\s+\(add ideas here\)\s*\n?", "", text)
    if new != text:
        atomic_write(target, new)


def add_idea(root: Path, title: str, body: str | None = None) -> Path | None:
    """Park an idea as ONE incubator bullet. Long-form content (brainstorm output,
    deferred review findings, phase sketches) goes to a linked note file under
    .roadmap/notes/ so ROADMAP.md itself stays short."""
    title = title.strip()
    if not title:
        raise ValueError("idea title must not be empty")
    read_config(root)  # fail early with a clear error if not initialized
    _strip_incubator_placeholder(root)
    stub = f"- {title}"
    note_path = None
    if body and body.strip():
        slug = slugify(title) or "idea"
        notes = roadmap_dir(root) / "notes"
        base = f"{datetime.date.today().isoformat()}-{slug}"
        dest, n = notes / f"{base}.md", 2
        while dest.exists():
            dest, n = notes / f"{base}-{n}.md", n + 1
        atomic_write(dest, f"# {title}\n\n{body.strip()}\n")
        note_path = dest
        stub += f" ([notes]({dest.relative_to(root)}))"
    _incubator_append(root, stub)
    return note_path


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

# Internal "tells" come in two tiers, matched case-insensitively as whole words.
#
# WARN tier = WORDING problems. The feature may still be public; the note just reads like it
# was written for engineers — rephrase, don't reclassify. (vendor/tool names, dev jargon,
# mechanism phrasing, plus file paths / issue refs detected by regex in lint_note.)
WARN_VENDORS = [
    "convex", "sentry", "aptabase", "codex", "eas", "clerk", "supabase", "firebase",
    "vercel", "netlify", "cloudflare", "r2", "s3", "docker", "kubernetes", "k8s",
    "redis", "postgres", "postgresql", "mysql", "mongodb", "stripe", "github actions",
    "expo", "webpack", "vite", "prisma", "graphql", "grpc",
]
WARN_JARGON = [
    "refactor", "schema", "migration", "mutation", "endpoint", "backend", "frontend",
    "polling", "cron", "webhook", "ci", "lint", "linter", "env var",
    "environment variable", "api key", "n+1", "regression",
    "under the hood", "data feed", "data feeds", "headliner index", "walk-through",
    "walkthrough index", "audit", "audits", "ota", "de-slop",
]
WARN_TELLS = [*WARN_VENDORS, *WARN_JARGON]

# DEMOTE tier = WRONG-AUDIENCE / self-incriminating. The *work* is internal, not just the
# wording. An item with no explicit audience that trips any of these auto-routes to
# CHANGELOG.internal.md (an explicit `audience --to public` still wins). Grouped by reason:
DEMOTE_ADMIN = [        # operator-only surfaces — staff read these, not end users
    "admin", "admins", "admin panel", "admin console", "admin area", "admin dashboard",
    "moderation", "moderator", "moderators", "audit trail", "audit log", "role-gated", "cms",
]
DEMOTE_COMPLIANCE = [   # legal/regulatory gates — required, not a feature anyone chose
    "compliance", "coppa", "gdpr", "age gate", "age-gate", "age verification", "13-and-up",
    "13 and up", "underage", "minimum age", "eula", "terms acceptance", "community guidelines",
]
DEMOTE_SECURITY = [     # security fixes that disclose a past hole — never advertise the weakness
    "hardening", "hardened", "privilege", "spam/abuse", "closed gaps", "vulnerability",
    "exploit", "public url", "public urls", "expiring link", "expiring links", "signed url",
    "signed urls",
]
DEMOTE_PLUMBING = [     # SEO/infra plumbing & internal milestones — no user-visible payoff
    "groundwork", "groundwork for", "reusable", "static-page", "sitemap", "robots rules",
    "robots.txt", "structured data", "metadata", "search-optimized", "search optimized", "seo",
    "scaffolding", "boilerplate", "rearchitect", "re-architect", "pre-launch", "prelaunch",
]
DEMOTE_TELLS = [*DEMOTE_ADMIN, *DEMOTE_COMPLIANCE, *DEMOTE_SECURITY, *DEMOTE_PLUMBING]

_PATH_RE = re.compile(r"\b[\w.-]+\.(?:ts|tsx|js|jsx|mjs|cjs|py|go|rs|java|rb|php|"
                      r"json|ya?ml|toml|sql|sh|css|scss|md|swift|kt)\b")  # foo/bar.ts
_SEG_RE = re.compile(r"\b\w+(?:/\w+){2,}\b")                          # a/b/c paths
_REF_RE = re.compile(r"#\d+")                                        # issue refs (#77)

# STATUS tier = status-dump tells — progress-report text (date stamps, plan-step refs,
# version numbers, shouted status words) that belongs in the plan file or a commit message,
# never in a release note. Any hit is structural evidence the note wasn't written for end
# users, so `note` / `new --note` REFUSE to save it on a public item (override: --force).
_STATUS_RES = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),                 # ISO date stamps (2026-07-15)
    re.compile(r"\bStep\s+\d+\b"),                        # plan-step refs ("Step 9")
    re.compile(r"\bv\d+\.\d+(?:\.\d+)?\b"),               # version refs (v1.6.0)
    re.compile(r"\b(?:DONE|WIP|TODO|BLOCKED|DEFERRED|DESCOPED|DESCOPE|ACCEPTED|"
               r"SHIPPED|MERGED|FIXED|QA|TBD)\b"),        # shouted status words
]


def _word_hits(text: str, terms: list[str]) -> list[str]:
    low = text.lower()
    return [t for t in terms if re.search(r"\b" + re.escape(t.lower()) + r"\b", low)]


def _dedupe(seq: list[str]) -> list[str]:
    seen, out = set(), []
    for h in seq:
        if h.lower() not in seen:
            seen.add(h.lower())
            out.append(h)
    return out


def status_tells(text: str) -> list[str]:
    """Structural status-dump evidence in a would-be PUBLIC note: issue refs, source/doc
    paths, ISO dates, plan-step refs, version numbers, shouted status words. Unlike the
    advisory word lists, any hit here means the text is a progress report rather than a
    release note, so `note` / `new --note` refuse to save it on a public item (--force
    overrides)."""
    hits = _REF_RE.findall(text) + _PATH_RE.findall(text) + _SEG_RE.findall(text)
    for rx in _STATUS_RES:
        hits += rx.findall(text)
    return _dedupe(hits)


def lint_note(text: str, extra_terms: list[str] | None = None) -> list[str]:
    """Every internal tell in a would-be PUBLIC note, for display/warnings — status-dump
    tells (issue refs, paths, dates, step/version refs, shouted status), vendor/jargon
    (warn tier), and scope/disclosure words (demote tier). Empty list == looks clean.
    Advisory here; the status-dump subset also hard-blocks in `note` / `new --note`."""
    hits = status_tells(text)
    hits += _word_hits(text, [*WARN_TELLS, *DEMOTE_TELLS, *(extra_terms or [])])
    return _dedupe(hits)


def demote_tells(text: str) -> list[str]:
    """Only the high-confidence WRONG-AUDIENCE tells (admin / compliance / security-disclosure
    / plumbing). Drives auto-routing of an unclassified item to the internal changelog."""
    return _dedupe(_word_hits(text, DEMOTE_TELLS))


def item_audience(item: dict) -> str:
    """An item's effective audience. An explicit `audience` always wins. Otherwise an item
    whose note/title trips a high-confidence demote tell auto-routes to `internal`; failing
    that, it falls back to the per-type default."""
    a = item.get("audience")
    if a in ("public", "internal"):
        return a
    if demote_tells(f"{item.get('note', '')} {item.get('title', '')}"):
        return "internal"
    return DEFAULT_AUDIENCE.get(item["type"], "internal")


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
    if it has already shipped (complete) that omission is returned as a warning and the
    item is covered by the roll-up line, so a shipped version never vanishes from the
    public changelog. The roll-up line appears ONLY when a version has nothing public to
    show — versions with real public bullets stay clean (less is more); internal work
    remains fully logged in CHANGELOG.internal.md. Returns (markdown, warnings)."""
    warnings: list[str] = []
    summaries = read_config(root).get("releaseNotes", {})
    out = ["# Changelog", ""]
    for version, header, rows in _changelog_versions(root):
        blurb = summaries.get(version)
        if blurb:
            # A curated per-version blurb IS the public release notes — item bullets
            # (and their missing-note warnings) don't apply; detail lives internally.
            out += [header, "", blurb, ""]
            continue
        sections: dict[str, list[tuple[bool, str]]] = {}
        rolled_up = False
        for row in rows:
            it = row["item"]
            if item_audience(it) != "public":
                rolled_up = True
                continue
            note = it.get("note")
            if not note:
                if row["complete"]:
                    warnings.append(
                        f"#{it['id']} \"{it['title']}\" is public but has no note; "
                        f"rolled up as behind-the-scenes work in CHANGELOG.md. Add one: "
                        f"roadmap note --plan {it['id']} --text \"...\"")
                    rolled_up = True
                continue
            section = TYPE_SECTION.get(it["type"], "⚡ Improved")
            sections.setdefault(section, []).append((row["complete"], note))
        lines = _grouped_lines(sections)
        if rolled_up and not lines:
            lines += [ROLLUP_LINE, ""]
        if not lines:
            continue                       # nothing public to show for this version
        out += [header, "", *lines]
    return "\n".join(out).rstrip() + "\n", warnings


def changelog_json(root: Path) -> list[dict]:
    """Structured public changelog for app builds (in-app changelog screens, "What's
    New" popups). Same selection rules as render_public_changelog — public audience,
    note text only — but as data: one object per version, newest first. Callers
    filtering for a popup should keep `released == true` versions only."""
    cfg = read_config(root)
    version_dates = cfg.get("versionDates", {})
    summaries = cfg.get("releaseNotes", {})
    out = []
    for version, _header, rows in _changelog_versions(root):
        blurb = summaries.get(version)
        sections: dict[str, list[dict]] = {}
        rollup = False
        released = bool(rows) and all(r["complete"] for r in rows)
        for row in rows:
            it = row["item"]
            if item_audience(it) != "public" or not it.get("note"):
                rollup = True
                continue
            section = TYPE_SECTION.get(it["type"], "⚡ Improved")
            # strip the emoji prefix for machine keys: "✨ New" -> "New"
            key = section.split(" ", 1)[1] if " " in section else section
            sections.setdefault(key, []).append(
                {"text": it["note"], "pending": not row["complete"]})
        if not sections and not rollup and not blurb:
            continue
        # `notes` is the curated per-version blurb; when present it supersedes
        # `sections` for user-facing display (mirrors CHANGELOG.md).
        out.append({"version": version, "date": version_dates.get(version),
                    "released": released, "notes": blurb,
                    "sections": {} if blurb else sections,
                    "rollup": False if blurb else rollup})
    return out


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
    summaries = cfg.get("releaseNotes", {})
    msgs = []
    # Completed versions still rendering raw item bullets: suggest a curated blurb —
    # the public changelog should read like App Store "What's New", not an item list.
    for version, _header, rows in _changelog_versions(root):
        if rows and all(r["complete"] for r in rows) and not summaries.get(version):
            msgs.append(f"v{version} has no release-notes summary — the public changelog "
                        f"lists raw item bullets. Write one short user-facing blurb: "
                        f"roadmap summary --version {version} --text \"...\"")
    # Orphaned blurbs: a summary for a version no items target (usually after retarget/
    # remove) renders nowhere — clear it or move it to the absorbing version.
    live = {i["version"] for i in cfg["items"]}
    for version in sorted(set(summaries) - live, key=_version_key):
        msgs.append(f"v{version} has a release-notes summary but no items target it "
                    f"(retargeted away?) — it renders nowhere. Clear it: "
                    f"roadmap summary --version {version} --clear")
    for it in sorted(cfg["items"], key=lambda i: i["id"]):
        if summaries.get(it["version"]):
            continue   # version ships a curated blurb; per-item notes are internal-only
        explicit = it.get("audience")
        blob = f"{it.get('note', '')} {it['title']}"
        eff = item_audience(it)
        # Auto-routed: no explicit audience, would be public by type, demoted by a high-conf tell.
        if explicit is None and DEFAULT_AUDIENCE.get(it["type"]) == "public" and eff == "internal":
            msgs.append(f"#{it['id']} \"{it['title']}\" auto-routed to internal "
                        f"({', '.join(demote_tells(blob))}); if it really is user-facing, "
                        f"override: roadmap audience --plan {it['id']} --to public")
            continue
        if eff != "public":
            continue
        # Explicitly marked public but matches a high-confidence internal signal — likely wrong.
        d = demote_tells(blob)
        if explicit == "public" and d:
            msgs.append(f"#{it['id']} is marked PUBLIC but matches high-confidence internal "
                        f"signals ({', '.join(d)}) — likely miscategorized: \"{it['title']}\"")
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


MAX_ROADMAP_LINES = 150
MAX_FREEFORM_LINES = 40
MAX_FREEFORM_CHARS = 4000


def roadmap_health(root: Path) -> list[str]:
    """Size warnings for ROADMAP.md: the dashboard should stay skimmable. The auto
    region is bounded by collapsing shipped versions; the free-form region only stays
    short if prose lives in .roadmap/notes/ files instead of inline. Checked by both
    line count and character volume (prose dumps often sit on few, very long lines)."""
    rm = root / "ROADMAP.md"
    if not rm.exists():
        return []
    lines = rm.read_text(encoding="utf-8").splitlines()
    warnings = []
    in_auto = False
    freeform = chars = 0
    for line in lines:
        if AUTO_START in line:
            in_auto = True
        elif AUTO_END in line:
            in_auto = False
        elif not in_auto and line.strip():
            freeform += 1
            chars += len(line)
    if freeform > MAX_FREEFORM_LINES or chars > MAX_FREEFORM_CHARS:
        size = (f"{freeform} lines (> {MAX_FREEFORM_LINES})"
                if freeform > MAX_FREEFORM_LINES
                else f"{chars} characters (> {MAX_FREEFORM_CHARS})")
        warnings.append(
            f"ROADMAP.md free-form region is {size}. Move long-form notes into linked "
            "files via `roadmap.py idea --title ... --body-file ...` and keep one "
            "bullet per idea.")
    if len(lines) > MAX_ROADMAP_LINES:
        warnings.append(
            f"ROADMAP.md is {len(lines)} lines (> {MAX_ROADMAP_LINES}). Shipped versions "
            "collapse automatically on sync (settings.collapseShipped); trim the "
            "free-form region into .roadmap/notes/ files.")
    return warnings


MAX_BULLET_CHARS = 200
DUPLICATE_RATIO = 0.8
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+\.md)\)")


def _freeform_lines(text: str) -> list[str]:
    """Lines of ROADMAP.md outside the roadmap:auto region."""
    out, in_auto = [], False
    for line in text.splitlines():
        if AUTO_START in line:
            in_auto = True
        elif AUTO_END in line:
            in_auto = False
        elif not in_auto:
            out.append(line)
    return out


def _norm_title(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", s.lower()).strip()


def externalize_incubator(root: Path, file: str = ".roadmap/IDEAS.md") -> Path:
    """Move the Idea Incubator region out of ROADMAP.md into `file` (verbatim,
    lossless), leave one linked bullet on the dashboard, and record
    settings.incubatorFile so idea/promote/remove target the new home."""
    cfg = read_config(root)
    settings = cfg.setdefault("settings", {})
    if settings.get("incubatorFile"):
        raise ValueError(f"incubator is already external: {settings['incubatorFile']}")
    dest = root / file
    if dest.exists():
        raise ValueError(f"{file} already exists — pick another path")
    rm = root / "ROADMAP.md"
    text = rm.read_text(encoding="utf-8") if rm.exists() else ""
    link = (f"- Parked ideas live in [{file}]({file}) — "
            "`roadmap.py idea` / `promote` target it.\n")
    kept, moved, in_region = [], [], False
    for ln in text.splitlines(keepends=True):
        if not in_region and INCUBATOR_RE.match(ln.rstrip("\n")):
            in_region = True
            kept.append(ln if ln.endswith("\n") else ln + "\n")
            kept.append(link)
            continue
        if in_region and (AUTO_START in ln or re.match(r"^#{1,6}\s", ln)):
            in_region = False
        (moved if in_region else kept).append(ln)
    if not any(INCUBATOR_RE.match(l.rstrip("\n")) for l in kept):
        kept.append(f"\n{INCUBATOR_HEADING}\n{link}")
    body = "".join(moved).strip("\n")
    atomic_write(dest, f"{INCUBATOR_HEADING}\n" + (body + "\n" if body else ""))
    atomic_write(rm, "".join(kept))
    settings["incubatorFile"] = file
    write_config(root, cfg)
    return dest


def tidy_report(root: Path) -> dict:
    """Analyze the free-form region of ROADMAP.md (Idea Incubator + surrounding prose,
    plus the external incubator file when settings.incubatorFile is set) and report
    what needs grooming. Report-only by design: scripts never rewrite the free-form
    region — the /roadmap:tidy command flow applies the judgment edits."""
    import difflib
    rm = root / "ROADMAP.md"
    report = {"clean": True, "warnings": [], "bullets": [],
              "prose": {"lines": 0, "leads": []}}
    if not rm.exists():
        return report
    report["warnings"] = roadmap_health(root)
    try:
        tracked = [(i["id"], i["title"]) for i in read_config(root)["items"]]
    except (ValueError, FileNotFoundError, KeyError):
        tracked = []

    src_lines = _freeform_lines(rm.read_text(encoding="utf-8"))
    inc = incubator_file(root)
    if inc != rm and inc.exists():
        src_lines += inc.read_text(encoding="utf-8").splitlines()

    bullets, prose = [], report["prose"]
    cur = None
    seen_h1 = in_comment = False
    for line in src_lines:
        stripped = line.strip()
        if in_comment:
            in_comment = "-->" not in stripped
            cur = None
            continue
        if stripped.startswith("<!--"):
            in_comment = "-->" not in stripped
            cur = None
            continue
        if not stripped:
            cur = None
            continue
        if re.match(r"^#\s", line):
            if not seen_h1:
                seen_h1 = True
                continue
        if re.match(r"^#{1,6}\s", line):
            cur = None
            if not INCUBATOR_RE.match(line):
                prose["leads"].append(stripped[:70])
            continue
        if re.match(r"^[-*+]\s", line):
            cur = {"index": len(bullets) + 1, "text": stripped[2:].strip(),
                   "chars": len(stripped), "children": 0}
            bullets.append(cur)
            continue
        if re.match(r"^\s+\S", line) and cur is not None:
            cur["chars"] += len(stripped)
            if re.match(r"^\s+[-*+]\s", line):
                cur["children"] += 1
            continue
        cur = None
        prose["lines"] += 1
        if stripped.startswith("**"):
            prose["leads"].append(stripped[:70])

    for b in bullets:
        title = re.sub(r"\s*\([^)]*\)\s*$", "", b["text"]).strip()
        title = re.sub(r"\s*\[[^\]]*\]\([^)]*\)\s*$", "", title).strip()
        entry = {"index": b["index"], "title": title[:100], "chars": b["chars"],
                 "children": b["children"],
                 "notesLink": bool(MD_LINK_RE.search(b["text"])), "flags": []}
        if b["children"]:
            entry["flags"].append("nested")
        if b["chars"] > MAX_BULLET_CHARS and not entry["notesLink"]:
            entry["flags"].append("long-no-link")
        elif b["chars"] > 2 * MAX_BULLET_CHARS:
            entry["flags"].append("long")
        norm = _norm_title(title)
        if norm and tracked:
            best = max(tracked, key=lambda t: difflib.SequenceMatcher(
                None, norm, _norm_title(t[1])).ratio())
            if difflib.SequenceMatcher(
                    None, norm, _norm_title(best[1])).ratio() >= DUPLICATE_RATIO:
                entry["flags"].append("duplicate")
                entry["duplicateOf"] = best[0]
        if entry["flags"]:
            report["bullets"].append(entry)

    report["clean"] = not (report["warnings"] or report["bullets"] or prose["lines"])
    return report


def format_tidy(report: dict) -> str:
    if report["clean"]:
        return "ROADMAP.md free-form region: clean — nothing to tidy."
    out = ["ROADMAP.md free-form region needs grooming:"]
    for w in report["warnings"]:
        out.append(f"  ! {w}")
    for b in report["bullets"]:
        detail = [f"{b['chars']} chars"]
        if b["children"]:
            detail.append(f"{b['children']} sub-bullets")
        if not b["notesLink"]:
            detail.append("no notes link")
        if "duplicate" in b["flags"]:
            detail.append(f"≈ tracked item #{b['duplicateOf']}")
        out.append(f"  - bullet {b['index']} “{b['title']}” — " + ", ".join(detail))
    if report["prose"]["lines"]:
        leads = "; ".join(report["prose"]["leads"][:5])
        out.append(f"  - {report['prose']['lines']} prose line(s) outside any bullet"
                   + (f" (sections: {leads})" if leads else ""))
    out.append("Groom with /roadmap:tidy · /roadmap-tidy — move bodies to linked "
               ".roadmap/notes/ files, one bullet per idea; drop bullets that "
               "duplicate tracked items (or promote them).")
    return "\n".join(out)


def status(root: Path) -> dict:
    cfg = read_config(root)
    by_id = {i["id"]: i for i in cfg["items"]}
    # Full progress map first — blockedBy for early ids must see later deps' progress.
    progress = _progress_map(root, cfg)
    items = []
    for item in cfg["items"]:
        done, total = progress.get(item["id"], (0, 0))
        pct = round(100 * done / total) if total else 0
        blocked_by = _incomplete_deps(item, progress, by_id)
        row = {**item, "done": done, "total": total, "pct": pct,
               "status": derive_status(done, total),
               "dependsOn": list(item.get("dependsOn") or []),
               "blockedBy": blocked_by}
        items.append(row)
    return {"project": cfg["project"], "currentVersion": cfg["currentVersion"],
            "items": items}


def _item_done(progress: dict[int, tuple[int, int]], plan_id: int) -> bool:
    done, total = progress.get(plan_id, (0, 0))
    return total > 0 and done == total


def _incomplete_deps(item: dict, progress: dict[int, tuple[int, int]],
                     by_id: dict[int, dict]) -> list[int]:
    """Dependency ids that exist and are not 100% complete."""
    out = []
    for d in item.get("dependsOn") or []:
        if d not in by_id:
            continue
        if not _item_done(progress, d):
            out.append(d)
    return out


def _progress_map(root: Path, cfg: dict | None = None) -> dict[int, tuple[int, int]]:
    cfg = cfg or read_config(root)
    progress = {}
    for item in cfg["items"]:
        path = roadmap_dir(root) / item["file"]
        progress[item["id"]] = count_progress(path) if path.exists() else (0, 0)
    return progress


def incomplete_deps(root: Path, plan_id: int) -> list[int]:
    """Return dependency plan ids that are not yet 100% complete."""
    cfg = read_config(root)
    by_id = {i["id"]: i for i in cfg["items"]}
    if plan_id not in by_id:
        raise ValueError(f"no plan with id {plan_id}")
    return _incomplete_deps(by_id[plan_id], _progress_map(root, cfg), by_id)


def warn_incomplete_deps(root: Path, plan_id: int, force: bool = False) -> list[int]:
    """Warn when building an item whose dependencies are incomplete. Returns blocker ids.
    Non-blocking unless the caller chooses to stop; --force silences the warning."""
    blocked = incomplete_deps(root, plan_id)
    if blocked and not force:
        print(f"warning: #{plan_id} depends on incomplete item(s) {blocked}; "
              f"prefer finishing them first (`roadmap.py next`), or continue carefully",
              file=sys.stderr)
    return blocked


def next_item(root: Path, version: str | None = None,
              force: bool = False, quiet: bool = False) -> dict | None:
    """Pick the next unfinished item in `version` (default: currentVersion).

    Order: explicit `order` field, then id. Skips items whose `dependsOn` targets are
    not 100% complete (unless force=True). Prints skipped blocked items to stderr
    unless quiet=True. Returns an enriched status row, or None if every item is done
    / only blocked remain.
    """
    st = status(root)
    ver = _norm_version(version or st["currentVersion"])
    candidates = [i for i in st["items"] if i["version"] == ver and i["pct"] < 100]
    candidates.sort(key=lambda i: (i.get("order", i["id"]), i["id"]))
    skipped = []
    for item in candidates:
        blocked = item.get("blockedBy") or []
        if blocked and not force:
            skipped.append((item["id"], blocked))
            continue
        if skipped and not quiet:
            for sid, deps in skipped:
                print(f"skipping #{sid} (blocked by {deps})", file=sys.stderr)
        return item
    if skipped and not quiet:
        for sid, deps in skipped:
            print(f"skipping #{sid} (blocked by {deps})", file=sys.stderr)
        print(f"no unblocked unfinished items in v{ver}", file=sys.stderr)
        return None
    return None


def _git_head(root: Path) -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root),
                             capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except FileNotFoundError:
        pass
    return None


def _record_last_seen_sha(root: Path) -> None:
    """Stamp config with current HEAD after a successful check-off (clears drift nudge)."""
    head = _git_head(root)
    if not head:
        return
    try:
        cfg = read_config(root)
    except (FileNotFoundError, json.JSONDecodeError):
        return
    if cfg.get("last_seen_sha") == head:
        return
    cfg["last_seen_sha"] = head
    write_config(root, cfg)


def drift_check(root: Path) -> str | None:
    """If the repo has commits since last check-off and the current version still has
    unfinished work, return a nudge message; otherwise None. Never raises; safe no-op
    without .roadmap/ or git."""
    try:
        cfg = read_config(root)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None
    head = _git_head(root)
    if not head:
        return None
    last = cfg.get("last_seen_sha")
    if not last or last == head:
        return None
    # Count commits between last seen and HEAD (best-effort)
    n = 0
    try:
        out = subprocess.run(
            ["git", "rev-list", "--count", f"{last}..HEAD"],
            cwd=str(root), capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip().isdigit():
            n = int(out.stdout.strip())
    except FileNotFoundError:
        return None
    if n <= 0:
        return None
    st = status(root)
    ver = st["currentVersion"]
    unfinished = [i for i in st["items"] if i["version"] == ver and i["pct"] < 100]
    if not unfinished:
        return None
    return (f"⚠ {n} commit(s) since last roadmap check-off — "
            f"run /roadmap:catchup or /roadmap-catchup?")


def _git_dirty(root: Path) -> bool:
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=str(root),
                             capture_output=True, text=True)
        return out.returncode == 0 and bool(out.stdout.strip())
    except FileNotFoundError:
        return False


def orient(root: Path) -> dict | None:
    """Session orientation: project, progress, next item, drift, skill versions.
    Returns None when .roadmap/ is absent — safe for hooks."""
    if not (roadmap_dir(root) / "config.json").exists():
        return None
    cfg = read_config(root)
    st = status(root)
    ver = st["currentVersion"]
    in_ver = [i for i in st["items"] if i["version"] == ver]
    steps_done = sum(i["done"] for i in in_ver)
    steps_total = sum(i["total"] for i in in_ver)
    items_done = sum(1 for i in in_ver if i["pct"] == 100)
    nxt = next_item(root, version=ver, quiet=True)
    installed = get_version()
    recorded = cfg.get("skillVersion") or "unknown"
    return {
        "project": st["project"],
        "currentVersion": ver,
        "stepsDone": steps_done,
        "stepsTotal": steps_total,
        "itemsDone": items_done,
        "itemsTotal": len(in_ver),
        "next": ({"id": nxt["id"], "title": nxt["title"], "type": nxt["type"],
                  "pct": nxt["pct"], "blockedBy": nxt.get("blockedBy") or [],
                  "file": nxt.get("file")}
                 if nxt else None),
        "drift": drift_check(root),
        "skillVersionInstalled": installed,
        "skillVersionProject": recorded,
        "skillVersionStale": recorded not in ("unknown", installed),
        "gitDirty": _git_dirty(root),
    }


def format_orient(payload: dict, handoff: bool = False) -> str:
    lines = [
        f"Roadmap: {payload['project']} — v{payload['currentVersion']}",
        f"Progress: {payload['itemsDone']}/{payload['itemsTotal']} items · "
        f"{payload['stepsDone']}/{payload['stepsTotal']} steps",
    ]
    nxt = payload.get("next")
    if nxt:
        nid = nxt["id"]
        lines.append(f"Next: #{nid} {nxt['title']} [{nxt['type']}] — {nxt['pct']}%")
        if handoff and nxt.get("file"):
            lines.append(f"Plan: .roadmap/{nxt['file']}")
        # Dual slash forms so Grok never gets colon-only recommendations
        lines.append(
            f"Continue: /roadmap:next · /roadmap-next · /roadmap next"
            f"  OR  /roadmap:build {nid} · /roadmap-build {nid} · /roadmap build {nid}"
        )
        lines.append(
            f"Chain version (pauses off): /roadmap:build {payload['currentVersion']} --auto"
            f" · /roadmap-build {payload['currentVersion']} --auto"
            f"  (not next --auto — next is always one item)"
        )
    else:
        lines.append("Next: (none — current version complete or all remaining items blocked)")
    if payload.get("drift"):
        lines.append(payload["drift"])
    if payload.get("gitDirty"):
        lines.append("⚠ Working tree has uncommitted changes — commit code+roadmap (or "
                     "inspect) before building more so nothing is agent-private.")
    inst = payload.get("skillVersionInstalled", "?")
    proj = payload.get("skillVersionProject", "?")
    if payload.get("skillVersionStale"):
        lines.append(f"⚠ Project rules at skill v{proj} but installed skill is v{inst} — "
                     f"run: roadmap.py upgrade")
    elif handoff:
        lines.append(f"Skill: v{inst} (project rules recorded: v{proj})")
    # Always useful after rate-limit / crash / agent switch (handoff adds the full list).
    if payload.get("gitDirty") or payload.get("drift") or handoff:
        lines.append(
            "Resume: commit or catchup if needed, then continue the plan checklist "
            "(/roadmap:next · /roadmap-next) — formal handoff is optional; git is the sync.")
    if handoff:
        lines.extend([
            "",
            "Multi-coder / rate-limit checklist:",
            "  1. Prefer micro-commits after every checked step (limits loss on rate-limit)",
            "  2. If you could not handoff: just open the other agent — run orient/handoff there",
            "  3. Commit any dirty tree (code + roadmap) the previous agent left",
            "  4. git pull/push if machines differ",
            "  5. Drift → /roadmap:catchup after tests; then next unfinished step",
            "  6. Continue quality-first build (do not re-plan from chat memory)",
            "Shared source of truth: ROADMAP.md + .roadmap/ + CHANGELOG*.md in git.",
        ])
    return "\n".join(lines)


def handoff(root: Path) -> dict | None:
    """Brief for switching between AI coders (Claude ↔ Grok ↔ …). Same data as orient
    with an explicit handoff checklist."""
    return orient(root)


INCUBATOR_BULLET_RE = re.compile(r"^(\s*[-*+]\s+)(.+)$")


def list_incubator_bullets(root: Path) -> list[dict]:
    """Parse free-form Idea Incubator bullets (from ROADMAP.md, or the external
    incubator file when settings.incubatorFile is set)."""
    rm = incubator_file(root)
    if not rm.exists():
        return []
    text = rm.read_text(encoding="utf-8")
    m = INCUBATOR_RE.search(text)
    if not m:
        return []
    bullets = []
    for line in text[m.end():].splitlines():
        if re.match(r"^#{1,6}\s+", line):
            break
        bm = INCUBATOR_BULLET_RE.match(line)
        if not bm:
            continue
        body = bm.group(2).strip()
        # Title is the line without a trailing markdown link
        title = re.sub(r"\s*\([^)]*\)\s*$", "", body).strip()
        title = re.sub(r"\s*\[[^\]]*\]\([^)]*\)\s*$", "", title).strip()
        bullets.append({"line": line, "body": body, "title": title or body})
    return bullets


def promote_idea(root: Path, *, match: str | None = None, index: int | None = None,
                 type_: str = "feature", version: str | None = None,
                 note: str = "", audience: str | None = None,
                 force: bool = False) -> Path:
    """Lift one Idea Incubator bullet into a tracked plan item and remove that bullet.

    Select by 1-based --index or by --match substring against the bullet title.
    Exactly one selector required when multiple bullets exist; a single bullet can be
    promoted with no selector.
    """
    if match and index is not None:
        raise ValueError("pass only one of --match / --index")
    _strip_incubator_placeholder(root)
    bullets = list_incubator_bullets(root)
    if not bullets:
        raise ValueError("Idea Incubator is empty — nothing to promote")
    chosen = None
    if index is not None:
        if index < 1 or index > len(bullets):
            raise ValueError(f"--index {index} out of range (1..{len(bullets)})")
        chosen = bullets[index - 1]
    elif match:
        hits = [b for b in bullets if match.lower() in b["title"].lower()
                or match.lower() in b["body"].lower()]
        if not hits:
            raise ValueError(f"no incubator bullet matches {match!r}")
        if len(hits) > 1:
            raise ValueError(
                f"{len(hits)} bullets match {match!r}; use a tighter --match or --index")
        chosen = hits[0]
    elif len(bullets) == 1:
        chosen = bullets[0]
    else:
        listing = "\n".join(f"  {i}. {b['title']}" for i, b in enumerate(bullets, 1))
        raise ValueError(
            f"multiple incubator bullets — pass --index N or --match TEXT:\n{listing}")

    title = chosen["title"]
    path = new_item(root, type_, title, version=version, note=note, audience=audience,
                    force=force)

    # Remove only the chosen bullet from the incubator (free-form region).
    rm = incubator_file(root)
    text = rm.read_text(encoding="utf-8")
    new_lines, removed = [], False
    target = chosen["line"].rstrip("\n")
    for line in text.splitlines(keepends=True):
        if not removed and line.rstrip("\n") == target:
            removed = True
            continue
        if not removed and chosen["body"] in line and INCUBATOR_BULLET_RE.match(
                line.rstrip("\n")):
            removed = True
            continue
        new_lines.append(line)
    atomic_write(rm, "".join(new_lines))
    return path


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


def _apply_rules_block(path: Path) -> None:
    """Idempotently write RULES_BLOCK into path (create or replace markers)."""
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if RULES_START in existing and RULES_END in existing:
        after = existing.split(RULES_END, 1)[1].lstrip("\n")
        new = existing.split(RULES_START)[0] + RULES_BLOCK + "\n" + after
    elif existing.strip():
        new = existing.rstrip() + "\n\n" + RULES_BLOCK + "\n"
    else:
        new = RULES_BLOCK + "\n"
    atomic_write(path, new)


def ensure_claude_md_rules(root: Path) -> Path:
    """Idempotently add the roadmap rules block to CLAUDE.md (creating it if absent).

    Also writes the same block to AGENTS.md so Grok, Codex, Cursor, and other
    agent-neutral readers pick up the same guardrails. Returns the CLAUDE.md path
    for backward compatibility with install.sh / tests.
    """
    ensure_project_rules(root)
    return root / "CLAUDE.md"


def ensure_project_rules(root: Path) -> list[Path]:
    """Write the roadmap rules block into every agent instruction file we know about."""
    written = []
    for name in RULES_FILES:
        path = root / name
        _apply_rules_block(path)
        written.append(path)
    return written


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
        ensure_project_rules(root)
    sync(root)
    return cfg


def upgrade(root: Path) -> None:
    """Project-level: refresh CLAUDE.md + AGENTS.md rules to the current skill version
    and resync. Run after updating the skill globally (global install does not touch
    per-project instruction files)."""
    cfg = read_config(root)
    old = cfg.get("skillVersion", "unknown")
    new = get_version()
    paths = ensure_project_rules(root)
    cfg["skillVersion"] = new
    write_config(root, cfg)
    sync(root)
    names = ", ".join(p.name for p in paths)
    print(f"Refreshed roadmap rules in {names} ({old} → v{new})")


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>roadmap</title>
<style>
  :root {
    --bg:#0e1116; --line:#232a34; --fg:#e6edf3; --muted:#8b98a5;
    --bar:#242c38; --done:#3fb950; --active:#d29922; --blocked:#f85149;
    --todo:#4b5563; --accent:#58a6ff;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
    font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }
  header { padding:20px 24px; border-bottom:1px solid var(--line);
    display:flex; align-items:baseline; gap:16px; flex-wrap:wrap; }
  header h1 { font-size:16px; margin:0; font-weight:600; }
  header .ver { color:var(--accent); }
  header .overall { margin-left:auto; color:var(--muted); font-size:12px; }
  #stale { display:inline-block; width:8px; height:8px; border-radius:50%;
    background:var(--done); margin-right:6px; vertical-align:middle;
    transition:background .3s; }
  #stale.off { background:var(--todo); }
  main { max-width:820px; margin:0 auto; padding:20px 24px 60px; }
  .ver-group { margin-bottom:26px; }
  .ver-head { display:flex; align-items:center; gap:10px; cursor:pointer;
    padding:6px 0; user-select:none; }
  .ver-head h2 { font-size:13px; margin:0; letter-spacing:.02em; }
  .ver-head .vpct { color:var(--muted); font-size:12px; margin-left:auto; }
  .ver-group.collapsed .items { display:none; }
  .chev { color:var(--muted); transition:transform .15s; }
  .ver-group.collapsed .chev { transform:rotate(-90deg); }
  .item { display:grid; grid-template-columns:14px 1fr auto;
    gap:10px; align-items:center; padding:7px 0;
    border-top:1px solid var(--line); }
  .dot { width:9px; height:9px; border-radius:50%; background:var(--todo); }
  .dot.done { background:var(--done); }
  .dot.active { background:var(--active); }
  .dot.blocked { background:var(--blocked); }
  .title { display:flex; align-items:center; gap:8px; min-width:0; }
  .title .num { color:var(--muted); flex:none; font-variant-numeric:tabular-nums; }
  .title .t { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .badge { font-size:10px; color:var(--muted); border:1px solid var(--line);
    border-radius:4px; padding:1px 5px; flex:none; }
  .blockedby { font-size:11px; color:var(--blocked); flex:none; }
  .right { display:flex; align-items:center; gap:10px; }
  .bar { width:120px; height:6px; background:var(--bar); border-radius:3px;
    overflow:hidden; }
  .bar > i { display:block; height:100%; background:var(--done);
    transition:width .3s; }
  .frac { color:var(--muted); font-size:12px; min-width:38px; text-align:right; }
  .empty { color:var(--muted); padding:40px 0; text-align:center; }
</style>
</head>
<body>
<header>
  <h1><span id="stale" title="live"></span><span id="project">roadmap</span>
    <span class="ver" id="cver"></span></h1>
  <span class="overall" id="overall"></span>
</header>
<main id="app"><div class="empty">connecting…</div></main>
<script>
// All text goes in via textContent — no innerHTML, no injection surface.
const DOT = s => ({done:"done",active:"active",blocked:"blocked"}[s]||"todo");
const el = (tag,cls) => { const e=document.createElement(tag);
  if(cls) e.className=cls; return e; };
const txt = (tag,cls,s) => { const e=el(tag,cls); e.textContent=s; return e; };
// Default: the current version is expanded, all others collapsed. `prefs` holds
// only the versions the user explicitly toggled, so it overrides the default and
// auto-advance still opens whatever the new current version is.
const prefs = JSON.parse(localStorage.getItem("rm-prefs")||"{}");
const savePrefs = () => localStorage.setItem("rm-prefs", JSON.stringify(prefs));
const isOpen = (v,cur) => (v in prefs) ? prefs[v] : (v === cur);
const stale = off => document.getElementById("stale").classList.toggle("off", off);

function itemRow(it){
  const row = el("div","item");
  row.appendChild(el("span","dot "+DOT(it.status)));
  const title = el("span","title");
  title.appendChild(txt("span","num", "#"+it.id));
  title.appendChild(txt("span","t", it.title));
  title.appendChild(txt("span","badge", it.type));
  if(it.blockedBy && it.blockedBy.length)
    title.appendChild(txt("span","blockedby",
      "blocked by "+it.blockedBy.map(x=>"#"+x).join(",")));
  row.appendChild(title);
  const right = el("span","right");
  const bar = el("span","bar"); const fill = el("i");
  fill.style.width = (it.pct||0)+"%"; bar.appendChild(fill);
  right.appendChild(bar);
  right.appendChild(txt("span","frac", (it.done||0)+"/"+(it.total||0)));
  row.appendChild(right);
  return row;
}

function verSection(v, items, cur){
  const gd = items.reduce((a,i)=>a+(i.done||0),0);
  const gt = items.reduce((a,i)=>a+(i.total||0),0);
  const sec = el("section","ver-group");
  if(!isOpen(v,cur)) sec.classList.add("collapsed");   // current open, rest closed
  sec.dataset.v = v;
  const head = el("div","ver-head");
  head.appendChild(txt("span","chev","▾"));
  head.appendChild(txt("h2",null,"v"+v+(v===cur?" · current":"")));
  head.appendChild(txt("span","vpct",
    (gt?Math.round(100*gd/gt):0)+"% · "+gd+"/"+gt));
  head.onclick = () => {
    sec.classList.toggle("collapsed");
    prefs[v] = !sec.classList.contains("collapsed");
    savePrefs();
  };
  sec.appendChild(head);
  const box = el("div","items");
  for(const it of items) box.appendChild(itemRow(it));
  sec.appendChild(box);
  return sec;
}

function render(d){
  document.getElementById("project").textContent = d.project || "roadmap";
  document.getElementById("cver").textContent =
    d.currentVersion ? "v"+d.currentVersion : "";
  const items = d.items || [];
  const td = items.reduce((a,i)=>a+(i.done||0),0);
  const tt = items.reduce((a,i)=>a+(i.total||0),0);
  document.getElementById("overall").textContent =
    tt ? Math.round(100*td/tt)+"% overall ("+td+"/"+tt+")" : "";
  const app = document.getElementById("app");
  if(!items.length){
    app.replaceChildren(txt("div","empty", d.error||"no roadmap items yet"));
    return;
  }
  const groups = {};
  for(const it of items){ (groups[it.version] ||= []).push(it); }
  const cur = d.currentVersion;
  const vers = Object.keys(groups).sort((a,b)=>
    a===cur?-1:b===cur?1:(a<b?1:-1));
  app.replaceChildren(...vers.map(v=>verSection(v, groups[v], cur)));
}

// Server-Sent Events: server pushes a fresh status on every .roadmap change.
// EventSource auto-reconnects on drop, so a closed terminal just goes stale-grey.
let es;
function connect(){
  es = new EventSource("/events");
  es.onmessage = ev => { try { render(JSON.parse(ev.data)); stale(false); }
    catch(_){} };
  es.onerror = () => stale(true);
}
connect();
</script>
</body>
</html>
"""


def _status_line(st: dict) -> str:
    items = st.get("items", [])
    td = sum(i.get("done", 0) for i in items)
    tt = sum(i.get("total", 0) for i in items)
    pct = round(100 * td / tt) if tt else 0
    active = sum(1 for i in items if i.get("status") == "active")
    ver = st.get("currentVersion") or "?"
    nvers = len({i.get("version") for i in items})
    return (f"current v{ver} · {pct}% ({td}/{tt}) · {active} active"
            f" · {nvers} version{'s' if nvers != 1 else ''}")


def _roadmap_signature(root: Path):
    """Cheap change token: newest mtime across .roadmap/ and ROADMAP.md."""
    latest = 0.0
    try:
        for f in roadmap_dir(root).rglob("*"):
            try:
                latest = max(latest, f.stat().st_mtime)
            except OSError:
                pass
        rm = root / "ROADMAP.md"
        if rm.exists():
            latest = max(latest, rm.stat().st_mtime)
    except OSError:
        pass
    return latest


def _safe_status(root: Path) -> dict:
    try:
        return status(root)
    except (ValueError, FileNotFoundError, OSError) as e:
        return {"project": None, "currentVersion": None, "items": [],
                "error": str(e)}


DEFAULT_PORT = 4700
PORT_SPAN = 40


def _project_port(root: Path) -> int:
    """Stable preferred port derived from the project path, so the same project
    always maps to the same port (one dashboard per project) while different
    projects land on different ports and coexist."""
    import hashlib
    h = hashlib.md5(str(root.resolve()).encode("utf-8")).hexdigest()
    return DEFAULT_PORT + int(h, 16) % PORT_SPAN


def _running_dashboard(root: Path, port: int):
    """Return the URL if a dashboard for THIS project is already serving on
    `port`, else None. Matched via the X-Roadmap-Root response header."""
    import urllib.request
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/status")
        with urllib.request.urlopen(req, timeout=0.4) as r:
            if r.headers.get("X-Roadmap-Root") == str(root.resolve()):
                return f"http://127.0.0.1:{port}"
    except Exception:
        return None
    return None


def serve(root: Path, port: int | None = None, open_browser: bool = True) -> int:
    """Run a local, read-only web dashboard that pushes live updates via SSE.

    One dashboard per project: port=None derives a stable port from the project
    path. If this project is already being served (in another terminal), point
    at that instance instead of starting a duplicate. Different projects get
    different ports and run side by side. An explicit --port is honored strictly.
    """
    import http.server
    import threading
    import time
    import webbrowser

    if not roadmap_dir(root).exists():
        print("No .roadmap/ here — run `roadmap init` first, then `roadmap serve`.")
        return 0

    root_id = str(root.resolve())

    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Roadmap-Root", root_id)
            self.end_headers()
            self.wfile.write(body)

        def _sse(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Roadmap-Root", root_id)
            self.end_headers()
            last_sig = None
            try:
                while True:
                    sig = _roadmap_signature(root)
                    if sig != last_sig:
                        last_sig = sig
                        data = "data: " + json.dumps(_safe_status(root)) + "\n\n"
                        self.wfile.write(data.encode("utf-8"))
                    else:
                        self.wfile.write(b": ping\n\n")   # keepalive / disconnect probe
                    self.wfile.flush()
                    time.sleep(1)
            except (BrokenPipeError, ConnectionResetError):
                return

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send(200, DASHBOARD_HTML.encode("utf-8"),
                           "text/html; charset=utf-8")
            elif path == "/events":
                self._sse()
            elif path == "/api/status":
                self._send(200, json.dumps(_safe_status(root)).encode("utf-8"),
                           "application/json")
            elif path == "/api/changelog":
                try:
                    payload = changelog_json(root)
                except (ValueError, FileNotFoundError, OSError) as e:
                    payload = {"error": str(e)}
                self._send(200, json.dumps(payload).encode("utf-8"),
                           "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def log_message(self, *args) -> None:  # silence per-request logging
            pass

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True   # worker threads die with the process

        def handle_error(self, request, client_address) -> None:
            # A browser closing an SSE stream resets the socket — that is normal,
            # not an error. Swallow it instead of dumping a traceback.
            exc = sys.exc_info()[1]
            if isinstance(exc, (ConnectionResetError, BrokenPipeError,
                                ConnectionAbortedError)):
                return
            super().handle_error(request, client_address)

    if port is None:
        preferred = _project_port(root)
        # Already serving THIS project in another terminal? Point at it, don't
        # start a duplicate. Scan the span in case it landed on a fallback port.
        for candidate in range(preferred, preferred + PORT_SPAN):
            existing = _running_dashboard(root, candidate)
            if existing:
                print(f"This project is already being served → {existing}"
                      "  (one dashboard per project)")
                if open_browser:
                    try:
                        webbrowser.open(existing)
                    except Exception:
                        pass
                return 0
        # Bind the project's stable port; if taken by something else, scan up.
        httpd = None
        for candidate in range(preferred, preferred + PORT_SPAN):
            try:
                httpd = Server(("127.0.0.1", candidate), Handler)
                break
            except OSError:
                continue
        if httpd is None:
            print(f"Error: no free port in {preferred}-{preferred + PORT_SPAN - 1} "
                  "(too many dashboards running?)", file=sys.stderr)
            return 1
    else:
        try:
            httpd = Server(("127.0.0.1", port), Handler)
        except OSError as e:
            print(f"Error: cannot bind 127.0.0.1:{port} — {e}", file=sys.stderr)
            return 1
    port = httpd.server_address[1]

    # Mirror live progress into the terminal running `serve`.
    def watch_terminal() -> None:
        last = _roadmap_signature(root)
        while True:
            time.sleep(1)
            sig = _roadmap_signature(root)
            if sig != last:
                last = sig
                print(f"  ↻ {_status_line(_safe_status(root))}", flush=True)

    threading.Thread(target=watch_terminal, daemon=True).start()

    url = f"http://127.0.0.1:{port}"
    print(f"roadmap dashboard → {url}  (Ctrl-C to stop)")
    print(f"  {_status_line(_safe_status(root))}", flush=True)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        httpd.server_close()
    return 0


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
    p_new.add_argument("--force", action="store_true",
                       help="save a public note even if it reads like a status dump")

    p_note = sub.add_parser("note")
    p_note.add_argument("--plan", type=int, required=True)
    p_note.add_argument("--text", required=True)
    p_note.add_argument("--force", action="store_true",
                        help="save a public note even if it reads like a status dump")

    p_aud = sub.add_parser("audience")
    p_aud.add_argument("--plan", type=int, required=True)
    p_aud.add_argument("--to", required=True, choices=["public", "internal"])

    p_sum = sub.add_parser("summary",
                           help="set a version's public release-notes blurb "
                                "(renders instead of item bullets in CHANGELOG.md)")
    p_sum.add_argument("--version", required=True)
    p_sum.add_argument("--text")
    p_sum.add_argument("--clear", action="store_true",
                       help="remove the blurb (fall back to item bullets)")
    p_sum.add_argument("--force", action="store_true",
                       help="save even if the text reads like a status dump")

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

    p_srv = sub.add_parser("serve",
                           help="local live web dashboard (SSE push, read-only)")
    p_srv.add_argument("--port", type=int, default=None,
                       help="fixed port; default auto-scans from 4700")
    p_srv.add_argument("--no-open", action="store_false", dest="open_browser",
                       help="do not open a browser window")

    p_next = sub.add_parser("next", help="print the next unblocked unfinished item")
    p_next.add_argument("--version", help="target version (default: current)")
    p_next.add_argument("--json", action="store_true", dest="as_json")
    p_next.add_argument("--force", action="store_true",
                        help="ignore dependsOn blockers")

    p_orient = sub.add_parser("orient", help="session orientation (safe no-op without .roadmap/)")
    p_orient.add_argument("--json", action="store_true", dest="as_json")
    p_orient.add_argument("--hook", action="store_true",
                          help="emit Claude SessionStart additionalContext JSON")

    p_handoff = sub.add_parser(
        "handoff",
        help="multi-coder switch brief (orient + drift + git dirty + checklist)")
    p_handoff.add_argument("--json", action="store_true", dest="as_json")

    sub.add_parser("drift-check", help="nudge if commits landed without check-off")

    p_promote = sub.add_parser("promote", help="lift an Idea Incubator bullet into a plan")
    p_promote.add_argument("--match", help="substring match against incubator bullet title")
    p_promote.add_argument("--index", type=int, help="1-based index into incubator bullets")
    p_promote.add_argument("--type", default="feature")
    p_promote.add_argument("--version")
    p_promote.add_argument("--note", default="")
    p_promote.add_argument("--audience", choices=["public", "internal"])
    p_promote.add_argument("--force", action="store_true",
                           help="save a public note even if it reads like a status dump")

    p_deps = sub.add_parser("deps-check",
                            help="warn if a plan's dependsOn targets are incomplete")
    p_deps.add_argument("--plan", type=int, required=True)
    p_deps.add_argument("--force", action="store_true")

    sub.add_parser("sync")
    sub.add_parser("version")
    sub.add_parser("upgrade")

    p_tidy = sub.add_parser(
        "tidy", help="report free-form / Idea Incubator hygiene issues (report-only)")
    p_tidy.add_argument("--json", action="store_true", dest="as_json")
    p_tidy.add_argument("--externalize", nargs="?", const=".roadmap/IDEAS.md",
                        metavar="PATH",
                        help="move the Idea Incubator into PATH (default "
                             ".roadmap/IDEAS.md), leaving a link in ROADMAP.md")

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

    p_idea = sub.add_parser("idea")
    p_idea.add_argument("--title", required=True)
    p_idea.add_argument("--body", help="long-form content -> .roadmap/notes/ file")
    p_idea.add_argument("--body-file", dest="body_file",
                        help="read long-form content from a file")

    p_cl = sub.add_parser("changelog")
    p_cl.add_argument("--backfill", action="store_true")
    p_cl.add_argument("--internal", action="store_true",
                      help="print CHANGELOG.internal.md instead of the public CHANGELOG.md")
    p_cl.add_argument("--json", action="store_true", dest="as_json",
                      help="emit the public changelog as structured JSON "
                           "(for in-app changelog screens / What's New popups)")

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
                            note=args.note, audience=args.audience, force=args.force)
            print(path)
            return 0
        if args.command == "note":
            set_note(root, args.plan, args.text, force=args.force)
            return 0
        if args.command == "audience":
            set_audience(root, args.plan, args.to)
            return 0
        if args.command == "summary":
            set_release_summary(root, args.version, text=args.text,
                                clear=args.clear, force=args.force)
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
        if args.command == "tidy":
            if args.externalize:
                dest = externalize_incubator(root, args.externalize)
                print(f"Idea Incubator moved to {dest.relative_to(root)} — ROADMAP.md "
                      "keeps a link; idea/promote/remove now target it.")
                return 0
            rep = tidy_report(root)
            if args.as_json:
                print(json.dumps(rep, indent=2))
            else:
                print(format_tidy(rep))
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
        if args.command == "idea":
            body = args.body
            if args.body_file:
                body = Path(args.body_file).read_text(encoding="utf-8")
            note = add_idea(root, args.title, body)
            print(f"Parked idea: {args.title}" + (f" (notes: {note})" if note else ""))
            return 0
        if args.command == "promote":
            path = promote_idea(root, match=args.match, index=args.index,
                                type_=args.type, version=args.version,
                                note=args.note, audience=args.audience,
                                force=args.force)
            print(path)
            return 0
        if args.command == "next":
            item = next_item(root, version=args.version, force=args.force)
            if item is None:
                print("No unfinished unblocked items.")
                return 0
            if args.as_json:
                print(json.dumps(item, indent=2))
            else:
                print(f"#{item['id']} {item['title']} [{item['type']}] "
                      f"v{item['version']} — {item['pct']}% "
                      f"(.roadmap/{item['file']})")
            return 0
        if args.command == "orient":
            payload = orient(root)
            if payload is None:
                return 0
            text = format_orient(payload)
            if args.hook:
                # Claude Code SessionStart: inject as additionalContext
                print(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": text,
                    }
                }))
            elif args.as_json:
                print(json.dumps(payload, indent=2))
            else:
                print(text)
            return 0
        if args.command == "handoff":
            payload = handoff(root)
            if payload is None:
                print("No .roadmap/ here — nothing to hand off.")
                return 0
            if args.as_json:
                print(json.dumps(payload, indent=2))
            else:
                print(format_orient(payload, handoff=True))
            return 0
        if args.command == "drift-check":
            msg = drift_check(root)
            if msg:
                print(msg)
            return 0
        if args.command == "deps-check":
            blocked = warn_incomplete_deps(root, args.plan, force=args.force)
            if args.force or not blocked:
                print(f"#{args.plan}: ok" + (" (force)" if args.force and blocked else ""))
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
            if args.as_json:
                print(json.dumps(changelog_json(root), indent=2))
                return 0
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
                    block = (f" blocked by {it['blockedBy']}"
                             if it.get("blockedBy") else "")
                    print(f"  #{it['id']} {it['title']} [{it['type']}] "
                          f"{it['pct']}% ({it['status']}){block}")
            for w in roadmap_health(root):
                print(f"warning: {w}", file=sys.stderr)
            return 0
        if args.command == "serve":
            return serve(root, port=args.port, open_browser=args.open_browser)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
