"""Output formatting."""


def format_text(items):
    return "\n".join(f"[{'x' if i['done'] else ' '}] {i['id']} {i['title']}" for i in items)
