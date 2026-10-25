import unittest

import api


class ApiTest(unittest.TestCase):
    def test_admin_deletes_user(self):
        self.assertEqual(api.handle("ann", "delete_user", "carl"), 204)

    def test_non_admin_cannot_delete_user(self):
        self.assertEqual(api.handle("bob", "delete_user", "carl"), 403)


if __name__ == "__main__":
    unittest.main()
