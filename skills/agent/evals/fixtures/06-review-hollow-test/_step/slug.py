"""URL slugs."""
import re


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def unique_slug(text, existing):
    """slugify(text), suffixed -2, -3, ... until it is not in `existing`."""
    base = slugify(text)
    if base not in existing:
        return base
    n = 1
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"
