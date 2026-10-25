import unittest

from pager import page_count, paginate


class Oracle(unittest.TestCase):
    def test_partial_last_page_counted(self):
        self.assertEqual(page_count(11, 5), 3)
        self.assertEqual(page_count(1, 5), 1)
        self.assertEqual(page_count(0, 5), 0)
        self.assertEqual(page_count(10, 5), 2)

    def test_every_item_reachable_once(self):
        items = list(range(11))
        seen = []
        for page in range(1, page_count(len(items), 5) + 1):
            seen += paginate(items, page, 5)
        self.assertEqual(seen, items)
        with self.assertRaises(IndexError):
            paginate(items, 4, 5)
