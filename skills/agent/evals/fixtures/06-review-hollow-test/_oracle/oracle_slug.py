import unittest

from slug import unique_slug


class Oracle(unittest.TestCase):
    def test_first_suffix_is_2(self):
        self.assertEqual(unique_slug("Hello", {"hello"}), "hello-2")

    def test_skips_taken_suffixes(self):
        self.assertEqual(unique_slug("Hello", {"hello", "hello-2"}), "hello-3")

    def test_unused(self):
        self.assertEqual(unique_slug("Hello", set()), "hello")
