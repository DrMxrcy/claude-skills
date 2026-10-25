"""Output formatting."""
import json


def format_text(items):
    return "\n".join(f"[{'x' if i['done'] else ' '}] {i['id']} {i['title']}" for i in items)


def format_json(items):
    keys = ("id", "title", "done")
    return json.dumps([{k: i[k] for k in keys} for i in sorted(items, key=lambda i: i["id"])])
