"""Command-line entry point."""
import argparse
import os

import client


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("--timeout", type=int)
    a = p.parse_args(argv)
    if a.timeout is not None:
        os.environ["APP_TIMEOUT"] = str(a.timeout)
    return client.fetch(a.url)
