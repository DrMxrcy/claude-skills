#!/usr/bin/env python3
"""Vendor the secaudit security checklists into references/security/ (manual sync).

Copies skills/<domain>/SKILL.md from the installed secaudit Claude plugin into
references/security/<domain>.md, together with the source LICENSE, an attribution
README.md and a VERSION file (source version + gitCommitSha). The review never needs the
plugin at run time: members read the vendored files by path.

The sync is never automatic. Run it after `claude plugin update secaudit@secaudit`:

  sync-security-refs.py                 # sync from the installed plugin
  sync-security-refs.py --source DIR    # sync from another checkout/cache dir
  sync-security-refs.py --check         # exit 1 if vendored refs are stale or missing

--check exit codes: 0 current (or secaudit not installed: nothing to compare);
1 vendored version/commit differs from the installed plugin, or nothing vendored.
Stdlib only.
"""
import argparse
import datetime as _dt
import json
import re
import shutil
import sys
from pathlib import Path

PLUGIN_KEY = "secaudit@secaudit"
SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DEST = SKILL_DIR / "references" / "security"
KEEP = {"LICENSE", "README.md", "VERSION"}
# A relative `references/<file>.md` (optionally ./) — not part of a URL path.
LOCAL_REF_RE = re.compile(r"(?<![/\w])(?:\./)?references/([A-Za-z0-9_.-]+\.md)")


def adapt(text, domain, version):
    """Vendored copy of one SKILL.md: mark links to files that are not vendored, and add
    a header (after the frontmatter) mapping `secaudit:<domain>` to sibling files."""
    text = LOCAL_REF_RE.sub(
        lambda m: f"secaudit skills/{domain}/references/{m.group(1)} (not vendored)", text)
    header = (f"> Vendored from secaudit v{version} (see README.md and LICENSE in this "
              "directory). `secaudit:<domain>` means the sibling file `<domain>.md` here. "
              "Paths marked \"(not vendored)\" exist only upstream; do not try to open them.\n\n")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            cut = end + len("\n---\n")
            return text[:cut] + "\n" + header + text[cut:].lstrip("\n")
    return header + text


def default_installed_json():
    return Path.home() / ".claude" / "plugins" / "installed_plugins.json"


def installed_info(installed_json=None):
    """{'version', 'sha', 'path'} of the installed secaudit plugin, or None."""
    path = Path(installed_json) if installed_json else default_installed_json()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    entries = (data.get("plugins", data) or {}).get(PLUGIN_KEY) or []
    if isinstance(entries, dict):
        entries = [entries]
    entries = [e for e in entries if isinstance(e, dict) and e.get("version")]
    if not entries:
        return None
    entry = next((e for e in entries if e.get("scope") == "user"), entries[0])
    return {"version": str(entry["version"]), "sha": str(entry.get("gitCommitSha") or ""),
            "path": entry.get("installPath") or ""}


def read_version_file(dest=DEFAULT_DEST):
    """Parsed `key: value` lines of <dest>/VERSION, or None when nothing is vendored."""
    try:
        text = (Path(dest) / "VERSION").read_text()
    except OSError:
        return None
    out = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            out[key.strip()] = value.strip()
    return out or None


def check(dest=DEFAULT_DEST, installed_json=None):
    """(exit code, message). 1 = stale or missing; 0 = current or nothing installed."""
    vendored = read_version_file(dest)
    installed = installed_info(installed_json)
    if vendored is None:
        return 1, f"no vendored security refs in {dest}; run sync-security-refs.py"
    have = f"{vendored.get('version', '?')} ({vendored.get('gitCommitSha', '?')[:7]})"
    if installed is None:
        return 0, f"secaudit plugin not installed; vendored refs {have} kept as-is"
    want = f"{installed['version']} ({installed['sha'][:7]})"
    stale = vendored.get("version") != installed["version"] or (
        installed["sha"] and vendored.get("gitCommitSha")
        and vendored["gitCommitSha"] != installed["sha"])
    if stale:
        return 1, (f"vendored security refs are {have}, installed secaudit is {want}; "
                   "run skills/adversarial-review/scripts/sync-security-refs.py")
    return 0, f"vendored security refs match installed secaudit {want}"


