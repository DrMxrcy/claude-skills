"""Views."""
from store import get_usr


def profile(user_id):
    user = get_usr(user_id)
    return f"<h1>{user['name']}</h1>" if user else "<h1>not found</h1>"
