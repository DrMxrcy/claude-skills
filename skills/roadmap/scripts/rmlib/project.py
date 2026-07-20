"""roadmap project lifecycle — init, upgrade, and CLAUDE.md/AGENTS.md rules.
Layer: rmcore + rmsync."""
from __future__ import annotations
from pathlib import Path
from rmlib.core import (
    AUTO_END, AUTO_START, RULES_BLOCK, RULES_END, RULES_FILES, RULES_START,
    _norm_version, _render_template, atomic_write, detect_version,
    get_version, read_config, roadmap_dir, write_config)
from rmlib.sync import (
    sync)


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
