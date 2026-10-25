"""Pagination helpers."""


def page_count(total, size):
    """Number of pages needed to show `total` items, `size` per page."""
    if size <= 0:
        raise ValueError("size must be positive")
    return total // size


def paginate(items, page, size):
    """Items on 1-based `page`. Raises IndexError past the last page."""
    if page < 1 or page > page_count(len(items), size):
        raise IndexError(page)
    start = (page - 1) * size
    return items[start:start + size]
