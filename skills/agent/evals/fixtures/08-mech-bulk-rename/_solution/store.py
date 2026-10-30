"""User store."""

_USERS = {1: {"name": "ann"}, 2: {"name": "bob"}}


def get_user(user_id):
    """Return the user record for `user_id`, or None."""
    return _USERS.get(user_id)
