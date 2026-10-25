# Roadmap removal + live changelog + dependency wiring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `remove` command, make the user-facing changelog a live artifact rendered on every `sync` (decoupled from the unused `release`), implement the missing `depends` setter, and surface the CLI-only verbs.

**Architecture:** All four changes mutate `.roadmap/config.json` and rely on the existing `sync()` re-render. The changelog moves from an append-in-`release()` step to a `render_changelog()` function called inside `sync()`, with per-version completion dates persisted in `config.json` (`versionDates`) for deterministic re-rendering. `remove` archives the plan file and demotes the item to the free-form Idea Incubator. `depends` writes the `dependsOn` field that `merge_items()` and `reevaluate.md` already consume.

**Tech Stack:** Python 3 stdlib only (`argparse`, `json`, `re`, `subprocess`, `datetime`, `pathlib`). Tests: pytest with `roadmap` + `repo` fixtures from `tests/conftest.py`.

**Design descope (important):** The spec's open-point ① (derive `currentVersion` in `sync`) is **dropped**. Reading the tests showed it conflicts with `test_release_force_bypasses_incomplete` (force-release would snap `currentVersion` back to the incomplete version) and it is unnecessary — the changelog groups by each item's own `version`, never `currentVersion`. `currentVersion` stays a stored pointer.

**File map:**
- Modify: `skills/roadmap/scripts/roadmap.py` (new functions + CLI wiring; remove `write_changelog`; slim `release`)
- Modify: `tests/test_roadmap.py` (new tests; update changelog/release tests)
- Create: `commands/roadmap/remove.md`
- Modify: `skills/roadmap/SKILL.md`, `README.md`, `skills/roadmap/VERSION`

Run all tests with: `python3 -m pytest tests/test_roadmap.py -q` (from repo root).

---

### Task 1: `depends` command (dependency setter)

**Files:**
- Modify: `skills/roadmap/scripts/roadmap.py` (add `set_depends`, CLI wiring)
- Test: `tests/test_roadmap.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_roadmap.py`:

```python
def test_depends_sets_field(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")   # 1
    roadmap.new_item(repo, "feature", "B")   # 2
    roadmap.set_depends(repo, 2, [1])
    dep = next(i for i in roadmap.read_config(repo)["items"] if i["id"] == 2)
    assert dep["dependsOn"] == [1]


def test_depends_dedups_and_preserves_order(roadmap, repo):
    roadmap.init_project(repo, "P")
    for t in ("A", "B", "C"):
        roadmap.new_item(repo, "feature", t)
    roadmap.set_depends(repo, 3, [2, 1, 2])
    dep = next(i for i in roadmap.read_config(repo)["items"] if i["id"] == 3)
    assert dep["dependsOn"] == [2, 1]


def test_depends_rejects_self_and_unknown(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    with pytest.raises(ValueError):
        roadmap.set_depends(repo, 1, [1])        # self
    with pytest.raises(ValueError):
        roadmap.set_depends(repo, 1, [99])       # unknown target
    with pytest.raises(ValueError):
        roadmap.set_depends(repo, 99, [1])       # unknown plan


def test_depends_clear_removes_field(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.new_item(repo, "feature", "B")
    roadmap.set_depends(repo, 2, [1])
    roadmap.set_depends(repo, 2, [], clear=True)
    dep = next(i for i in roadmap.read_config(repo)["items"] if i["id"] == 2)
    assert "dependsOn" not in dep


def test_cli_depends(roadmap, repo, monkeypatch):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.new_item(repo, "feature", "B")
    assert roadmap.main(["depends", "--plan", "2", "--on", "1"]) == 0
    dep = next(i for i in roadmap.read_config(repo)["items"] if i["id"] == 2)
    assert dep["dependsOn"] == [1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_roadmap.py -k depends -q`
Expected: FAIL — `module 'roadmap' has no attribute 'set_depends'`.

- [ ] **Step 3: Implement `set_depends`**

Add to `skills/roadmap/scripts/roadmap.py` after `set_note` (around line 322):

```python
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
```

- [ ] **Step 4: Wire the CLI**

In `main()`, add the subparser after the `p_mg` (merge) block (around line 584):

```python
    p_dep = sub.add_parser("depends")
    p_dep.add_argument("--plan", type=int, required=True)
    p_dep.add_argument("--on", default="")
    p_dep.add_argument("--clear", action="store_true")
```

And add the dispatch branch after the `merge` branch (around line 619):

