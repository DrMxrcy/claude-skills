import unittest

import api


class Oracle(unittest.TestCase):
    def test_non_admin_forbidden_and_project_kept(self):
        self.assertEqual(api.handle("bob", "delete_project", "gemini"), 403)
        self.assertIn("gemini", api.DB["projects"])

    def test_unknown_actor_forbidden(self):
        self.assertEqual(api.handle("mallory", "delete_project", "gemini"), 403)
        self.assertIn("gemini", api.DB["projects"])

    def test_admin_still_deletes(self):
        api.DB["projects"]["tmp"] = {}
        self.assertEqual(api.handle("ann", "delete_project", "tmp"), 204)
