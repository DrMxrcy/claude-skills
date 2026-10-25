#!/usr/bin/env python3
"""Write model.md: each member CLI's baseline model and effort, verified against --help.

For every member this runs only `<cli> --version` and `<cli> [subcommand] --help`. It
never calls a model. It parses the help text for the member's model flag and effort
flag, then writes one row per member: model flag, baseline model, fallback model,
effort flag, baseline effort, CLI version and probe date.

A baseline of `cli-default` means the runner passes no flag and the CLI's own configured
default applies. A pinned value (`--pin member:model=X`, `--pin member:effort=Y`) is
written only when its flag appears in that CLI's --help; otherwise the member gets no
row. A member with no row is listed under "Not probed", and run_review.py refuses it
instead of running it with a guessed model.

model.md ends with a sha256 digest of everything above it. run_review.py refuses a
model.md whose digest does not match, so the file is generated, never hand-edited.

Usage:
  probe_models.py [--out model.md] [--members a,b] [--pin member:model=X] ...
Stdlib only.
"""
import argparse
import datetime as _dt
import hashlib
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROBE_TIMEOUT = 15
DEFAULT = "cli-default"
NONE = "none"
DIGEST_PREFIX = "<!-- model.md digest: sha256:"
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ENV_ALLOW = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "TERM", "TMPDIR", "SHELL",
             "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME")


@dataclass
class Spec:
    """How to probe one member. `model_flags` / `effort_flags` are candidates in the
    order the runner prefers; the first one present in --help is recorded."""
    name: str
    binary: str
    help_args: tuple
    model_flags: tuple
    effort_flags: tuple = ()
    model: str = DEFAULT
    fallback: str = "-"
    effort: str = DEFAULT
    effort_note: str = ""


# Checked against each CLI's own --help (2026-10). codex's reasoning effort is only
# settable with `-c model_reasoning_effort=…`, and `-c` is refused by the runner's
# session-flag guard, so codex has no usable effort flag. cursor-agent and opencode set
# effort inside the model id (`model[effort=high]`, `provider/model#variant`).
SPECS = {
    "codex": Spec("codex", "codex", ("exec", "--help"), ("-m", "--model"),
                  ("--effort", "--reasoning-effort"),
                  effort_note="effort only via `-c`, which the session guard refuses"),
    "cursor-agent": Spec("cursor-agent", "cursor-agent", ("--help",), ("--model",),
                         ("--effort", "--reasoning-effort"),
                         effort_note="effort is part of the model id"),
    "agy": Spec("agy", "agy", ("--help",), ("--model",), ("--effort",)),
    "claude": Spec("claude", "claude", ("--help",), ("--model",), ("--effort",)),
    # The runner's opencode argv uses `-m`, so `-m` itself must be in --help.
    "opencode": Spec("opencode", "opencode", ("run", "--help"), ("-m",), ("--effort",),
                     effort_note="effort is the model's #variant"),
}


def flag_in_help(text, flag):
    """True when `flag` appears in help text as a flag token (not inside a longer flag)."""
    return re.search(r"(?:^|[\s,\[(|])" + re.escape(flag) + r"(?=$|[\s,=<\[\]|)])", text,
                     re.MULTILINE) is not None


def _env():
    env = {k: v for k, v in os.environ.items() if k in ENV_ALLOW or k.startswith("LC_")}
    env["NO_COLOR"] = "1"
    return env


def _run(argv, timeout, env, cwd):
    """(returncode or None on timeout, combined text). Own process group, killed on
    timeout."""
    proc = subprocess.Popen(argv, cwd=cwd, text=True, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True, env=env)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return None, ""
    return proc.returncode, ANSI_RE.sub("", (out or "") + "\n" + (err or ""))


def probe_member(spec, env=None, timeout=PROBE_TIMEOUT, date=None, which=shutil.which):
    """(entry dict, "") or (None, reason). Runs only --version and --help."""
    env = _env() if env is None else env
    path = which(spec.binary, path=env.get("PATH"))   # the PATH the probe runs with
    if not path:
        return None, f"not installed: `{spec.binary}` not on PATH"
    cwd = tempfile.mkdtemp(prefix="advrev-probe-")
    try:
        try:
            rc, text = _run([path, "--version"], timeout, env, cwd)
        except OSError as exc:
            return None, f"--version failed to start: {exc}"
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if rc is None:
            return None, f"--version timed out after {timeout}s"
        if rc != 0 or not lines:
            return None, f"--version exit {rc}"
        version = lines[0][:120]
        try:
            rc, help_text = _run([path, *spec.help_args], timeout, env, cwd)
        except OSError as exc:
            return None, f"--help failed to start: {exc}"
        if rc is None:
            return None, f"`{' '.join(spec.help_args)}` timed out after {timeout}s"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
    shown = " ".join([spec.binary, *spec.help_args])
    model_flag = next((f for f in spec.model_flags if flag_in_help(help_text, f)), None)
    if model_flag is None:
        return None, (f"no model flag ({' or '.join(spec.model_flags)}) in `{shown}`; "
                      "refused rather than run with a guessed model")
    effort_flag = next((f for f in spec.effort_flags if flag_in_help(help_text, f)), None)
    if spec.effort != DEFAULT and effort_flag is None:
        return None, (f"effort pinned to {spec.effort!r} but `{shown}` shows no effort "
                      "flag; refused rather than guess one")
    return {"member": spec.name, "model_flag": model_flag, "model": spec.model,
            "fallback": spec.fallback or "-", "effort_flag": effort_flag or NONE,
            "effort": spec.effort, "version": version,
            "probed": date or _dt.date.today().isoformat(),
            "note": "" if effort_flag else spec.effort_note}, ""


