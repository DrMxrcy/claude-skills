"""Todo storage (in-memory for the fixture)."""

ITEMS = [
    {"id": 2, "title": "write tests", "done": False},
    {"id": 1, "title": "buy milk", "done": True},
]


def load():
    return [dict(item) for item in ITEMS]
