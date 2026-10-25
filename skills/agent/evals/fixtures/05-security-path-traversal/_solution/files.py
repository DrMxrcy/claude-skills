"""Serve user uploads from an upload root."""
import os


def read_upload(root, name):
    """Return the bytes of upload `name` stored under `root`."""
    base = os.path.realpath(root)
    path = os.path.realpath(os.path.join(base, name))
    if os.path.commonpath([base, path]) != base:
        raise PermissionError(name)
    with open(path, "rb") as f:
        return f.read()