def _plugin_meta(source):
    try:
        return json.loads((Path(source) / ".claude-plugin" / "plugin.json").read_text())
    except (OSError, ValueError):
        return {}


def sync(source, dest=DEFAULT_DEST, version=None, sha=""):
    source, dest = Path(source), Path(dest)
    skills = sorted(p for p in (source / "skills").glob("*/SKILL.md"))
    if not skills:
        raise SystemExit(f"error: no skills/*/SKILL.md under {source}")
    license_file = source / "LICENSE"
    if not license_file.is_file():
        raise SystemExit(f"error: {license_file} missing; refusing to vendor without a license")
    meta = _plugin_meta(source)
    version = version or str(meta.get("version") or "unknown")
    repo_url = meta.get("repository") or meta.get("homepage") or "unknown"
    license_name = meta.get("license") or "see LICENSE"

    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("*.md"):           # drop domains removed upstream
        if old.name not in KEEP:
            old.unlink()
    names = []
    for skill_md in skills:
        name = skill_md.parent.name
        (dest / f"{name}.md").write_text(adapt(skill_md.read_text(), name, version))
        names.append(name)
    shutil.copyfile(license_file, dest / "LICENSE")
    copyright_line = next((ln.strip() for ln in license_file.read_text().splitlines()
                           if ln.strip().lower().startswith("copyright")), "")

    (dest / "VERSION").write_text(
        f"source: {PLUGIN_KEY}\nversion: {version}\ngitCommitSha: {sha or 'unknown'}\n"
        f"synced: {_dt.date.today().isoformat()}\nskills: {len(names)}\n")
    (dest / "README.md").write_text(
        "# Vendored security checklists (secaudit)\n\n"
        f"These files are copies of `skills/<domain>/SKILL.md` from **secaudit** "
        f"v{version} (commit `{(sha or 'unknown')[:12]}`), {repo_url}, renamed "
        "`<domain>.md`. Two changes are made at sync time. A one-line header after the "
        "frontmatter maps `secaudit:<domain>` to the sibling `<domain>.md`. Relative "
        "links to upstream `references/*.md` files, which are not vendored, are rewritten "
        "to say \"(not vendored)\". Everything else is verbatim.\n\n"
        f"License: {license_name}. {copyright_line}. The full license text is in "
        "`LICENSE` next to this file and applies to every `<domain>.md` here.\n\n"
        "Do not edit these files. Re-sync with "
        "`python3 skills/adversarial-review/scripts/sync-security-refs.py` after "
        "`claude plugin update secaudit@secaudit`. `--check` reports staleness. The "
        "adversarial review never requires the plugin to be installed.\n\n"
        "Domains: " + ", ".join(f"`{n}`" for n in names) + "\n")
    return names, version


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", help="plugin root with skills/ and LICENSE "
                                     "(default: installPath of the installed secaudit plugin)")
    ap.add_argument("--installed-json", help="installed_plugins.json "
                                             "(default: ~/.claude/plugins/installed_plugins.json)")
    ap.add_argument("--dest", default=str(DEFAULT_DEST))
    ap.add_argument("--check", action="store_true",
                    help="exit 1 when the vendored refs differ from the installed plugin")
    args = ap.parse_args(argv)

    if args.check:
        code, msg = check(args.dest, args.installed_json)
        print(msg, file=sys.stderr if code else sys.stdout)
        return code

    installed = installed_info(args.installed_json)
    if args.source:
        source = Path(args.source).expanduser()
        same = bool(installed and installed["path"]
                    and Path(installed["path"]).expanduser().resolve() == source.resolve())
        version = installed["version"] if same else None   # else plugin.json version
        sha = installed["sha"] if same else ""
    else:
        if installed is None:
            print("error: secaudit plugin not installed; pass --source DIR", file=sys.stderr)
            return 1
        source = Path(installed["path"]).expanduser()
        if not source.is_dir():
            source = (Path.home() / ".claude/plugins/cache/secaudit/secaudit"
                      / installed["version"])
        version, sha = installed["version"], installed["sha"]
    names, version = sync(source, args.dest, version, sha)
    print(f"synced {len(names)} secaudit checklists v{version} -> {args.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
