"""Reports."""
import store


def names(ids):
    return [store.get_usr(i)["name"] for i in ids if store.get_usr(i)]
