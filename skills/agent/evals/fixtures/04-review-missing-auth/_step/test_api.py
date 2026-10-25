import unittest

import api


class ApiTest(unittest.TestCase):
    def test_admin_deletes_user(self):
        self.assertEqual(api.handle("ann", "delete_user", "carl"), 204)

    def test_non_admin_cannot_delete_user(self):
        self.assertEqual(api.handle("bob", "delete_user", "carl"), 403)

    def test_admin_deletes_project(self):
        self.assertEqual(api.handle("ann", "delete_project", "apollo"), 204)
        self.assertNotIn("apollo", api.DB["projects"])

    def test_missing_project(self):
        self.assertEqual(api.handle("ann", "delete_project", "nope"), 404)


if __name__ == "__main__":
    unittest.main()