```python
        if args.command == "depends":
            set_depends(root, args.plan,
                        [int(x) for x in args.on.split(",") if x.strip()],
                        clear=args.clear)
            return 0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_roadmap.py -k depends -q`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add skills/roadmap/scripts/roadmap.py tests/test_roadmap.py
git commit -m "feat(roadmap): add depends command to set dependsOn"
```

---

### Task 2: `remove` command (archive + demote to Incubator)

**Files:**
- Modify: `skills/roadmap/scripts/roadmap.py` (add `_incubator_stub`, `remove_item`, CLI wiring)
- Test: `tests/test_roadmap.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_roadmap.py`:

```python
def test_remove_archives_and_drops(roadmap, repo):
    roadmap.init_project(repo, "P")
    p = roadmap.new_item(repo, "feature", "Stray thing")
    roadmap.remove_item(repo, 1)
    cfg = roadmap.read_config(repo)
    assert cfg["items"] == []                                  # dropped from registry
    assert not p.exists()                                      # original gone
    assert (repo / ".roadmap/archive/001-stray-thing.md").exists()  # archived
    rm = (repo / "ROADMAP.md").read_text()
    assert "(was #1) Stray thing" in rm                        # demoted to Incubator
    assert rm.index("Idea Incubator") < rm.index("(was #1)")   # under the heading


