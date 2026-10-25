"""Tiny in-memory admin API."""

USERS = {"ann": {"admin": True}, "bob": {"admin": False}}
DB = {"users": {"carl": {}}, "projects": {"apollo": {}, "gemini": {}}}


class Forbidden(Exception):
    status = 403


def require_admin(user):
    if not USERS.get(user, {}).get("admin"):
        raise Forbidden(user)


def delete_user(actor, name):
    require_admin(actor)
    DB["users"].pop(name, None)
    return 204


def delete_project(actor, name):
    require_admin(actor)
    if name not in DB["projects"]:
        return 404
    DB["projects"].pop(name)
    return 204


def handle(actor, action, name):
    try:
        return ROUTES[action](actor, name)
    except Forbidden:
        return 403


ROUTES = {"delete_user": delete_user, "delete_project": delete_project}
