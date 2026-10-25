"""Serve user uploads from an upload root."""
import os


def read_upload(root, name):
    """Return the bytes of upload `name` stored under `root`."""
    with open(os.path.join(root, name), "rb") as f:
        return f.read()
