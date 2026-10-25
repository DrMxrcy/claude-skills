"""todo CLI."""
import argparse

import store
from format import format_text


def main(argv=None):
    p = argparse.ArgumentParser(prog="todo")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    a = p.parse_args(argv)
    if a.cmd == "list":
        print(format_text(store.load()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
