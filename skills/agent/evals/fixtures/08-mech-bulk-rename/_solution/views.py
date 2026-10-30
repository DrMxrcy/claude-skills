"""Views."""
from store import get_user


def profile(user_id):
    user = get_user(user_id)
    return f"<h1>{user['name']}</h1>" if user else "<h1>not found</h1>"
