"""todo CLI."""
import argparse

import store
from format import format_json, format_text


def main(argv=None):
    p = argparse.ArgumentParser(prog="todo")
    sub = p.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    if a.cmd == "list":
        items = store.load()
        print(format_json(items) if a.json else format_text(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