def test_remove_retargets_dependents(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")   # 1
    roadmap.new_item(repo, "feature", "B")   # 2
    roadmap.set_depends(repo, 2, [1])
    roadmap.remove_item(repo, 1)
    dep = next(i for i in roadmap.read_config(repo)["items"] if i["id"] == 2)
    assert "dependsOn" not in dep            # link to removed item cleared


def test_remove_missing_plan_file_still_drops(roadmap, repo):
    roadmap.init_project(repo, "P")
    p = roadmap.new_item(repo, "feature", "A")
    p.unlink()                               # plan file already gone
    roadmap.remove_item(repo, 1)
    assert roadmap.read_config(repo)["items"] == []


def test_remove_unknown_id_raises(roadmap, repo):
    roadmap.init_project(repo, "P")
    with pytest.raises(ValueError):
        roadmap.remove_item(repo, 99)


def test_cli_remove(roadmap, repo, monkeypatch):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    assert roadmap.main(["remove", "--plan", "1"]) == 0
    assert roadmap.read_config(repo)["items"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_roadmap.py -k remove -q`
Expected: FAIL — `module 'roadmap' has no attribute 'remove_item'`.

- [ ] **Step 3: Implement `_incubator_stub` and `remove_item`**

Add to `skills/roadmap/scripts/roadmap.py` after `set_depends`:

```python
INCUBATOR_RE = re.compile(r"(?im)^#{1,6}\s+.*idea incubator.*$")


def _incubator_stub(root: Path, plan_id: int, title: str) -> None:
    """Append a breadcrumb for a removed item under the free-form Idea Incubator heading.
    Edits ROADMAP.md directly (outside the roadmap:auto markers, which sync owns)."""
    rm = root / "ROADMAP.md"
    text = rm.read_text(encoding="utf-8")
    stub = f"- (was #{plan_id}) {title}"
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
    if src.exists():
        dest = roadmap_dir(root) / "archive" / Path(item["file"]).name
        atomic_write(dest, src.read_text(encoding="utf-8"))
        src.unlink()
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
    _incubator_stub(root, plan_id, item["title"])
    sync(root)
```

- [ ] **Step 4: Wire the CLI**

In `main()`, add the subparser after the `depends` block:

```python
    p_rm = sub.add_parser("remove")
    p_rm.add_argument("--plan", type=int, required=True)
```

And the dispatch branch after the `depends` branch:

```python
        if args.command == "remove":
            remove_item(root, args.plan)
            return 0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_roadmap.py -k remove -q`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add skills/roadmap/scripts/roadmap.py tests/test_roadmap.py
git commit -m "feat(roadmap): add remove command (archive + demote to Incubator)"
```

---

### Task 3: Live changelog in `sync()` + slim `release()`

**Files:**
- Modify: `skills/roadmap/scripts/roadmap.py` (add `render_changelog`, version-date stamping in `sync`, remove `write_changelog`, slim `release`)
- Test: `tests/test_roadmap.py` (add completion + in-progress tests; remove `--no-changelog` test)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_roadmap.py`:

```python
def test_changelog_written_on_completion_via_sync(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login", note="Sign in with email")
    assert not (repo / "CHANGELOG.md").exists() or "(pending)" in (repo / "CHANGELOG.md").read_text()
    roadmap.check_step(repo, 1, None, all_done=True)           # triggers sync
    cl = (repo / "CHANGELOG.md").read_text()
    assert "## v0.0.1" in cl and "✨ New" in cl and "Sign in with email" in cl
    assert "(pending)" not in cl                               # version fully done


def test_changelog_in_progress_shows_pending(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Big feature")          # 0/2 done
    cl = (repo / "CHANGELOG.md").read_text()
    assert "(in progress)" in cl and "- (pending) Big feature" in cl


def test_changelog_date_is_stable_across_resync(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, None, all_done=True)
    first = (repo / "CHANGELOG.md").read_text()
    date = roadmap.read_config(repo)["versionDates"]["0.0.1"]
    roadmap.sync(repo)
    roadmap.sync(repo)
    assert (repo / "CHANGELOG.md").read_text() == first        # no churn
    assert roadmap.read_config(repo)["versionDates"]["0.0.1"] == date
```

Update the two existing changelog tests to drop the now-redundant `release` trigger (sync already wrote the file). Replace the bodies of `test_release_writes_changelog` and `test_changelog_uses_note_and_groups_by_type` so the final assertions read `CHANGELOG.md` after `check_step(..., all_done=True)` **without** a `release` call:

```python
def test_release_writes_changelog(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login")
    roadmap.check_step(repo, 1, None, all_done=True)           # sync writes changelog
    cl = (repo / "CHANGELOG.md").read_text()
    assert "## v0.0.1" in cl and "✨ New" in cl and "Login" in cl
    assert "(feature)" not in cl


def test_changelog_uses_note_and_groups_by_type(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Auth backend", note="Sign in with email")
    roadmap.new_item(repo, "bug", "Null deref on logout")
    roadmap.check_step(repo, 1, None, all_done=True)
    roadmap.check_step(repo, 2, None, all_done=True)
    cl = (repo / "CHANGELOG.md").read_text()
    assert "Sign in with email" in cl and "Auth backend" not in cl
    assert "🐛 Fixed" in cl and "Null deref on logout" in cl
    assert cl.index("✨ New") < cl.index("🐛 Fixed")
```

Delete `test_release_no_changelog_skips` entirely (the `--no-changelog` flag is removed).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_roadmap.py -k changelog -q`
Expected: FAIL — `render_changelog` missing / `CHANGELOG.md` not written by sync / `versionDates` KeyError.

- [ ] **Step 3: Add `render_changelog`**

Replace the entire `write_changelog` function (roadmap.py:398-431) with `render_changelog`:

```python
def render_changelog(root: Path) -> str:
    """Render CHANGELOG.md from config: every version that has items, grouped by section,
    using each item's user-facing `note` (fallback: title). A version is dated once all its
    items reach 100% (date persisted in config.versionDates for stable re-rendering);
    otherwise it renders '(in progress)' with '(pending)' lines for unfinished items."""
    cfg = read_config(root)
    version_dates = cfg.get("versionDates", {})
    by_version: dict[str, list] = {}
    for item in cfg["items"]:
        by_version.setdefault(item["version"], []).append(item)
    out = ["# Changelog", ""]
    for version in sorted(by_version, key=_version_key, reverse=True):
        vitems = sorted(by_version[version], key=lambda i: i["id"])
        sections: dict[str, list[tuple[bool, str]]] = {}
        done_all = True
        for it in vitems:
            p = roadmap_dir(root) / it["file"]
            done, total = count_progress(p) if p.exists() else (0, 0)
            complete = total > 0 and done == total
            done_all = done_all and complete
            section = TYPE_SECTION.get(it["type"], "⚡ Improved")
            sections.setdefault(section, []).append((complete, it.get("note") or it["title"]))
        date = version_dates.get(version)
        if done_all and date:
            out.append(f"## v{version} — {date}")
        elif done_all:
            out.append(f"## v{version}")
        else:
            out.append(f"## v{version} — (in progress)")
        out.append("")
        for section in SECTION_ORDER:
            entries = sections.get(section)
            if not entries:
                continue
            out.append(f"### {section}")
            out += [f"- {label}" if complete else f"- (pending) {label}"
                    for complete, label in entries]
            out.append("")
    return "\n".join(out).rstrip() + "\n"
```

- [ ] **Step 4: Stamp version dates + write changelog inside `sync()`**

In `sync()` (roadmap.py:175-216), after the progress loop that builds the `progress` dict and before `body = render_region(...)`, insert version-date stamping; and after the final `atomic_write(rm_path, ...)`, write the changelog. Concretely, edit `sync` so its tail reads:

```python
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
        if vitems and all((progress.get(i["id"], (0, 0))[1] > 0
                           and progress.get(i["id"], (0, 0))[0] == progress.get(i["id"], (0, 0))[1])
                          for i in vitems):
            version_dates[version] = datetime.date.today().isoformat()
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
    atomic_write(root / "CHANGELOG.md", render_changelog(root))
```

(The `changed` variable already exists earlier in `sync` for version normalization; this reuses it.)

- [ ] **Step 5: Slim `release()` — remove changelog responsibility**

Replace the `release` signature and body (roadmap.py:434-454) so it no longer writes the changelog and drops the `changelog` parameter:

```python
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
```

In `main()`, remove the `--no-changelog` argument (delete the line
`p_rel.add_argument("--no-changelog", action="store_false", dest="changelog")`) and change
the release dispatch to drop `changelog=args.changelog`:

```python
        if args.command == "release":
            release(root, args.version, tag=args.tag, force=args.force)
            return 0
```

- [ ] **Step 6: Run the full suite to verify pass + no regressions**

Run: `python3 -m pytest tests/test_roadmap.py -q`
Expected: PASS (all tests, including the updated `test_release_*` and the new changelog tests; `test_release_no_changelog_skips` is gone).

- [ ] **Step 7: Commit**

```bash
git add skills/roadmap/scripts/roadmap.py tests/test_roadmap.py
git commit -m "feat(roadmap): render CHANGELOG.md live in sync; decouple from release"
```

---

### Task 4: `changelog` CLI verb + `--backfill`

**Files:**
- Modify: `skills/roadmap/scripts/roadmap.py` (add `backfill_changelog`, `changelog` subcommand)
- Test: `tests/test_roadmap.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_roadmap.py`:

```python
def test_changelog_command_prints(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login", note="Sign in")
    roadmap.check_step(repo, 1, None, all_done=True)
    assert roadmap.main(["changelog"]) == 0
    assert "Sign in" in capsys.readouterr().out


def test_backfill_dates_from_git_tag(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, None, all_done=True)
    # remove the auto-stamped date so backfill has work to do
    cfg = roadmap.read_config(repo)
    cfg["versionDates"] = {}
    roadmap.write_config(repo, cfg)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=repo, check=True)
    subprocess.run(["git", "tag", "v0.0.1"], cwd=repo, check=True)
    roadmap.backfill_changelog(repo)
    date = roadmap.read_config(repo)["versionDates"].get("0.0.1")
    assert date and date.count("-") == 2          # ISO YYYY-MM-DD from tag commit


def test_backfill_no_tag_leaves_undated(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")        # incomplete, no tag
    cfg = roadmap.read_config(repo)
    cfg["versionDates"] = {}
    roadmap.write_config(repo, cfg)
    roadmap.backfill_changelog(repo)
    assert roadmap.read_config(repo)["versionDates"] == {}   # nothing to backfill
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_roadmap.py -k "changelog_command or backfill" -q`
Expected: FAIL — `backfill_changelog` missing / unknown command `changelog`.

- [ ] **Step 3: Implement `backfill_changelog`**

Add to `skills/roadmap/scripts/roadmap.py` after `render_changelog`:

```python
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
```

- [ ] **Step 4: Wire the CLI**

In `main()`, add after the `remove` subparser block:

```python
    p_cl = sub.add_parser("changelog")
    p_cl.add_argument("--backfill", action="store_true")
```

And the dispatch branch after the `remove` branch:

```python
        if args.command == "changelog":
            if args.backfill:
                backfill_changelog(root)
            else:
                sync(root)
            cl = root / "CHANGELOG.md"
            if cl.exists():
                print(cl.read_text(encoding="utf-8"), end="")
            return 0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_roadmap.py -k "changelog_command or backfill" -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add skills/roadmap/scripts/roadmap.py tests/test_roadmap.py
git commit -m "feat(roadmap): changelog CLI verb with --backfill from git tags"
```

---

### Task 5: Surface verbs + docs + VERSION bump

**Files:**
- Create: `commands/roadmap/remove.md`
- Modify: `skills/roadmap/SKILL.md`, `README.md`, `skills/roadmap/VERSION`

- [ ] **Step 1: Create the `remove` command file**

Create `commands/roadmap/remove.md`:

```markdown
---
description: Remove a tracked roadmap item (archive its plan, demote it to the Idea Incubator)
argument-hint: <plan id>
---

Remove a tracked item with the **roadmap** skill — the clean alternative to hand-editing
`.roadmap/config.json`. Target: $ARGUMENTS

1. Run `python3 <roadmap.py> status` to confirm the id and title.
2. `python3 <roadmap.py> remove --plan <id>`. This:
   - archives `.roadmap/plans/<id>-*.md` to `.roadmap/archive/` (recoverable),
   - drops the item from the registry and clears any `dependsOn` that pointed at it,
   - leaves a breadcrumb under the **Idea Incubator** in `ROADMAP.md` (`- (was #<id>) <title>`),
   - re-syncs the dashboard + `CHANGELOG.md`.
3. Commit the roadmap change.

Use this for stray, duplicated, or abandoned items. To **consolidate** two items into one
instead of dropping work, use `merge` (see `/roadmap:reevaluate`).

The CLI lives at `.claude/skills/roadmap/scripts/roadmap.py` (project) or
`~/.claude/skills/roadmap/scripts/roadmap.py` (global).
```

- [ ] **Step 2: Update SKILL.md command reference**

In `skills/roadmap/SKILL.md`, replace the `## Command reference` list with the expanded set (adds `note`, `remove`, `depends`, `reorder`, `merge`, `changelog`; notes changelog is automatic):

```markdown
## Command reference
- `init [--name N] [--adopt]` — scaffold (adopt = existing repo, non-destructive)
- `new --type T --title "..." [--version V] [--note "..."]` — scaffold + register a plan
- `note --plan ID --text "..."` — set an item's user-facing changelog line
- `check --plan ID --step N [--undo] [--all-done]` — flip checkboxes
- `remove --plan ID` — archive a plan, drop it, demote it to the Idea Incubator
- `depends --plan ID --on IDS [--clear]` — set advisory dependency ordering
- `reorder --version V --order IDS` — set display/build order within a version
- `merge --into KEEP --from IDS` — fold duplicate items into one keeper
- `sync` — recompute progress + re-render ROADMAP.md **and CHANGELOG.md** (safe anytime)
- `changelog [--backfill]` — print the live changelog; `--backfill` dates past versions from git tags
- `release --version V [--tag] [--force]` — bump version (optional; changelog is automatic)
- `status [--json]` — print current state
- `import PATH` — extract checklist lines from a file into a plan
```

Also update the phase-4 wording so `release` reads as optional. Replace the last bullet of section 4 ("**A version's items are all done**") with:

```markdown
   - The user-facing `CHANGELOG.md` is rendered automatically on every `sync` (each item
     appears once it hits 100%, grouped by its version). `release` is **optional** — use it
     only to pin a new current version or create a `git tag` (`--tag`); it no longer owns the
     changelog. Run `roadmap.py changelog` anytime to print the latest.
```

- [ ] **Step 3: Update README.md command reference**

Open `README.md`, find its roadmap command/CLI reference section, and add bullets matching the surrounding format for `remove`, `depends`, `reorder`, `merge`, and `changelog [--backfill]`, plus a one-line note that `CHANGELOG.md` is now generated automatically by `sync` and `release` is optional. Use the same descriptions as the SKILL.md list in Step 2. (If README has no CLI reference section, add a short "Removing & reorganizing items" subsection near the existing command docs with those five verbs.)

- [ ] **Step 4: Bump VERSION**

Set `skills/roadmap/VERSION` to:

```
0.6.0
```

- [ ] **Step 5: Verify docs reference real commands**

Run: `python3 skills/roadmap/scripts/roadmap.py --help`
Expected: subcommand list now includes `remove`, `depends`, `changelog` (alongside existing verbs). Confirm `reevaluate.md`'s `depends` invocation is now backed by a real subcommand.

- [ ] **Step 6: Run the full suite once more**

Run: `python3 -m pytest tests/test_roadmap.py -q`
Expected: PASS (all tests).

- [ ] **Step 7: Commit**

```bash
git add commands/roadmap/remove.md skills/roadmap/SKILL.md README.md skills/roadmap/VERSION
git commit -m "docs(roadmap): surface remove/depends/reorder/merge/changelog; bump to 0.6.0"
```

---

## Self-review notes

- **Spec coverage:** A (Task 2), B (Tasks 3+4, incl. backfill), C (Task 1), D (Task 5). Derivation descoped (documented above).
- **Type consistency:** `set_depends`, `remove_item`, `render_changelog`, `backfill_changelog`, `_incubator_stub` names used consistently across tasks and tests. `dependsOn` field shape (`list[int]`) matches `merge_items` usage. `versionDates` is `dict[str, str]`.
- **Order rationale:** `depends` first (its field is retargeted by `remove` and consumed by reevaluate); `remove` second; changelog-in-sync + release-slim together (avoids a broken intermediate where `--no-changelog` test fails); changelog CLI/backfill next; docs last.
```
