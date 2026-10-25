import unittest

from pager import page_count, paginate


class PagerTest(unittest.TestCase):
    def test_page_count(self):
        self.assertEqual(page_count(10, 5), 2)

    def test_first_and_last_page(self):
        items = list(range(10))
        self.assertEqual(paginate(items, 1, 5), [0, 1, 2, 3, 4])
        self.assertEqual(paginate(items, 2, 5), [5, 6, 7, 8, 9])

    def test_past_end(self):
        with self.assertRaises(IndexError):
            paginate(list(range(10)), 3, 5)


if __name__ == "__main__":
    unittest.main()
