import unittest

import report
import views
from store import get_user


class StoreTest(unittest.TestCase):
    def test_lookup(self):
        self.assertEqual(get_user(1)["name"], "ann")
        self.assertIsNone(get_user(9))

    def test_callers(self):
        self.assertEqual(views.profile(2), "<h1>bob</h1>")
        self.assertEqual(report.names([1, 2, 9]), ["ann", "bob"])


if __name__ == "__main__":
    unittest.main()