COLUMNS = ("member", "model flag", "baseline model", "fallback model", "effort flag",
           "baseline effort", "CLI version", "probed")
KEYS = ("member", "model_flag", "model", "fallback", "effort_flag", "effort", "version",
        "probed")


def _cell(text):
    return str(text).replace("|", "/").replace("\n", " ").strip() or "-"


def render_model_md(entries, refused, date):
    """model.md text (with its digest line) for {name: entry} and {name: reason}."""
    lines = ["# model.md: member model baseline", "",
             f"Generated by `probe_models.py` on {date} from each CLI's own `--version` and "
             "`--help`; no model was called. Do not hand-edit: the runner checks the digest "
             "at the end and refuses a member with no row.", "",
             f"`{DEFAULT}` means the runner passes no flag and the CLI's configured default "
             f"applies. Effort flag `{NONE}` means `--help` shows no usable effort flag.", "",
             "| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    for name in sorted(entries):
        e = entries[name]
        lines.append("| " + " | ".join(_cell(e[k]) for k in KEYS) + " |")
    notes = [(n, entries[n]["note"]) for n in sorted(entries) if entries[n].get("note")]
    if notes:
        lines += ["", "## Notes", ""] + [f"- {n}: {why}" for n, why in notes]
    lines += ["", "## Not probed (the runner refuses these)", ""]
    lines += [f"- {n}: {_cell(why)}" for n, why in sorted(refused.items())] or ["- none"]
    body = "\n".join(lines) + "\n"
    digest = hashlib.sha256(body.encode()).hexdigest()
    return body + f"\n{DIGEST_PREFIX}{digest} -->\n"


def parse_model_md(text):
    """({name: entry}, {name: reason}). Raises ValueError when the digest is missing or
    does not match (the file was edited by hand) or the table is malformed."""
    head, sep, tail = text.rpartition("\n" + DIGEST_PREFIX)
    if not sep:
        raise ValueError("model.md has no digest line; regenerate it with probe_models.py")
    digest = tail.split(" ", 1)[0].strip()
    if hashlib.sha256(head.encode()).hexdigest() != digest:
        raise ValueError("model.md digest does not match its content (hand-edited?); "
                         "regenerate it with probe_models.py")
    entries, refused, section = {}, {}, "table"
    for line in head.splitlines():
        if line.startswith("## Not probed"):
            section = "refused"
            continue
        if line.startswith("## "):
            section = "other"
            continue
        if section == "table" and line.startswith("| ") and not line.startswith("| member |"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) != len(KEYS):
                raise ValueError(f"model.md row has {len(cells)} cells: {line!r}")
            entry = dict(zip(KEYS, cells))
            entries[entry["member"]] = entry
        elif section == "refused" and line.startswith("- ") and ": " in line:
            name, _, why = line[2:].partition(": ")
            refused[name] = why
    return entries, refused


def read_model_md(path):
    return parse_model_md(Path(path).read_text())


def probe_all(specs, env_for=None, date=None, timeout=PROBE_TIMEOUT):
    """({name: entry}, {name: reason}) for an iterable of Spec."""
    entries, refused = {}, {}
    for spec in specs:
        entry, why = probe_member(spec, env=env_for(spec.name) if env_for else None,
                                  timeout=timeout, date=date)
        if entry is None:
            refused[spec.name] = why
        else:
            entries[spec.name] = entry
    return entries, refused


def write_model_md(path, specs, env_for=None, date=None, timeout=PROBE_TIMEOUT):
    date = date or _dt.date.today().isoformat()
    entries, refused = probe_all(specs, env_for, date, timeout)
    Path(path).write_text(render_model_md(entries, refused, date))
    return entries, refused


def specs_for(names, pins=None, models=None):
    """Spec per member name. `pins`: {(name, "model"|"effort"): value}. `models`:
    {name: (primary, fallback)} from the runner's registry (opencode)."""
    out = []
    for name in names:
        base = SPECS.get(name)
        if base is None:
            continue
        spec = Spec(**base.__dict__)
        if models and name in models:
            spec.model, spec.fallback = models[name]
        for (pname, what), value in (pins or {}).items():
            if pname == name:
                setattr(spec, what, value)
        out.append(spec)
    return out


def _parse_pins(values):
    pins = {}
    for raw in values:
        m = re.match(r"^([\w-]+):(model|effort)=(\S+)$", raw)
        if not m:
            raise ValueError(f"bad --pin {raw!r}; expected member:model=VALUE or "
                             "member:effort=VALUE")
        pins[(m.group(1), m.group(2))] = m.group(3)
    return pins


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default="model.md")
    ap.add_argument("--members", help="comma-separated subset (default: every member)")
    ap.add_argument("--pin", action="append", default=[],
                    help="member:model=VALUE or member:effort=VALUE (flag must be in --help)")
    args = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run_review   # noqa: E402  (registry: member names and opencode models)
    names = [n.strip() for n in (args.members or "").split(",") if n.strip()] or \
        [m.name for m in run_review.MEMBERS]
    unknown = [n for n in names if n not in SPECS]
    try:
        if unknown:
            raise ValueError(f"unknown member(s): {', '.join(unknown)}")
        pins = _parse_pins(args.pin)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    models = {m.name: m.models for m in run_review.MEMBERS if m.models}
    by_name = {m.name: m for m in run_review.MEMBERS}
    entries, refused = write_model_md(
        args.out, specs_for(names, pins, models),
        env_for=lambda n: run_review.member_env(by_name[n]))
    print(f"model.md: {args.out}")
    for name in names:
        if name in entries:
            e = entries[name]
            print(f"  {name:13} {e['model_flag']} {e['model']} · effort {e['effort_flag']} "
                  f"{e['effort']} · {e['version']}")
        else:
            print(f"  {name:13} not probed: {refused.get(name, '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
