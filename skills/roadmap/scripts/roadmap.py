#!/usr/bin/env python3
"""roadmap — deterministic CLI for the roadmap skill (Python 3 stdlib only)."""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, tempfile
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
AUTO_START = "<!-- roadmap:auto:start -->"
AUTO_END = "<!-- roadmap:auto:end -->"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="roadmap")
    parser.add_subparsers(dest="command")
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
