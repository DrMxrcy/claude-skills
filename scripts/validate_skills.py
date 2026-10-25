#!/usr/bin/env python3
"""Validate every skill package under skills/ against schemas/skill.schema.json.

Stdlib only (no jsonschema): the schema file is documentation, this script is the
enforcer. Keep the rules here and the schema in sync.

Usage: python3 scripts/validate_skills.py [REPO_ROOT]
Exit 0 when clean, 1 with one named violation per line.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$"
)
REQUIRED_FILES = ("SKILL.md", "README.md", "VERSION")


def parse_frontmatter(text):
    """Top-level keys of a leading `---` YAML block. Returns {} if absent.

    Handles the block scalars this repo uses (`description: >` plus indented
    continuation lines) by joining continuations into the value.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}
    out, key = {}, None
    for line in lines[1:end]:
        match = re.match(r"^([A-Za-z_][\w-]*):[ \t]*(.*)$", line)
        if match:
            key, value = match.group(1), match.group(2).strip()
            out[key] = "" if value in (">", "|", ">-", "|-") else value
        elif key and line.strip():
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


def validate(root=REPO_ROOT):
    """Return a list of human-readable violation strings (empty == valid)."""
    root = Path(root)
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return [f"skills/: directory not found under {root}"]

    violations = []
    entries = sorted(p for p in skills_dir.iterdir()
                     if not p.name.startswith(".") and p.name != ".DS_Store")
    for p in entries:
        if not p.is_dir():
            violations.append(f"skills/{p.name}: stray file — only skill directories belong under skills/")
    packages = [p for p in entries if p.is_dir()]
    if not packages:
        violations.append("skills/: no skill packages found")

    for pkg in packages:
        name = pkg.name
        where = f"skills/{name}"
        if not NAME_RE.match(name):
            violations.append(f"{where}: directory name is not lowercase-hyphen")

        for required in REQUIRED_FILES:
            if not (pkg / required).is_file():
                violations.append(f"{where}: missing required file {required}")

        version_file = pkg / "VERSION"
        if version_file.is_file():
            version = version_file.read_text().strip()
            if not SEMVER_RE.match(version):
                violations.append(f"{where}: VERSION {version!r} is not semver")

        skill_md = pkg / "SKILL.md"
        if skill_md.is_file():
            meta = parse_frontmatter(skill_md.read_text())
            if not meta:
                violations.append(f"{where}: SKILL.md has no YAML frontmatter block")
            else:
                declared = meta.get("name", "")
                if not declared:
                    violations.append(f"{where}: SKILL.md frontmatter missing 'name'")
                elif declared != name:
                    violations.append(
                        f"{where}: SKILL.md frontmatter name {declared!r} "
                        f"does not match directory name {name!r}")
                if not meta.get("description"):
                    violations.append(
                        f"{where}: SKILL.md frontmatter missing 'description'")

        commands = root / "commands" / name
        if commands.is_dir():
            for entry in sorted(commands.iterdir()):
                if entry.is_file() and entry.suffix != ".md":
                    violations.append(
                        f"commands/{name}/{entry.name}: slash commands must be .md")

    return violations


def main(argv):
    root = Path(argv[1]) if len(argv) > 1 else REPO_ROOT
    violations = validate(root)
    for violation in violations:
        print(violation, file=sys.stderr)
    if violations:
        print(f"{len(violations)} violation(s)", file=sys.stderr)
        return 1
    print("skills/ ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
