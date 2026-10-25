"""Reports."""
import store


def names(ids):
    return [store.get_user(i)["name"] for i in ids if store.get_user(i)]
