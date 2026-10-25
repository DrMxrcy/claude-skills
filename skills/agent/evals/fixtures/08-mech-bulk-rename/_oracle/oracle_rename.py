import re
import unittest
from pathlib import Path

FILES = ["store.py", "views.py", "report.py", "README.md", "test_store.py"]


class Oracle(unittest.TestCase):
    def test_old_name_gone(self):
        for name in FILES:
            text = Path(name).read_text()
            self.assertIsNone(re.search(r"\bget_usr\b", text), name)

    def test_new_name_works(self):
        import report
        import store
        import views
        self.assertEqual(store.get_user(1)["name"], "ann")
        self.assertIsNone(store.get_user(9))
        self.assertEqual(views.profile(2), "<h1>bob</h1>")
        self.assertEqual(report.names([1, 2, 9]), ["ann", "bob"])
        self.assertIn("get_user", Path("README.md").read_text())
